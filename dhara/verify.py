"""Deterministic checks on a generated answer.

For every point the model wrote:
1. each cited span id must be one we actually put in the context
2. every section number written in the text must exist in our provision tables
3. a provision written in the text must be in force on `as_of`, unless it has a counterpart in
   the mapping (lawyers legitimately write "BNS 103 (old IPC 302)"); an omitted old section
   presented as current law fails
Points that fail are dropped. If more than half fail, the whole answer becomes an abstention.
The one-line short answer gets checks 1 to 3 on the span ids and sections written into it, and
is dropped on failure. What these checks cannot prove is that a sentence says what its passage
says; that needs a human reader, and the README lists it as a limitation.
This is code, not an LLM judge, so "no fabricated citation reaches the user" is testable.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from dhara.citations import extract

MARK = re.compile(r"\b[SJ]\d+\b")  # span ids the model writes into its own text


@dataclass
class Report:
    kept: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    summary_problem: str = ""  # the one-line answer gets the same checks; it has no separate cites list

    @property
    def abstain(self) -> bool:
        total = len(self.kept) + len(self.dropped)
        return total == 0 or len(self.dropped) > total / 2


def check(answer: dict[str, Any], context_ids: set[str], con: Any, as_of: date) -> Report:
    known = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            "SELECT p.id, a.in_force_from, coalesce(a.in_force_to, '9999-12-31') FROM provisions p "
            "JOIN acts a ON a.code = p.act"
        )
    }
    counterparts = {(n, o) for n, o in con.execute("SELECT new_id, old_id FROM section_map WHERE old_id IS NOT NULL")}
    report = Report()
    if summary := answer.get("short_answer", ""):
        cites = MARK.findall(summary)
        report.summary_problem = (_cite_problem(cites, context_ids) if cites else "") or _section_problem(
            summary, known, counterparts, as_of
        )
    for point in answer.get("points", []):
        problem = _problem(point, context_ids, known, counterparts, as_of)
        if problem:
            report.dropped.append((point, problem))
        else:
            report.kept.append(point)
    return report


def _problem(
    point: dict[str, Any],
    context: set[str],
    known: dict[str, tuple[str, str]],
    counterparts: set[tuple[str, str]],
    as_of: date,
) -> str:
    cites = point.get("cites", [])
    if not cites:
        return "no citation"
    return _cite_problem(cites, context) or _section_problem(point.get("text", ""), known, counterparts, as_of)


def _cite_problem(cites: list[str], context: set[str]) -> str:
    missing = [c for c in cites if c not in context]
    return f"cites spans not in context: {missing}" if missing else ""


def _section_problem(
    text: str, known: dict[str, tuple[str, str]], counterparts: set[tuple[str, str]], as_of: date
) -> str:
    d = as_of.isoformat()
    written = {c.provision_id for c in extract(text, query=True)}
    for pid in written:
        if pid not in known:
            return f"{pid} does not exist"
        lo, hi = known[pid]
        mapped = any(pid in pair for pair in counterparts)  # "BNS 103 (old IPC 302)" is fine
        if not (lo <= d <= hi) and not mapped:
            return f"{pid} was not in force on {d}"
    return ""
