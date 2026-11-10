"""Gate G4's adversarial row on a date (TODO 5 in starter/).

The row (Chapter 12, relay-coverage-gate-v2): the coverage gate passes on the release's own artefacts, AND every
control the gate counts has deployment evidence. Deployment evidence is a record in `data/deployments.json`:
a post-deploy check of that control in production, with a date, an owner and a result. The records are
GENERATED: they stand for checks this offline lab cannot run.

The row cannot be waived, so there is no override here.
"""

from __future__ import annotations

from . import adversarial


def deployed(records: list[dict], control: str, as_of: str) -> dict | None:
    """The first passing record for `control` dated on or before `as_of` (ISO dates compare as strings)."""
    for r in records:
        if r["control"] == control and r["result"] == "pass" and r["date"] <= as_of:
            return r
    return None


def g4_row(matrix, records: list[dict], as_of: str) -> tuple[bool, list[str]]:
    """(met, reasons). Reasons: the coverage gate's own reasons first, then one line per counted control
    without deployment evidence by `as_of`, in counted order:
    '<control>: no deployment evidence by <as_of> (owner <owner>, due <due>)', taking owner and due from the
    control's catalogue entry (`deploy_owner`, `deploy_due`)."""
    passed, reasons = adversarial.gate(matrix)
    missing = []
    for control in adversarial.counted(matrix):
        if deployed(records, control, as_of) is None:
            info = matrix.controls[control]
            missing.append(f"{control}: no deployment evidence by {as_of} "
                           f"(owner {info.get('deploy_owner', '?')}, due {info.get('deploy_due', '?')})")
    return passed and not missing, reasons + missing
