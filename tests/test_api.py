import pytest
from fastapi.testclient import TestClient

from dhara import db
from dhara.api import app

pytestmark = pytest.mark.skipif(not db.path().exists(), reason="needs the built database")
client = TestClient(app)


def test_provision_page() -> None:
    p = client.get("/v1/provisions/bns/103").json()
    assert p["heading"] == "Punishment for murder"
    assert [c["id"] for c in p["counterparts"]] == ["IPC:302"]
    assert p["classification"][0]["triable_by"] == "Court of Session."
    assert p["precedent"] and all("IPC:302" in j["via"] or "BNS:103" in j["via"] for j in p["precedent"])


def test_compare_both_ways() -> None:
    old = client.get("/v1/compare/ipc/498A").json()
    assert sorted(c["id"] for c in old["counterparts"]) == ["BNS:85", "BNS:86"]
    assert {"IPC:498A", "BNS:85", "BNS:86"} <= set(old["texts"])
    new = client.get("/v1/compare/bnss/528").json()
    assert [c["id"] for c in new["counterparts"]] == ["CRPC:482"]


def test_judgment_lists_citations_under_both_codes() -> None:
    j = client.get("/v1/judgments/2013INSC164").json()
    assert j["passages"] and j["passages"][0]["role"] == "headnote"
    assert {"id": "CRPC:482", "counterparts": ["BNSS:528"]}.items() <= next(
        c for c in j["cites"] if c["id"] == "CRPC:482"
    ).items()


def test_unknown_code_is_404() -> None:
    assert client.get("/v1/provisions/xyz/1").status_code == 404


def test_judgment_search_by_section_topic_and_page() -> None:
    by_section = client.get("/v1/judgments", params={"q": "BNS 316"}).json()
    assert by_section["mode"] == "section" and any("IPC:406" in j["via"] for j in by_section["items"])
    recent = client.get("/v1/judgments", params={"q": "BNS 316", "after": "2024-07-01"}).json()
    assert recent["items"] and all(j["decided_on"] >= "2024-07-01" for j in recent["items"])
    topic = client.get("/v1/judgments", params={"q": "anticipatory bail"}).json()
    assert topic["mode"] == "topic" and topic["more"]
    assert sum("anticipatory" in j["snippet"].lower() for j in topic["items"]) >= 10
    second = client.get("/v1/judgments", params={"q": "anticipatory bail", "offset": 20}).json()
    assert not {j["id"] for j in second["items"]} & {j["id"] for j in topic["items"]}
