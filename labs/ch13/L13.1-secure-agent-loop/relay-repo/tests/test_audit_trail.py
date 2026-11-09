"""The audit trail of agent actions (4.23.0, ADR-021): append-only, hash-chained, anchored, redacted."""

import json

import pytest

from relay.audit import GENESIS, AuditTrail, load, record_hash, verify


def clock(times):
    it = iter(times)
    return lambda: next(it)


def three(path=None):
    trail = AuditTrail(path, clock=clock(["2027-01-06T10:00:00Z", "2027-01-06T10:00:02Z", "2027-01-06T10:00:04Z"]))
    for n in range(3):
        trail.append(agent_id="eval-harvester", owner="tomas.b", on_behalf_of="tomas.b", credential=f"jti-{n}",
                     action="tickets.list", resource="workspace:support/project:support-inbox", outcome="ok",
                     source="github-actions", detail={"rows": 100})
    return trail


def test_records_are_numbered_and_chained_from_genesis():
    recs = three().records
    assert [r["seq"] for r in recs] == [1, 2, 3]
    assert recs[0]["prev"] == GENESIS
    assert recs[1]["prev"] == recs[0]["hash"] and recs[2]["prev"] == recs[1]["hash"]
    assert all(r["hash"] == record_hash(r) for r in recs)
    assert verify(recs).ok and verify(recs).checked == 3


def test_an_edited_record_breaks_the_chain_at_that_record():
    recs = three().records
    recs[1] = {**recs[1], "detail": {"rows": 3}}
    v = verify(recs)
    assert (v.ok, v.seq, v.problem) == (False, 2, "hash mismatch")


def test_a_deleted_record_is_a_sequence_gap():
    recs = three().records
    v = verify([recs[0], recs[2]])
    assert (v.ok, v.seq, v.problem) == (False, 3, "sequence gap")


def test_an_edit_with_every_later_hash_recomputed_passes_the_chain_but_not_the_anchor():
    recs = three().records
    anchor = (3, recs[2]["hash"])
    forged = [dict(r) for r in recs]
    forged[1]["detail"] = {"rows": 3}
    forged[1]["hash"] = record_hash(forged[1])
    forged[2]["prev"] = forged[1]["hash"]
    forged[2]["hash"] = record_hash(forged[2])
    assert verify(forged).ok
    v = verify(forged, anchor)
    assert (v.ok, v.seq, v.problem) == (False, 3, "anchor mismatch")


def test_a_cut_tail_is_found_only_by_an_anchor():
    recs = three().records
    assert verify(recs[:2]).ok
    v = verify(recs[:2], (3, recs[2]["hash"]))
    assert (v.ok, v.problem) == (False, "truncated after anchor")


def test_detail_and_resource_are_redacted_before_they_are_written(tmp_path):
    trail = AuditTrail(tmp_path / "trail.jsonl", clock=lambda: "2027-01-06T10:00:00Z")
    rec = trail.append(agent_id="coding-session", owner="sam.o", on_behalf_of="priya.n", action="testdb.query",
                       resource="note for mara.ilves@example.com", outcome="ok",
                       detail={"token": "anything", "rows": 4})
    assert rec["resource"] == "note for [redacted:email]"
    assert rec["detail"] == {"token": "[redacted:sensitive-key]", "rows": 4}
    assert "mara.ilves" not in (tmp_path / "trail.jsonl").read_text(encoding="utf-8")
    assert dict(trail.redactions) == {"email": 1, "sensitive-key": 1}


def test_reopening_a_file_continues_its_chain(tmp_path):
    path = tmp_path / "trail.jsonl"
    first = three(path)
    again = AuditTrail(path, clock=lambda: "2027-01-06T10:01:00Z")
    assert again.head == first.head
    rec = again.append(agent_id="eval-harvester", owner="tomas.b", on_behalf_of="tomas.b", action="tickets.list",
                       resource="x", outcome="ok")
    assert rec["seq"] == 4 and rec["prev"] == first.head[1]
    assert verify(load(path)).ok


def test_each_line_is_one_json_object_with_the_documented_fields(tmp_path):
    path = tmp_path / "trail.jsonl"
    three(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert set(json.loads(lines[0])) == {"seq", "at", "agent_id", "owner", "on_behalf_of", "credential", "action",
                                         "resource", "outcome", "source", "detail", "prev", "hash"}


@pytest.mark.parametrize("field", ["agent_id", "owner", "outcome", "at"])
def test_changing_any_field_changes_the_hash(field):
    rec = three().records[0]
    assert record_hash({**rec, field: "changed"}) != rec["hash"]
