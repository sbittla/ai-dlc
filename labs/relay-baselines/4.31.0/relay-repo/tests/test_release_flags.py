"""Feature flags and kill switches for AI features (4.29.0, ADR-047). Hand-checkable cases."""

import json
import sqlite3
from pathlib import Path

import pytest

from relay.release import FlagError, FlagSet, KillStore
from relay.release.flags import bucket

ROOT = Path(__file__).resolve().parent.parent
PEOPLE = frozenset({"sam.o", "lena.k", "aisha.r"})


def doc(**features):
    return {"policy": "relay-flags-v1", "features": features}


def store():
    return KillStore(sqlite3.connect(":memory:"), PEOPLE)


def test_the_committed_flag_document_is_valid_and_every_feature_is_ai_with_an_owner():
    d = json.loads((ROOT / "deploy" / "flags.json").read_text(encoding="utf-8"))
    flags = FlagSet(d, store())
    assert flags.features() == ["ticket_summaries", "triage_routing_c", "triage_suggestions"]
    assert all(e["ai"] and e["owner"] for e in d["features"].values())
    assert flags.enabled("triage_suggestions", "ws-1") and not flags.enabled("triage_routing_c", "ws-1")


def test_bucket_is_stable_and_spread():
    assert bucket("f", "ws-1") == bucket("f", "ws-1")
    shares = sum(bucket("f", f"ws-{i}") < 25 for i in range(2000)) / 2000
    assert 0.22 < shares < 0.28


def test_rollout_grows_without_dropping_anyone():
    small = FlagSet(doc(f={"ai": True, "rollout_percent": 10}), store())
    large = FlagSet(doc(f={"ai": True, "rollout_percent": 50}), store())
    on_small = {w for w in (f"ws-{i}" for i in range(500)) if small.enabled("f", w)}
    on_large = {w for w in (f"ws-{i}" for i in range(500)) if large.enabled("f", w)}
    assert on_small and on_small < on_large


@pytest.mark.parametrize("document", [
    None, [], {"policy": "other", "features": {"f": {"ai": True, "rollout_percent": 100}}},
    doc(f={"ai": True, "rollout_percent": "100"}), doc(f={"ai": True, "rollout_percent": 101}),
    doc(f={"ai": True, "rollout_percent": True}), doc(f={"ai": "yes", "rollout_percent": 100}),
    doc(f={"ai": True, "rollout_percent": 100, "killed": "no"}), doc(f="on"), doc(),
])
def test_anything_malformed_or_unknown_is_off(document):
    assert FlagSet(document, store()).enabled("f", "ws-1") is False


def test_an_ai_feature_without_a_kill_store_is_off_and_a_plain_feature_is_not():
    d = doc(ai_f={"ai": True, "rollout_percent": 100}, plain={"ai": False, "rollout_percent": 100})
    assert FlagSet(d).enabled("ai_f", "ws-1") is False
    assert FlagSet(d).enabled("plain", "ws-1") is True


def test_a_trip_beats_100_percent_and_takes_effect_on_the_next_decision():
    kills = store()
    flags = FlagSet(doc(f={"ai": True, "rollout_percent": 100}), kills)
    assert flags.enabled("f", "ws-1")
    kills.trip("f", "automation:canary-ai-quality", "SLO-TRIAGE-QUALITY breach on the canary", "2027-05-04T15:20Z")
    assert not flags.enabled("f", "ws-1")
    kills.trip("f", "sam.o", "second trip is harmless", "2027-05-04T15:21Z")
    assert kills.killed("f")


def test_the_document_can_also_kill():
    assert not FlagSet(doc(f={"ai": True, "rollout_percent": 100, "killed": True}), store()).enabled("f", "w")


def test_trip_refusals_are_logged():
    kills = store()
    with pytest.raises(FlagError):
        kills.trip("f", "mallory", "no", "t1")
    with pytest.raises(FlagError):
        kills.trip("f", "automation:Bad Name", "x", "t2")
    with pytest.raises(FlagError):
        kills.trip("f", "sam.o", "  ", "t3")
    assert [r["outcome"] for r in kills.log()] == ["refused", "refused", "refused"]
    assert not kills.killed("f")


def test_only_a_person_restores_with_a_reason_that_names_a_ticket():
    kills = store()
    kills.trip("f", "automation:canary-ai-quality", "breach", "t1")
    for actor, reason in [("automation:canary-ai-quality", "RLY-2701: the fix passed the eval gate on 5 May"),
                          ("mallory", "RLY-2701: the fix passed the eval gate on 5 May"),
                          ("sam.o", "fixed"), ("sam.o", "RLY-2701: too short")]:
        with pytest.raises(FlagError):
            kills.restore("f", actor, reason, "t2")
    assert kills.killed("f")
    kills.restore("f", "lena.k", "RLY-2701: the fix passed the eval gate on 5 May", "t3")
    assert not kills.killed("f")
    with pytest.raises(FlagError):
        kills.restore("f", "lena.k", "RLY-2701: the fix passed the eval gate on 5 May", "t4")
    log = kills.log()
    assert [(r["action"], r["outcome"]) for r in log] == [("trip", "done")] + [("restore", "refused")] * 4 + [
        ("restore", "done"), ("restore", "refused")]
