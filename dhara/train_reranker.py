"""Fine-tune a cross-encoder reranker on pairs mined from our own corpus.

1. Queries for TRAIN-split judgments and provisions, written the same way as DharaBench
   (bench.precedent_queries / statute_queries), so train and test differ only in what they cover.
2. Positives: chunks of the source judgment that cite the provisions behind the query (never the
   headnote it was written from), or the provision's own units for statute queries.
3. Hard negatives: the live retriever's top hits that are NOT the answer, plus passages citing a
   neighbouring section of the same code (murder vs culpable homicide vs attempt), the confusion
   a lawyer would never make and the retriever often does. A passage from another judgment that
   cites the same law is never a negative: it is often a right answer too, and labelling it wrong
   teaches the model a distinction its text can't support. For statute queries the old/new
   counterpart is never a negative (it's the same law under another number).
4. Train with binary cross-entropy (sentence-transformers CrossEncoder) from bge-reranker-base or
   bge-reranker-v2-m3, at the passage length it reads in use. Dev and test are only used afterwards,
   by evaluate.py.
5. Optionally distil the fine-tuned model into a MiniLM cross-encoder a tenth its size, trained to
   reproduce the teacher's scores on the same pairs.

Splits are by judgment and provision (bench.split_of), so nothing here appears in dev or test.
"""

import json
import random
from typing import Any

from dhara import bench, db
from dhara.config import ROOT, settings
from dhara.retrieve import LIVE_WEIGHTS, Index, Query

PAIRS = ROOT / "data" / "processed" / "train_pairs.jsonl"
BASE = "BAAI/bge-reranker-base"
LARGE = "BAAI/bge-reranker-v2-m3"
STUDENT = "cross-encoder/ms-marco-MiniLM-L-6-v2"
OUT_DIR = settings.processed_dir / "models" / "dhara-reranker"  # the one the API serves, copied from MODELS
MODELS = {k: settings.processed_dir / "models" / f"dhara-reranker-{k}" for k in ("base", "large", "mini")}
NEGATIVES = 7  # per question: 3 from the retriever's top 10, 2 citing a neighbouring section, the rest further down
NEAR = 3  # sections either side in the code's own order


def make_queries(n_precedent: int = 2400, n_statute: int = 900) -> int:
    """Appends to train_queries.jsonl as it goes, so a stopped run resumes."""
    con = db.connect()
    path = settings.processed_dir / "train_queries.jsonl"
    have = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    seen = {x["id"] for x in have}
    n_p = sum(1 for x in have if x["type"] == "precedent")
    n_s = sum(1 for x in have if x["type"] == "statute")
    bench.precedent_queries(con, "train", max(0, n_precedent - n_p), skip=seen, sink=path)
    bench.statute_queries(con, "train", max(0, n_statute - n_s), skip=seen, sink=path)
    return len(path.read_text().splitlines())


def mine(ix: Index, seed: int = 13) -> int:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    queries = [json.loads(x) for x in (settings.processed_dir / "train_queries.jsonl").read_text().splitlines()]
    for item in queries:
        kind = "statute" if item["type"] == "statute" else "judgment"
        q = Query(item["query"], kind=kind, exclude=frozenset(item.get("exclude_units", [])))
        hits = ix.search(q, k=40, weights=LIVE_WEIGHTS)
        if kind == "judgment":
            jid = item["relevant_judgments"][0]
            pos = _citing_chunks(ix, jid, item["cited_by_judgment"])
            law = set(item["cited_by_judgment"]) | set(item.get("provisions_in_query", [])) | set(q.counterparts)
            same_law = _citing(ix, [ix.ids[h.ord] for h in hits], law)
            negs = [ix.ids[h.ord] for h in hits if ix.ref[h.ord] != jid and ix.ids[h.ord] not in same_law]
            nb = _neighbours(ix, law) or [""]
            near_units = [
                u
                for (u,) in ix.con.execute(
                    f"SELECT DISTINCT chunk_id FROM citations WHERE judgment_id != ? AND provision_id IN "
                    f"({','.join('?' * len(nb))})",
                    (jid, *nb),
                )
            ]
            near = _top(ix, item["query"], near_units, 10)
            cites = _citing(ix, near, law)
            near = [u for u in near if u not in cites]
        else:
            pid = next(iter(item["relevant_provisions"]))
            pos = [u for (u,) in ix.con.execute("SELECT id FROM units WHERE ref_id=?", (pid,))]
            bad = set(item["relevant_provisions"]) | set(q.counterparts)
            negs = [ix.ids[h.ord] for h in hits if ix.ref[h.ord] not in bad]
            nb = [p for p in _neighbours(ix, bad) if p not in bad] or [""]
            near_units = [
                u for (u,) in ix.con.execute(f"SELECT id FROM units WHERE ref_id IN ({','.join('?' * len(nb))})", nb)
            ]
            near = _top(ix, item["query"], near_units, 5)
        hard, rest = negs[:10], negs[10:]
        chosen = rng.sample(hard, min(3, len(hard)))
        chosen += rng.sample([u for u in near if u not in chosen], min(2, len([u for u in near if u not in chosen])))
        spare = [u for u in rest if u not in chosen]
        chosen += rng.sample(spare, min(NEGATIVES - len(chosen), len(spare)))
        if not pos or not chosen:
            continue
        pos_text = _unit_text(ix, _best(ix, item["query"], pos))
        rows.append({"query": item["query"], "positive": pos_text, "negatives": [_unit_text(ix, u) for u in chosen]})
    PAIRS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return len(rows)


def _neighbours(ix: Index, provisions: set[str]) -> list[str]:
    """Sections within NEAR places of any of `provisions` in the same code, excluding those."""
    out: list[str] = []
    for pid in provisions:
        row = ix.con.execute("SELECT act, sort_key FROM provisions WHERE id=?", (pid,)).fetchone()
        if row:
            out += [
                p
                for (p,) in ix.con.execute(
                    "SELECT id FROM provisions WHERE act=? AND sort_key BETWEEN ? AND ?",
                    (row[0], row[1] - NEAR, row[1] + NEAR),
                )
                if p not in provisions
            ]
    return list(dict.fromkeys(out))


def _top(ix: Index, query: str, units: list[str], k: int) -> list[str]:
    """The `k` of `units` that best match the question by keywords: the hardest of them."""
    import numpy as np

    units = [u for u in units if u in ix.pos]
    if not units:
        return []
    mask = np.zeros(len(ix.ids), dtype=bool)
    mask[[ix.pos[u] for u in units]] = True
    return [ix.ids[i] for i in ix.run_bm25(query, mask, k)]


def _citing(ix: Index, units: list[str], provisions: set[str]) -> set[str]:
    """The units among `units` that cite any of `provisions`."""
    if not units or not provisions:
        return set()
    rows = ix.con.execute(
        f"SELECT DISTINCT chunk_id FROM citations WHERE chunk_id IN ({','.join('?' * len(units))}) "
        f"AND provision_id IN ({','.join('?' * len(provisions))})",
        (*units, *provisions),
    ).fetchall()
    return {r[0] for r in rows}


def _citing_chunks(ix: Index, jid: str, provisions: list[str]) -> list[str]:
    ph = ",".join("?" * len(provisions))
    rows = ix.con.execute(
        f"""SELECT DISTINCT c.chunk_id FROM citations c JOIN judgment_chunks k ON k.id = c.chunk_id
            WHERE c.judgment_id=? AND k.role='judgment' AND c.provision_id IN ({ph})""",
        (jid, *provisions),
    ).fetchall()
    return [r[0] for r in rows if r[0] in ix.pos]


def _best(ix: Index, query: str, units: list[str]) -> str:
    """The positive is the passage that best matches the question, not just any passage citing the section
    (which could be the counsel list at the top of the judgment)."""
    import numpy as np

    mask = np.zeros(len(ix.ids), dtype=bool)
    mask[[ix.pos[u] for u in units]] = True
    top = ix.run_bm25(query, mask, 1)
    return ix.ids[top[0]] if top else units[0]


def _unit_text(ix: Index, unit_id: str) -> str:
    return str(ix.con.execute("SELECT text FROM units WHERE id=?", (unit_id,)).fetchone()[0])


def _pairs() -> list[dict[str, Any]]:
    rows = [json.loads(x) for x in PAIRS.read_text().splitlines()]
    flat = [{"query": r["query"], "passage": r["positive"], "label": 1.0} for r in rows]
    flat += [{"query": r["query"], "passage": n, "label": 0.0} for r in rows for n in r["negatives"]]
    random.Random(0).shuffle(flat)
    return flat


def train(
    base: str = BASE,
    out: str = str(OUT_DIR),
    epochs: int = 2,
    batch: int = 8,
    accumulate: int = 2,
    lr: float = 2e-5,
    max_length: int = 512,
) -> str:
    """An epoch is over an hour on a laptop GPU, so it checkpoints every 150 updates and picks up
    from the last checkpoint if it was interrupted."""
    import torch
    from sentence_transformers.cross_encoder import CrossEncoder
    from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss

    model = CrossEncoder(base, num_labels=1, max_length=max_length)
    loss = BinaryCrossEntropyLoss(model, pos_weight=torch.tensor(float(NEGATIVES)))
    return _fit(model, loss, _pairs(), out, epochs, batch, accumulate, lr)


def distil(teacher: str, out: str, epochs: int = 2, batch: int = 32, lr: float = 5e-5) -> str:
    """The student learns the teacher's scores rather than the 0/1 labels, so it also learns how far
    apart a near miss and a wrong passage are."""
    from sentence_transformers.cross_encoder import CrossEncoder
    from sentence_transformers.cross_encoder.losses import MSELoss

    flat = _pairs()
    scores = CrossEncoder(teacher, max_length=512).predict(
        [(r["query"], r["passage"]) for r in flat], batch_size=32, activation_fn=None, show_progress_bar=False
    )
    flat = [{**r, "label": float(s)} for r, s in zip(flat, scores, strict=True)]
    model = CrossEncoder(STUDENT, num_labels=1, max_length=512)
    return _fit(model, MSELoss(model), flat, out, epochs, batch, 1, lr)


def _fit(
    model: Any, loss: Any, flat: list[dict[str, Any]], out: str, epochs: int, batch: int, accumulate: int, lr: float
) -> str:
    import torch
    from datasets import Dataset
    from sentence_transformers.cross_encoder import CrossEncoderTrainer, CrossEncoderTrainingArguments
    from transformers import TrainerCallback
    from transformers.trainer_utils import get_last_checkpoint

    args = CrossEncoderTrainingArguments(
        output_dir=f"{out}/checkpoints",
        num_train_epochs=epochs,
        per_device_train_batch_size=batch,  # small batches, accumulated, to fit a laptop GPU
        gradient_accumulation_steps=accumulate,
        learning_rate=lr,
        warmup_ratio=0.1,
        logging_steps=50,
        save_strategy="steps",
        save_steps=150,
        save_total_limit=2,
        report_to="none",
        dataloader_drop_last=True,
    )

    class FreeCache(TrainerCallback):  # Apple's GPU cache otherwise grows with every batch shape until it swaps
        def on_step_end(self, *_: Any, **__: Any) -> None:
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()

    trainer = CrossEncoderTrainer(
        model=model, args=args, train_dataset=Dataset.from_list(flat), loss=loss, callbacks=[FreeCache()]
    )
    trainer.train(resume_from_checkpoint=get_last_checkpoint(args.output_dir))
    model.save_pretrained(out)
    return out
