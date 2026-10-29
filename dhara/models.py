"""Typed records shared across ingestion, retrieval and the API."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PartKind = Literal["body", "subsection", "proviso", "explanation", "exception", "illustration"]
Status = Literal["in_force", "repealed", "omitted", "not_commenced"]


class Changes(BaseModel):
    """What changed relative to the old code, as marked up in the official NCRB text."""

    added: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)


class Part(BaseModel):
    """One citable piece of a section: a sub-section, proviso, explanation, etc."""

    kind: PartKind
    label: str = ""  # "(2)", "Explanation 1", "(a)" for illustrations
    text: str
    status: Status = "in_force"
    changes: Changes = Field(default_factory=Changes)


class Section(BaseModel):
    act: str  # BNS, BNSS, BSA, IPC, CRPC, IEA
    number: str  # "103", "65B"
    heading: str
    chapter_no: str = ""
    chapter_title: str = ""
    subheading: str = ""  # e.g. "Of offences affecting life"
    parts: list[Part]
    status: Status = "in_force"
    flag: Literal["", "new", "change"] = ""  # NCRB marker on the heading
    notes: list[str] = Field(default_factory=list)
    source_page: int | None = None  # PDF page, for the spot-check report

    @property
    def id(self) -> str:
        return f"{self.act}:{self.number}"

    @property
    def text(self) -> str:
        return "\n".join(f"{p.label} {p.text}".strip() for p in self.parts)


class Act(BaseModel):
    code: str
    title: str
    act_no: str
    in_force_from: date
    in_force_to: date | None = None
    replaced_by: str | None = None
    source: str
