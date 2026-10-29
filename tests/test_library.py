import sqlite3

from dhara import library, llm


def test_brief_drops_points_citing_passages_it_was_not_given(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    con = sqlite3.connect(":memory:")
    con.executescript(
        """CREATE TABLE judgment_chunks (id TEXT, judgment_id TEXT, ord INTEGER, role TEXT, text TEXT);
           CREATE TABLE briefs (judgment_id TEXT PRIMARY KEY, body TEXT);"""
    )
    con.executemany(
        "INSERT INTO judgment_chunks VALUES (?, 'J', ?, ?, ?)",
        [("J#0", 0, "headnote", "Quashing after settlement."), ("J#1", 1, "judgment", "Appeal allowed.")],
    )
    reply = {
        "facts": {"text": "f", "cites": ["P1"]},
        "issue": {"text": "i", "cites": ["P7"]},
        "held": [{"text": "kept", "cites": ["P2"]}, {"text": "invented", "cites": ["P9"]}],
        "cite_for": [{"text": "uncited", "cites": []}],
    }
    monkeypatch.setattr(llm, "json_call", lambda *a, **k: dict(reply))
    out = library.brief(con, "J")
    assert [p["text"] for p in out["held"]] == ["kept"] and out["cite_for"] == []
    assert out["facts"]["text"] == "f" and out["issue"] is None
    monkeypatch.setattr(llm, "json_call", lambda *a, **k: {})  # second call is served from the table
    assert library.brief(con, "J")["held"][0]["text"] == "kept"


def test_daily_cap_counts_only_public_calls_from_today(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json
    from datetime import datetime

    from dhara.config import settings

    today = datetime.now().isoformat(timespec="seconds")
    rows = [
        {"ts": today, "purpose": "answer", "usd": 0.4},
        {"ts": today, "purpose": "brief", "usd": 0.3},
        {"ts": today, "purpose": "bench:precedent:dev", "usd": 5.0},  # offline work isn't capped
        {"ts": "2020-01-01T10:00:00", "purpose": "answer", "usd": 9.0},
    ]
    (tmp_path / "processed").mkdir()
    (tmp_path / "processed" / "llm_usage.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    assert round(llm.spent_today(), 2) == 0.7
