"""Retrieval units and the three indexes over them.

Units: every provision (long ones split at part boundaries) and every judgment chunk.
Judgments flagged `sensitive` come last, so adding them later only appends shards. Each unit gets
- a BM25 entry (bm25s)
- a bge-m3 dense vector (1024-d, float16)
- bge-m3 sparse lexical weights (stored as a CSR matrix over the tokenizer vocabulary)

At ~225k units everything fits in memory, so search is exact (a matrix product) and
no ANN index is needed. Encoding is resumable: shards of 4,096 units are saved
as they finish, which matters on a fanless laptop that throttles.
"""

import json
import re
import sqlite3
from pathlib import Path

import numpy as np
from scipy import sparse

from dhara import db
from dhara.config import settings

SHARD = 4096
MAX_WORDS = 350


def index_dir() -> Path:
    d = settings.processed_dir / "index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_units(con: sqlite3.Connection) -> int:
    """(Re)create the `units` table: what gets retrieved."""
    con.executescript(
        """DROP TABLE IF EXISTS units;
           CREATE TABLE units (
               ord INTEGER PRIMARY KEY, id TEXT UNIQUE, kind TEXT, ref_id TEXT,
               act TEXT, decided_on TEXT, text TEXT
           );"""
    )
    rows: list[tuple[str, str, str, str | None, str | None, str]] = []
    acts = dict(con.execute("SELECT code, title FROM acts").fetchall())
    for pid, act, number, heading, chapter, sub in con.execute(
        "SELECT id, act, number, heading, chapter_title, subheading FROM provisions ORDER BY act, sort_key"
    ).fetchall():
        crumb = f"{acts[act]} › {chapter} › {sub + ' › ' if sub else ''}Section {number}: {heading}"
        parts = [
            f"{lbl} {txt}".strip()
            for lbl, txt in con.execute(
                "SELECT label, text FROM provision_parts WHERE provision_id=? ORDER BY ord", (pid,)
            )
        ]
        for i, piece in enumerate(_group(parts)):
            rows.append((f"{pid}#{i}", "statute", pid, act, None, f"{crumb}\n{piece}"))
    for cid, jid, decided, text in con.execute(
        """SELECT c.id, c.judgment_id, j.decided_on, c.text FROM judgment_chunks c
           JOIN judgments j ON j.id = c.judgment_id ORDER BY j.sensitive, c.judgment_id, c.ord"""
    ):
        rows.append((cid, "judgment", jid, None, decided, text))
    con.executemany("INSERT INTO units (id, kind, ref_id, act, decided_on, text) VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def _group(parts: list[str]) -> list[str]:
    """Keep a section whole unless it's long; then split at part boundaries."""
    out: list[str] = []
    cur: list[str] = []
    for p in parts:
        if cur and sum(len(x.split()) for x in cur) + len(p.split()) > MAX_WORDS:
            out.append("\n".join(cur))
            cur = []
        cur.append(p)
    if cur:
        out.append("\n".join(cur))
    return out or [""]


def texts(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT text FROM units ORDER BY ord")]


def build_bm25(con: sqlite3.Connection) -> None:
    import bm25s

    retriever = bm25s.BM25()
    retriever.index(bm25s.tokenize([_bm25_text(t) for t in texts(con)], stopwords="en"))
    retriever.save(str(index_dir() / "bm25"))


def _bm25_text(text: str) -> str:
    # keep "302", "498A", "65B" as tokens: bm25s' default tokenizer drops single digits only
    return re.sub(r"(\d+)\s*-\s*([A-Z])\b", r"\1\2", text)


def encode(batch: int = 32, max_length: int = 512) -> int:
    """bge-m3 dense + sparse for every unit, shard by shard (resumable)."""
    from FlagEmbedding import BGEM3FlagModel

    con = db.connect()
    all_texts = texts(con)
    shards = index_dir() / "shards"
    shards.mkdir(exist_ok=True)
    model = BGEM3FlagModel(embed_model(), use_fp16=True, devices=_device())
    done = 0
    for s in range(0, len(all_texts), SHARD):
        out = shards / f"{s // SHARD:05d}.npz"
        if out.exists():
            continue
        enc = model.encode(
            all_texts[s : s + SHARD],
            batch_size=batch,
            max_length=max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        rows, cols, vals = [], [], []
        for i, weights in enumerate(enc["lexical_weights"]):
            for tok, w in weights.items():
                rows.append(i)
                cols.append(int(tok))
                vals.append(float(w))
        np.savez(
            out,
            dense=enc["dense_vecs"].astype(np.float16),
            rows=np.array(rows, np.int32),
            cols=np.array(cols, np.int32),
            vals=np.array(vals, np.float16),
        )
        done += 1
    return done


def assemble() -> dict[str, int]:
    """Concatenate shards into dense.npy and sparse.npz."""
    files = sorted((index_dir() / "shards").glob("*.npz"))
    dense, blocks = [], []
    for f in files:
        z = np.load(f)
        dense.append(z["dense"])
        n = z["dense"].shape[0]
        blocks.append(sparse.csr_matrix((z["vals"].astype(np.float32), (z["rows"], z["cols"])), shape=(n, 250_002)))
    np.save(index_dir() / "dense.npy", np.concatenate(dense))
    sparse.save_npz(index_dir() / "sparse.npz", sparse.vstack(blocks).tocsr())
    meta = {"units": int(sum(d.shape[0] for d in dense)), "shards": len(files)}
    (index_dir() / "meta.json").write_text(json.dumps(meta))
    return meta


def embed_model() -> str:
    """Local path to bge-m3 without its ONNX export (2.3 GB), which FlagEmbedding would download too."""
    from huggingface_hub import snapshot_download

    return snapshot_download(settings.dhara_embed_model, ignore_patterns=["onnx/*", "imgs/*", "*.jpg"])


def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
