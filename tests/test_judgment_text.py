from dhara.judgments import chunk, split

TEXT = """[2025] 1 S.C.R. 10 : 2025 INSC 1
A v. State
Headnotes Penal Code, 1860 – s.302 – Conviction upheld.
CRIMINAL APPELLATE JURISDICTION: Criminal Appeal No. 1 of 2025
Judgment
1. The appellant was convicted under Section 302 IPC and the High Court affirmed.
2. The only question is whether the dying declaration was reliable. The witnesses were:
3. PW-1, the brother of the deceased, deposed that he saw the incident.
4. We find no reason to interfere. The appeal is dismissed.
"""


def test_split_headnote_and_numbered_paragraphs() -> None:
    head, paras = split(TEXT)
    assert "Headnotes" in head and "JURISDICTION" not in head
    assert [p for p, _ in paras if p] == [1, 2, 3, 4]


def test_chunks_keep_paragraph_ranges() -> None:
    head, paras = split(TEXT)
    chunks = chunk(head, paras)
    roles = {c.role for c in chunks}
    assert roles == {"headnote", "judgment"}
    body = [c for c in chunks if c.role == "judgment" and c.para_from]
    assert body[0].para_from == 1 and body[-1].para_to == 4
