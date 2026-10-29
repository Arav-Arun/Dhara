from datetime import date

import pytest

from dhara.citations import bridges, extract


def ids(text: str, when: date | None = None) -> list[str]:
    return [f"{c.act}:{c.section}{c.sub}" for c in extract(text, when)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("convicted u/s 302/34 IPC and sentenced", ["IPC:302", "IPC:34"]),
        ("under Section 302 read with Section 34 of the Indian Penal Code", ["IPC:302", "IPC:34"]),
        ("Sections 120B, 420, 467 and 471 IPC", ["IPC:120B", "IPC:420", "IPC:467", "IPC:471"]),
        ("the requirement of s.239 CrPC is", ["CRPC:239"]),
        ("certificate under Section 65-B of the Evidence Act", ["IEA:65B"]),
        ("Section 223(d) Cr.P.C. permits", ["CRPC:223(d)"]),
        ("offence punishable under Section 103(1) of the BNS", ["BNS:103(1)"]),
        ("Section 528 of the Bharatiya Nagarik Suraksha Sanhita, 2023", ["BNSS:528"]),
        (
            "Sections 299 to 304 IPC deal with",
            ["IPC:299", "IPC:300", "IPC:301", "IPC:302", "IPC:303", "IPC:304"],
        ),
        ("Section 313 of the Code", []),  # ambiguous act: skipped on purpose
        ("Crime No. 99/2018 registered", []),
    ],
)
def test_extract(text: str, expected: list[str]) -> None:
    assert ids(text) == expected


def test_old_crpc_before_1974() -> None:
    assert ids("Section 342 Cr.P.C.", date(1965, 5, 1)) == ["CRPC1898:342"]
    assert ids("Section 342 Cr.P.C.", date(1995, 5, 1)) == ["CRPC:342"]


def test_bridges() -> None:
    text = "non-compliance with Section 50 of the CrPC 1973 (now Section 47 of BNSS 2023) vitiates"
    found = bridges(text, extract(text))
    assert [(n, o) for n, o, _ in found] == [("BNSS:47", "CRPC:50")]


def test_bridges_align_lists_by_position() -> None:
    text = "ss.340 and 341 of the BNSS correspond to ss.303 and 304 CrPC"
    found = [(n, o) for n, o, _ in bridges(text, extract(text))]
    assert found == [("BNSS:340", "CRPC:303"), ("BNSS:341", "CRPC:304")]


def test_bridge_keeps_in_text_order() -> None:
    text = (
        "under Sections 409, 420, 120-B read with Sections 34 & 37 of the Indian Penal Code, 1860 "
        "(now Sections 316(5), 318(4), 61(2), 3(5) & 3(8) of the BNS)"
    )
    found = [(n, o) for n, o, _ in bridges(text, extract(text))]
    assert ("BNS:318", "IPC:420") in found and ("BNS:61", "IPC:120B") in found


def test_act_abbreviation_is_not_a_section_suffix() -> None:
    assert ids("FIR u/s 420 IPC and Section 438 CrPC") == ["IPC:420", "CRPC:438"]
    assert ids("Section 120 B IPC and Section 65-B of the Evidence Act") == ["IPC:120B", "IEA:65B"]
