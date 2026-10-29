"""Build the statute tables and check them against the official PDFs.

Six codes, their citable parts, lifecycle (in-force dates) and the BNSS First Schedule.
"""

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pymupdf

from dhara import db, statutes_ncrb, statutes_pdf
from dhara.config import settings
from dhara.models import Act, Section

NCRB = "https://www.ncrb.gov.in/uploads/SankalanPortal/"
CUTOVER, LAST_OLD_DAY = date(2024, 7, 1), date(2024, 6, 30)

ACTS = [
    Act(
        code="BNS",
        title="Bharatiya Nyaya Sanhita, 2023",
        act_no="45 of 2023",
        in_force_from=CUTOVER,
        source="Gazette S.O. 850(E); NCRB Sankalan",
    ),
    Act(
        code="BNSS",
        title="Bharatiya Nagarik Suraksha Sanhita, 2023",
        act_no="46 of 2023",
        in_force_from=CUTOVER,
        source="Gazette S.O. 848(E); NCRB Sankalan",
    ),
    Act(
        code="BSA",
        title="Bharatiya Sakshya Adhiniyam, 2023",
        act_no="47 of 2023",
        in_force_from=CUTOVER,
        source="Gazette S.O. 849(E); NCRB Sankalan",
    ),
    Act(
        code="IPC",
        title="Indian Penal Code, 1860",
        act_no="45 of 1860",
        in_force_from=date(1862, 1, 1),
        in_force_to=LAST_OLD_DAY,
        replaced_by="BNS",
        source="India Code 123456789/488475",
    ),
    Act(
        code="CRPC",
        title="Code of Criminal Procedure, 1973",
        act_no="2 of 1974",
        in_force_from=date(1974, 4, 1),
        in_force_to=LAST_OLD_DAY,
        replaced_by="BNSS",
        source="India Code 123456789/549163",
    ),
    Act(
        code="IEA",
        title="Indian Evidence Act, 1872",
        act_no="1 of 1872",
        in_force_from=date(1872, 9, 1),
        in_force_to=LAST_OLD_DAY,
        replaced_by="BSA",
        source="India Code 123456789/488783",
    ),
]

NOT_COMMENCED = re.compile(r"Section (\d+[A-Z]?)\((\w+)\) of BNS shall not come into force")


def sort_key(number: str) -> int:
    m = re.match(r"(\d+)([A-Z]*)", number)
    assert m, number
    suffix = sum((ord(c) - 64) * 27 ** (2 - i) for i, c in enumerate(m.group(2)[:3]))
    return int(m.group(1)) * 100_000 + suffix


def load_sections() -> dict[str, list[Section]]:
    raw = settings.raw_dir
    out = {
        code: statutes_ncrb.parse(raw / "ncrb_sankalan" / f"Chapters{code}.html", code)
        for code in ("BNS", "BNSS", "BSA")
    }
    for code in ("IPC", "CRPC", "IEA"):
        out[code] = statutes_pdf.parse(raw / "indiacode" / f"{code}.pdf", code)
    return out


def _part_id(sec: Section, label: str, i: int) -> str:
    if label.startswith("("):
        return f"{sec.id}{label}"
    return f"{sec.id}:{label or 'body'}" + (f":{i}" if not label else "")


def write(con: sqlite3.Connection, sections: dict[str, list[Section]]) -> None:
    con.executescript(
        "DELETE FROM provision_parts; DELETE FROM provisions; DELETE FROM acts;DELETE FROM offence_classification;"
    )
    for a in ACTS:
        con.execute(
            "INSERT INTO acts VALUES (?,?,?,?,?,?,?)",
            (
                a.code,
                a.title,
                a.act_no,
                a.in_force_from.isoformat(),
                a.in_force_to.isoformat() if a.in_force_to else None,
                a.replaced_by,
                a.source,
            ),
        )
    for code, secs in sections.items():
        for sec in secs:
            for note in sec.notes:  # e.g. BNS 106(2) was never brought into force
                if m := NOT_COMMENCED.search(note):
                    for p in sec.parts:
                        if p.label == f"({m.group(2)})":
                            p.status = "not_commenced"
            url = f"{NCRB}Chapters{code}.html#{sec.number}" if code in ("BNS", "BNSS", "BSA") else None
            con.execute(
                "INSERT INTO provisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sec.id,
                    code,
                    sec.number,
                    sort_key(sec.number),
                    sec.heading,
                    sec.chapter_no,
                    sec.chapter_title,
                    sec.subheading,
                    sec.text,
                    sec.status,
                    sec.flag,
                    json.dumps(sec.notes),
                    url,
                    sec.source_page,
                ),
            )
            seen: set[str] = set()
            for i, p in enumerate(sec.parts):
                pid = _part_id(sec, p.label, i)
                while pid in seen:  # repeated labels, e.g. several provisos
                    pid += "'"
                seen.add(pid)
                con.execute(
                    "INSERT INTO provision_parts VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        pid,
                        sec.id,
                        i,
                        p.kind,
                        p.label,
                        p.text,
                        p.status,
                        json.dumps(p.changes.added),
                        json.dumps(p.changes.changed),
                        json.dumps(p.changes.deleted),
                    ),
                )
    for c in statutes_ncrb.parse_schedule(settings.raw_dir / "ncrb_sankalan" / "ScheduleBNSS.html"):
        if c.part == "I":
            con.execute(
                "INSERT INTO offence_classification VALUES (?,?,?,?,?,?,?)",
                (f"BNS:{c.section}", c.sub, c.offence, c.punishment, c.cognizable, c.bailable, c.triable_by),
            )
    con.commit()


def build() -> dict[str, int]:
    sections = load_sections()
    con = db.connect()
    write(con, sections)
    counts = {code: len(s) for code, s in sections.items()}
    counts["parts"] = con.execute("SELECT count(*) FROM provision_parts").fetchone()[0]
    counts["classification_rows"] = con.execute("SELECT count(*) FROM offence_classification").fetchone()[0]
    return counts


# Check parsed statute text against the official PDFs.
#
# For every section we take the first ~80 characters of its parsed text and look for them
# in the official PDF (the Gazette copy for BNS/BNSS/BSA, India Code for the old codes).
# Comparison ignores case, spacing and punctuation. A miss means the parser mangled the
# start of a section, or the HTML and the Gazette text differ.
SOURCES = {
    "BNS": "ncrb_sankalan/DownloadPDF__BNS2023.pdf",
    "BNSS": "ncrb_sankalan/DownloadPDF__BNSS2023.pdf",
    "BSA": "ncrb_sankalan/DownloadPDF__BSA2023.pdf",
    "IPC": "indiacode/IPC.pdf",
    "CRPC": "indiacode/CRPC.pdf",
    "IEA": "indiacode/IEA.pdf",
}


def _norm(s: str) -> str:
    s = re.sub(r"\d+\[|\*", "", s)  # India Code footnote markers "1[" and omission stars
    return re.sub(r"[^a-z0-9]", "", s.lower())


def check(con: sqlite3.Connection, probe: int = 80) -> dict[str, tuple[int, int, list[str]]]:
    out = {}
    for act, rel in SOURCES.items():
        doc = pymupdf.open(Path(settings.raw_dir) / rel)
        pdf = _norm("".join(doc[i].get_text() for i in range(len(doc))))
        rows = con.execute("SELECT id, text FROM provisions WHERE act=? AND status='in_force'", (act,)).fetchall()
        misses = [pid for pid, text in rows if _norm(text)[:probe] not in pdf]
        out[act] = (len(rows) - len(misses), len(rows), misses)
    return out
