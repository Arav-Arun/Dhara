"""Check a draft: every section cited in it, against the code in force on its dates.

Offences follow the offence date and procedure and evidence follow the date the case began
(rules.py). A wrong citation gets the corrected section, narrowed to the subsection where NCRB's
table maps at that level, and each offence gets its row from the BNSS First Schedule (arrest,
bail, court, punishment), which is what a chargesheet turns on.
"""

import re
import sqlite3
from datetime import date
from typing import Any

from dhara import rules
from dhara.citations import extract

NAMES = {"CRPC": "CrPC", "IEA": "the Evidence Act"}
AREA = {
    "IPC": "substantive",
    "BNS": "substantive",
    "CRPC": "procedure",
    "BNSS": "procedure",
    "IEA": "evidence",
    "BSA": "evidence",
}


def check(con: sqlite3.Connection, text: str, offence: date | None, started: date | None) -> list[dict[str, Any]]:
    """Every citation in the draft, with what's wrong with it (if anything) and the fix."""
    governing = {r.area: r.code for r in rules.applicable(offence, started)} if offence else {}
    # an old offence with no FIR date: CrPC if the case was pending on 1 July 2024, BNSS if it began later
    unsure = bool(offence and not started and offence < rules.CUTOVER)
    known = {r[0]: r[1] for r in con.execute("SELECT id, status FROM provisions")}
    out = []
    for c in extract(text, query=True):
        issue, note = "", ""
        area = AREA.get(c.act, "")
        should = governing.get(area, "")
        if c.provision_id not in known:
            issue = "no such section"
        elif known[c.provision_id] == "omitted":
            issue = "repealed or omitted section"
        elif area != "substantive" and unsure:
            note = "Depends on when the case began. Add the FIR date to check."
        elif should == "contested":
            note = "Courts differ on old offences with a new FIR; most apply the BNSS."
        elif should and should != c.act:
            issue = f"wrong code for these dates: {NAMES.get(should, should)} applies"
        out.append(
            {
                "raw": c.raw,
                "start": c.start,
                "end": c.end,
                "provision": c.provision_id,
                "sub": c.sub,
                "issue": issue,
                "note": note,
                "suggest": (
                    fix := suggestions(con, c.provision_id, c.sub) if issue and issue != "no such section" else []
                ),
                "classified": _classified(con, c.provision_id, c.sub, issue, fix),
            }
        )
    return out


def classification(con: sqlite3.Connection, pid: str, sub: str = "") -> list[dict[str, str]]:
    """The First Schedule row(s) for a BNS section as cited; empty for anything else."""
    return _classified(con, pid, sub, "", [])


def _classified(
    con: sqlite3.Connection, pid: str, sub: str, issue: str, fix: list[dict[str, str]]
) -> list[dict[str, str]]:
    """The BNSS First Schedule entry for the offence that applies: arrest, bail and court are what a
    chargesheet turns on. The Schedule often lists several rows under one section without saying
    which subsection each is (BNS 318 has three), so the row is picked by matching its description
    against the cited subsection's text, or the old section's heading when correcting an IPC cite."""
    if not issue and pid.startswith("BNS:"):
        target, tsub = pid, sub
        hint = _first(con, "SELECT text FROM provision_parts WHERE id=?", pid + sub) if sub else ""
    elif issue and fix and fix[0]["id"].startswith("BNS:"):
        target, tsub = fix[0]["id"], fix[0]["sub"]
        hint = _first(con, "SELECT heading FROM provisions WHERE id=?", pid)
    else:
        return []
    rows = [
        dict(r)
        for r in con.execute(
            "SELECT sub, offence, punishment, cognizable, bailable, triable_by FROM offence_classification "
            "WHERE provision_id=?",
            (target,),
        )
    ]
    exact = [r for r in rows if tsub and r["sub"] and (tsub.startswith(r["sub"]) or r["sub"].startswith(tsub))]
    if exact:
        return exact
    if len(rows) > 1 and hint:
        # among rows that mostly match, the most specific wins: "Cheating." matches any cheating text
        ranked = sorted(_rank(r["offence"], hint, i) for i, r in enumerate(rows))[::-1]
        if ranked[0][0] and ranked[0][:3] > ranked[1][:3]:
            return [rows[ranked[0][3]]]
    return rows[:4]


def _first(con: sqlite3.Connection, sql: str, arg: str) -> str:
    row = con.execute(sql, (arg,)).fetchone()
    return row[0] if row else ""


def _rank(description: str, hint: str, i: int) -> tuple[bool, int, float, int]:
    share, hits = _overlap(description, hint)
    return (share >= 0.6, hits, share, i)


def _overlap(description: str, hint: str) -> tuple[float, int]:
    """Share and number of the description's word stems found in the hint ("cheats" and "cheating"
    share "cheat")."""
    d = _stems(description)
    hit = len(d & _stems(hint))
    return (hit / len(d) if d else 0.0, hit)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", text.lower())}


def suggestions(con: sqlite3.Connection, pid: str, sub: str) -> list[dict[str, str]]:
    """The other code's provision, narrowed to the subsection when NCRB's table maps at that level:
    BNS 3(5) is IPC 34, not all nine sections BNS 3 gathers up."""
    old = pid.split(":")[0] in ("IPC", "CRPC", "IEA")
    me, me_sub, other, other_sub = (
        ("old_id", "old_sub", "new_id", "new_sub") if old else ("new_id", "new_sub", "old_id", "old_sub")
    )
    rows = con.execute(
        f"SELECT {other}, {other_sub}, {me_sub} FROM mapping_rows WHERE {me}=? AND coalesce({other}, '') != ''",
        (pid,),
    ).fetchall()
    if sub:
        rows = [r for r in rows if r[2] and (sub.startswith(r[2]) or r[2].startswith(sub))] or rows
    pairs = dict.fromkeys((r[0], r[1] or "") for r in rows)
    if pairs:
        return [{"id": i, "sub": s} for i, s in pairs]
    rows = con.execute(
        "SELECT CASE WHEN new_id = ? THEN old_id ELSE new_id END FROM section_map WHERE new_id = ? OR old_id = ?",
        (pid, pid, pid),
    ).fetchall()
    return [{"id": r[0], "sub": ""} for r in rows if r[0]]
