"""SQLite storage for everything structured (statutes, mappings, judgments, citations).

One file, `data/processed/dhara.sqlite`, used the same way on the laptop and in
production. Vectors live next to it as NumPy and SciPy files."""

import sqlite3
import threading
from pathlib import Path

from dhara.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS acts (
    code TEXT PRIMARY KEY, title TEXT, act_no TEXT,
    in_force_from TEXT, in_force_to TEXT, replaced_by TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS provisions (
    id TEXT PRIMARY KEY,               -- 'BNS:103'
    act TEXT REFERENCES acts(code), number TEXT, sort_key INTEGER,
    heading TEXT, chapter_no TEXT, chapter_title TEXT, subheading TEXT,
    text TEXT, status TEXT, flag TEXT, notes TEXT, source_url TEXT, source_page INTEGER
);
CREATE TABLE IF NOT EXISTS provision_parts (
    id TEXT PRIMARY KEY,               -- 'BNS:103(2)', 'BNS:100:Explanation 1'
    provision_id TEXT REFERENCES provisions(id), ord INTEGER,
    kind TEXT, label TEXT, text TEXT, status TEXT,
    added TEXT, changed TEXT, deleted TEXT   -- JSON lists from NCRB colour coding
);
CREATE TABLE IF NOT EXISTS offence_classification (
    provision_id TEXT, sub TEXT, offence TEXT, punishment TEXT,
    cognizable TEXT, bailable TEXT, triable_by TEXT
);
CREATE TABLE IF NOT EXISTS briefs (judgment_id TEXT PRIMARY KEY, body TEXT);  -- generated once, see brief.py
CREATE INDEX IF NOT EXISTS ix_prov_act ON provisions(act, sort_key);
CREATE INDEX IF NOT EXISTS ix_parts_prov ON provision_parts(provision_id, ord);
CREATE INDEX IF NOT EXISTS ix_cls_prov ON offence_classification(provision_id);
"""


def path() -> Path:
    return settings.processed_dir / "dhara.sqlite"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    p = db_path or path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


_local = threading.local()


def shared() -> sqlite3.Connection:
    """This thread's connection. The API and the evaluation run queries from several threads, and a
    sqlite3 connection can't run two at once."""
    if not hasattr(_local, "con"):
        _local.con = connect()
    return _local.con  # type: ignore[no-any-return]
