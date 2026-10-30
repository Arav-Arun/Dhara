"""Second-stage rerankers, each one an ablation row.

- multivector: bge-m3's ColBERT-style token vectors, computed on the fly for the fused top-N
  (late interaction: every query token finds its best-matching passage token)
- cross_encoder: a cross-encoder reads query and passage together; off-the-shelf or our
  fine-tuned model (train_reranker.py). A name ending in "#int8" loads it on the CPU with 8-bit
  weights, as the API serves it
- llm: gpt-6-luna orders the top-N in one call, the baseline the small model has to beat on
  quality per rupee and per millisecond
"""

from typing import Any

import numpy as np

from dhara import llm
from dhara.retrieve import MODEL_LOCK, Hit, Index, Query

_cross: dict[str, Any] = {}
_scored: dict[tuple[str, str, int], float] = {}


def texts(ix: Index, hits: list[Hit]) -> list[str]:
    rows = (
        dict(
            ix.con.execute(
                f"SELECT id, text FROM units WHERE id IN ({','.join('?' * len(hits))})", [ix.ids[h.ord] for h in hits]
            ).fetchall()
        )
        if hits
        else {}
    )
    return [rows[ix.ids[h.ord]] for h in hits]


def _reorder(hits: list[Hit], top: int, scores: list[float]) -> list[Hit]:
    head = [h for _, h in sorted(zip(scores, hits[:top], strict=True), key=lambda x: -x[0])]
    for h, s in zip(head, sorted(scores, reverse=True), strict=True):
        h.score = float(s)
    return head + hits[top:]


def multivector(ix: Index, q: Query, hits: list[Hit], top: int = 30) -> list[Hit]:
    model = ix.encoder()
    cand = texts(ix, hits[:top])
    with MODEL_LOCK:
        qv = model.encode([q.expanded or q.text], return_dense=False, return_sparse=False, return_colbert_vecs=True)
        pv = model.encode(
            cand, batch_size=16, max_length=512, return_dense=False, return_sparse=False, return_colbert_vecs=True
        )
    scores = [float(model.colbert_score(qv["colbert_vecs"][0], p)) for p in pv["colbert_vecs"]]
    return _reorder(hits, len(cand), scores)


def clear_cache() -> None:
    _scored.clear()


def cross_encoder(ix: Index, q: Query, hits: list[Hit], model_name: str, top: int = 50) -> list[Hit]:
    from sentence_transformers import CrossEncoder

    from dhara.index import _device

    with MODEL_LOCK:
        if model_name not in _cross:
            name, _, mode = model_name.partition("#")
            model = CrossEncoder(name, max_length=512, device="cpu" if mode else _device())
            if mode == "int8":  # dynamic quantization: weights stored in 8 bits, activations quantized per batch
                import torch

                torch.backends.quantized.engine = (
                    "fbgemm" if "fbgemm" in torch.backends.quantized.supported_engines else "qnnpack"
                )
                model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
            _cross[model_name] = model
    # a (question, passage) pair is scored once: ablation rows and repeat questions share most pairs
    if len(_scored) > 500_000:
        _scored.clear()
    keys = [(model_name, q.text, h.ord) for h in hits[:top]]
    todo = [(k, h) for k, h in zip(keys, hits, strict=False) if k not in _scored]
    if todo:
        cand = texts(ix, [h for _, h in todo])
        with MODEL_LOCK:
            out = _cross[model_name].predict([(q.text, t) for t in cand], batch_size=16, show_progress_bar=False)
        _scored.update(zip([k for k, _ in todo], np.asarray(out, dtype=float).tolist(), strict=True))
    return _reorder(hits, len(keys), [_scored[k] for k in keys])


LLM_SYS = (
    "You rank search results for an Indian criminal-law research tool. Old and new codes map to each other "
    "(IPC→BNS, CrPC→BNSS, Evidence Act→BSA), so a passage citing the old number of the provision in the query "
    "can be exactly right. Return the passage numbers from most to least useful for answering the query."
)
LLM_SCHEMA = {
    "type": "object",
    "properties": {"order": {"type": "array", "items": {"type": "integer"}}},
    "required": ["order"],
    "additionalProperties": False,
}


def llm_rerank(ix: Index, q: Query, hits: list[Hit], top: int = 20) -> list[Hit]:
    cand = texts(ix, hits[:top])
    listing = "\n\n".join(f"[{i}] {' '.join(t.split()[:120])}" for i, t in enumerate(cand))
    order = llm.json_call(
        LLM_SYS, f"Query: {q.text}\n\nPassages:\n{listing}", LLM_SCHEMA, "rerank:llm", max_tokens=600
    ).get("order", [])
    order = [i for i in dict.fromkeys(order) if 0 <= i < len(cand)]
    order += [i for i in range(len(cand)) if i not in order]
    scores = [0.0] * len(cand)
    for rank, i in enumerate(order):
        scores[i] = float(len(order) - rank)
    return _reorder(hits, len(cand), scores)
