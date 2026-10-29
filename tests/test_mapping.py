import sqlite3

import pytest

from dhara import db
from dhara.mapping import classify
from dhara.mapping_tables import parse_cell


@pytest.mark.parametrize(
    ("cell", "refs"),
    [
        ("1. Short title, commencement and application. 1(1)", [("1", "(1)")]),
        ("2(8) ‘document’ (Change)", [("2", "(8)")]),
        ("35(3), 35(4) 35(5), 35(6)", [("35", "(3)"), ("35", "(4)"), ("35", "(5)"), ("35", "(6)")]),
        ("Cheating by personation 319(1)", [("319", "(1)")]),
        ("Explanation to 489A", [("489A", "Explanation")]),
        (
            "246. Diminishing weight of coin. 248. Altering coin. (reference to ‘Indian coin’ removed)",
            [("246", ""), ("248", "")],
        ),
        ("151 Arrest to prevent commission of cognizable offences.", [("151", "")]),
        ("105-I. Fine in lieu of forfeiture.", [("105I", "")]),
        ("B.–AID TO THE MAGISTRATES AND THE POLICE 37. Public when to assist.", [("37", "")]),
        ("Abetment of offences defined in sections 162 or 163", []),
    ],
)
def test_parse_cell(cell: str, refs: list[tuple[str, str]]) -> None:
    assert [(r.section, r.sub) for r in parse_cell(cell)] == refs


def test_classify_relations() -> None:
    pairs = {("N1", "O1"), ("N2", "O2"), ("N2", "O3"), ("N3", "O4"), ("N4", "O4")}
    rel = classify(pairs)
    assert rel[("N1", "O1")] == "equivalent"
    assert rel[("N2", "O2")] == rel[("N2", "O3")] == "merged"
    assert rel[("N3", "O4")] == rel[("N4", "O4")] == "split"


needs_db = pytest.mark.skipif(not db.path().exists(), reason="run `make statutes mapping` first")


@needs_db
@pytest.mark.parametrize(
    ("old", "new", "relation"),
    [
        ("IPC:302", "BNS:103", "equivalent"),
        ("IPC:420", "BNS:318", "merged"),
        ("IPC:498A", "BNS:85", "split"),
        ("IPC:120B", "BNS:61", "merged"),
        ("CRPC:482", "BNSS:528", "equivalent"),
        ("CRPC:438", "BNSS:482", "equivalent"),
        ("IEA:65B", "BSA:63", "equivalent"),
        ("IPC:377", None, "omitted"),
    ],
)
def test_known_mappings(old: str, new: str | None, relation: str) -> None:
    con: sqlite3.Connection = db.connect()
    rows = con.execute("SELECT new_id, relation FROM section_map WHERE old_id=?", (old,)).fetchall()
    assert (new, relation) in [tuple(r) for r in rows]


@needs_db
def test_new_sections_have_no_old_counterpart() -> None:
    con = db.connect()
    rel = con.execute("SELECT relation FROM section_map WHERE new_id='BNS:152'").fetchall()
    assert [r[0] for r in rel] == ["new"]
