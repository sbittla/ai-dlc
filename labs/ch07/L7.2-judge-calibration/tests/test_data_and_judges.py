"""Provided code: the dataset, the simulated judges and the live judge's failure handling."""

import json
import subprocess
import sys

import pytest
from conftest import DATA_DIR, LAB_ROOT

from judgecal import calibrate, judges

ANSWERS = calibrate.load(DATA_DIR / "answers.jsonl")
PAIRS = calibrate.load(DATA_DIR / "pairs.jsonl")


def test_dataset_shape_and_split_by_fact():
    assert len(ANSWERS) == 180 and len(PAIRS) == 90
    cal = {a["fact"] for a in ANSWERS if a["split"] == "calibration"}
    held = {a["fact"] for a in ANSWERS if a["split"] == "heldout"}
    assert len(cal) == 10 and len(held) == 20 and not cal & held


def test_every_pair_has_one_right_and_one_wrong_answer():
    by_id = {a["id"]: a for a in ANSWERS}
    for p in PAIRS:
        a, b = by_id[p["a"]], by_id[p["b"]]
        assert {a["human"], b["human"]} == {"pass", "fail"}
        assert p["human_preferred"] == ("A" if a["human"] == "pass" else "B")


def test_generator_reproduces_the_data_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    for name in ("answers.jsonl", "pairs.jsonl", "manifest.json"):
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name


def test_simulated_judges_are_deterministic_and_only_configured():
    a, b = judges.SimulatedJudge("judge-v1"), judges.SimulatedJudge("judge-v1")
    assert [a.grade(x) for x in ANSWERS] == [b.grade(x) for x in ANSWERS]
    with pytest.raises(ValueError):
        judges.SimulatedJudge("judge-v9")


def test_reference_answer_only_in_v2_messages():
    item = ANSWERS[0]
    assert "<reference>" in judges.grade_message(item, True)
    assert "<reference>" not in judges.grade_message(item, False)


class FakeResponse:
    def __init__(self, text, stop="end_turn"):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.stop_reason = stop
        self.usage = type("U", (), {"input_tokens": 100, "output_tokens": 10})()


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = self

    def create(self, **kwargs):
        return self.responses.pop(0)


@pytest.mark.parametrize("response, outcome", [
    (FakeResponse("", "refusal"), "refusal"),
    (FakeResponse('{"verdict"', "max_tokens"), "max_tokens"),
    (FakeResponse("Sure! pass"), "invalid"),
])
def test_live_judge_records_failures_as_no_verdict(response, outcome):
    j = judges.ClaudeJudge("judge-v2", "claude-opus-5-5", max_usd=1.0)
    j._client = FakeClient([response])
    assert j.grade(ANSWERS[0]) is None
    assert j.outcomes == {outcome: 1}


def test_live_judge_stops_at_the_ceiling():
    j = judges.ClaudeJudge("judge-v2", "claude-opus-5-5", max_usd=0.005)
    assert j.grade(ANSWERS[0]) is None and j.outcomes == {"budget": 1}


def test_live_judge_parses_a_verdict():
    j = judges.ClaudeJudge("judge-v2", "claude-opus-5-5", max_usd=1.0)
    j._client = FakeClient([FakeResponse(json.dumps({"verdict": "fail"}))])
    assert j.grade(ANSWERS[0]) == "fail" and j.spent_usd == pytest.approx((100 * 4 + 10 * 20) / 1e6)
