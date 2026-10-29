"""Official old <-> new mapping.

Parse NCRB's correspondence tables, type each relation, and summarise what changed.
"""

import difflib
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from dhara import db
from dhara.config import settings
from dhara.mapping_tables import Row, parse_tables

# Summarise what changed between an old section and its new counterpart.
#
# Computed once at build time from the two texts (never generated live):
# - `similarity`: word-level similarity, 0..1 (difflib ratio on normalised tokens)
# - `tags`: coarse, explainable labels derived from the word diff
#
#     identical       same text apart from numbering and cross-references
#     punishment      words about imprisonment, fines or death were added or removed
#     gender_neutral  "he"/"man"/"woman" replaced by gender-neutral wording, or "child"/"person" added
#     expanded        new text is substantially longer (>25%)
#     narrowed        new text is substantially shorter (>25%)
#     electronic      electronic/digital wording was added
PUNISHMENT = {
    "imprisonment",
    "fine",
    "death",
    "years",
    "months",
    "rupees",
    "life",
    "rigorous",
    "simple",
    "community",
    "service",
    "punished",
    "punishable",
}
GENDER = {"he", "him", "his", "man", "woman", "she", "her", "child", "person", "transgender"}
ELECTRONIC = {"electronic", "digital", "audio-video", "email", "e-mail", "device", "online", "communication"}


def _tokens(text: str) -> list[str]:
    text = re.sub(r"\b(?:section|sections|sub-section|clause)\s+[\d()A-Za-z,\s]+?(?=\s[a-z]{3,}|\.|,|;|$)", " ", text)
    return re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())


def summarise(old: str, new: str) -> tuple[float, list[str]]:
    a, b = _tokens(old), _tokens(new)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    added: list[str] = []
    removed: list[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("replace", "delete"):
            removed += a[i1:i2]
        if op in ("replace", "insert"):
            added += b[j1:j2]
    sim = round(sm.ratio(), 3)
    tags: list[str] = []
    if sim >= 0.98:
        tags.append("identical")
    if PUNISHMENT & (set(added) | set(removed)):
        tags.append("punishment")
    if (GENDER & set(removed)) and (GENDER & set(added)):
        tags.append("gender_neutral")
    if a and len(b) > 1.25 * len(a):
        tags.append("expanded")
    if a and len(b) < 0.75 * len(a):
        tags.append("narrowed")
    if ELECTRONIC & set(added):
        tags.append("electronic")
    return sim, tags


# Turn NCRB correspondence rows into typed old <-> new relations.
#
# Two tables are written:
# - `mapping_rows`: every edge as NCRB states it, at sub-section level, with the raw cells.
# - `section_map`: one row per (new section, old section) pair with a relation type:
#
#     equivalent  one old section <-> one new section
#     merged      several old sections became this one new section
#     split       this old section was spread across several new sections
#     partial     many-to-many (pieces moved in both directions)
#     new         new section with no old counterpart       (old_id is NULL)
#     omitted     old section dropped from the new code      (new_id is NULL)
#
# The mapping is data, not something a model guesses. The reverse table NCRB
# publishes alongside each forward table is used as an independent consistency check.
PAIRS = {"BNS": "IPC", "BNSS": "CRPC", "BSA": "IEA"}

# Old sections NCRB's table leaves out. The public GSMS-B dataset maps them by hand; we
# adopt those links with a note so the provenance stays visible.
SUPPLEMENT = {
    "BNS": [
        ("BNS:189", "IPC:142"),
        ("BNS:178", "IPC:232"),
        ("BNS:178", "IPC:247"),
        ("BNS:178", "IPC:249"),
        ("BNS:5", "IPC:55A"),
    ],
}
SUPPLEMENT_NOTE = "not in NCRB table; adopted from the GSMS-B public mapping dataset"

SCHEMA = """
DROP TABLE IF EXISTS mapping_rows;
DROP TABLE IF EXISTS section_map;
CREATE TABLE mapping_rows (
    new_id TEXT, new_sub TEXT, old_id TEXT, old_sub TEXT,
    status TEXT,            -- '', 'new', 'deleted'
    changed INTEGER, note TEXT, raw_new TEXT, raw_old TEXT, row_order INTEGER
);
CREATE TABLE section_map (
    new_id TEXT, old_id TEXT, relation TEXT, changed INTEGER, note TEXT,
    n_rows INTEGER, in_reverse INTEGER,
    similarity REAL, tags TEXT         -- from changes.summarise (equivalent pairs only)
);
CREATE INDEX ix_map_new ON section_map(new_id);
CREATE INDEX ix_map_old ON section_map(old_id);
"""


def _edges(rows: list[Row], new_act: str, old_act: str) -> list[tuple[str | None, str, str | None, str, Row]]:
    out: list[tuple[str | None, str, str | None, str, Row]] = []
    for r in rows:
        if r.left_status == "deleted":
            out += [(None, "", f"{old_act}:{o.section}", o.sub, r) for o in r.right]
        elif r.right_status == "new":
            out += [(f"{new_act}:{n.section}", n.sub, None, "", r) for n in r.left]
        else:
            out += [
                (f"{new_act}:{n.section}", n.sub, f"{old_act}:{o.section}", o.sub, r) for n in r.left for o in r.right
            ]
    return out


def classify(pairs: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    n2o: dict[str, set[str]] = defaultdict(set)
    o2n: dict[str, set[str]] = defaultdict(set)
    for n, o in pairs:
        n2o[n].add(o)
        o2n[o].add(n)
    rel = {}
    for n, o in pairs:
        many_old, many_new = len(n2o[n]) > 1, len(o2n[o]) > 1
        rel[(n, o)] = (
            "partial" if many_old and many_new else "merged" if many_old else "split" if many_new else "equivalent"
        )
    return rel


def build_pair(con: sqlite3.Connection, new_act: str, old_act: str, path: Path) -> dict[str, object]:
    forward, reverse = parse_tables(path)
    edges = _edges(forward, new_act, old_act)
    for n, ns, o, os_, r in edges:
        status = "deleted" if n is None else "new" if o is None else ""
        con.execute(
            "INSERT INTO mapping_rows VALUES (?,?,?,?,?,?,?,?,?,?)",
            (n, ns, o, os_, status, int(r.changed), r.note, r.raw[0], r.raw[1], r.order),
        )

    # reverse table: left = old code, right = new code
    rev_pairs = {(f"{new_act}:{n.section}", f"{old_act}:{o.section}") for r in reverse for o in r.left for n in r.right}

    for n, o in SUPPLEMENT.get(new_act, []):
        edges.append((n, "", o, "", Row([], [], note=SUPPLEMENT_NOTE)))
    mapped = {(n, o) for n, _, o, _, _ in edges if n and o}
    relations = classify(mapped)
    agg: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for n, _, o, _, r in edges:
        if n and o:
            agg[(n, o)].append(r)
    text = dict(con.execute("SELECT id, text FROM provisions WHERE act IN (?,?)", (new_act, old_act)).fetchall())
    for (n, o), rows in agg.items():
        notes = "; ".join(sorted({r.note for r in rows if r.note}))
        sim: float | None = None
        tags: list[str] = []
        if relations[(n, o)] == "equivalent" and n in text and o in text:
            sim, tags = summarise(text[o], text[n])
            if new_act != "BNS":  # "punishment" is only meaningful for the penal code
                tags = [t for t in tags if t != "punishment"]
        con.execute(
            "INSERT INTO section_map VALUES (?,?,?,?,?,?,?,?,?)",
            (
                n,
                o,
                relations[(n, o)],
                int(any(r.changed for r in rows)),
                notes,
                len(rows),
                int((n, o) in rev_pairs),
                sim,
                json.dumps(tags),
            ),
        )

    has_old = {n for n, o in mapped}
    for n in sorted({n for n, _, o, _, _ in edges if n and o is None} - has_old):
        con.execute("INSERT INTO section_map VALUES (?,NULL,'new',1,'',1,1,NULL,'[]')", (n,))
    still_mapped = {o for _, o in mapped}
    for o in sorted({o for n, _, o, _, _ in edges if n is None and o} - still_mapped):
        con.execute("INSERT INTO section_map VALUES (NULL,?,'omitted',1,'',1,1,NULL,'[]')", (o,))

    known = {r[0] for r in con.execute("SELECT id FROM provisions WHERE act IN (?,?)", (new_act, old_act))}
    refs = {x for e in edges for x in (e[0], e[2]) if x}
    unresolved = sorted(refs - known)
    in_force_old = {
        r[0] for r in con.execute("SELECT id FROM provisions WHERE act=? AND status='in_force'", (old_act,))
    }
    in_force_new = {r[0] for r in con.execute("SELECT id FROM provisions WHERE act=?", (new_act,))}
    covered_old = {o for _, _, o, _, _ in edges if o}
    covered_new = {n for n, _, _, _, _ in edges if n}
    return {
        "rows": len(forward),
        "pairs": len(mapped),
        "reverse_agreement": round(len(mapped & rev_pairs) / max(1, len(mapped | rev_pairs)), 3),
        "new_coverage": round(len(covered_new & in_force_new) / len(in_force_new), 3),
        "old_coverage": round(len(covered_old & in_force_old) / len(in_force_old), 3),
        "unresolved": unresolved,
        "old_unmapped": sorted(in_force_old - covered_old),
        "new_unmapped": sorted(in_force_new - covered_new),
    }


def build() -> dict[str, dict[str, object]]:
    con = db.connect()
    con.executescript(SCHEMA)
    out = {}
    for new_act, old_act in PAIRS.items():
        out[new_act] = build_pair(
            con, new_act, old_act, settings.raw_dir / "ncrb_sankalan" / f"SectionTable{new_act}.html"
        )
    con.commit()
    return out


# Compare with the public mapping datasets on Hugging Face (both derived from the NCRB tables):
#   GSMS-B/ipc-bns-crpc-bnss-iea-bsa-respective-old-new-sections-mapping (CC-BY-4.0, one target per section)
#   nandhakumarg/IPC_and_BNS_transformation (Apache-2.0, IPC -> BNS prompt/response pairs)
def _sec(value: object) -> str:
    m = re.match(r"\s*(\d{1,3})\s*-?\s*([A-Z]{0,3})", str(value or ""))
    return f"{m.group(1)}{m.group(2)}" if m else ""


def prior_pairs() -> dict[str, dict[str, set[tuple[str, str]]]]:
    """{dataset: {new_act: {(new_id, old_id), ...}}} at section level."""
    import ast
    import csv

    root = settings.raw_dir / "prior_mappings"
    out: dict[str, dict[str, set[tuple[str, str]]]] = {
        "GSMS-B": defaultdict(set),
        "nandhakumarg": defaultdict(set),
    }
    for new_act, old_act in PAIRS.items():
        for name, old_is_source in (
            (f"{old_act.lower()}_to_{new_act.lower()}", True),
            (f"{new_act.lower()}_to_{old_act.lower()}", False),
        ):
            for rec in json.loads((root / "GSMS-B" / f"{name}.json").read_text()):
                if not rec.get("target"):
                    continue
                old, new = (rec["source"], rec["target"]) if old_is_source else (rec["target"], rec["source"])
                if _sec(old["section"]) and _sec(new["section"]):
                    out["GSMS-B"][new_act].add(
                        (f"{new_act}:{_sec(new['section'])}", f"{old_act}:{_sec(old['section'])}")
                    )
    with (root / "nandhakumarg" / "IPC and BNS transformation .csv").open(encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f):
            try:
                r = ast.literal_eval(row["response"])
            except (ValueError, SyntaxError):
                continue
            if _sec(r.get("IPC Section")) and _sec(r.get("BNS Section")):
                out["nandhakumarg"]["BNS"].add((f"BNS:{_sec(r['BNS Section'])}", f"IPC:{_sec(r['IPC Section'])}"))
    return out


def compare_prior() -> list[dict[str, object]]:
    con = db.connect()
    rows = []
    for dataset, by_act in prior_pairs().items():
        for new_act, theirs in by_act.items():
            ours = {
                tuple(r)
                for r in con.execute(
                    "SELECT new_id, old_id FROM section_map WHERE new_id LIKE ? AND old_id IS NOT NULL",
                    (f"{new_act}:%",),
                )
            }
            ours_multi = {p for p in ours if p[0] in {n for n, o in ours if sum(1 for x in ours if x[0] == n) > 1}}
            rows.append(
                {
                    "dataset": dataset,
                    "code": new_act,
                    "theirs": len(theirs),
                    "ours": len(ours),
                    "agree": len(ours & theirs),
                    "jaccard": round(len(ours & theirs) / max(1, len(ours | theirs)), 3),
                    "only_ours": len(ours - theirs),
                    "only_theirs": len(theirs - ours),
                    "only_ours_in_many_to_one": len((ours - theirs) & ours_multi),
                    "examples_only_theirs": sorted(theirs - ours)[:6],
                }
            )
    return rows
