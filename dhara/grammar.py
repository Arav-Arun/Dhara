"""Split a section's paragraphs into citable parts.

Statutes follow a small, regular grammar: numbered sub-sections "(1)", provisos
("Provided that"), explanations, exceptions and illustrations. Clauses "(a)" stay
inside the sub-section they belong to; inside an "Illustrations" block each "(a)"
is its own illustration. Rules beat a model here: the format is regular and every
mistake is visible in the spot-check report."""

import re

from dhara.models import Changes, Part

SUBSECTION = re.compile(r"^\((\d+[A-Z]?)\)\s*")
CLAUSE = re.compile(r"^\(([a-z]{1,4})\)\s*")
PROVISO = re.compile(r"^Provided\b")
EXPLANATION = re.compile(r"^Explanation\s*(\d*)\s*\.?\s*[—–-]*\s*", re.I)
EXCEPTION = re.compile(r"^Exception\s*(\d*)\s*\.?\s*[—–-]*\s*", re.I)
ILLUSTRATIONS = re.compile(r"^Illustrations?\s*\.?$", re.I)


def split_parts(paras: list[tuple[str, Changes]]) -> list[Part]:
    parts: list[Part] = []
    in_illustrations = False

    def start(kind: str, label: str, text: str, ch: Changes) -> None:
        parts.append(Part(kind=kind, label=label, text=text.strip(), changes=ch))  # type: ignore[arg-type]

    for raw, ch in paras:
        text = raw.strip()
        if not text:
            continue
        if ILLUSTRATIONS.match(text):
            in_illustrations = True
            continue
        if m := EXPLANATION.match(text):
            in_illustrations = False
            start("explanation", f"Explanation {m.group(1)}".strip(), text[m.end() :], ch)
        elif m := EXCEPTION.match(text):
            in_illustrations = False
            start("exception", f"Exception {m.group(1)}".strip(), text[m.end() :], ch)
        elif PROVISO.match(text):
            start("proviso", "Proviso", text, ch)
        elif m := SUBSECTION.match(text):  # a numbered subsection also ends a run of illustrations (BNS 318(2))
            in_illustrations = False
            start("subsection", f"({m.group(1)})", text[m.end() :], ch)
        elif in_illustrations:
            m = CLAUSE.match(text)
            start("illustration", f"({m.group(1)})" if m else "", text[m.end() :] if m else text, ch)
        elif parts:
            _append(parts[-1], text, ch)
        else:
            start("body", "", text, ch)
    return parts


def _append(part: Part, text: str, ch: Changes) -> None:
    part.text = f"{part.text}\n{text}"
    part.changes.added += ch.added
    part.changes.changed += ch.changed
    part.changes.deleted += ch.deleted
