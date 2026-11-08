"""Judges: two simulated LLM judges (default) and an optional live Claude judge.

The simulated judges are NOT real models. They are seeded random processes
whose biases are CONFIGURED in PROFILES below: how often each passes a
correct answer, how often it passes a wrong one (more often when the wrong
answer is long, or written by its own model family), and how often it simply
picks whichever answer it is shown first. The probes in this lab will find
exactly these biases, because they were put there. What transfers is the
calibration method, not the numbers.

The live adapter follows Lab 2.1's (labs/ch02/L2.1-model-eval-harness/
solution/harness/models.py): structured output, and refusals, truncation and
API errors recorded as "no verdict" rather than raised.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

JUDGE_FAMILY = "large"  # the judge is a large model, the same family as one of the assistants

GRADE_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]}},
                "required": ["verdict"], "additionalProperties": False}
PREFER_SCHEMA = {"type": "object", "properties": {"preferred": {"type": "string", "enum": ["A", "B"]}},
                 "required": ["preferred"], "additionalProperties": False}

PROMPTS = {
    "judge-v1": {
        "grade": ("You review answers written by Relay's support assistant.\n"
                  "Decide whether the answer is a good answer to the customer's question.\n"
                  'Reply with JSON only: {"verdict": "pass"} or {"verdict": "fail"}.'),
        "prefer": ("You compare two answers written by Relay's support assistant.\n"
                   "Decide which answer is better for the customer.\n"
                   'Reply with JSON only: {"preferred": "A"} or {"preferred": "B"}.'),
    },
    "judge-v2": {
        "grade": ("You check answers written by Relay's support assistant against a reference answer\n"
                  "written by Relay's support leads.\n"
                  "Pass the answer only if every factual claim in it agrees with the reference.\n"
                  "Ignore length, tone and politeness: a longer or friendlier answer is not better.\n"
                  "If the answer adds a fact the reference does not support, fail it.\n"
                  'Reply with JSON only: {"verdict": "pass"} or {"verdict": "fail"}.'),
        "prefer": ("You compare two answers against a reference answer written by Relay's support leads.\n"
                   "Prefer the answer whose factual claims agree with the reference.\n"
                   "Ignore length, tone and the order in which the answers appear.\n"
                   'Reply with JSON only: {"preferred": "A"} or {"preferred": "B"}.'),
    },
}


def grade_message(item: dict, with_reference: bool) -> str:
    ref = f"<reference>\n{item['reference']}\n</reference>\n" if with_reference else ""
    return f"<question>\n{item['question']}\n</question>\n{ref}<answer>\n{item['answer']}\n</answer>"


def prefer_message(question: str, reference: str, first: str, second: str, with_reference: bool) -> str:
    ref = f"<reference>\n{reference}\n</reference>\n" if with_reference else ""
    return (f"<question>\n{question}\n</question>\n{ref}"
            f"<answer_a>\n{first}\n</answer_a>\n<answer_b>\n{second}\n</answer_b>")


# ------------------------------------------------------------------ simulated

@dataclass(frozen=True)
class Profile:
    pass_correct: float          # P(pass | the answer is correct)
    pass_wrong: dict[str, float]  # P(pass | wrong), by answer style: concise or verbose
    self_bonus: float            # added to P(pass | wrong) when the judge's own family wrote it
    prefer_correct: float        # P(prefer the correct answer), before biases
    prefer_verbose_penalty: float  # subtracted when the wrong answer is the verbose one
    prefer_self_penalty: float   # subtracted when the judge's own family wrote the wrong answer
    first_position: float        # P(pick whichever answer is shown first, regardless of content)


PROFILES = {
    "judge-v1": Profile(0.93, {"concise": 0.15, "verbose": 0.45}, 0.15, 0.85, 0.15, 0.10, 0.30),
    "judge-v2": Profile(0.95, {"concise": 0.05, "verbose": 0.08}, 0.03, 0.95, 0.03, 0.02, 0.08),
}


@dataclass
class SimulatedJudge:
    name: str
    seed: int = 13

    def __post_init__(self) -> None:
        if self.name not in PROFILES:
            raise ValueError(f"no simulated profile is configured for {self.name}")
        self.p = PROFILES[self.name]

    def _u(self, *parts) -> float:
        return random.Random("|".join(str(x) for x in (self.seed, self.name, *parts))).random()

    def grade(self, item: dict) -> str | None:
        if item["human"] == "pass":
            p = self.p.pass_correct
        else:
            p = self.p.pass_wrong[item["style"]] + (self.p.self_bonus if item["source_family"] == JUDGE_FAMILY else 0)
        return "pass" if self._u(item["id"], "grade") < p else "fail"

    def prefer(self, pair_id: str, order: str, first: dict, second: dict) -> str | None:
        """'A' if the judge prefers the answer shown first, 'B' otherwise."""
        if self._u(pair_id, order, "position") < self.p.first_position:
            return "A"
        right, wrong = (first, second) if first["human"] == "pass" else (second, first)
        p = self.p.prefer_correct
        p -= self.p.prefer_verbose_penalty if wrong["style"] == "verbose" else 0
        p -= self.p.prefer_self_penalty if wrong["source_family"] == JUDGE_FAMILY else 0
        picks_right = self._u(pair_id, order, "pick") < p
        chosen = right if picks_right else wrong
        return "A" if chosen is first else "B"


# ------------------------------------------------------------------ live

def _api_errors() -> tuple:
    """The SDK's error class, or nothing to catch when the SDK is not installed."""
    try:
        import anthropic
    except ImportError:
        return ()
    return (anthropic.APIError,)


@dataclass
class ClaudeJudge:
    """Live judge via the official Anthropic SDK (`pip install -e ".[live]"`), adapted from Lab 2.1.

    Any refusal, truncation or API error returns None ("no verdict"), which the
    metrics count as a disagreement with the humans. Nothing is retried silently.
    """

    name: str            # the judge prompt version, e.g. "judge-v2"
    model: str           # an exact model ID, e.g. "claude-opus-5-5"
    max_usd: float
    price_in_per_mtok: float = 4.00
    price_out_per_mtok: float = 20.00
    effort: str = "low"
    spent_usd: float = 0.0
    outcomes: dict[str, int] = field(default_factory=dict)
    _client: object = field(default=None, init=False, repr=False)

    def _call(self, system: str, user: str, schema: dict, key: str) -> str | None:
        if self.spent_usd + 0.01 > self.max_usd:   # 0.01 USD: a pessimistic cost for one judge call
            self.outcomes["budget"] = self.outcomes.get("budget", 0) + 1
            return None
        if self._client is None:
            import anthropic  # imported lazily so offline runs need no package
            self._client = anthropic.Anthropic()
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            )
        except _api_errors() as exc:
            kind = f"api_error:{type(exc).__name__}"
            self.outcomes[kind] = self.outcomes.get(kind, 0) + 1
            return None
        self.spent_usd += (response.usage.input_tokens * self.price_in_per_mtok
                           + response.usage.output_tokens * self.price_out_per_mtok) / 1_000_000
        stop = response.stop_reason or ""
        if stop in ("refusal", "max_tokens"):
            self.outcomes[stop] = self.outcomes.get(stop, 0) + 1
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            value = json.loads(text)[key]
        except (json.JSONDecodeError, KeyError, TypeError):
            self.outcomes["invalid"] = self.outcomes.get("invalid", 0) + 1
            return None
        return value if value in schema["properties"][key]["enum"] else None

    def grade(self, item: dict) -> str | None:
        return self._call(PROMPTS[self.name]["grade"], grade_message(item, self.name != "judge-v1"),
                          GRADE_SCHEMA, "verdict")

    def prefer(self, pair_id: str, order: str, first: dict, second: dict) -> str | None:
        msg = prefer_message(first["question"], first["reference"], first["answer"], second["answer"],
                             self.name != "judge-v1")
        return self._call(PROMPTS[self.name]["prefer"], msg, PREFER_SCHEMA, "preferred")
