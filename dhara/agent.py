"""The research pipeline, end to end, with a bounded agentic step and a full trace.

    route → expand + retrieve (statutes ∥ judgments, fused by rank) → rerank judgments → scope check
          → [≤2 follow-up searches] → context budget → structured answer → deterministic verification

The only "agentic" part is one decision: after the first pass, the model may ask for up to two
more searches (e.g. "judgments on the companion procedural section"). It can't loop, can't call
anything but our retriever, and every call it makes is in the trace. That keeps cost and latency
bounded and makes the behaviour easy to show in the UI and to ablate.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from dhara import generate, llm, rerank, verify
from dhara.retrieve import LIVE_WEIGHTS, Hit, Index, Query

FOLLOWUP_SYS = (
    "You plan searches for an Indian criminal-law research tool. Given a question and the passages found so far, "
    "decide whether one or two more searches would clearly help (for example the companion procedural or evidence "
    "provision, or judgments on a specific element). If the passages already cover the question, return no searches."
)
FOLLOWUP_SCHEMA = {
    "type": "object",
    "properties": {
        "searches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string", "enum": ["statute", "judgment"]},
                },
                "required": ["query", "kind"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["searches"],
    "additionalProperties": False,
}
REWRITE_SYS = (
    "You rewrite a follow-up in an Indian criminal-law research conversation as one standalone question. Keep every "
    "section number, date and fact it relies on from the earlier turns. If it already stands alone, return it as is."
)
REWRITE_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}},
    "required": ["question"],
    "additionalProperties": False,
}
LOOKUP = re.compile(
    r"^\s*(?:what\s+is\s+)?(?:section\s+)?(?:BNS|BNSS|BSA|IPC|CrPC|Cr\.P\.C\.?|IEA)\s*\d{1,3}[A-Z]{0,3}\s*\??\s*$", re.I
)


@dataclass
class Trace:
    events: list[dict[str, Any]] = field(default_factory=list)
    on_event: Callable[[dict[str, Any]], None] | None = None  # the API streams events as they happen

    def add(self, stage: str, started: float, **detail: Any) -> None:
        event = {"stage": stage, "ms": round((time.perf_counter() - started) * 1000), **detail}
        self.events.append(event)
        if self.on_event:
            self.on_event(event)


@dataclass
class Pipeline:
    ix: Index
    reranker: str | None = None  # cross-encoder that reorders judgment passages; None = fused order
    gate: str | None = None  # cross-encoder whose top statute score decides out-of-scope questions
    followups: int = 2
    top_statutes: int = 8
    top_judgments: int = 12
    abstain_below: float | None = None  # cross-encoder score, from evaluate.calibrate_abstention

    def first_pass(self, text: str, kind: str, as_of: date, trace: Trace) -> list[Hit]:
        t = time.perf_counter()
        q = Query(text, as_of=as_of, kind=kind)
        reranked = self.reranker is not None and kind == "judgment"
        # as measured (evaluate.configs): the reranker helps over the even fusion and hurts over the
        # weighted one, and it doesn't help statutes, which keep the weighted order
        hits = self.ix.search(q, k=100, weights=None if reranked else LIVE_WEIGHTS)
        trace.add(
            f"retrieve:{kind}",
            t,
            query=text,
            refs=q.refs,
            counterparts=q.counterparts,
            top=[{"unit": self.ix.ids[h.ord], "rrf": round(h.score, 4), "by": h.by} for h in hits[:10]],
        )
        if reranked and self.reranker:
            t = time.perf_counter()
            hits = rerank.cross_encoder(self.ix, q, hits, self.reranker)
            trace.add(
                f"rerank:{kind}", t, top=[{"unit": self.ix.ids[h.ord], "score": round(h.score, 3)} for h in hits[:10]]
            )
        return hits

    def run(
        self,
        question: str,
        as_of: date | None = None,
        trace: Trace | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        as_of = as_of or date.today()
        trace = trace or Trace()
        if history:
            question = self._standalone(question, history, trace)
        t = time.perf_counter()
        route = "lookup" if LOOKUP.match(question) else "research"
        trace.add("route", t, route=route)
        statutes = self.first_pass(question, "statute", as_of, trace)
        if route == "lookup":
            return {
                "route": route,
                "question": question,
                "statutes": list(dict.fromkeys(self.ix.ref[h.ord] for h in statutes[:3])),
                "trace": trace.events,
            }
        if self._out_of_scope(question, statutes, as_of, trace):
            trace.add(
                "abstain", time.perf_counter(), reason="nothing in the criminal codes matches this question closely"
            )
            return {
                "route": route,
                "question": question,
                "abstain": True,
                "short_answer": "",
                "points": [],
                "caveats": [
                    "This doesn't look like a question about Indian criminal law, or the codes don't cover it."
                ],
                "context": [],
                "follow_ups": [],
                "trace": trace.events,
            }
        judgments = self.first_pass(question, "judgment", as_of, trace)
        statutes, judgments = self._follow_up(question, statutes, judgments, as_of, trace)

        t = time.perf_counter()
        context = generate.budget(self.ix, statutes[: self.top_statutes], judgments[: self.top_judgments])
        trace.add(
            "budget",
            t,
            passages=[{"id": c["id"], "unit": c["unit"]} for c in context],
            words=sum(len(c["text"].split()) for c in context),
        )
        t = time.perf_counter()
        ans = generate.answer(question, context, as_of)
        trace.add("generate", t)
        t = time.perf_counter()
        report = verify.check(ans, {c["id"] for c in context}, self.ix.con, as_of)
        trace.add(
            "verify",
            t,
            kept=len(report.kept),
            summary=report.summary_problem or "ok",
            dropped=[{"text": p["text"][:80], "why": why} for p, why in report.dropped],
        )
        abstain = bool(ans.get("abstain")) or report.abstain
        ids = {c["id"] for c in context}
        # authorities pass the same checks as points (a judgment passage we supplied, real sections),
        # once each; a caveat that cites a passage we didn't supply is dropped
        listed = list({a["id"]: a for a in ans.get("authorities", []) if a["id"].startswith("J")}.values())
        cited = verify.check(
            {"points": [{"text": a["proposition"], "cites": [a["id"]]} for a in listed]}, ids, self.ix.con, as_of
        )
        caveats = [c for c in ans.get("caveats", []) if set(verify.MARK.findall(c)) <= ids]
        return {
            "route": route,
            "question": question,
            "abstain": abstain,
            # a one-line answer that fails the checks is dropped; the checked points still stand
            "short_answer": "" if abstain or report.summary_problem else ans.get("short_answer", ""),
            "points": report.kept,
            "authorities": [] if abstain else [{"id": p["cites"][0], "proposition": p["text"]} for p in cited.kept],
            "caveats": caveats,
            "context": context,
            "follow_ups": [] if abstain else ans.get("follow_ups", [])[:3],
            "trace": trace.events,
        }

    def _out_of_scope(self, question: str, statutes: list[Hit], as_of: date, trace: Trace) -> bool:
        """The gate model scores the top statutes as the calibration did (evaluate.calibrate_abstention)."""
        if not self.gate or self.abstain_below is None:
            return False
        t = time.perf_counter()
        q = Query(question, as_of=as_of, kind="statute")
        top = rerank.cross_encoder(self.ix, q, [replace(h) for h in statutes[:20]], self.gate, top=20)
        score = top[0].score if top else -99.0
        trace.add("gate", t, score=round(score, 3), threshold=round(self.abstain_below, 3))
        return score < self.abstain_below

    def _standalone(self, question: str, history: list[dict[str, str]], trace: Trace) -> str:
        """A follow-up like "and if the accused is a juvenile?" can't be searched on its own words."""
        t = time.perf_counter()
        turns = "\n".join(f"Q: {h['q']}\nA: {h['a'][:600]}" for h in history[-2:])
        out = (
            llm.json_call(
                REWRITE_SYS,
                f"Earlier:\n{turns}\n\nFollow-up: {question}",
                REWRITE_SCHEMA,
                "agent:rewrite",
                max_tokens=300,
            )
            .get("question", "")
            .strip()
        )
        trace.add("rewrite", t, question=out or question)
        return out or question

    def _follow_up(
        self, question: str, statutes: list[Hit], judgments: list[Hit], as_of: date, trace: Trace
    ) -> tuple[list[Hit], list[Hit]]:
        if self.followups <= 0:
            return statutes, judgments
        t = time.perf_counter()
        found = rerank.texts(self.ix, statutes[:4] + judgments[:4])
        listing = "\n".join(f"- {' '.join(x.split()[:40])}" for x in found)
        plan = llm.json_call(
            FOLLOWUP_SYS,
            f"Question: {question}\n\nFound so far:\n{listing}",
            FOLLOWUP_SCHEMA,
            "agent:followup",
            max_tokens=800,
        ).get("searches", [])[: self.followups]
        trace.add("plan", t, searches=plan)
        for s in plan:
            extra = self.first_pass(s["query"], s["kind"], as_of, trace)
            pool = statutes if s["kind"] == "statute" else judgments
            have = {h.ord for h in pool}
            # interleave: keep the original top results first, then the new ones
            new = [h for h in extra[:6] if h.ord not in have]
            pool[6:6] = new
        return statutes, judgments
