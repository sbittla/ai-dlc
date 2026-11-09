"""Checks on a data protection impact assessment written as structured data (starter: TODOs).

The checks test that the document contains what GDPR Article 35(7) asks a DPIA to contain, and that every
data flow involving agents and models has a purpose, a basis, a retention period within policy, a residency,
recorded processor terms and a minimization measure. They cannot judge whether the answers are true or the
risks complete; the data protection officer does that.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTIONS = ("description", "necessity_proportionality", "risks")


@dataclass(frozen=True)
class Finding:
    rule: str
    subject: str
    message: str


def check_dpia(dpia: dict, retention_policy: dict) -> list[Finding]:
    """Findings in this order: document sections, then each flow in order, then each risk, then consultation.

    DP001  each of SECTIONS missing or empty, in SECTIONS order      -> subject "document", "missing <section>"
    For each flow (subject = its id), in this order:
    DP002  purpose or lawful_basis missing                           -> "no purpose" / "no lawful basis"
                                                                        (one finding naming the first missing)
    DP003  retention_days is None                                    -> "no retention period (kept indefinitely)"
           retention_days above max_retention_days[kind]             -> "retention <n> days, above the policy's <m>"
    DP004  processor present and its terms missing                   -> "processor <name>: data-use terms not recorded"
    DP005  residency missing                                         -> "no residency recorded"
    DP007  personal_data non-empty and minimisation missing          -> "personal data with no minimisation measure"
    For each risk (subject = its id):
    DP006  owner missing                                             -> "no owner"
           measures empty                                            -> "no measures"
    DP008  dpo_consulted missing                                     -> subject "document", "no DPO consultation recorded"
           review_by missing                                         -> subject "document", "no review date"
    "Missing" means absent, None, or empty.
    """
    raise NotImplementedError("TODO 2: check the DPIA")
