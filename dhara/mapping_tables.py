"""Parse NCRB's official correspondence tables (new code -> old code, sub-section level).

Each page has two tables: new -> old, and the same mapping old -> new. We parse both;
the forward table is the source of truth and the reverse one is a consistency check.
"""

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

# Cell shapes seen in the real tables:
#     "1. Short title, commencement and application. 1(1)"   section + its sub-section
#     "2(8) ‘document’ (Change)"                              sub-section with a change flag
#     "35(3), 35(4) 35(5), 35(6)"                             several refs
#     "Cheating by personation 319(1)"                        ref at the end
#     "Explanation to 489A"                                   a part of a section
#     "246. Fraudulently ... 248. Altering ... (reference to ‘Indian coin’ removed)"
#     "151 Arrest to prevent ..."                             no full stop after the number
#     "New Section" / "New Sub-Section" / "Deleted"
REF = re.compile(r"(?<![\w(])(\d{1,3}[A-Z]{0,3})((?:\s*\(\s*\w{1,4}\s*\))*)")
EXPLANATION_TO = re.compile(r"Explanation\s*(\d*)\s*to\s+(?:section\s+)?(\d{1,3}[A-Z]{0,3})", re.I)
FLAG = re.compile(r"\((Change|New)\)", re.I)
NOTE = re.compile(
    r"\(([^()]*\b(?:removed|added|deleted|inserted|omitted|substituted|modified|enhanced|"
    r"increased|reduced|replaced|merged|expanded)\b[^()]*)\)",
    re.I,
)


@dataclass(frozen=True)
class Ref:
    section: str
    sub: str = ""  # "(1)", "(1)(a)", "Explanation", ""


@dataclass
class Row:
    """One mapping row: new refs on the left, old refs on the right (as read from the table)."""

    left: list[Ref]
    right: list[Ref]
    left_status: str = ""  # "", "new", "deleted"
    right_status: str = ""
    changed: bool = False
    note: str = ""
    raw: tuple[str, str] = ("", "")
    order: int = 0
    extra: dict[str, str] = field(default_factory=dict)


def _clean(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def _status(cell: str) -> str:
    c = cell.lower()
    if c.startswith("new") and len(c) < 30:  # "New Section", "New Sub-Section", "New clause"
        return "new"
    if c.startswith("deleted") and len(c) < 30:
        return "deleted"
    return ""


def parse_cell(cell: str) -> list[Ref]:
    """Section references in one table cell, in order, most specific first per section."""
    text = FLAG.sub(" ", NOTE.sub(" ", cell))
    text = re.sub(r"\b(\d{1,3})-([A-Z])\b", r"\1\2", text)  # "105-I" is section 105I
    text = re.sub(r"^[A-Z]\.\s*[—–-]+\s*[A-Z ,]+?\s+(?=\d)", "", text)  # "B.–AID TO ... POLICE 37."
    refs: list[Ref] = []
    for m in EXPLANATION_TO.finditer(text):
        refs.append(Ref(m.group(2), f"Explanation {m.group(1)}".strip()))
    text = EXPLANATION_TO.sub(" ", text)
    for m in REF.finditer(text):
        before = text[: m.start()]
        after = text[m.end() :]
        at_start = (
            not before.strip()
            or re.search(r"([.,;:)]|\band)\s*$", before) is not None  # after punctuation or a ref
            or (bool(m.group(2)) and not after.strip())  # "Cheating by personation 319(1)"
        )
        looks_like_ref = (
            not after.strip()
            or re.match(r"\s*[.\-–,]", after) is not None
            or re.match(r"\s+[A-Z“‘\"']", after) is not None
            or bool(m.group(2))
        )
        if re.search(r"\b(sections?|of|under|clause|year|rupees)\s*$", before, re.I):
            continue
        if at_start and looks_like_ref and int(re.match(r"\d+", m.group(1)).group()) < 600:  # type: ignore[union-attr]
            refs.append(Ref(m.group(1), re.sub(r"\s+", "", m.group(2))))
    # "1. Short title ... 1(1)": keep the sub-section ref, drop the bare section ref
    specific = {r.section for r in refs if r.sub}
    out = [r for r in refs if r.sub or r.section not in specific]
    return list(dict.fromkeys(out))


def parse_table(table_html: str) -> list[Row]:
    rows: list[Row] = []
    pending: list[Row] = []
    current_left: list[Ref] = []
    for i, tr in enumerate(re.findall(r"<tr.*?</tr>", table_html, re.S)):
        cells = [_clean(c) for c in re.findall(r"<t[hd].*?</t[hd]>", tr, re.S)]
        if len(cells) != 2:
            continue
        left_raw, right_raw = cells
        if re.search(r"(Sanhita|Code|Act|Adhiniyam),?\s*\d{4}\s*-->", left_raw, re.I):
            continue  # the table's own header row
        if re.match(r"^(CHAPTER|PART)\b", left_raw, re.I):
            continue
        ls, rs = _status(left_raw), _status(right_raw)
        left = [] if ls else parse_cell(left_raw)
        right = [] if rs else parse_cell(right_raw)
        if left_raw.strip().lower().startswith("explanation") and not left and current_left:
            left = [Ref(current_left[0].section, "Explanation")]
        if not left and not ls and right:  # continuation row: same left provision as above
            left = current_left
        if left:
            current_left = left
        if left and not right and not rs and not right_raw:
            # "105. Recording of search ... (Change)" with an empty old cell: either a header
            # whose sub-sections follow, or a new section. Decided after the whole table is read.
            pending.append(Row(left, [], "", "new", bool(FLAG.search(left_raw)), "", (left_raw, ""), i))
            continue
        if not (left or ls) or not (right or rs):
            continue  # headings, sub-headings, blank rows
        note = "; ".join(m.group(1).strip() for m in NOTE.finditer(right_raw + " " + left_raw))
        rows.append(Row(left, right, ls, rs, bool(FLAG.search(left_raw)), note, (left_raw, right_raw), i))
    seen = {ref.section for r in rows for ref in r.left}
    rows += [r for r in pending if not ({ref.section for ref in r.left} & seen)]
    return sorted(rows, key=lambda r: r.order)


def parse_tables(path: Path) -> tuple[list[Row], list[Row]]:
    """(forward new->old rows, reverse old->new rows)."""
    tables = re.findall(r"<table.*?</table>", path.read_text(encoding="utf-8"), re.S)
    return parse_table(tables[0]), parse_table(tables[1])
