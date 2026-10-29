"""Golden checks against the built database. Skipped when the data hasn't been built."""

import sqlite3

import pytest

from dhara import db

pytestmark = pytest.mark.skipif(not db.path().exists(), reason="run `dhara build-statutes` first")


@pytest.fixture(scope="module")
def con() -> sqlite3.Connection:
    return db.connect()


def test_section_counts(con: sqlite3.Connection) -> None:
    counts = dict(con.execute("SELECT act, count(*) FROM provisions GROUP BY act").fetchall())
    assert counts == {"BNS": 358, "BNSS": 531, "BSA": 170, "IPC": 575, "CRPC": 534, "IEA": 185}


def test_every_numbered_section_present(con: sqlite3.Connection) -> None:
    for act, last in [("IPC", 511), ("CRPC", 484), ("IEA", 167), ("BNS", 358), ("BNSS", 531), ("BSA", 170)]:
        nums = {r[0] for r in con.execute("SELECT number FROM provisions WHERE act=?", (act,))}
        assert {str(i) for i in range(1, last + 1)} <= nums, act


def test_known_provisions(con: sqlite3.Connection) -> None:
    def parts(pid: str) -> list[str]:
        return [
            r[0] for r in con.execute("SELECT label FROM provision_parts WHERE provision_id=? ORDER BY ord", (pid,))
        ]

    assert parts("BNS:103") == ["(1)", "(2)"]
    assert parts("IPC:300").count("Exception 1") == 1 and "Exception 5" in parts("IPC:300")
    assert parts("IEA:65B")[:2] == ["(1)", "(2)"]
    status = con.execute("SELECT status FROM provision_parts WHERE id='BNS:106(2)'").fetchone()[0]
    assert status == "not_commenced"


def test_state_amendments_are_excluded(con: sqlite3.Connection) -> None:
    # Haryana's "382B. Snatching" lives in a STATE AMENDMENT block, not the central Act
    assert con.execute("SELECT 1 FROM provisions WHERE id='IPC:382B'").fetchone() is None
    texts = " ".join(r[0] for r in con.execute("SELECT heading || text FROM provisions WHERE act='IPC'"))
    assert "STATE AMENDMENT" not in texts.upper()


def test_first_schedule(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT cognizable, bailable, triable_by FROM offence_classification WHERE provision_id='BNS:103' AND sub='(1)'"
    ).fetchone()
    assert tuple(row) == ("Cognizable.", "Non-bailable.", "Court of Session.")
