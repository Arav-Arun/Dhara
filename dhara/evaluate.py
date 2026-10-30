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
from dataclasses import replace
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


def configs(models: dict[str, str] | None = None) -> dict[str, Ranker]:
    """The ablation rows, cheapest first. Each adds one thing to the row above it. `models` holds
    the fine-tuned rerankers that exist (train_reranker.MODELS): "base", "large", "mini"."""
    from dhara import rerank
    from dhara.agent import legal_terms

    def first(use: tuple[str, ...], raw: bool = False) -> Ranker:
        return lambda ix, q: ix.search(q, use=use, expand_codes=not raw, raw=raw)

    def then(base: Ranker, step: Callable[[Index, Query, list[Hit]], list[Hit]]) -> Ranker:
        return lambda ix, q: step(ix, q, base(ix, q))

    def reranked(base: Ranker, model: str) -> Ranker:
        return then(base, lambda ix, q, h: rerank.cross_encoder(ix, q, h, model))

    fused = first(("bm25", "cited", "dense", "sparse"))
    rows: dict[str, Ranker] = {
        "keyword search, query as typed": first(("bm25",), raw=True),
        "dense only, query as typed (plain RAG, as in prior IPC/BNS repos)": first(("dense",), raw=True),
        "keyword search, section numbers set aside": first(("bm25",)),
        "+ citation graph": first(("bm25", "cited")),
        "+ bge-m3 dense and sparse, fused by RRF": fused,
        "+ multi-vector rescoring": then(fused, rerank.multivector),
        "+ cross-encoder (bge-reranker-base)": reranked(fused, "BAAI/bge-reranker-base"),
        "+ cross-encoder (bge-reranker-v2-m3)": reranked(fused, "BAAI/bge-reranker-v2-m3"),
        "+ LLM reranker (gpt-6-luna)": then(fused, rerank.llm_rerank),
    }
    models = models or {}
    for key, label in (
        ("base", "fine-tuned bge-reranker-base"),
        ("large", "fine-tuned bge-reranker-v2-m3"),
        ("mini", "MiniLM distilled from the fine-tuned v2-m3"),
    ):
        if key in models:
            rows[f"+ {label}"] = reranked(fused, models[key])
    if "base" in models:
        # dense and sparse dilute the citation graph when every list counts the same; weight 2 was
        # fixed before measuring, so it is not tuned on dev or test
        weighted = lambda ix, q: ix.search(q, use=("bm25", "cited", "dense", "sparse"), weights={"cited": 2.0})  # noqa: E731
        rows["+ fusion with the citation graph weighted x2"] = weighted
        rows["+ fine-tuned bge-reranker-base over the weighted fusion"] = reranked(weighted, models["base"])
    for key in ("base", "large", "mini"):
        if f"{key}#int8" in models:
            rows[f"+ the {key} model with 8-bit weights, on the CPU"] = reranked(fused, models[f"{key}#int8"])
    if "live" in models:
        live = models["live"]

        def with_terms(ix: Index, q: Query) -> list[Hit]:
            terms = legal_terms(q.text)
            searched = replace(q, text=f"{q.text}\n{terms}") if terms else q
            return rerank.cross_encoder(ix, q, ix.search(searched), live)

        rows["+ questions without a section number put into legal terms first"] = with_terms
    return rows


def ablate(split: str = "dev", only: list[str] | None = None, models: dict[str, str] | None = None) -> str:
    """Each row is saved as it finishes, and rows already in the results file are skipped, so a
    stopped run resumes. Delete the file to measure everything again."""
    from dhara import rerank

    ix = Index()
    path = RESULTS / f"{split}.json"
    done = json.loads(path.read_text()) if path.exists() else {}
    for name, ranker in configs(models).items():
        if (only and not any(o in name for o in only)) or name in done:
            continue
        rerank.clear_cache()  # each row pays for its own reranker scores, so its latency is real
        save(split, {name: run(ix, ranker, split, workers=8 if "LLM" in name else 1)})
    return (RESULTS / f"{split}.md").read_text()


def calibrate_abstention(
    ix: Index, reranker: str, split: str = "dev", keep: float = 0.95, top: int = 20
) -> dict[str, float]:
    """Pick the cross-encoder score below which Dhara declines instead of answering.

    In-scope questions (statute and precedent) should clear it; the out-of-scope ones in the
    benchmark (civil, tax, family…) should not. Turning away a real criminal-law question is the worse
    mistake: an off-topic one still only gets criminal-law passages, and every citation is checked.
    So the threshold is the highest that still answers `keep` of the in-scope questions. `top` is how
    many statutes are scored: the right one is nearly always in the first few, so fewer is cheaper.
    """
    from dhara import rerank

    scores: list[tuple[float, bool]] = []
    for item in bench.load(split):
        kind = "statute"  # every question is first checked against the statutes
        q = Query(str(item["query"]), kind=kind)
        hits = rerank.cross_encoder(ix, q, ix.search(q, k=50, weights=LIVE_WEIGHTS), reranker, top=top)
        scores.append((hits[0].score if hits else -99.0, item["type"] != "abstain"))
    in_scope = sorted(s for s, ok in scores if ok)
    out_scope = [s for s, ok in scores if not ok]
    t = in_scope[int(len(in_scope) * (1 - keep))]
    return {
        "threshold": t,
        "in_scope_answered": round(sum(s >= t for s in in_scope) / len(in_scope), 3),
        "out_of_scope_declined": round(sum(s < t for s in out_scope) / len(out_scope), 3),
        "n": len(scores),
        "top": top,
    }
