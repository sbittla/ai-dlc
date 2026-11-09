"""A first-pass EU AI Act classification of Relay's features (starter: TODOs).

This is a triage tool for a governance review, not a legal determination. It applies a fixed order of
questions to the team's recorded answers, cites the provision each answer points to, and leaves the final
reading to a qualified person. Its output says so.
"""

from __future__ import annotations

from dataclasses import dataclass

HIGH_RISK_DUTIES = ("risk management (Art. 9)", "data governance (Art. 10)", "technical documentation (Art. 11)",
                    "record-keeping (Art. 12)", "information to deployers (Art. 13)", "human oversight (Art. 14)",
                    "accuracy, robustness and cybersecurity (Art. 15)", "conformity assessment and registration")
LITERACY = "measures to support AI literacy of staff (Art. 4, as amended in 2026)"


@dataclass(frozen=True)
class Classification:
    feature: str
    tier: str
    role: str
    basis: str
    applies_from: str | None
    obligations: tuple[str, ...]


def classify_feature(f: dict, dates: dict) -> Classification:
    """Classify one feature. Questions, in this order; the first that applies decides the tier:

    1. not f["ai_system"]            -> tier "outside the definition", basis "not an AI system (Art. 3(1)) on the
                                        team's answers", applies_from None, obligations ()
    2. f["prohibited_practice"]      -> "prohibited", basis = that text, applies_from dates["prohibited"],
                                        obligations ("do not build or place on the market",)
    3. f["annex_iii_area"] and (f["profiles_people"] or not f["narrow_procedural_task"])
                                     -> "high-risk", basis "Annex III " + the area, plus
                                        "; it profiles people, so the Art. 6(3) exception cannot apply" when
                                        profiles_people; applies_from dates["high-risk (Annex III)"];
                                        obligations HIGH_RISK_DUTIES + (LITERACY,)
    4. f["interacts_with_people"] or f["generates_synthetic_content"]
                                     -> "transparency", basis: "Art. 50(1)" if it interacts, "Art. 50(2)" if it
                                        generates content, joined by " and "; applies_from dates["transparency"];
                                        obligations: "tell people they are interacting with an AI system" if
                                        50(1), "mark generated content as machine-generated" if 50(2), then LITERACY
    5. otherwise                     -> "minimal", basis "no Art. 5, Annex III or Art. 50 trigger on the team's
                                        answers", applies_from dates["ai_literacy"], obligations (LITERACY,)
    role is "provider" if f["placed_on_market"] else "deployer".
    """
    raise NotImplementedError("TODO 1: classify one feature")
