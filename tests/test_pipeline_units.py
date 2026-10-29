from datetime import date

import pytest

from dhara import db, rules
from dhara.agent import LOOKUP
from dhara.retrieve import rrf
from dhara.verify import check


def test_rrf_rewards_agreement() -> None:
    fused = rrf({"bm25": [1, 2, 3], "dense": [2, 3, 1], "sparse": [2, 1]}, k=3)
    assert [h.ord for h in fused] == [2, 1, 3]
    assert fused[0].by == {"bm25": 2, "dense": 1, "sparse": 1}


@pytest.mark.parametrize(
    ("offence", "started", "expected"),
    [
        (date(2024, 6, 20), date(2024, 6, 25), {"substantive": "IPC", "procedure": "CRPC", "evidence": "IEA"}),
        (date(2024, 6, 20), date(2024, 7, 5), {"substantive": "IPC", "procedure": "contested", "evidence": "BSA"}),
        (date(2024, 8, 1), None, {"substantive": "BNS", "procedure": "BNSS", "evidence": "BSA"}),
    ],
)
def test_applicability(offence: date, started: date | None, expected: dict[str, str]) -> None:
    assert {r.area: r.code for r in rules.applicable(offence, started)} == expected


@pytest.mark.parametrize("q", ["BNS 103", "what is IPC 420?", "Section CrPC 438", "bnss 528"])
def test_lookup_route(q: str) -> None:
    assert LOOKUP.match(q)


def test_research_route() -> None:
    assert not LOOKUP.match("When can BNS 103 apply to a mob killing?")


needs_db = pytest.mark.skipif(not db.path().exists(), reason="needs the built database")


@needs_db
def test_verifier_drops_fabricated_citations() -> None:
    answer = {
        "points": [
            {"text": "Murder is punishable under BNS 103 (old IPC 302).", "cites": ["S1"]},
            {"text": "See BNS 600 for this.", "cites": ["S1"]},
            {"text": "Uncited claim.", "cites": []},
            {"text": "Supported by a passage we never showed.", "cites": ["J9"]},
        ]
    }
    report = check(answer, {"S1", "J1"}, db.connect(), date(2026, 1, 1))
    assert [p["text"][:6] for p in report.kept] == ["Murder"]
    reasons = [why for _, why in report.dropped]
    assert "BNS:600 does not exist" in reasons and "no citation" in reasons
    assert report.abstain  # 3 of 4 points failed


@needs_db
def test_verifier_drops_a_short_answer_citing_a_passage_it_was_not_given() -> None:
    from dhara import verify

    con = db.connect()
    answer = {"short_answer": "Yes, the High Court can quash [J9].", "points": [{"text": "It can.", "cites": ["S1"]}]}
    report = verify.check(answer, {"S1", "J1"}, con, date(2025, 1, 1))
    assert report.summary_problem.startswith("cites spans not in context") and len(report.kept) == 1
    fine = verify.check({**answer, "short_answer": "Yes [S1]."}, {"S1"}, con, date(2025, 1, 1))
    assert fine.summary_problem == ""
