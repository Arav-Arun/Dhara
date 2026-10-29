"""BNS, BNSS and BSA from the NCRB Sankalan portal.

Section text with NCRB's colour-coded changes, the arrangement-of-sections headings, and the
BNSS First Schedule (classification of offences).
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from pydantic import BaseModel

from dhara.grammar import ILLUSTRATIONS, split_parts
from dhara.models import Changes, Section

# Parse BNS, BNSS and BSA from the NCRB Sankalan chapter pages.
#
# Each section starts at an anchor <span id="N"> followed by <p> paragraphs; chapter
# headings and sub-headings are centred <p> elements between sections. The HTML has a
# few mismatched tags, so instead of trusting the tag tree we split the page at the
# section anchors and parse each slice on its own.
#
# NCRB colour-codes text against the old codes: green = new addition, navy = change,
# red = deleted. Red text is dropped from the provision and kept in `changes.deleted`.
ADDED, CHANGED, DELETED = "#00b050", "#000080", "red"
ANCHOR = re.compile(r'<span id="(\d+[A-Z]?)">\s*<p')
CHAPTER = re.compile(r"^CHAPTER\s+([IVXLC]+[A-Z]?)\b", re.I)
FLAG = re.compile(r"\((Change|New)\)\s*$", re.I)
NOT_IN_FORCE = re.compile(r"shall not come into force", re.I)


def index_headings(path: Path) -> dict[str, str]:
    """Section headings from NCRB's "Arrangement of sections" page (Index{BNS,BNSS,BSA}.html)."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    out: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = [_clean(td.get_text(" ")) for td in tr.find_all("td")]
        if len(cells) == 2 and (m := re.match(r"^(\d+[A-Z]?)\s*\.$", cells[0])):
            out[m.group(1)] = FLAG.sub("", cells[1]).strip().rstrip(".")
    return out


def parse(path: Path, act: str) -> list[Section]:
    html = _repair(path.read_text(encoding="utf-8"))
    headings = index_headings(path.with_name(f"Index{act}.html"))
    anchors = list(ANCHOR.finditer(html))
    sections: list[Section] = []
    chapter = {"no": "", "title": "", "sub": ""}

    _structure(BeautifulSoup(html[: anchors[0].start()], "html.parser").find_all("p"), chapter)
    for i, a in enumerate(anchors):
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html)
        paras = BeautifulSoup(html[a.start() : end], "html.parser").find_all("p")
        body = [p for p in paras if not _is_structural(p)]
        sec = _section(body, act, a.group(1), chapter, headings)
        sections.append(sec)
        _structure([p for p in paras if _is_structural(p)], chapter)  # applies to later sections
    return sections


def _repair(html: str) -> str:
    """Fix the two kinds of broken markup in the NCRB pages."""
    html = re.sub(r'<(\w+)"+\s*>', r"<\1>", html)  # `<span">`
    # stray `</span>` after a bold section number closes the paragraph early: `<strong>112. </span></strong>`
    return re.sub(r"(<strong>\s*\d+[A-Z]?\.(?:&#160;|\s)*)</span>(\s*</strong>)", r"\1\2", html)


def _is_structural(p: Tag) -> bool:
    """Chapter numbers, chapter titles and sub-headings (not part of any section)."""
    text = _clean(p.get_text(" "))
    if ILLUSTRATIONS.match(text):
        return False
    centred = "text-align: center" in (p.get("style") or "")
    return centred or bool(CHAPTER.match(text)) or (text.isupper() and len(text) < 160)


def _structure(paras: list[Tag], chapter: dict[str, str]) -> None:
    expect_title = False
    for p in paras:
        text = _clean(p.get_text(" "))
        if not text or not _is_structural(p):
            continue
        if m := CHAPTER.match(text):
            chapter.update(no=m.group(1).upper(), title="", sub="")
            expect_title = True
        elif expect_title:
            chapter["title"], expect_title = text.title(), False
        elif chapter["no"] and len(text) < 160 and not text.startswith(("Note", "—")):
            chapter["sub"] = text


def _section(paras: list[Tag], act: str, number: str, chapter: dict[str, str], headings: dict[str, str]) -> Section:
    paras = [p for p in paras if p.get_text(strip=True)]
    first = _clean(paras[0].get_text(" ")) if paras else ""
    flag_m = FLAG.search(first)
    if re.match(rf"^{re.escape(number)}\s*\.", first):
        heading, body_paras = headings.get(number, ""), paras  # no heading paragraph
    else:
        heading, body_paras = FLAG.sub("", first).strip().rstrip("."), paras[1:]

    body: list[tuple[str, Changes]] = []
    notes: list[str] = []
    for p in body_paras:
        text, ch, para_notes = _paragraph(p)
        notes += para_notes
        if NOT_IN_FORCE.search(text) and len(text) < 200:
            notes.append(text.strip("() "))
            continue
        body.append((text, ch))
    if body:  # drop the leading "103." (and, old-style, "103. Heading.—") from the first paragraph
        text, ch = body[0]
        text = re.sub(rf"^{re.escape(number)}\s*\.+\s*", "", text)
        if heading and text.startswith(heading[:25]) and (m := re.search(r"[—–]+\s*", text)):
            text = text[m.end() :]
        body[0] = (text, ch)

    return Section(
        act=act,
        number=number,
        heading=heading or headings.get(number, ""),
        chapter_no=chapter["no"],
        chapter_title=chapter["title"],
        subheading=chapter["sub"],
        parts=split_parts(body),
        flag=flag_m.group(1).lower() if flag_m else "",  # type: ignore[arg-type]
        notes=notes,
    )


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _colour(node: NavigableString, stop: Tag) -> str:
    for parent in node.parents:
        if parent is stop:
            break
        if m := re.search(r"(?<!-)color:\s*([#\w]+)", str(parent.get("style") or "").lower()):
            return m.group(1)
    return ""


def _in_note(node: NavigableString, stop: Tag) -> bool:
    """Inside a red editorial note such as "(Section 106(2) ... shall not come into force ...)"."""
    for parent in node.parents:
        if parent is stop:
            return False
        style = str(parent.get("style") or "").lower()
        if re.search(r"(?<!-)color:\s*red", style) and NOT_IN_FORCE.search(parent.get_text()):
            return True
    return False


def _paragraph(p: Tag) -> tuple[str, Changes, list[str]]:
    """Text of one <p> minus deleted text, what was marked as changed, and editorial notes."""
    kept: list[str] = []
    notes: list[str] = []
    ch = Changes()
    for s in p.descendants:
        if not isinstance(s, NavigableString):
            continue
        frag = str(s).replace("\xa0", " ")
        if _in_note(s, p):
            notes.append(frag)
            continue
        colour = _colour(s, p)
        if colour == DELETED:
            ch.deleted.append(frag.strip())
            continue
        kept.append(frag)
        if colour == ADDED:
            ch.added.append(frag.strip())
        elif colour == CHANGED:
            ch.changed.append(frag.strip())
    ch.added, ch.changed, ch.deleted = ([x for x in lst if x] for lst in (ch.added, ch.changed, ch.deleted))
    note = _clean("".join(notes)).strip(" ()")
    return _clean("".join(kept)), ch, [note] if note else []


# Parse the BNSS First Schedule (classification of offences) from NCRB's HTML table.
#
# Each row: section ref, offence, punishment, cognizable?, bailable?, triable by.
# Part I covers BNS offences; Part II ("offences against other laws") is kept as-is.
REF = re.compile(r"^(\d+[A-Z]?)\s*((?:\(\w+\))*)")


class Classification(BaseModel):
    part: str  # "I" or "II"
    section: str  # "117"
    sub: str  # "(3)" or ""
    offence: str
    punishment: str
    cognizable: str
    bailable: str
    triable_by: str


def parse_schedule(path: Path) -> list[Classification]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows: list[Classification] = []
    for part, table in zip(("I", "II"), soup.find_all("table"), strict=False):
        last_section = ""
        for tr in table.find_all("tr"):
            cells = [re.sub(r"\s+", " ", td.get_text(" ")).strip() for td in tr.find_all(["td", "th"])]
            if len(cells) != 6 or cells[0] in ("Section", "1"):
                continue
            m = REF.match(cells[0].replace(" (", "("))
            if m:
                last_section = m.group(1)
            elif part == "II":
                rows.append(
                    Classification(
                        part=part,
                        section="",
                        sub="",
                        offence=cells[1],
                        punishment=cells[2],
                        cognizable=cells[3],
                        bailable=cells[4],
                        triable_by=cells[5],
                    )
                )
                continue
            if not last_section:
                continue
            rows.append(
                Classification(
                    part=part,
                    section=m.group(1) if m else last_section,
                    sub=m.group(2) if m else "",
                    offence=cells[1],
                    punishment=cells[2],
                    cognizable=cells[3],
                    bailable=cells[4],
                    triable_by=cells[5],
                )
            )
    return rows
