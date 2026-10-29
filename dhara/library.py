"""The judgment library: finding judgments, and reading one (a cited brief, questions answered from
inside it, related judgments).

Search takes three kinds of query. A section, old or new, finds judgments citing it or its
counterparts, so "BNS 316" reaches the IPC 405-409 judgments. A case name or report citation
matches the record. Anything else is a topic and goes through the same hybrid retriever as
Research, so "anticipatory bail" finds judgments about it whatever their titles say.

A Supreme Court judgment runs to dozens of pages. The brief and the answers use only that
judgment's own passages, numbered P1, P2… in reading order, and every point must cite the
passages it rests on. A point citing a passage we didn't supply is dropped: the same rule the
research pipeline's verifier applies, here at the scale of a single document.
"""

import json
import re
import sqlite3
from typing import Any

from dhara import llm
from dhara.citations import extract
from dhara.retrieve import Index, Query, rrf, strip_refs

BRIEF_WORDS = 3500
TOPIC_UNITS = 600  # passages pulled for a topic search, grouped into judgments
ORDER = {"newest": "j.decided_on DESC", "oldest": "j.decided_on ASC"}
ASK_PASSAGES = 8

POINT = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}}},
    "required": ["text", "cites"],
    "additionalProperties": False,
}
POINTS = {"type": "array", "items": POINT}
MARK = re.compile(r"\bP\d+\b")
BRIEF_SYS = (
    "You brief Supreme Court of India criminal judgments for lawyers and law students, using ONLY the numbered "
    "passages. facts: two or three plain sentences. issue: the question the Court decided, one sentence. held: the "
    "Court's conclusions as short points. cite_for: two or three legal propositions a lawyer could cite this judgment "
    "for. Every part, facts and issue included, must cite the passage ids it rests on, e.g. P4. Refer to sections as "
    "the judgment does. Never name a victim or a witness."
)
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {"facts": POINT, "issue": POINT, "held": POINTS, "cite_for": POINTS},
    "required": ["facts", "issue", "held", "cite_for"],
    "additionalProperties": False,
}
ASK_SYS = (
    "Answer a question about one Supreme Court of India judgment using ONLY the numbered passages from it. "
    "Start with a one or two sentence answer, then short points, each citing the passage ids it rests on, e.g. P12. "
    "If the passages don't address the question, set found=false and say so in the answer. Never name a victim."
)
ASK_SCHEMA = {
    "type": "object",
    "properties": {"found": {"type": "boolean"}, "answer": {"type": "string"}, "points": POINTS},
    "required": ["found", "answer", "points"],
    "additionalProperties": False,
}


def search(
    ix: Index,
    con: sqlite3.Connection,
    q: str,
    after: str = "",
    before: str = "",
    sort: str = "relevance",
    offset: int = 0,
    n: int = 20,
) -> dict[str, Any]:
    lo, hi = after or "0000-00-00", before or "9999-12-31"
    refs = [c.provision_id for c in extract(q, query=True)]
    if refs:
        mode, rows = "section", _by_section(con, refs, lo, hi, sort, offset, n + 1)
    elif not q.strip():
        mode = "all"
        rows = [
            {**dict(r), "via": [], "mentions": 0, "snippet": ""}
            for r in con.execute(
                f"SELECT id, title, decided_on, citation FROM judgments j WHERE decided_on BETWEEN ? AND ? "
                f"ORDER BY {ORDER.get(sort, ORDER['newest'])} LIMIT ? OFFSET ?",
                (lo, hi, n + 1, offset),
            )
        ]
    else:
        mode, rows = "topic", _by_topic(ix, con, q, lo, hi, sort)[offset : offset + n + 1]
    return {"mode": mode, "items": rows[:n], "more": len(rows) > n}


def _by_section(
    con: sqlite3.Connection, refs: list[str], lo: str, hi: str, sort: str, offset: int, n: int
) -> list[dict[str, Any]]:
    others = [r[0] for p in refs for r in con.execute(_COUNTERPARTS, (p, p, p)) if r[0]]
    pids = list(dict.fromkeys(refs + others))
    order = ORDER.get(sort, "n DESC, j.decided_on DESC")
    rows = con.execute(
        f"""SELECT j.id, j.title, j.decided_on, j.citation, count(*) AS n, group_concat(DISTINCT c.provision_id)
            FROM citations c JOIN judgments j ON j.id = c.judgment_id
            WHERE c.provision_id IN ({",".join("?" * len(pids))}) AND j.decided_on BETWEEN ? AND ?
            GROUP BY j.id ORDER BY {order} LIMIT ? OFFSET ?""",
        (*pids, lo, hi, n, offset),
    )
    return [
        {
            "id": r[0],
            "title": r[1],
            "decided_on": r[2],
            "citation": r[3],
            "mentions": r[4],
            "via": r[5].split(","),
            "snippet": "",
        }
        for r in rows
    ]


_COUNTERPARTS = (
    "SELECT CASE WHEN new_id = ? THEN old_id ELSE new_id END FROM section_map WHERE new_id = ? OR old_id = ?"
)


def _by_topic(ix: Index, con: sqlite3.Connection, q: str, lo: str, hi: str, sort: str) -> list[dict[str, Any]]:
    """Case-name matches first, then judgments the retriever finds, each with the passage that matched."""
    like = f"%{q.strip()}%"
    named = [
        {**dict(r), "via": [], "mentions": 0, "snippet": ""}
        for r in con.execute(
            "SELECT id, title, decided_on, citation FROM judgments "
            "WHERE (title LIKE ? OR citation LIKE ? OR id LIKE ?) AND decided_on BETWEEN ? AND ? "
            "ORDER BY decided_on DESC LIMIT 50",
            (like, like, like, lo, hi),
        )
    ]
    mask = ix.mask(Query(q, kind="judgment")) & (ix.decided >= lo) & (ix.decided <= hi)
    lists = {"bm25": ix.run_bm25(q, mask, TOPIC_UNITS)}
    if "dense" in ix.available:
        lists["dense"], lists["sparse"] = ix.run_vectors(q, mask, TOPIC_UNITS)
    best: dict[str, int] = {}
    for h in rrf(lists, TOPIC_UNITS):
        if mask[h.ord]:
            best.setdefault(ix.ref[h.ord], h.ord)
    found = [j for j in best if j not in {r["id"] for r in named}]
    units = [ix.ids[best[j]] for j in found]
    text = dict(_where_in(con, "SELECT id, text FROM units", units))
    meta = {r[0]: r for r in _where_in(con, "SELECT id, title, decided_on, citation FROM judgments", found)}
    rows = named + [
        {
            "id": j,
            "title": meta[j][1],
            "decided_on": meta[j][2],
            "citation": meta[j][3],
            "via": [],
            "mentions": 0,
            "snippet": _snippet(text.get(ix.ids[best[j]], ""), q),
        }
        for j in found
        if j in meta
    ]
    if sort in ORDER:
        rows.sort(key=lambda r: r["decided_on"], reverse=sort == "newest")
    return rows


def _where_in(con: sqlite3.Connection, select: str, ids: list[str]) -> list[Any]:
    return con.execute(f"{select} WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() if ids else []


def _snippet(text: str, q: str, size: int = 45) -> str:
    """The words around the first query term in the passage, so a hit shows why it matched."""
    words = text.split()
    terms = {t.lower() for t in q.split() if len(t) > 3}
    at = next((i for i, w in enumerate(words) if w.lower().strip(".,;:()\"'") in terms), 0)
    start = max(0, at - 15)
    return ("… " if start else "") + " ".join(words[start : start + size]) + (" …" if start + size < len(words) else "")


CORAM = re.compile(r"\[\s*([A-Z][A-Za-z.,'\s*@&()-]{3,250}?)\s*,?\s*(?:CJI|JJ|J)\s*\.?\s*\]")
TITLES = {"CJ", "CJI", "J", "JJ"}


def bench(con: sqlite3.Connection, jid: str) -> list[str]:
    """The judges, from the reporter's line "[A, B AND C, JJ.]" near the top of the headnote. A
    larger bench binds a smaller one, so a lawyer weighs a judgment by this. Found for about two
    thirds of judgments; empty when the headnote doesn't carry it."""
    row = con.execute("SELECT text FROM judgment_chunks WHERE judgment_id=? AND role='headnote' ORDER BY ord", (jid,))
    head = " ".join(r[0] for r in row)[:1500]
    m = CORAM.search(head)
    if not m:
        return []
    names = [n.strip(" .,*") for n in re.split(r",|\band\b", m.group(1), flags=re.I)]
    names = [n for n in names if n and n not in TITLES]
    return [] if any(len(n) > 40 for n in names) else [n.title() for n in names]


def passages(con: sqlite3.Connection, jid: str) -> list[dict[str, Any]]:
    rows = con.execute("SELECT id, role, text FROM judgment_chunks WHERE judgment_id=? ORDER BY ord", (jid,))
    return [{"n": f"P{i + 1}", "id": r[0], "role": r[1], "text": r[2]} for i, r in enumerate(rows)]


def brief(con: sqlite3.Connection, jid: str) -> dict[str, Any]:
    """Generated once per judgment and kept in the `briefs` table."""
    if row := con.execute("SELECT body FROM briefs WHERE judgment_id=?", (jid,)).fetchone():
        return json.loads(row[0])  # type: ignore[no-any-return]
    ps = passages(con, jid)
    # the headnote first, then the judgment in order, always keeping its last two passages
    # (the operative conclusion) even when the middle has to be cut
    head = [p for p in ps if p["role"] == "headnote"]
    body = [p for p in ps if p["role"] != "headnote"]
    picked, words = list(head), sum(len(p["text"].split()) for p in head)
    tail = body[-2:]
    for p in body[:-2]:
        if words + len(p["text"].split()) > BRIEF_WORDS:
            break
        picked.append(p)
        words += len(p["text"].split())
    picked += [p for p in tail if p not in picked]
    out = llm.json_call(BRIEF_SYS, _listing(picked), BRIEF_SCHEMA, "brief", max_tokens=2000)
    if not out:
        return {}
    shown = {p["n"] for p in picked}
    for key in ("facts", "issue"):
        out[key] = out[key] if _supported(out.get(key), shown) else None
    for key in ("held", "cite_for"):
        out[key] = [pt for pt in out.get(key, []) if _supported(pt, shown)]
    con.execute("INSERT OR REPLACE INTO briefs VALUES (?, ?)", (jid, json.dumps(out)))
    con.commit()
    return out


def ask(ix: Index, con: sqlite3.Connection, jid: str, question: str) -> dict[str, Any]:
    """Retrieve the judgment's passages that bear on the question, then answer from them alone."""
    ps = passages(con, jid)
    by_id = {p["id"]: p for p in ps}
    mask = ix.kind == "none"
    for u in by_id:
        if u in ix.pos:
            mask[ix.pos[u]] = True
    lists = {"bm25": ix.run_bm25(strip_refs(question) or question, mask, ASK_PASSAGES)}
    if "dense" in ix.available:
        lists["dense"], lists["sparse"] = ix.run_vectors(question, mask, ASK_PASSAGES)
    # a short judgment has fewer passages than we ask for; the extra ranks are outside the mask
    hits = [by_id[u] for h in rrf(lists, ASK_PASSAGES) if (u := ix.ids[h.ord]) in by_id]
    hits.sort(key=lambda p: int(p["n"][1:]))  # reading order makes the context easier to follow
    out = llm.json_call(ASK_SYS, f"Question: {question}\n\n{_listing(hits)}", ASK_SCHEMA, "ask", max_tokens=1500)
    shown = {p["n"] for p in hits}
    points = [pt for pt in out.get("points", []) if _supported(pt, shown)]
    answer = out.get("answer", "")
    if not set(MARK.findall(answer)) <= shown:  # the lead answer cited a passage it wasn't given
        answer = ""
    return {
        "found": bool(out.get("found")) and bool(points),
        "answer": answer,
        "points": points,
        "read": [p["n"] for p in hits],
    }


def related(ix: Index, con: sqlite3.Connection, jid: str, n: int = 5) -> list[dict[str, str]]:
    """Judgments on the same question, found with the headnote as the query, not by shared section numbers."""
    head = " ".join(p["text"] for p in passages(con, jid) if p["role"] == "headnote")
    text = " ".join(head.split()[:120])
    if not text:
        return []
    q = Query(text, kind="judgment")
    mask = ix.mask(q)
    for u in ix.units_of(jid):
        mask[ix.pos[u]] = False
    lists = {"bm25": ix.run_bm25(strip_refs(text) or text, mask, 80)}
    if "dense" in ix.available:
        lists["dense"], lists["sparse"] = ix.run_vectors(text, mask, 80)
    seen: list[str] = []
    for h in rrf(lists, 80):
        ref = ix.ref[h.ord]
        if mask[h.ord] and ref not in seen:
            seen.append(ref)
        if len(seen) == n:
            break
    rows = {
        r[0]: r
        for r in con.execute(
            f"SELECT id, title, decided_on, citation FROM judgments WHERE id IN ({','.join('?' * len(seen))})", seen
        )
    }
    return [{"id": i, "title": rows[i][1], "decided_on": rows[i][2], "citation": rows[i][3]} for i in seen if i in rows]


def _supported(point: dict[str, Any] | None, shown: set[str]) -> bool:
    """Kept only if it cites at least one passage and every passage it cites was supplied."""
    return bool(point and point["cites"] and set(point["cites"]) <= shown)


def _listing(ps: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"[{p['n']}]{' (headnote)' if p['role'] == 'headnote' else ''}\n{p['text']}" for p in ps)
