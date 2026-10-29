"""Find statute citations in judgment text.

A small grammar, tuned for how Indian courts actually write citations:

    u/s 302/34 IPC · Section 302 read with Section 34 of the Indian Penal Code
    Sections 120B, 420, 467 and 471 IPC · s.239 CrPC · Section 65-B of the Evidence Act
    Section 528 of the BNSS (corresponding to Section 482 of the CrPC)

Design choices:
- precision over recall: a number only counts when the act is named right after it
  (bare "Section 313 of the Code" is skipped because "the Code" is ambiguous)
- before 1 April 1974, "Cr.P.C." means the 1898 Code, which has different numbering,
  so those citations are kept but not resolved to CrPC 1973
- citations to other Acts are kept with their name, unresolved"""

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dhara.config import ROOT

# Find statute citations in judgment text.
#
# A small grammar, tuned for how Indian courts actually write citations:
#
#     u/s 302/34 IPC · Section 302 read with Section 34 of the Indian Penal Code
#     Sections 120B, 420, 467 and 471 IPC · s.239 CrPC · Section 65-B of the Evidence Act
#     Section 528 of the BNSS (corresponding to Section 482 of the CrPC)
#
# Design choices:
# - precision over recall: a number only counts when the act is named right after it
#   (bare "Section 313 of the Code" is skipped because "the Code" is ambiguous)
# - before 1 April 1974, "Cr.P.C." means the 1898 Code, which has different numbering,
#   so those citations are kept but not resolved to CrPC 1973
# - citations to other Acts are kept with their name, unresolved
ACTS: list[tuple[str, str]] = [  # order matters: BNSS before BNS
    ("BNSS", r"B\.?\s?N\.?\s?S\.?\s?S\.?|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita(?:,?\s*2023)?"),
    ("BNS", r"B\.?\s?N\.?\s?S\.?|Bharatiya\s+Nyaya\s+Sanhita(?:,?\s*2023)?"),
    ("BSA", r"B\.?\s?S\.?\s?A\.?|Bharatiya\s+Sakshya\s+Adhiniyam(?:,?\s*2023)?"),
    ("IPC", r"I\.?\s?P\.?\s?C\.?|Indian\s+Penal\s+Code(?:,?\s*1860)?|Penal\s+Code(?:,?\s*1860)?"),
    (
        "CRPC1898",
        r"(?:Code\s+of\s+Criminal\s+Procedure|Criminal\s+Procedure\s+Code|Cr\.?\s?P\.?\s?C\.?),?\s*1898"
        r"|old\s+Code\s+of\s+Criminal\s+Procedure|old\s+Cr\.?\s?P\.?\s?C\.?",
    ),
    (
        "CRPC",
        r"Code\s*\.?\s*of\s+Criminal\s+Procedure(?:,?\s*1973)?|Criminal\s+Procedure\s+Code(?:,?\s*1973)?"
        r"|Cr\.?\s?P\.?\s?C\.?(?:,?\s*1973)?|CrPC",
    ),
    ("IEA", r"(?:Indian\s+)?Evidence\s+Act(?:,?\s*1872)?|I\.?\s?E\.?\s?A\.?(?=\W)"),
]
ACT_RE = "|".join(f"(?P<{code}>{pat})" for code, pat in ACTS)

# the letter suffix ("498A") stays case-sensitive even inside re.I patterns, so "107 and" isn't "107AND"
# a spaced or hyphenated suffix is one letter ("120 B", "65-B"), so "420 IPC" is never section "420IPC"
NUM = r"\d{1,3}(?:(?-i:[A-Z]{1,2})\b|\s?-\s?(?-i:[A-Z]{1,2})\b|\s(?-i:[A-Z])(?![A-Za-z]))?(?:\s*\(\s*\w{1,4}\s*\))*"
JOIN = r"\s*(?:,|/|&|\band\b|\bor\b|r\s?/\s?w|read\s+with(?:\s+sections?)?|with|to)\s*"
LIST = rf"{NUM}(?:{JOIN}(?:sections?\s+)?{NUM})*"
SEC_WORD = r"(?:Sections?|Secs?\.?|S{1,2}\.|u\s?/\s?s{1,2}\.?|under\s+sections?|sec\.)"

PART = r"(?:\s+Part\s+I{1,2}\b)?"  # "Section 304 Part I, IPC"
WITH_WORD = re.compile(
    rf"\b{SEC_WORD}\s*(?P<list>{LIST}){PART}\s*,?\s*(?:of\s+(?:the\s+)?)?(?P<act>{ACT_RE})(?![A-Za-z])", re.I
)
BARE = re.compile(
    rf"(?<![\w.(/])(?P<list>{NUM}(?:{JOIN}(?:sections?\s+)?{NUM})+|{NUM}){PART}\s+(?:of\s+(?:the\s+)?)?"
    rf"(?P<act>{ACT_RE})(?![A-Za-z])",
    re.I,
)
# Queries are written act-first ("BNS 103", "CrPC s.482"); only used for queries, where years
# like "IPC 1860" are rare, and never for judgment text (keeps the measured precision intact)
ACT_FIRST = re.compile(
    rf"(?<![\w])(?P<act>{ACT_RE})\s*,?\s*(?:{SEC_WORD}\s*)?(?P<list>{LIST})(?!\d)(?![A-Za-z]{{2}})", re.I
)
ONE_NUM = re.compile(r"(\d{1,3})(?:\s?-?\s?([A-Z]{1,2})(?![A-Za-z]))?((?:\s*\(\s*\w{1,4}\s*\))*)")
OLD_CRPC_UNTIL = date(1974, 4, 1)


@dataclass(frozen=True)
class Citation:
    act: str  # BNS, BNSS, BSA, IPC, CRPC, IEA, CRPC1898
    section: str  # "302", "65B"
    sub: str  # "(1)", "(1)(a)", ""
    start: int
    end: int
    raw: str
    pos: int = 0  # position within a list such as "302/34" (keeps in-text order)

    @property
    def provision_id(self) -> str:
        return f"{self.act}:{self.section}"


def _act(m: re.Match[str]) -> str:
    return next(code for code, _ in ACTS if m.group(code))


def _numbers(list_text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    parts = ONE_NUM.findall(list_text)
    # "Sections 299 to 304": expand short ranges of plain numbers
    rng = re.fullmatch(r"\s*(\d{1,3})\s+to\s+(\d{1,3})\s*", list_text)
    if rng and 0 < int(rng.group(2)) - int(rng.group(1)) <= 20:
        return [(str(i), "") for i in range(int(rng.group(1)), int(rng.group(2)) + 1)]
    for num, letters, sub in parts:
        out.append((num + (letters or "").upper(), re.sub(r"\s+", "", sub)))
    return out


def extract(text: str, decided_on: date | None = None, query: bool = False) -> list[Citation]:
    found: dict[tuple[int, str, str], Citation] = {}
    taken: list[tuple[int, int]] = []
    for pattern in (WITH_WORD, BARE, ACT_FIRST) if query else (WITH_WORD, BARE):
        for m in pattern.finditer(text):
            if any(s <= m.start() < e for s, e in taken):
                continue
            act = _act(m)
            if act == "CRPC" and decided_on and decided_on < OLD_CRPC_UNTIL:
                act = "CRPC1898"
            for pos, (section, sub) in enumerate(_numbers(m.group("list"))):
                if int(re.match(r"\d+", section).group()) == 0:  # type: ignore[union-attr]
                    continue
                key = (m.start(), act, section + sub)
                found[key] = Citation(act, section, sub, m.start(), m.end(), m.group(0), pos)
            taken.append((m.start(), m.end()))
    return sorted(found.values(), key=lambda c: (c.start, c.pos))


BRIDGE = re.compile(
    r"\b(correspond\w*|equivalent|erstwhile|now|earlier|previously|formerly|old|new|pari\s+materia|"
    r"replaced|in\s+place\s+of|analogous|i\.e\.|which\s+was)\b",
    re.I,
)
ERA = {"BNS": "IPC", "BNSS": "CRPC", "BSA": "IEA"}


def bridges(text: str, cites: list[Citation], max_gap: int = 80) -> list[tuple[str, str, str]]:
    """(new_id, old_id, snippet) where the court itself links an old and a new provision.

    Citations written as one list ("ss.340 and 341 BNSS") share a start offset. When a court
    bridges two lists of equal length ("ss.340 and 341 BNSS correspond to ss.303 and 304 CrPC")
    they are aligned by position; otherwise only single-to-single links are kept.
    """
    groups: list[list[Citation]] = []
    for c in cites:
        if groups and groups[-1][0].start == c.start and groups[-1][0].act == c.act:
            groups[-1].append(c)
        else:
            groups.append([c])
    out = []
    for a, b in zip(groups, groups[1:], strict=False):
        acts = {a[0].act, b[0].act}
        gap = b[0].start - a[0].end
        for new, old in ERA.items():
            if acts != {new, old} or not (0 <= gap <= max_gap) or not BRIDGE.search(text[a[0].end : b[0].start + 10]):
                continue
            ns, os_ = (a, b) if a[0].act == new else (b, a)
            if len(ns) != len(os_):  # "302(1), 302(2)" may stand for one section
                ns, os_ = _dedupe(ns), _dedupe(os_)
            if len(ns) == len(os_):
                snippet = text[a[0].start : b[0].end]
                out += [(n.provision_id, o.provision_id, snippet) for n, o in zip(ns, os_, strict=True)]
    return out


def _dedupe(cs: list[Citation]) -> list[Citation]:
    """One entry per section, in order ("302(1)" and "302(2)" count once)."""
    seen: dict[str, Citation] = {}
    for c in sorted(cs, key=lambda c: (c.start, c.pos)):
        seen.setdefault(c.section, c)
    return list(seen.values())


# Precision / recall of the citation extractor on the hand-labelled gold set.
#
# Gold scope: citations of the six criminal codes (and the 1898 CrPC) where the Act is
# named in the same sentence. "Section 313 of the Code" is labelled as no citation, by design.
DEV = ROOT / "eval" / "citation_extractor_dev.jsonl"
TEST = ROOT / "eval" / "citation_extractor_test.jsonl"  # held out: never used while tuning


def evaluate(path: Path = TEST) -> dict[str, object]:
    tp = fp = fn = 0
    errors = []
    for line in path.read_text().splitlines():
        item = json.loads(line)
        when = date.fromisoformat(item["date"])
        got = {f"{c.act}:{c.section}{c.sub}" for c in extract(item["text"], when)}
        want = set(item["expected"])
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
        if got != want:
            errors.append({"i": item["i"], "missed": sorted(want - got), "extra": sorted(got - want)})
    p = tp / max(1, tp + fp)
    r = tp / max(1, tp + fn)
    return {
        "precision": round(p, 3),
        "recall": round(r, 3),
        "f1": round(2 * p * r / max(1e-9, p + r), 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "errors": errors,
    }
