"""HTTP API (FastAPI). Only /research, a judgment's brief and questions about a judgment call the model.

GET  /v1/search?q=             command-palette typeahead
GET  /v1/provisions/{act}/{n}  provision page: text, parts, status, classification, counterparts, precedent
GET  /v1/compare/{act}/{n}     both sides of the mapping, for the section page's word diff
POST /v1/check                 flag wrong-code, missing or renumbered citations in a draft
POST /v1/research              the full pipeline, streamed as server-sent events (trace, then answer)
GET  /v1/judgments?q=          judgments by section (either numbering), name, citation or topic; filtered, paged
GET  /v1/judgments/{id}        one judgment, each section reference in it annotated with its counterpart
GET  /v1/judgments/{id}/brief  a cited brief of it (generated once, then stored)
POST /v1/judgments/{id}/ask    a question answered from that judgment's passages alone
GET  /v1/meta                  corpus counts and the retrievers available
"""

import asyncio
import json
import logging
import re
import threading
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from dhara import checker, db, library, llm
from dhara.agent import Pipeline, Trace
from dhara.citations import extract
from dhara.config import INDIA_CODE_PDF, sc_pdf_url, settings
from dhara.retrieve import Index

app = FastAPI(title="Dhara API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.dhara_allowed_origins.split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
ACTS = {"bns": "BNS", "bnss": "BNSS", "bsa": "BSA", "ipc": "IPC", "crpc": "CRPC", "iea": "IEA"}
_state: dict[str, Any] = {}
log = logging.getLogger("dhara.api")
_hits: dict[str, list[float]] = defaultdict(list)


def con() -> Any:
    return db.shared()


def pipeline() -> Pipeline:
    if "pipeline" not in _state:
        model = settings.processed_dir / "models" / "dhara-reranker"
        trained = (model / "config.json").exists()  # the folder appears with the first checkpoint
        cal = settings.processed_dir.parent.parent / "eval" / "results" / "abstention.json"
        threshold = json.loads(cal.read_text())["threshold"] if cal.exists() and trained else None
        path = str(model) if trained else None  # one fine-tuned model reranks judgments and gates scope
        _state["pipeline"] = Pipeline(Index(), reranker=path, gate=path, abstain_below=threshold)
    return _state["pipeline"]  # type: ignore[no-any-return]


def within_budget() -> None:
    """Refuse model calls once the day's budget is spent; search and section pages keep working."""
    if llm.spent_today() >= settings.dhara_daily_usd:
        raise HTTPException(503, "daily budget for AI answers used up")


def limit(request: Request, per_minute: int = 6) -> None:
    """Small per-IP limit on the routes that cost money."""
    ip = request.client.host if request.client else "?"
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < 60] + [now]
    if len(_hits[ip]) > per_minute:
        raise HTTPException(429, "Too many requests; try again in a minute.")


def _pid(act: str, number: str) -> str:
    code = ACTS.get(act.lower())
    if not code:
        raise HTTPException(404, f"Unknown code {act}")
    return f"{code}:{number.upper()}"


@app.get("/v1/meta")
def meta() -> dict[str, Any]:
    """Counted once per process: they change only when the corpus is rebuilt, and every page asks."""
    if "meta" not in _state:
        c = con()
        _state["meta"] = {
            "provisions": dict(c.execute("SELECT act, count(*) FROM provisions GROUP BY act").fetchall()),
            "mapping_pairs": c.execute("SELECT count(*) FROM section_map").fetchone()[0],
            "judgments": c.execute("SELECT count(*) FROM judgments").fetchone()[0],
            "relations": dict(c.execute("SELECT relation, count(*) FROM section_map GROUP BY relation").fetchall()),
            "passages": c.execute("SELECT count(*) FROM judgment_chunks").fetchone()[0],
            "references": c.execute("SELECT count(*) FROM citations WHERE resolved = 1").fetchone()[0],
        }
    return {**_state["meta"], "retrievers": list(pipeline().ix.available) if "pipeline" in _state else None}


@app.get("/v1/search")
def search(q: str, limit_: int = 8) -> dict[str, list[dict[str, Any]]]:
    """The ⌘K finder: sections by number (either code) or heading, each with its counterpart, and
    judgments by case name or report citation. Database lookups only, so it answers as you type."""
    q = q.strip()[:120]
    refs = [c.provision_id for c in extract(q, query=True)]
    if not refs and (m := re.fullmatch(r"(\d{1,3}[A-Za-z]{0,3})", q)):
        # a bare number usually means the familiar old section (302 is murder), then the new one
        refs = [f"{a}:{m.group(1).upper()}" for a in ("IPC", "BNS", "CRPC", "BNSS", "IEA", "BSA")]
    c = con()
    rows = [c.execute("SELECT id, heading FROM provisions WHERE id=?", (r,)).fetchone() for r in refs]
    found = [r for r in rows if r]
    if len(found) < limit_ and len(q) >= 3 and re.search(r"[A-Za-z]{3}", q):  # headings match words, not numbers
        found += c.execute(
            "SELECT id, heading FROM provisions WHERE heading LIKE ? "
            "ORDER BY act IN ('BNS','BNSS','BSA') DESC, sort_key LIMIT ?",
            (f"%{q}%", limit_),
        ).fetchall()
    sections = [
        {"id": pid, "heading": heading, "other": [x["id"] for x in counterparts(pid) if x["id"]][:3]}
        for pid, heading in dict(found).items()
    ][:limit_]
    judgments = []
    if len(q) >= 3 and not refs:
        judgments = [
            {"id": r[0], "title": r[1], "year": r[2][:4], "citation": r[3]}
            for r in c.execute(
                "SELECT id, title, decided_on, citation FROM judgments WHERE title LIKE ? OR citation LIKE ? "
                "ORDER BY decided_on DESC LIMIT 4",
                (f"%{q}%", f"%{q}%"),
            )
        ]
    return {"sections": sections, "judgments": judgments}


@app.get("/v1/provisions/{act}/{number}")
def provision(act: str, number: str) -> dict[str, Any]:
    pid = _pid(act, number)
    c = con()
    row = c.execute("SELECT * FROM provisions WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, f"{pid} not found")
    out = dict(row)
    out["act_title"], out["in_force_from"], out["in_force_to"] = c.execute(
        "SELECT title, in_force_from, in_force_to FROM acts WHERE code=?", (row["act"],)
    ).fetchone()
    out["parts"] = [
        dict(r)
        for r in c.execute(
            "SELECT id, kind, label, text, status, added, changed, deleted FROM provision_parts WHERE provision_id=? "
            "ORDER BY ord",
            (pid,),
        )
    ]
    out["classification"] = [
        dict(r)
        for r in c.execute(
            "SELECT sub, offence, punishment, cognizable, bailable, triable_by FROM offence_classification "
            "WHERE provision_id=?",
            (pid,),
        )
    ]
    out["official"] = official(pid)
    out["counterparts"] = counterparts(pid)
    out["precedent"] = precedent([pid] + [x["id"] for x in out["counterparts"] if x["id"]])
    out["neighbours"] = [
        dict(r)
        for r in c.execute(
            "SELECT id, number, heading FROM provisions WHERE act=? AND chapter_no=? AND abs(sort_key - ?) <= 300000 "
            "AND id != ? ORDER BY sort_key",
            (row["act"], row["chapter_no"], row["sort_key"], pid),
        )
    ]
    return out


def counterparts(pid: str) -> list[dict[str, Any]]:
    rows = (
        con()
        .execute(
            """SELECT CASE WHEN m.new_id = ? THEN m.old_id ELSE m.new_id END AS other, m.relation, m.changed, m.note,
                  m.similarity, m.tags, m.in_reverse, p.heading
           FROM section_map m LEFT JOIN provisions p ON p.id = CASE WHEN m.new_id = ? THEN m.old_id ELSE m.new_id END
           WHERE m.new_id = ? OR m.old_id = ?""",
            (pid, pid, pid, pid),
        )
        .fetchall()
    )
    return [
        {
            "id": r[0],
            "relation": r[1],
            "changed": bool(r[2]),
            "note": r[3],
            "similarity": r[4],
            "tags": json.loads(r[5] or "[]"),
            "in_reverse_table": bool(r[6]),
            "heading": r[7],
        }
        for r in rows
    ]


def precedent(pids: list[str], n: int = 12) -> list[dict[str, Any]]:
    """Judgments citing the provision or its counterparts: most-cited-for-this first, newer first on ties."""
    ph = ",".join("?" * len(pids))
    rows = (
        con()
        .execute(
            f"""SELECT j.id, j.title, j.decided_on, j.citation, count(*) AS n, group_concat(DISTINCT c.provision_id)
            FROM citations c JOIN judgments j ON j.id = c.judgment_id
            WHERE c.provision_id IN ({ph})
            GROUP BY j.id ORDER BY n DESC, j.decided_on DESC LIMIT ?""",
            (*pids, n),
        )
        .fetchall()
    )
    return [
        {"id": r[0], "title": r[1], "decided_on": r[2], "citation": r[3], "mentions": r[4], "via": r[5].split(",")}
        for r in rows
    ]


@app.get("/v1/compare/{act}/{number}")
def compare(act: str, number: str) -> dict[str, Any]:
    pid = _pid(act, number)
    sides = [pid] + [x["id"] for x in counterparts(pid) if x["id"]]
    texts = {
        r[0]: {"heading": r[1], "text": r[2]}
        for r in con().execute(
            f"SELECT id, heading, text FROM provisions WHERE id IN ({','.join('?' * len(sides))})", sides
        )
    }
    return {"id": pid, "counterparts": counterparts(pid), "texts": texts}


class Draft(BaseModel):
    text: str = Field(max_length=50_000)
    offence_date: date | None = None
    proceeding_date: date | None = None  # FIR or complaint; procedure and evidence turn on this


@app.post("/v1/check")
def check(body: Draft) -> list[dict[str, Any]]:
    return checker.check(con(), body.text, body.offence_date, body.proceeding_date)


class Turn(BaseModel):
    q: str = Field(max_length=2000)
    a: str = Field(max_length=4000)


class Ask(BaseModel):
    # lengths are capped because each request is a paid model call
    query: str = Field(min_length=2, max_length=1000)
    as_of: date | None = None
    history: list[Turn] = Field(default=[], max_length=10)


@app.post("/v1/research")
async def research(body: Ask, request: Request) -> EventSourceResponse:
    limit(request)
    within_budget()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def work() -> None:
        def emit(e: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"event": "trace", "data": e})

        trace = Trace(on_event=emit)
        try:
            history = [t.model_dump() for t in body.history[-2:]]
            result = pipeline().run(body.query, body.as_of, trace, history)
            result.pop("trace", None)
            for passage in result.get("context", []):
                passage.update(describe(passage))
            loop.call_soon_threadsafe(queue.put_nowait, {"event": "answer", "data": result})
        except Exception:  # surface failures to the UI instead of a hung stream; details go to the log
            log.exception("research failed for %r", body.query)
            message = "Something went wrong while researching. Please try again."
            loop.call_soon_threadsafe(queue.put_nowait, {"event": "error", "data": {"message": message}})
        loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=work, daemon=True).start()

    async def events() -> AsyncIterator[dict[str, str]]:
        while (item := await queue.get()) is not None:
            yield {"event": item["event"], "data": json.dumps(item["data"], default=str)}

    return EventSourceResponse(events())


def official(pid: str) -> str:
    """Where to check a section's text: its NCRB Sankalan page for the new codes, the page of the
    official India Code PDF for the old ones."""
    row = con().execute("SELECT act, source_url, source_page FROM provisions WHERE id=?", (pid,)).fetchone()
    if not row:
        return ""
    act, url, page = row
    return url or (f"{INDIA_CODE_PDF[act]}#page={page}" if act in INDIA_CODE_PDF and page else "")


def original(jid: str) -> str:
    """The judgment's PDF as the Supreme Court published it (via the open dataset's bucket)."""
    row = con().execute("SELECT decided_on, source_path FROM judgments WHERE id=?", (jid,)).fetchone()
    return sc_pdf_url(row[0][:4], row[1].removesuffix("_EN.pdf")) if row and row[1] else ""


def describe(passage: dict[str, Any]) -> dict[str, Any]:
    """What the UI shows about a source beyond its text: the section's status and counterparts,
    or the judgment's report details and the provisions it turns on, under both codes."""
    c = con()
    if passage["id"].startswith("S"):
        heading, status = c.execute("SELECT heading, status FROM provisions WHERE id=?", (passage["ref"],)).fetchone()
        others = [{"id": x["id"], "relation": x["relation"]} for x in counterparts(passage["ref"]) if x["id"]]
        return {
            "kind": "statute",
            "heading": heading,
            "status": status,
            "counterparts": others,
            "official": official(passage["ref"]),
            "classified": checker.classification(c, passage["ref"]),
        }
    title, decided, citation, court = c.execute(
        "SELECT title, decided_on, citation, court FROM judgments WHERE id=?", (passage["ref"],)
    ).fetchone()
    role = c.execute("SELECT role FROM judgment_chunks WHERE id=?", (passage["unit"],)).fetchone()
    return {
        "kind": "judgment",
        "case": title,
        "decided_on": decided,
        "citation": citation,
        "court": court,
        "role": role[0] if role else "judgment",
        "cites": cited_by(passage["ref"], 5),
        "original": original(passage["ref"]),
        "bench": library.bench(c, passage["ref"]),
    }


def cited_by(jid: str, n: int) -> list[dict[str, Any]]:
    """The provisions a judgment cites most, each with its counterpart in the other code."""
    rows = con().execute(
        "SELECT provision_id, count(*) AS k FROM citations WHERE judgment_id=? AND resolved=1 "
        "GROUP BY provision_id ORDER BY k DESC LIMIT ?",
        (jid, n),
    )
    return [
        {"id": pid, "mentions": k, "counterparts": [x["id"] for x in counterparts(pid) if x["id"]]} for pid, k in rows
    ]


@app.get("/v1/judgments")
def judgments(
    q: str = "", after: str = "", before: str = "", sort: str = "relevance", offset: int = 0
) -> dict[str, Any]:
    return library.search(pipeline().ix, con(), q[:300], after, before, sort, max(0, min(offset, 2000)))


@app.get("/v1/judgments/{jid}")
def judgment(jid: str) -> dict[str, Any]:
    c = con()
    row = c.execute(
        "SELECT id, title, decided_on, citation, court, licence FROM judgments WHERE id=?", (jid,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"{jid} not found")
    out = dict(row)
    out["original"] = original(jid)
    out["passages"] = library.passages(c, jid)
    now: dict[str, list[str]] = {}
    for p in out["passages"]:
        refs = c.execute(
            "SELECT DISTINCT raw, provision_id FROM citations WHERE chunk_id=? AND resolved=1", (p["id"],)
        ).fetchall()
        for _, pid in refs:
            if pid not in now:
                now[pid] = [x["id"] for x in counterparts(pid) if x["id"]]
        # the exact words the extractor matched, so the page can mark them where they stand
        p["refs"] = [{"raw": raw, "id": pid, "other": now[pid]} for raw, pid in refs]
    out["cites"] = cited_by(jid, 30)
    out["related"] = library.related(pipeline().ix, c, jid)
    return out


@app.get("/v1/judgments/{jid}/brief")
def judgment_brief(jid: str, request: Request) -> dict[str, Any]:
    if not con().execute("SELECT 1 FROM briefs WHERE judgment_id=?", (jid,)).fetchone():
        limit(request)  # only a new brief costs a model call
        within_budget()
    return library.brief(con(), jid)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@app.post("/v1/judgments/{jid}/ask")
def judgment_ask(jid: str, body: Question, request: Request) -> dict[str, Any]:
    limit(request)
    within_budget()
    return library.ask(pipeline().ix, con(), jid, body.question)


@app.get("/v1/results")
def results() -> dict[str, Any]:
    """The ablation table (eval/results/test.json), for the /method page."""
    path = settings.processed_dir.parent.parent / "eval" / "results" / "test.json"
    return json.loads(path.read_text()) if path.exists() else {}
