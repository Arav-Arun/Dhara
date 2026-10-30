"""Context budget, structured answer, abstention.

The budget is the answer to NyayaRAG's finding that adding precedent made answers worse:
not more context, better-chosen context. Statutes go in first and whole (they're short and
authoritative); judgments are capped per judgment and de-duplicated; we stop at the budget.
Every passage gets a span id ([S1], [J3]) that the model must cite and the verifier checks.
"""

from datetime import date
from typing import Any

from dhara import llm
from dhara.rerank import texts
from dhara.retrieve import Hit, Index

STATUTE_WORDS, JUDGMENT_WORDS, PER_JUDGMENT = 2500, 3000, 2

SYSTEM = (
    "You write a short research note on Indian criminal law for a practising lawyer, using ONLY the numbered "
    "passages given. Start with short_answer: one or two sentences that answer the question directly. "
    "Since 1 July 2024 the BNS, BNSS and BSA replaced the IPC, CrPC and Evidence Act; judgments before then cite the "
    "old numbers, and the passages may give both. Then write short points, each of one kind: 'law' for what the "
    "statute provides (the offence, its ingredients, punishment, the procedure the code lays down), 'holding' for "
    "what a court decided and why, naming the case and year as given in the passage heading, and 'practice' for what "
    "follows for a lawyer (the forum, arrest and bail, what must be shown or pleaded), which must still rest on a "
    "passage. Every point cites the passage ids it relies on, e.g. [S1] or [J2]. Name provisions by their current "
    "number with the old number in brackets. In authorities, list the judgments worth citing, strongest first and at "
    "most five, each with its passage id and the one proposition it supports. If the passages don't support an "
    "answer, set abstain=true and say what's missing. Do the same if the question is about civil, family, tax or "
    "property law rather than an offence or criminal procedure (cruelty, dowry death or maintenance under BNSS 144 "
    "are criminal), and say it is outside the criminal codes. Finally suggest up to three short follow-up questions "
    "a lawyer would plausibly ask next on this matter. This is research help, not legal advice."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "abstain": {"type": "boolean"},
        "short_answer": {"type": "string"},
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["law", "holding", "practice"]},
                    "text": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "text", "cites"],
                "additionalProperties": False,
            },
        },
        "authorities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "proposition": {"type": "string"}},
                "required": ["id", "proposition"],
                "additionalProperties": False,
            },
        },
        "caveats": {"type": "array", "items": {"type": "string"}},
        "follow_ups": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["abstain", "short_answer", "points", "authorities", "caveats", "follow_ups"],
    "additionalProperties": False,
}


def budget(ix: Index, statutes: list[Hit], judgments: list[Hit]) -> list[dict[str, Any]]:
    """Pick passages within the word budget; returns [{id, unit, ref, text}]."""
    out: list[dict[str, Any]] = []
    used = 0
    for hit, text in zip(statutes, texts(ix, statutes), strict=True):
        if used + len(text.split()) > STATUTE_WORDS:
            break
        used += len(text.split())
        pid = ix.ref[hit.ord]
        out.append(
            {
                "id": f"S{len(out) + 1}",
                "unit": ix.ids[hit.ord],
                "ref": pid,
                "title": _statute_title(ix, pid),
                "text": text,
            }
        )
    per: dict[str, int] = {}
    used = 0
    seen: set[str] = set()
    for hit, text in zip(judgments, texts(ix, judgments), strict=True):
        jid = ix.ref[hit.ord]
        key = " ".join(text.split()[:25])
        if per.get(jid, 0) >= PER_JUDGMENT or key in seen or used + len(text.split()) > JUDGMENT_WORDS:
            continue
        per[jid] = per.get(jid, 0) + 1
        seen.add(key)
        used += len(text.split())
        n = sum(1 for x in out if x["id"].startswith("J")) + 1
        title, decided, citation = ix.con.execute(
            "SELECT title, decided_on, citation FROM judgments WHERE id = ?", (jid,)
        ).fetchone()
        name = title.title().replace(" Versus ", " v. ")
        out.append(
            {
                "id": f"J{n}",
                "unit": ix.ids[hit.ord],
                "ref": jid,
                "title": f"{name} ({decided[:4]}) {citation}".strip(),
                "text": text,
            }
        )
    return out


def _statute_title(ix: Index, pid: str) -> str:
    """ "BNS section 316 (formerly IPC 405, 406, 407, 408, 409)": the model can only name the
    other code's number if the passage tells it, and lawyers still cite the old one."""
    act, num = pid.split(":")
    old = act in ("IPC", "CRPC", "IEA")
    col, other = ("new_id", "old_id") if old else ("old_id", "new_id")
    ids = [r[0] for r in ix.con.execute(f"SELECT {col} FROM section_map WHERE {other}=? AND {col} IS NOT NULL", (pid,))]
    if not ids:
        return f"{act} section {num}"
    names = ", ".join(i.replace(":", " ").replace("CRPC", "CrPC") for i in ids[:6])
    return f"{act} section {num} ({'now' if old else 'formerly'} {names})"


def answer(question: str, context: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    passages = "\n\n".join(f"[{c['id']}] {c['title']}\n{c['text']}" for c in context)
    user = f"Date of the question: {as_of.isoformat()}\nQuestion: {question}\n\nPassages:\n{passages}"
    return llm.json_call(SYSTEM, user, SCHEMA, "answer", max_tokens=2500) or {
        "abstain": True,
        "short_answer": "",
        "points": [],
        "caveats": ["The model did not return an answer."],
    }
