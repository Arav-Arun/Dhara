from pathlib import Path

from dhara import statutes_ncrb as ncrb_html

FIXTURE = Path(__file__).parent / "fixtures" / "ncrb" / "ChaptersTST.html"


def test_sections_chapters_and_flags() -> None:
    secs = {s.number: s for s in ncrb_html.parse(FIXTURE, "TST")}
    s103 = secs["103"]
    assert s103.heading == "Punishment for murder"
    assert s103.flag == "change"
    assert (s103.chapter_no, s103.chapter_title, s103.subheading) == (
        "VI",
        "Of Offences Affecting The Human Body",
        "Of offences affecting life",
    )
    assert [p.label for p in s103.parts] == ["(1)", "(2)"]


def test_colour_coding_becomes_changes() -> None:
    s103 = ncrb_html.parse(FIXTURE, "TST")[0]
    assert s103.parts[1].changes.added == ["When a group of five or more persons commits murder."]
    assert s103.notes == ["Section 103(2) of BNS shall not come into force on 1st July 2024"]
    assert "come into force" not in s103.text  # editorial note is not statute text


def test_broken_markup_and_missing_heading() -> None:
    s104 = {s.number: s for s in ncrb_html.parse(FIXTURE, "TST")}["104"]
    assert s104.heading == "Punishment for murder by life-convict"  # taken from the index page
    assert s104.parts[0].text.startswith("Whoever, being under sentence")
    assert [p.kind for p in s104.parts] == ["body", "illustration", "explanation"]
    expl = s104.parts[2]
    assert expl.changes.deleted == ["old text"] and "old text" not in expl.text
