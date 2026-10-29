from dhara.grammar import split_parts
from dhara.models import Changes


def _parts(*paras: str) -> list[tuple[str, str]]:
    return [(p.kind, p.label) for p in split_parts([(x, Changes()) for x in paras])]


def test_subsections_clauses_and_provisos() -> None:
    got = _parts(
        "(1) Whoever—",
        "(a) does one thing; or",
        "(b) does another,",
        "shall be punished.",
        "Provided that this is a proviso.",
        "(2) Second sub-section.",
    )
    assert got == [("subsection", "(1)"), ("proviso", "Proviso"), ("subsection", "(2)")]


def test_illustrations_explanations_exceptions() -> None:
    got = _parts(
        "Whoever causes death commits culpable homicide.",
        "Illustrations",
        "(a) A lays sticks over a pit.",
        "(b) A knows Z to be behind a bush.",
        "Explanation 1.—A person who causes injury.",
        "Exception 1.—When provoked.",
    )
    assert got == [
        ("body", ""),
        ("illustration", "(a)"),
        ("illustration", "(b)"),
        ("explanation", "Explanation 1"),
        ("exception", "Exception 1"),
    ]


def test_clause_text_stays_with_its_subsection() -> None:
    parts = split_parts([("(1) Whoever—", Changes()), ("(a) does a thing,", Changes())])
    assert parts[0].text == "Whoever—\n(a) does a thing,"


def test_numbered_subsection_after_illustrations_is_a_subsection() -> None:
    # BNS 318: the illustrations follow sub-section (1), and (2) to (4) come after them
    got = _parts("(1) Whoever deceives...", "Illustrations", "(a) A deceives Z.", "(2) Whoever cheats is punished.")
    assert got == [("subsection", "(1)"), ("illustration", "(a)"), ("subsection", "(2)")]
