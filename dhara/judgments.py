"""Supreme Court criminal judgments.

Select them from the AWS metadata, download the PDFs, clean and chunk the text, then extract
citations and the places where a court links an old and a new provision ("code bridges").
"""

import asyncio
import re
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb
import httpx
import pymupdf

from dhara import db
from dhara.citations import bridges, extract
from dhara.config import settings

# Pick the criminal judgments we index.
#
# Supreme Court metadata has no case-type column, but `raw_html` holds the case number
# ("CRIMINAL APPEAL No. …") and the SCR headnote ("Code of Criminal Procedure, 1973 – s.239 …").
# A judgment is criminal if either names a criminal matter or statute.
CASE_NO = r"Case No\s*:\s*[^|]{0,80}?(CRIMINAL|CRL)"
HEADNOTE = (
    r"(Penal Code|Code of Criminal Procedure|Cr\.?\s*P\.?\s*C|Evidence Act|Bharatiya Nyaya|"
    r"Bharatiya Nagarik|Bharatiya Sakshya|Narcotic|POCSO|Prevention of Corruption|Negotiable Instruments)"
)


def sc_criminal() -> list[tuple[str, str, str, str, str, str]]:
    """(case_id, year, path, title, decision_date, citation) for criminal SC judgments."""
    con = duckdb.connect()
    src = str(settings.raw_dir / "aws_sc" / "metadata" / "*.parquet")
    con.execute(
        f"""CREATE VIEW m AS SELECT *, regexp_replace(raw_html, '<[^>]+>', ' ', 'g') AS txt
            FROM read_parquet('{src}', union_by_name=true)"""
    )
    return con.execute(
        f"""SELECT case_id, year, path, title, decision_date, citation FROM m
            WHERE (regexp_matches(txt, '{CASE_NO}', 'i') OR regexp_matches(txt, '{HEADNOTE}', 'i'))
              AND path IS NOT NULL
            ORDER BY year, path"""
    ).fetchall()


# Download judgment PDFs from the AWS Open Data buckets (Dattam Labs, CC-BY-4.0).
#
# The buckets are public, so plain HTTPS works without an AWS account. Downloads are
# resumable (existing files are skipped) and run with bounded concurrency.
async def _get(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    async with sem:
        for attempt in range(3):
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    dest.write_bytes(r.content)
                    return True
                if r.status_code == 404:
                    return False
            except httpx.HTTPError:
                await asyncio.sleep(2 * (attempt + 1))
    return False


async def download(items: Iterable[tuple[str, Path]], concurrency: int = 12) -> tuple[int, int]:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": "Dhara research project"}) as c:
        results = await asyncio.gather(*[_get(c, sem, url, dest) for url, dest in items])
    return sum(results), len(results) - sum(results)


# Judgment PDF -> clean text -> headnote + numbered paragraphs -> retrieval chunks.
#
# Supreme Court Reports PDFs have the same skeleton across eras:
#     title, editor's headnote, "CRIMINAL APPELLATE JURISDICTION: …", judgment with numbered paragraphs.
# Older scans add marginal letters (A–H) and running headers, which we strip.
# Chunks are ~1–3 numbered paragraphs (<= ~300 words) so a citation can point at "paras 12–14".
HEADER_PATTERNS = [
    r"^\s*\d{1,4}\s*$",  # page numbers
    r"SUPREME COURT REPORTS",
    r"Supreme Court Reports",
    r"Digital Supreme Court Reports",
    r"^\s*\[\d{4}\]\s*\d+\s*S\.C\.R\.\s*$",
    r"^.{5,80}\sv\.\s.{2,60}\s\d{1,4}\s*$",  # "SHEORAJ SINGH v. STATE OF 1035" (even-page header)
    r"^\s*\d{1,4}\s+.{0,60}\sv\.\s.{2,60}$",
]
HEADER = re.compile("|".join(HEADER_PATTERNS))
JURISDICTION = re.compile(r"\b(?:APPELLATE|ORIGINAL|ADVISORY|REVIEW)?\s*JURISDICTION\s*:", re.I)
PARA = re.compile(r"(?:^|\n)\s*(\d{1,3})\.[ \t]*\n?(?=\s*[A-Z“\"‘(])")
MAX_WORDS = 300


@dataclass
class Chunk:
    ord: int
    role: str  # "headnote" | "judgment"
    para_from: int | None
    para_to: int | None
    text: str


def pdf_text(path: str) -> str:
    doc = pymupdf.open(path)
    pages = [doc[i].get_text() for i in range(len(doc))]
    raw = "\n".join(pages).replace("\x08", "").replace("\xa0", " ")
    lines = raw.split("\n")
    has_margin_letters = sum(bool(re.fullmatch(r"\s*[A-H]\s*", ln)) for ln in lines) >= 10
    kept = []
    for ln in lines:
        if HEADER.search(ln) and len(ln) < 120:
            continue
        if has_margin_letters:
            if re.fullmatch(r"\s*[A-H]\s*", ln):
                continue
            ln = re.sub(r"\s+[A-H]\s*$", "", ln)  # trailing marginal letter
        kept.append(ln)
    text = "\n".join(kept)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    return re.sub(r"[ \t]+", " ", text)


def split(text: str) -> tuple[str, list[tuple[int | None, str]]]:
    """(headnote, [(para_no, para_text), ...])"""
    m = JURISDICTION.search(text)
    head, body = (text[: m.start()], text[m.start() :]) if m else ("", text)
    paras: list[tuple[int | None, str]] = []
    marks = list(PARA.finditer(body))
    if len(marks) < 3:  # unnumbered judgment (common before the 1990s): split on blank-ish lines
        blocks = [b for b in re.split(r"\n\s*\n|(?<=\.)\n(?=[A-Z])", body) if b.strip()]
        return _flat(head), [(None, _flat(b)) for b in blocks]
    if marks[0].start() > 0:
        paras.append((None, _flat(body[: marks[0].start()])))
    expected = 1
    for i, mk in enumerate(marks):
        n = int(mk.group(1))
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        seg = _flat(body[mk.end() : end])
        if n == expected or (paras and n == expected + 1):
            paras.append((n, seg))
            expected = n + 1
        elif paras:  # a number that isn't the next paragraph (e.g. a list item): keep with previous
            p, t = paras[-1]
            paras[-1] = (p, f"{t} {n}. {seg}")
    return _flat(head), paras


def chunk(head: str, paras: list[tuple[int | None, str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for piece in _pieces(head):
        chunks.append(Chunk(len(chunks), "headnote", None, None, piece))
    buf: list[tuple[int | None, str]] = []

    def flush() -> None:
        if buf:
            nums = [p for p, _ in buf if p is not None]
            chunks.append(
                Chunk(
                    len(chunks),
                    "judgment",
                    min(nums, default=None),
                    max(nums, default=None),
                    " ".join(t for _, t in buf),
                )
            )
            buf.clear()

    for p, t in paras:
        words = len(t.split())
        if words > MAX_WORDS:
            flush()
            for piece in _pieces(t):
                chunks.append(Chunk(len(chunks), "judgment", p, p, piece))
            continue
        if sum(len(x.split()) for _, x in buf) + words > MAX_WORDS:
            flush()
        buf.append((p, t))
    flush()
    return [c for c in chunks if len(c.text.split()) >= 12]


def _pieces(text: str) -> list[str]:
    """Split long text at sentence boundaries into <= MAX_WORDS pieces."""
    sentences = re.split(r"(?<=[.;:])\s+(?=[A-Z(“])", text)
    out, cur = [], ""
    for s in sentences:
        if cur and len((cur + " " + s).split()) > MAX_WORDS:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# Build judgments, chunks, citations and code-bridges from the downloaded SC PDFs.
#
# Also marks `sensitive` judgments: those citing sexual-offence provisions, where Indian
# law (BNS s.72, formerly IPC s.228A) restricts disclosing the victim's identity. The
# reports anonymise victims, so they are searchable like any other; the flag is kept so
# the index can place them last and a deployment can filter them if it ever needs to.
SCHEMA = """
DROP TABLE IF EXISTS judgments; DROP TABLE IF EXISTS judgment_chunks;
DROP TABLE IF EXISTS citations; DROP TABLE IF EXISTS bridges;
CREATE TABLE judgments (
    id TEXT PRIMARY KEY, title TEXT, decided_on TEXT, citation TEXT, court TEXT,
    n_chunks INTEGER, sensitive INTEGER, source TEXT, source_path TEXT, licence TEXT
);
CREATE TABLE judgment_chunks (
    id TEXT PRIMARY KEY, judgment_id TEXT, ord INTEGER, role TEXT,
    para_from INTEGER, para_to INTEGER, text TEXT
);
CREATE TABLE citations (
    judgment_id TEXT, chunk_id TEXT, act TEXT, section TEXT, sub TEXT,
    provision_id TEXT, resolved INTEGER, raw TEXT
);
CREATE TABLE bridges (judgment_id TEXT, new_id TEXT, old_id TEXT, snippet TEXT);
CREATE INDEX ix_chunks_j ON judgment_chunks(judgment_id);
CREATE INDEX ix_cit_p ON citations(provision_id);
CREATE INDEX ix_cit_j ON citations(judgment_id);
"""

SENSITIVE = {
    "IPC": re.compile(r"^(354[A-D]?|376[A-Z]*|509|228A)$"),
    "BNS": re.compile(r"^(6[3-9]|7[0-9])$"),
}
SENSITIVE_TEXT = re.compile(r"\b(POCSO|prosecutrix|Protection of Children from Sexual Offences)\b", re.I)
Row = tuple[object, ...]


@dataclass
class Processed:
    judgment: Row
    chunks: list[Row]
    cites: list[Row]
    bridges: list[Row]


LICENCE = "CC-BY-4.0 (Indian Supreme Court Judgments, Dattam Labs, AWS Open Data)"
# OCR slips in the source metadata's case titles (a stray full stop inside a word)
TITLE_FIXES = {
    "DALM.IA": "DALMIA",
    "CENTR.AL": "CENTRAL",
    "RA.IENDRA": "RAJENDRA",
    "MADHYA.PRADESH": "MADHYA PRADESH",
    "UNI.ON": "UNION",
}


def _process(args: tuple[str, str, str, str, str, str]) -> Processed | None:
    case_id, year, path, title, decided, citation = args
    for wrong, right in TITLE_FIXES.items():
        title = title.replace(wrong, right)
    pdf = settings.raw_dir / "aws_sc" / "pdf" / f"{path}_EN.pdf"
    if not pdf.exists():
        return None
    try:
        when = datetime.strptime(decided, "%d-%m-%Y").date()
    except ValueError:
        when = date(int(year), 1, 1)
    try:
        head, paras = split(pdf_text(str(pdf)))
    except Exception:  # unreadable PDF
        return None
    chunks = chunk(head, paras)
    jid = case_id.replace(" ", "") or path  # a few old reports carry no neutral citation
    cites: list[Row] = []
    brs: list[Row] = []
    sensitive = False
    for c in chunks:
        found = extract(c.text, when)
        for ci in found:
            cites.append((jid, f"{jid}#{c.ord}", ci.act, ci.section, ci.sub, ci.provision_id, ci.raw))
            pat = SENSITIVE.get(ci.act)
            sensitive |= bool(pat and pat.match(ci.section))
        brs += [(jid, n, o, s) for n, o, s in bridges(c.text, found)]
        sensitive |= bool(SENSITIVE_TEXT.search(c.text))
    return Processed(
        judgment=(
            jid,
            title,
            when.isoformat(),
            citation,
            "Supreme Court of India",
            len(chunks),
            int(sensitive),
            "aws_sc",
            str(pdf.name),
            LICENCE,
        ),
        chunks=[(f"{jid}#{c.ord}", jid, c.ord, c.role, c.para_from, c.para_to, c.text) for c in chunks],
        cites=cites,
        bridges=brs,
    )


def build(workers: int = 6) -> dict[str, int]:
    con = db.connect()
    con.executescript(SCHEMA)
    known = {r[0] for r in con.execute("SELECT id FROM provisions")}
    rows = sc_criminal()
    n = 0
    with ProcessPoolExecutor(workers) as pool:
        for res in pool.map(_process, rows, chunksize=16):
            if res is None:
                continue
            n += 1
            con.execute("INSERT OR IGNORE INTO judgments VALUES (?,?,?,?,?,?,?,?,?,?)", res.judgment)
            con.executemany("INSERT OR IGNORE INTO judgment_chunks VALUES (?,?,?,?,?,?,?)", res.chunks)
            con.executemany(
                "INSERT INTO citations VALUES (?,?,?,?,?,?,?,?)",
                [(*c[:6], int(c[5] in known), c[6]) for c in res.cites],
            )
            con.executemany("INSERT INTO bridges VALUES (?,?,?,?)", res.bridges)
    con.commit()
    stats = {
        k: con.execute(f"SELECT count(*) FROM {k}").fetchone()[0]
        for k in ("judgments", "judgment_chunks", "citations", "bridges")
    }
    stats["sensitive"] = con.execute("SELECT sum(sensitive) FROM judgments").fetchone()[0] or 0
    stats["resolved_citations"] = con.execute("SELECT sum(resolved) FROM citations").fetchone()[0] or 0
    return stats


def bridge_agreement() -> dict[str, float | int]:
    """How often a court's own "corresponding to" link matches the official mapping."""
    con = db.connect()
    rows = con.execute("SELECT DISTINCT new_id, old_id FROM bridges").fetchall()
    official = {tuple(r) for r in con.execute("SELECT new_id, old_id FROM section_map WHERE old_id IS NOT NULL")}
    hits = sum(1 for r in rows if tuple(r) in official)
    return {"distinct_pairs": len(rows), "match_official": hits, "rate": round(hits / max(1, len(rows)), 3)}
