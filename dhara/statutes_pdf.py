"""Parse IPC, CrPC and the Evidence Act from India Code PDFs.

India Code PDFs use fonts consistently, so we read spans with their size and weight:
- section headings start with a bold run like "302. Punishment for murder"
- body text is ~11pt; illustrations ~9pt
- amendment footnote markers are ~7pt superscripts (dropped)
- footnotes sit at the bottom of each page and start "1. Subs. by Act ..." (dropped)
The "Arrangement of Sections" at the front is skipped because its entries aren't bold."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from dhara.grammar import split_parts
from dhara.models import Changes, Section

# the dot is optional before a quoted heading: the official IPC text has "17 “Government”.—"
# "105-I." is printed with a hyphen (to avoid confusion with a Roman numeral); stored as "105I"
SECTION_HEAD = re.compile(r"^\[?(\d+-?[A-Z]{0,3})\s*(?:\.|(?=\s*“))\s*(\S.*)")
CHAPTER = re.compile(r"^C\s*HAPTER\s+([IVXLC]+[A-Z]?)\b\.?\s*[—–-]*\s*(.*)")
HEAD_SEP = re.compile(r"\.?\s*[—–]+-?\s*")
# amendment footnotes: "1. Subs. by Act 25 of 2005 ..." (sometimes without the dot or number)
FOOTNOTE = re.compile(
    r"^(\d+\.?\s*(Subs\.|Ins\.|Omitted|Rep\.|The\s|Added|Cl\.|Sub-|Section|Certain|Now|Renumbered|"
    r"Proviso|Explanation|Clause|Vide|See|As to|w\.e\.f|Words|Ss\.|S\.)|(Subs\.|Ins\.) by\b)"
)
PARA_START = re.compile(r"^(\(\d+[A-Z]?\)|\([a-z]{1,4}\)|Provided\b|Explanation\b|Exception\b|Illustrations?\b)")
INCOMPLETE = re.compile(r"\b(section|sections|of|under|and|or|to|the|in|by|with)\s*$|,\s*$", re.I)
STATE_AMENDMENT = re.compile(r"^STATE AMENDMENTS?\b", re.I)
REPEALED = re.compile(r"\b(Rep\.|Omitted|Repealed)(\s+by\b|\.?\]?\s*$)")


@dataclass
class Line:
    text: str
    starts_bold: bool  # first real span (ignoring a leading "[") is bold
    size: float  # relative to the page's body text size
    y: float = 0.0  # vertical position as a fraction of page height
    page: int = 0


def _lines(doc: pymupdf.Document) -> list[Line]:
    out: list[Line] = []
    for i in range(len(doc)):
        page_no, page = i + 1, doc[i]
        raw = [ln for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])]
        body = _body_size(raw)
        page_lines: list[Line] = []
        for ln in raw:
            # drop superscript footnote markers and the large "IndiaCode" watermark
            spans = [s for s in ln["spans"] if 0.75 * body <= s["size"] < 20]
            if not spans:
                continue
            top = max(s["size"] for s in spans)
            # superscript markers like the "1" in "1[108A." are smaller than the line's text
            spans = [s for s in spans if not (s["text"].strip().isdigit() and s["size"] < 0.8 * top)]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if not text or re.fullmatch(r"\d{1,3}", text):
                continue  # page numbers
            # inserted sections start with a plain "[" before the bold number
            first = next((s for s in spans if s["text"].strip() not in ("", "[")), spans[0])
            bold = "Bold" in first["font"] or bool(first["flags"] & 16)
            size = max(s["size"] for s in spans) / body
            page_lines.append(Line(text, bold, size, ln["bbox"][1] / page.rect.height, page_no))
        # footnotes: everything from the first smaller "1. Subs. by ..." line to page end
        for i, line in enumerate(page_lines):
            if not line.starts_bold and FOOTNOTE.match(line.text) and (line.size < 0.95 or line.y > 0.55):
                page_lines = page_lines[:i]
                break
        out.extend(page_lines)
    return out


def _body_size(lines: list[dict]) -> float:  # type: ignore[type-arg]
    """Most common font size on the page, weighted by characters (body sizes vary by page)."""
    weight: dict[float, int] = {}
    for ln in lines:
        for s in ln["spans"]:
            if s["size"] < 20:
                weight[round(s["size"], 1)] = weight.get(round(s["size"], 1), 0) + len(s["text"])
    return max(weight, key=weight.__getitem__) if weight else 11.0


def parse(path: Path, act: str) -> list[Section]:
    """Central text only: "STATE AMENDMENT" blocks are skipped until the next real section.

    A state block can itself contain bold pseudo-sections (e.g. Haryana's "382B. Snatching"),
    so while skipping we only resume at a plain-numbered section or one listed in the
    Act's own arrangement of sections.
    """
    lines = _lines(pymupdf.open(path))
    known = set(toc_numbers(path))
    skipping = False
    sections: list[Section] = []
    chapter_no = chapter_title = subheading = ""
    cur: dict[str, object] | None = None
    paras: list[str] = []
    expect_title = False

    def flush() -> None:
        if cur is None:
            return
        if not paras and len(str(cur["heading"])) > 150 and not REPEALED.search(str(cur["heading"])):
            # no "—" separator: the heading ran into the body; split at the first sentence end
            head, _, rest = str(cur["heading"]).partition(". ")
            cur["heading"] = head
            paras.append(rest)
        body = [(re.sub(r"\s+", " ", p).replace("[", "").replace("]", "").strip(), Changes()) for p in paras]
        text = " ".join(b for b, _ in body)
        repealed = REPEALED.search(f"{cur['heading']} {text}"[:240]) and len(text) < 160
        status = "omitted" if (not body or repealed) else "in_force"
        sections.append(
            Section(
                act=act,
                number=str(cur["number"]),
                heading=str(cur["heading"]),
                chapter_no=str(cur["chapter_no"]),
                chapter_title=str(cur["chapter_title"]),
                subheading=str(cur["subheading"]),
                parts=split_parts(body),
                status=status,  # type: ignore[arg-type]
                source_page=int(cur["page"]),  # type: ignore[call-overload]
            )
        )

    for ln in lines:
        if STATE_AMENDMENT.match(ln.text):
            skipping = True
            if cur is not None:
                cur["heading_open"] = False
            continue
        if skipping:
            head = SECTION_HEAD.match(ln.text) if ln.starts_bold and ln.size >= 0.86 else None
            num = head.group(1).replace("-", "") if head else ""
            if not (head and (num.isdigit() or num in known)) and not CHAPTER.match(ln.text):
                continue
            skipping = False
        if m := CHAPTER.match(ln.text):
            chapter_no, subheading = m.group(1), ""
            chapter_title = m.group(2).strip().title()
            expect_title = not chapter_title
            continue
        if expect_title:
            chapter_title, expect_title = ln.text.strip().title(), False
            continue
        # a heading can wrap onto the next line, even one starting with a number:
        # "... punishable under section\n467.—Whoever ..." is still section 472's heading
        if cur is not None and cur.get("heading_open"):
            head = SECTION_HEAD.match(ln.text) if ln.starts_bold else None
            if not head or INCOMPLETE.search(str(cur["heading"])):
                bits = HEAD_SEP.split(ln.text, maxsplit=1)
                more, sep, rest = bits[0], len(bits) > 1, bits[1] if len(bits) > 1 else ""
                cur["heading"] = f"{cur['heading']} {more.strip().rstrip('.')}".strip()
                if sep:
                    cur["heading_open"] = False
                    paras = [rest] if rest else []
                continue
        m = SECTION_HEAD.match(ln.text) if ln.starts_bold else None
        if m and ln.size >= 0.86:
            flush()
            after = m.group(2).strip()
            parts = HEAD_SEP.split(after, maxsplit=1)
            heading, _, rest = parts[0], len(parts) > 1, parts[1] if len(parts) > 1 else ""
            cur = {
                "number": m.group(1).replace("-", ""),
                "heading": heading.strip().rstrip(".").replace("[", "").replace("]", ""),
                "chapter_no": chapter_no,
                "chapter_title": chapter_title,
                "subheading": subheading,
                "heading_open": not _,  # heading continues on the next line until "—"
                "page": ln.page,
            }
            paras = [rest] if rest else []
            continue
        if cur is None:
            continue
        if ln.size >= 0.86 and not ln.starts_bold and len(ln.text) < 120 and _is_subheading(ln.text):
            subheading = ln.text.strip()
            continue
        if PARA_START.match(ln.text) or not paras:
            paras.append(ln.text)
        else:
            paras[-1] = f"{paras[-1]} {ln.text}"
    flush()
    return _dedupe(sections)


def _is_subheading(text: str) -> bool:
    return bool(re.match(r"^(Of|When)\s+[a-z]", text)) and not text.rstrip().endswith((",", ";"))


def _dedupe(sections: list[Section]) -> list[Section]:
    """Keep the first occurrence of each section number (guards against stray bold lines)."""
    seen: set[str] = set()
    out = []
    for s in sections:
        if s.number not in seen:
            seen.add(s.number)
            out.append(s)
    return out


def toc_numbers(path: Path) -> list[str]:
    """Section numbers listed in the PDF's "Arrangement of Sections" (used as a completeness check)."""
    doc = pymupdf.open(path)
    nums: list[str] = []
    for i in range(len(doc)):
        page = doc[i]
        text_lines: list[tuple[str, bool]] = []
        body_started = False
        for block in page.get_text("dict")["blocks"]:
            for ln in block.get("lines", []):
                spans = [s for s in ln["spans"] if s["text"].strip() not in ("", "[")]
                if not spans:
                    continue
                bold = "Bold" in spans[0]["font"] or bool(spans[0]["flags"] & 16)
                text = "".join(s["text"] for s in spans).strip()
                if bold and SECTION_HEAD.match(text) and spans[0]["size"] >= 9.5:
                    body_started = True
                text_lines.append((text, bold))
        if body_started:
            break
        for text, bold in text_lines:
            if not bold and (m := re.match(r"^\[?(\d+-?[A-Z]{0,3})\s*\.\s*[A-Z\[]", text)):
                nums.append(m.group(1).replace("-", ""))
    return list(dict.fromkeys(nums))
