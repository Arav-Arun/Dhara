"""Which code applies? Rules, not a model.

Substantive law follows the date of the offence: IPC up to 30 June 2024, BNS from 1 July 2024
(Article 20(1) of the Constitution bars retrospective penal law; BNS s.358 saves the IPC for
earlier acts). Procedure and evidence follow the proceeding: BNSS s.531(2)(a) keeps the CrPC for
appeals, applications, trials, inquiries and investigations pending on 1 July 2024; BSA s.170
saves the Evidence Act for pending proceedings in the same way. Where courts have disagreed
(an FIR registered after 1 July 2024 for an earlier offence), we say so instead of choosing.
"""

from dataclasses import dataclass
from datetime import date

CUTOVER = date(2024, 7, 1)


@dataclass
class Resolution:
    area: str  # "substantive" | "procedure" | "evidence"
    code: str  # "IPC", "BNS", "CRPC", "BNSS", "IEA", "BSA", or "contested"
    reason: str
    basis: list[str]


def applicable(offence_date: date, proceeding_started: date | None = None) -> list[Resolution]:
    """`proceeding_started`: FIR/complaint date (or first proceeding), if known."""
    sub = (
        Resolution(
            "substantive",
            "IPC",
            "Offence committed before 1 July 2024: the IPC defines it and fixes punishment.",
            ["BNS:358", "Art. 20(1) Constitution"],
        )
        if offence_date < CUTOVER
        else Resolution("substantive", "BNS", "Offence committed on or after 1 July 2024.", ["BNS:1"])
    )
    out = [sub]
    started = proceeding_started or offence_date
    if started < CUTOVER:
        out.append(
            Resolution(
                "procedure",
                "CRPC",
                "Proceedings were pending on 1 July 2024, so they continue under the CrPC.",
                ["BNSS:531"],
            )
        )
        out.append(Resolution("evidence", "IEA", "Pending proceedings keep the Evidence Act.", ["BSA:170"]))
    elif offence_date < CUTOVER:
        out.append(
            Resolution(
                "procedure",
                "contested",
                "Old offence, but the FIR or proceeding started after 1 July "
                "2024. Courts have read BNSS s.531 differently here; most apply the BNSS to the new "
                "proceeding. Check current High Court and Supreme Court authority.",
                ["BNSS:531"],
            )
        )
        out.append(
            Resolution("evidence", "BSA", "Evidence is led in a proceeding that began after 1 July 2024.", ["BSA:170"])
        )
    else:
        out.append(Resolution("procedure", "BNSS", "Proceeding began on or after 1 July 2024.", ["BNSS:1"]))
        out.append(Resolution("evidence", "BSA", "Proceeding began on or after 1 July 2024.", ["BSA:1"]))
    return out
