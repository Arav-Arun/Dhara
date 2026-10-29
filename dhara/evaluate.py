"""Metrics and the ablation runner over DharaBench.

Precedent queries are scored at judgment level (a judgment counts once, at the rank of its
best chunk); statute queries at provision level with graded relevance (new provision = 2,
its old counterpart = 1). Results go to eval/results/<split>.json and a Markdown table,
which the README and /method page read, so published numbers always match the code.
"""

import json
import math
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dhara import bench
from dhara.config import ROOT
from dhara.retrieve import LIVE_WEIGHTS, Hit, Index, Query, strip_refs

RESULTS = ROOT / "eval" / "results"
Ranker = Callable[[Index, Query], list[Hit]]


def ranked_refs(ix: Index, hits: list[Hit]) -> list[str]:
    """Collapse unit hits to judgment ids / provision ids, keeping first occurrence."""
    seen: dict[str, None] = {}
    for h in hits:
        seen.setdefault(ix.ref[h.ord], None)
    return list(seen)


def ndcg(ranked: list[str], gains: dict[str, int], k: int = 10) -> float:
    dcg = sum(gains.get(r, 0) / math.log2(i + 2) for i, r in enumerate(ranked[:k]))
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(gains.values(), reverse=True)[:k]))
    return dcg / ideal if ideal else 0.0


def score(ranked: list[str], gains: dict[str, int]) -> dict[str, float]:
    rel = {r for r, g in gains.items() if g > 0}
    first = next((i for i, r in enumerate(ranked) if r in rel), None)
    return {
        "recall@10": float(any(r in rel for r in ranked[:10])),
        "recall@50": float(any(r in rel for r in ranked[:50])),
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
        "ndcg@10": ndcg(ranked, gains),
    }


def run(
    ix: Index,
    ranker: Ranker,
    split: str = "dev",
    types: tuple[str, ...] = ("precedent", "precedent_plain", "precedent_reverse", "statute"),
    workers: int = 1,
) -> dict[str, Any]:
    """Score one configuration. `workers` > 1 only for rankers that wait on the network (the LLM
    reranker); the GPU-bound ones would just compete with each other."""
    by_type: dict[str, list[dict[str, float]]] = {}
    latency: list[float] = []
    items = bench.load(split)
    if "precedent_plain" in types:
        items += [
            {**x, "type": "precedent_plain", "query": strip_refs(x["query"])} for x in items if x["type"] == "precedent"
        ]

    def one(item: dict[str, Any]) -> tuple[str, dict[str, float], float]:
        kind = "statute" if item["type"] == "statute" else "judgment"
        q = Query(str(item["query"]), kind=kind, exclude=frozenset(item.get("exclude_units", [])))
        t = time.perf_counter()
        hits = ranker(ix, q)
        took = time.perf_counter() - t
        gains = {j: 1 for j in item["relevant_judgments"]} if kind == "judgment" else dict(item["relevant_provisions"])
        return str(item["type"]), score(ranked_refs(ix, hits), gains), took

    todo = [x for x in items if x["type"] in types]
    with ThreadPoolExecutor(workers) as pool:
        for kind, s, took in pool.map(one, todo):
            by_type.setdefault(kind, []).append(s)
            latency.append(took)
    out: dict[str, Any] = {t: _mean(v) | {"n": len(v)} for t, v in by_type.items()}
    out["latency_p50_s"] = sorted(latency)[len(latency) // 2] if latency else 0.0
    return out


def _mean(rows: list[dict[str, float]]) -> dict[str, float]:
    return {k: round(sum(r[k] for r in rows) / len(rows), 3) for k in rows[0]} if rows else {}


def save(split: str, results: dict[str, dict[str, Any]]) -> str:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{split}.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update(results)
    path.write_text(json.dumps(old, indent=2))
    lines = [
        "| Config | Precedent R@10 | Precedent MRR | Same, no section numbers R@10 | Reverse R@10 "
        "| Statute nDCG@10 | Statute R@10 | p50 s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, r in old.items():
        p, pl, rv, s = (r.get(k, {}) for k in ("precedent", "precedent_plain", "precedent_reverse", "statute"))
        lines.append(
            f"| {name} | {p.get('recall@10', '')} | {p.get('mrr', '')} | {pl.get('recall@10', '')} | "
            f"{rv.get('recall@10', '')} | {s.get('ndcg@10', '')} | {s.get('recall@10', '')} | "
            f"{round(r.get('latency_p50_s', 0), 3)} |"
        )
    table = "\n".join(lines) + "\n"
    (RESULTS / f"{split}.md").write_text(table)
    return table


def configs(finetuned: str | None = None) -> dict[str, Ranker]:
    """The ablation rows, cheapest first. Each adds one thing to the row above it."""
    from dhara import rerank

    def first(use: tuple[str, ...], raw: bool = False) -> Ranker:
        return lambda ix, q: ix.search(q, use=use, expand_codes=not raw, raw=raw)

    def then(base: Ranker, step: Callable[[Index, Query, list[Hit]], list[Hit]]) -> Ranker:
        return lambda ix, q: step(ix, q, base(ix, q))

    fused = first(("bm25", "cited", "dense", "sparse"))
    rows: dict[str, Ranker] = {
        "keyword search, query as typed": first(("bm25",), raw=True),
        "dense only, query as typed (plain RAG, as in prior IPC/BNS repos)": first(("dense",), raw=True),
        "keyword search, section numbers set aside": first(("bm25",)),
        "+ citation graph": first(("bm25", "cited")),
        "+ bge-m3 dense and sparse, fused by RRF": fused,
        "+ multi-vector rescoring": then(fused, rerank.multivector),
        "+ cross-encoder (bge-reranker-base)": then(
            fused, lambda ix, q, h: rerank.cross_encoder(ix, q, h, "BAAI/bge-reranker-base")
        ),
        "+ cross-encoder (bge-reranker-v2-m3)": then(
            fused, lambda ix, q, h: rerank.cross_encoder(ix, q, h, "BAAI/bge-reranker-v2-m3")
        ),
        "+ LLM reranker (gpt-6-luna)": then(fused, rerank.llm_rerank),
    }
    if finetuned:
        rows["+ fine-tuned cross-encoder (ours)"] = then(
            fused, lambda ix, q, h: rerank.cross_encoder(ix, q, h, finetuned)
        )
        # dense and sparse dilute the citation graph when every list counts the same; weight 2 was
        # fixed before measuring, so it is not tuned on dev or test
        weighted = lambda ix, q: ix.search(q, use=("bm25", "cited", "dense", "sparse"), weights={"cited": 2.0})  # noqa: E731
        rows["+ fusion with the citation graph weighted x2"] = weighted
        rows["+ fine-tuned cross-encoder over the weighted fusion"] = then(
            weighted, lambda ix, q, h: rerank.cross_encoder(ix, q, h, finetuned)
        )
    return rows


def ablate(split: str = "dev", only: list[str] | None = None, finetuned: str | None = None) -> str:
    """Each row is saved as it finishes, and rows already in the results file are skipped, so a
    stopped run resumes. Delete the file to measure everything again."""
    from dhara import rerank

    ix = Index()
    path = RESULTS / f"{split}.json"
    done = json.loads(path.read_text()) if path.exists() else {}
    for name, ranker in configs(finetuned).items():
        if (only and not any(o in name for o in only)) or name in done:
            continue
        rerank.clear_cache()  # each row pays for its own reranker scores, so its latency is real
        save(split, {name: run(ix, ranker, split, workers=8 if "LLM" in name else 1)})
    return (RESULTS / f"{split}.md").read_text()


def calibrate_abstention(ix: Index, reranker: str, split: str = "dev") -> dict[str, float]:
    """Pick the cross-encoder score below which Dhara declines instead of answering.

    In-scope questions (statute and precedent) should clear it; the out-of-scope ones in the
    benchmark (civil, tax, family…) should not. We take the threshold with the best balanced accuracy.
    """
    from dhara import rerank

    scores: list[tuple[float, bool]] = []
    for item in bench.load(split):
        kind = "statute"  # every question is first checked against the statutes
        q = Query(str(item["query"]), kind=kind)
        hits = rerank.cross_encoder(ix, q, ix.search(q, k=50, weights=LIVE_WEIGHTS), reranker, top=20)
        scores.append((hits[0].score if hits else -99.0, item["type"] != "abstain"))
    best = (0.0, 0.0)
    for t in sorted({s for s, _ in scores}):
        in_scope = [s >= t for s, ok in scores if ok]
        out_scope = [s < t for s, ok in scores if not ok]
        balanced = (sum(in_scope) / len(in_scope) + sum(out_scope) / len(out_scope)) / 2
        best = max(best, (balanced, t))
    return {"threshold": best[1], "balanced_accuracy": round(best[0], 3), "n": len(scores)}
