"""First-stage retrieval: BM25 ∥ citation-graph BM25 ∥ bge-m3 dense ∥ bge-m3 sparse → Reciprocal Rank Fusion.

What makes it legal-specific:
- cross-code citation graph: provisions named in the query ("BNS 103") are mapped to their
  old/new counterparts (IPC 302), and one retriever searches only the judgment chunks that
  actually cite those provisions. A BNS question reaches judgments that only ever cite the IPC.
  (Appending counterpart names to the query text instead was measured and hurt BM25: generic
  words like "Indian Penal Code" drown the legal issue.)
- separate pools: statutes and judgments are ranked separately so one can't crowd out the other

Filters (applied before ranking): unit kind, a date (`as_of`: provisions in force then,
judgments decided by then), and per-query exclusions used by the benchmark.
"""

import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy import sparse

from dhara import db
from dhara.citations import extract
from dhara.index import _bm25_text, index_dir

RRF_K = 60
RETRIEVERS = ("bm25", "cited", "dense", "sparse")
# the live fusion: the citation graph counts twice, since dense and sparse otherwise dilute it (weight fixed
# before measuring; it helps on both the dev and the test split, see eval/results/)
LIVE_WEIGHTS = {"cited": 2.0}
MAX_COUNTERPARTS = 3  # per named provision; merged sections (BNS 3 ← nine IPC sections) would flood the query


# the models run on one GPU (or CPU) at a time: Apple's MPS backend aborts on concurrent calls, and the
# evaluation and the API call them from several threads
MODEL_LOCK = threading.RLock()


@dataclass
class Hit:
    ord: int  # row in the units table / index matrices
    score: float
    by: dict[str, int] = field(default_factory=dict)  # retriever -> rank (1-based)


@dataclass
class Query:
    text: str
    as_of: date | None = None
    kind: str = "judgment"  # "judgment" | "statute"
    exclude: frozenset[str] = frozenset()
    expanded: str = ""  # filled by expand()
    refs: list[str] = field(default_factory=list)
    counterparts: list[str] = field(default_factory=list)


class Index:
    """Everything retrieval needs, loaded once (about 1.5 GB in memory)."""

    def __init__(self, load_vectors: bool = True) -> None:
        import bm25s

        con = db.connect()
        rows = con.execute("SELECT id, kind, ref_id, act, decided_on FROM units ORDER BY ord").fetchall()
        self.ids = [r[0] for r in rows]
        self.kind = np.array([r[1] for r in rows])
        self.ref = [r[2] for r in rows]
        self.pos = {u: i for i, u in enumerate(self.ids)}
        cited: dict[str, list[int]] = {}
        for chunk, pid in con.execute("SELECT DISTINCT chunk_id, provision_id FROM citations WHERE resolved = 1"):
            if chunk in self.pos:
                cited.setdefault(pid, []).append(self.pos[chunk])
        self.cited = {pid: np.array(rows) for pid, rows in cited.items()}
        self.decided = np.array([r[4] or "0000-00-00" for r in rows])
        acts = dict(con.execute("SELECT code, in_force_from || '|' || coalesce(in_force_to,'9999-12-31') FROM acts"))
        self.in_force = np.array([acts.get(r[3] or "", "0000-00-00|9999-12-31") for r in rows])
        self.bm25 = bm25s.BM25.load(str(index_dir() / "bm25"))
        self.dense: np.ndarray | None = None
        self.sparse: sparse.csr_matrix | None = None
        self.model = None
        if load_vectors and (index_dir() / "dense.npy").exists():
            self.dense = np.load(index_dir() / "dense.npy").astype(np.float32)
            self.sparse = sparse.load_npz(index_dir() / "sparse.npz").tocsr()

    @property
    def con(self) -> sqlite3.Connection:
        return db.shared()

    # ---- query side -------------------------------------------------------------------------
    def encoder(self):  # type: ignore[no-untyped-def]
        with MODEL_LOCK:
            return self._load_encoder()

    def _load_encoder(self):  # type: ignore[no-untyped-def]
        if self.model is None:
            from FlagEmbedding import BGEM3FlagModel

            from dhara.config import settings
            from dhara.index import _device

            device = _device()
            # half precision only on a GPU; a CPU server (production) runs it in full precision
            self.model = BGEM3FlagModel(settings.dhara_embed_model, use_fp16=device != "cpu", devices=device)
        return self.model

    def mask(self, q: Query) -> np.ndarray:
        m = self.kind == q.kind
        if q.as_of is not None:
            d = q.as_of.isoformat()
            if q.kind == "judgment":
                m &= self.decided <= d
            else:
                lo_hi = np.char.partition(self.in_force, "|")
                m &= (lo_hi[:, 0] <= d) & (lo_hi[:, 2] >= d)
        for u in q.exclude:
            if u in self.pos:
                m[self.pos[u]] = False
        return m

    # ---- the three retrievers ----------------------------------------------------------------
    def run_bm25(self, text: str, mask: np.ndarray, k: int) -> list[int]:
        import bm25s

        tokens = bm25s.tokenize(_bm25_text(text), stopwords="en", return_ids=False, show_progress=False)[0]
        scores = self.bm25.get_scores(tokens)
        return _topk(np.where(mask, scores, -np.inf), k)

    def run_vectors(self, text: str, mask: np.ndarray, k: int) -> tuple[list[int], list[int]]:
        assert self.dense is not None and self.sparse is not None
        with MODEL_LOCK:
            enc = self.encoder().encode([text], return_dense=True, return_sparse=True, return_colbert_vecs=False)
        dense_scores = self.dense @ enc["dense_vecs"][0].astype(np.float32)
        w = enc["lexical_weights"][0]
        qvec = sparse.csr_matrix(
            (list(map(float, w.values())), ([0] * len(w), list(map(int, w.keys())))),
            shape=(1, self.sparse.shape[1]),
        )
        sparse_scores = np.asarray((self.sparse @ qvec.T).todense()).ravel()
        return (
            _topk(np.where(mask, dense_scores, -np.inf), k),
            _topk(np.where(mask, sparse_scores, -np.inf), k),
        )

    # ---- fusion ----------------------------------------------------------------------------
    @property
    def available(self) -> tuple[str, ...]:
        return RETRIEVERS if self.dense is not None else ("bm25", "cited")

    def units_of(self, pid: str) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT id FROM units WHERE ref_id = ? ORDER BY ord", (pid,))]

    def cited_mask(self, q: Query) -> np.ndarray:
        """Judgment chunks that cite any provision named in the query or its counterpart."""
        m = np.zeros(len(self.ids), dtype=bool)
        for pid in set(q.refs) | set(q.counterparts):
            if pid in self.cited:
                m[self.cited[pid]] = True
        return m

    def search(
        self,
        q: Query,
        use: tuple[str, ...] | None = None,
        k: int = 100,
        expand_codes: bool = True,
        raw: bool = False,
        weights: dict[str, float] | None = None,
    ) -> list[Hit]:
        """`raw` searches the query exactly as typed (the ablation baseline); `weights` scale a
        retriever's share of the fused score (the citation-graph ablation)."""
        use = tuple(u for u in (use or RETRIEVERS) if u in self.available)
        if expand_codes:
            expand(q, self.con)
        mask = self.mask(q)
        words = q.text if raw else strip_refs(q.text) or q.text
        lists: dict[str, list[int]] = {}
        if q.kind == "statute" and q.refs:  # the sections the user named, and their counterparts, first
            named = [self.pos[u] for pid in q.refs + q.counterparts for u in self.units_of(pid)]
            lists["named"] = [o for o in dict.fromkeys(named) if mask[o]]
        if "bm25" in use:
            lists["bm25"] = self.run_bm25(words, mask, k)
        if "cited" in use and q.kind == "judgment" and (cited := self.cited_mask(q) & mask).any():
            lists["cited"] = self.run_bm25(words, cited, k)
        if "dense" in use or "sparse" in use:
            dense, sparse_ = self.run_vectors(q.text if raw else q.expanded or q.text, mask, k)
            if "dense" in use:
                lists["dense"] = dense
            if "sparse" in use:
                lists["sparse"] = sparse_
        return rrf(lists, k, weights)


def strip_refs(query: str) -> str:
    """The query without its section numbers. Keyword search does better without them: judgments
    mostly use the old numbers, so "BNS 103" only matches the wrong documents."""
    for c in sorted(extract(query, query=True), key=lambda c: c.start, reverse=True):
        before = re.search(r"(?:\s*(?:,|\band\b|\bunder\b|\bof\b|\bin\b|\bread with\b))*\s*$", query[: c.start])
        start = before.start() if before else c.start
        query = query[:start] + query[c.end :]
    return re.sub(r"\s+([,.?])", r"\1", re.sub(r"\s+", " ", query)).strip(" ,")


def rrf(lists: dict[str, list[int]], k: int, weights: dict[str, float] | None = None) -> list[Hit]:
    """Reciprocal Rank Fusion: score = Σ w / (60 + rank), w = 1 unless weighted. No score calibration needed."""
    hits: dict[int, Hit] = {}
    for name, ranked in lists.items():
        w = (weights or {}).get(name, 1.0)
        for rank, o in enumerate(ranked, start=1):
            h = hits.setdefault(o, Hit(o, 0.0))
            h.score += w / (RRF_K + rank)
            h.by[name] = rank
    return sorted(hits.values(), key=lambda h: -h.score)[:k]


def expand(q: Query, con) -> None:  # type: ignore[no-untyped-def]
    """Find the provisions named in the query and their counterparts in the other code.

    `refs` and `counterparts` drive the citation-graph retriever; `expanded` (the query plus the
    counterparts' names) is what the vector retrievers embed.
    """
    q.refs = list(dict.fromkeys(c.provision_id for c in extract(q.text, query=True)))
    q.counterparts = []
    extra: list[str] = []
    for pid in q.refs:
        rows = con.execute(
            """SELECT p.id, p.heading FROM section_map m JOIN provisions p ON p.id = coalesce(
                   CASE WHEN m.new_id = ? THEN m.old_id END, CASE WHEN m.old_id = ? THEN m.new_id END)
               WHERE m.new_id = ? OR m.old_id = ?""",
            (pid, pid, pid, pid),
        ).fetchall()
        for other, heading in rows[:MAX_COUNTERPARTS]:
            q.counterparts.append(other)
            act, num = other.split(":")
            extra.append(f"Section {num} {_act_words(act)} ({heading})")
    q.expanded = q.text + ("\n" + "; ".join(dict.fromkeys(extra)) if extra else "")


def _act_words(act: str) -> str:
    return {
        "IPC": "IPC Indian Penal Code",
        "CRPC": "CrPC Code of Criminal Procedure",
        "IEA": "Evidence Act",
        "BNS": "BNS Bharatiya Nyaya Sanhita",
        "BNSS": "BNSS Bharatiya Nagarik Suraksha Sanhita",
        "BSA": "BSA Bharatiya Sakshya Adhiniyam",
    }[act]


def _topk(scores: np.ndarray, k: int) -> list[int]:
    k = min(k, int(np.isfinite(scores).sum()))
    if k <= 0:
        return []
    idx = np.argpartition(-scores, k - 1)[:k]
    return idx[np.argsort(-scores[idx])].tolist()
