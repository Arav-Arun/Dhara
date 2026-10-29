"""DharaBench: queries with known answers, mined from our own corpus.

Three query types:
- `precedent` (the headline): the question a lawyer would type today, using NEW-code numbers,
  whose answer is a judgment that cites only the OLD codes. Written by the LLM from the judgment's
  headnote and its mapped citations. The source judgment's headnote chunks are excluded from
  retrieval for that query, so a paraphrase of the headnote can't be matched against itself.
  A reverse slice does the opposite: old numbers in the query, a judgment citing the new codes.
- `statute`: a plain-language question answered by one new-code provision (old counterpart = partial credit).
- `abstain`: out-of-scope questions (civil, tax, corporate…) that the system should decline.

Every judgment and provision is assigned to train / dev / test by a hash, so reranker training
pairs (train) never share a judgment or provision with the benchmark (dev, test).
"""

import hashlib
import json
import random
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from dhara import db, llm
from dhara.config import ROOT

OUT = ROOT / "eval" / "dharabench"


def split_of(key: str) -> str:
    h = int(hashlib.sha1(key.encode()).hexdigest(), 16) % 10
    return "test" if h == 0 else "dev" if h == 1 else "train"


PRECEDENT_SYS = (
    "You write realistic search queries for an Indian criminal-law research tool used by lawyers in 2026. "
    "Given a Supreme Court judgment's headnote and the provisions it applies, write ONE question that this "
    "judgment answers well. Refer to provisions ONLY by the numbers given to you, in the form given "
    "(e.g. 'BNS 103', 'Section 482 BNSS'). Describe the legal issue in your own words: do not copy any run of "
    "more than four words from the headnote, do not mention party names, years or the court's conclusion. "
    "At most 35 words. Vary the style: some terse keyword queries, some full questions."
)
STATUTE_SYS = (
    "You write realistic questions an Indian lawyer or law student would ask. Given one provision, write ONE "
    "question it answers. Do not mention the section number or the Act's name, and do not copy phrases of more "
    "than four words. At most 30 words."
)
ABSTAIN_SYS = (
    "Write realistic legal questions an Indian user might ask that are NOT about criminal law (civil, family "
    "property, tax, corporate, consumer, labour, constitutional service matters). One question per item, "
    "at most 25 words each."
)
Q_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}


def _new_ids(con: sqlite3.Connection, old_id: str) -> list[str]:
    return [
        r[0] for r in con.execute("SELECT new_id FROM section_map WHERE old_id=? AND new_id IS NOT NULL", (old_id,))
    ]


def _label(pid: str) -> str:
    act, num = pid.split(":")
    return f"{act.replace('CRPC', 'CrPC')} {num}"


def _copies_headnote(query: str, head: str, n: int = 5) -> bool:
    words = re.findall(r"\w+", head.lower())
    grams = {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}
    q = re.findall(r"\w+", query.lower())
    return any(" ".join(q[i : i + n]) in grams for i in range(len(q) - n + 1))


def precedent_queries(
    con: sqlite3.Connection,
    split: str,
    n: int,
    reverse: bool = False,
    seed: int = 7,
    skip: set[str] | None = None,
    sink: Path | None = None,
) -> list[dict[str, Any]]:
    """Old-code judgment, new-code query (or the reverse slice with `reverse=True`)."""
    rng = random.Random(seed + (1 if reverse else 0))
    acts = ("BNS", "BNSS", "BSA") if reverse else ("IPC", "CRPC", "IEA")
    cand = defaultdict(set)
    for jid, pid in con.execute(
        f"""SELECT DISTINCT c.judgment_id, c.provision_id FROM citations c JOIN judgments j ON j.id=c.judgment_id
            WHERE j.sensitive=0 AND c.resolved=1 AND c.act IN ({",".join("?" * len(acts))})""",
        acts,
    ):
        cand[jid].add(pid)
    jids = sorted(j for j in cand if split_of(j) == split)
    rng.shuffle(jids)
    out: list[dict[str, Any]] = []
    prefix = "PR-" if reverse else "P-"
    for jid in jids:
        if len(out) >= n:
            break
        if skip and f"{prefix}{jid}" in skip:
            continue
        head = " ".join(
            r[0]
            for r in con.execute(
                "SELECT text FROM judgment_chunks WHERE judgment_id=? AND role='headnote' ORDER BY ord",
                (jid,),
            )
        )
        if len(head.split()) < 60:
            continue
        cited = sorted(cand[jid])[:6]
        if reverse:
            shown = sorted(
                {
                    o
                    for p in cited
                    for (o,) in con.execute(
                        "SELECT old_id FROM section_map WHERE new_id=? AND old_id IS NOT NULL", (p,)
                    )
                }
            )
        else:
            shown = sorted({n_ for p in cited for n_ in _new_ids(con, p)})
        if not shown:
            continue
        user = f"Headnote:\n{' '.join(head.split()[:260])}\n\nProvisions (use these numbers only): " + ", ".join(
            _label(p) for p in shown
        )
        q = llm.json_call(PRECEDENT_SYS, user, Q_SCHEMA, f"bench:precedent:{split}").get("query", "").strip()
        if not q:
            continue
        if _copies_headnote(q, head) or (not reverse and re.search(r"\b(IPC|CrPC|Cr\.P\.C|Evidence Act)\b", q)):
            continue
        exclude = [
            r[0] for r in con.execute("SELECT id FROM judgment_chunks WHERE judgment_id=? AND role='headnote'", (jid,))
        ]
        out.append(
            {
                "id": f"P{'R' if reverse else ''}-{jid}",
                "type": "precedent_reverse" if reverse else "precedent",
                "split": split,
                "query": q,
                "relevant_judgments": [jid],
                "provisions_in_query": shown,
                "cited_by_judgment": cited,
                "exclude_units": exclude,
            }
        )
        if sink:
            _append(sink, out[-1:])
    return out


def statute_queries(
    con: sqlite3.Connection, split: str, n: int, seed: int = 11, skip: set[str] | None = None, sink: Path | None = None
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows = [
        r
        for r in con.execute(
            "SELECT id, heading, text FROM provisions WHERE act IN ('BNS','BNSS','BSA') AND length(text) > 200"
        )
        if split_of(r[0]) == split
    ]
    rng.shuffle(rows)
    out: list[dict[str, Any]] = []
    for pid, heading, text in rows:
        if len(out) >= n:
            break
        if skip and f"S-{pid}" in skip:
            continue
        q = llm.json_call(STATUTE_SYS, f"{heading}\n{text[:1800]}", Q_SCHEMA, f"bench:statute:{split}").get("query", "")
        if not q:
            continue
        old = [
            r[0] for r in con.execute("SELECT old_id FROM section_map WHERE new_id=? AND old_id IS NOT NULL", (pid,))
        ]
        out.append(
            {
                "id": f"S-{pid}",
                "type": "statute",
                "split": split,
                "query": q.strip(),
                "relevant_provisions": {pid: 2, **{o: 1 for o in old}},
            }
        )
        if sink:
            _append(sink, out[-1:])
    return out


def abstain_queries(n: int = 40) -> list[dict[str, Any]]:
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"type": "string"}}},
        "required": ["items"],
        "additionalProperties": False,
    }
    items = llm.json_call(ABSTAIN_SYS, f"Write {n} questions.", schema, "bench:abstain", max_tokens=3000).get(
        "items", []
    )
    return [
        {"id": f"A-{i:03d}", "type": "abstain", "split": "test" if i % 2 else "dev", "query": q.strip()}
        for i, q in enumerate(items[:n])
    ]


def build(n_precedent: int = 150, n_reverse: int = 30, n_statute: int = 100) -> dict[str, int]:
    """Writes dev.jsonl and test.jsonl. Each query is appended as soon as it exists, so a stopped
    run resumes where it left off instead of paying for the same LLM calls again."""
    con = db.connect()
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split in ("dev", "test"):
        path = OUT / f"{split}.jsonl"
        have = load(split) if path.exists() else []
        kinds = {
            t: sum(1 for x in have if x["type"] == t) for t in ("precedent", "precedent_reverse", "statute", "abstain")
        }
        seen = {x["id"] for x in have}
        if kinds["precedent"] < n_precedent:
            precedent_queries(con, split, n_precedent - kinds["precedent"], skip=seen, sink=path)
        if kinds["precedent_reverse"] < n_reverse:
            precedent_queries(con, split, n_reverse - kinds["precedent_reverse"], reverse=True, skip=seen, sink=path)
        if kinds["statute"] < n_statute:
            statute_queries(con, split, n_statute - kinds["statute"], skip=seen, sink=path)
        if kinds["abstain"] == 0:
            _append(path, [a for a in abstain_queries() if a["split"] == split])
        counts[split] = len(load(split))
    return counts


def _append(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("a") as f:
        for x in items:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


def load(split: str) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (OUT / f"{split}.jsonl").read_text().splitlines()]
