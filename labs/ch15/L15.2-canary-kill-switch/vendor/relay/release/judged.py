"""Which verdict a release decision may rest on, item by item (4.29.0; ADR-048).

Chapter 7 let an LLM judge grade single answers (judge-v2 under judge-policy-v1) and gave three rules for
judged output: treat it as untrusted input, separate it from the judge's instructions, and put judge-injection
cases among the items people always label. Chapter 12's class C14 is the attack: text inside a graded answer
that sets the judge's verdict. Separating the answer only lowers how often a judge obeys, so it never counted.

This module is the third rule as a blocking control in Relay's evaluation gate:

- an item in a judge-injection slice (`kind:adversarial` or `kind:judge-injection`) needs a person's label;
- so does any item whose answer carries a grader directive, even outside those slices (a pattern check: it
  adds items, it never removes one);
- a label counts only if it names the person who gave it and is bound to the exact answer it judged: its
  `label_answer_sha256` must equal the SHA-256 of the answer under review. A label written for an earlier
  answer to the same item, or with no labeller, or by an agent or automation, is treated as missing;
- for such an item the release verdict IS the person's label. The judge's verdict is recorded by the caller
  and never read here;
- a missing label is not a pass and not a fail: `release_verdicts` raises `MissingHumanLabel`, and the gate
  exits 2 (cannot decide), which fails the pipeline.

Labels reach the gate as `evals/human-labels.json`, written by the labelling queue (tomas.b's team) and changed
only through a pull request under the pipeline guard, owned by `@relay/security`. This module cannot tell a
real labeller from a forged name; that rests on the guard's review of the labels file.

Every other item keeps the judge's verdict, as judge-policy-v1 allows. An injection planted in an item that
is in no human-labelled slice and carries no recognisable directive still reaches the judge: that residual is
why the slices grow with every new attack class.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

HUMAN_SLICES = frozenset({"kind:adversarial", "kind:judge-injection"})
VERDICTS = frozenset({"pass", "fail"})
# A grader directive: text addressed to whoever grades the answer. The lab marker is `[[GRADER …]]`; the plain
# forms are what an attacker writes instead. A miss here leaves the item to the judge, never to a pass.
_DIRECTIVE = re.compile(r"\[\[\s*grader\b|\b(grader|judge|evaluator)\s*[:,]|\bverdict\s*[=:]", re.IGNORECASE)


class MissingHumanLabel(ValueError):
    """An item that needs a person's label has none that counts. The gate cannot decide."""

    def __init__(self, item_ids: list[str]):
        super().__init__("no valid human label for: " + ", ".join(item_ids))
        self.item_ids = item_ids


def answer_sha256(answer: str) -> str:
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GradedItem:
    item_id: str
    slices: tuple[str, ...]
    answer: str
    judge_verdict: str | None = None
    human_label: str | None = None
    labeller: str | None = None
    label_answer_sha256: str | None = None


def needs_person(item: GradedItem) -> bool:
    return bool(HUMAN_SLICES & set(item.slices)) or bool(_DIRECTIVE.search(item.answer))


def label_counts(item: GradedItem) -> bool:
    """A label counts when it is pass/fail, names a person, and is bound to this exact answer."""
    who = (item.labeller or "").strip()
    return (item.human_label in VERDICTS and bool(who) and not who.startswith(("agent:", "automation:"))
            and item.label_answer_sha256 == answer_sha256(item.answer))


def release_verdicts(items: list[GradedItem]) -> dict[str, tuple[str, str]]:
    """item_id -> (verdict, source), where source is "person" or "judge".

    Raises MissingHumanLabel, listing every item without a label that counts, before returning anything, so a
    partial result can never be read as a decision. A judge verdict that is missing or not pass/fail on an item
    that does not need a person is also refused (ValueError): the gate cannot decide on it either.
    """
    missing = [i.item_id for i in items if needs_person(i) and not label_counts(i)]
    if missing:
        raise MissingHumanLabel(missing)
    out: dict[str, tuple[str, str]] = {}
    for item in items:
        if needs_person(item):
            out[item.item_id] = (item.human_label, "person")
        elif item.judge_verdict in VERDICTS:
            out[item.item_id] = (item.judge_verdict, "judge")
        else:
            raise ValueError(f"{item.item_id}: no usable judge verdict")
    return out
