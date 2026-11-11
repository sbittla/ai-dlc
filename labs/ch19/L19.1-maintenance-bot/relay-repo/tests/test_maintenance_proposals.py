"""Proposals, approvals and the pull request (4.31.0, ADR-053): the bot never approves, its owner never approves,
every refusal is audited, an approval covers one diff and one evidence bundle, and the kill switch stops it."""

import pytest

from maintenance_helpers import World
from relay.agents import ApprovalRefused
from relay.maintenance import Bundle, Check, ProposalRefused, item

LOCK = "gunicorn==23.1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n"
DIFF = {"deploy/requirements.txt": LOCK}
GOOD = Bundle((item("E1", "reproduction fails before and passes after", Check("r", "pass", "")),
               item("E2", "tests pass", Check("t", "pass", "")),
               item("E3", "scanner report for this diff", Check("s", "pass", ""), status="modelled")))


def proposed(w: World, task="VF-1", task_type="vulnerability-fix", paths=("deploy/requirements.txt",),
             packages=("sessionkeel",)):
    return w.desk.propose(w.run(task), task, task_type, {p: LOCK for p in paths}, list(packages), GOOD)


@pytest.mark.parametrize("task_type,paths,code", [
    ("vulnerability-fix", [".github/workflows/maintenance.yml"], "protected_path:.github/workflows/maintenance.yml"),
    ("vulnerability-fix", ["maintenance/policy.json"], "protected_path:maintenance/policy.json"),
    ("vulnerability-fix", ["src/relay/store.py"], "not_writable:src/relay/store.py"),
    ("bug-reproduction", ["docs/x.md"], "tier_does_not_allow_changes"),
    ("deploy-to-production", ["docs/x.md"], "unknown_task_type"),
    ("docs-upkeep", [], "no_changes"),
])
def test_proposals_outside_the_policy_are_refused_and_audited(task_type, paths, code):
    w = World()
    with pytest.raises(ProposalRefused) as exc:
        w.desk.propose(w.run("T-1"), "T-1", task_type, {p: "x" for p in paths}, [], GOOD)
    assert exc.value.code == code and w.refusals("maintenance.propose") == [code]


def test_a_proposal_with_missing_or_failing_evidence_is_refused():
    w = World()
    bad = Bundle(GOOD.items + (item("E4", "pinned defaults unchanged", Check("d", "fail", "")),
                               item("E5", "lock matches the mirror", None)))
    with pytest.raises(ProposalRefused) as exc:
        w.desk.propose(w.run("T-2"), "T-2", "vulnerability-fix", DIFF, [], bad)
    assert exc.value.code == "evidence_blocking:E4,E5"


def test_the_bot_its_owner_and_people_who_do_not_own_the_paths_cannot_approve():
    w = World()
    p = proposed(w)
    attempts = [(w.proof(), "bad_person_proof"),                              # the bot's own workload proof
                ({**w.person("aisha.r"), "iat": w.clock() - 600}, "bad_person_proof"),  # stale
                ({**w.person("maintenance-bot")}, "not_a_person"),
                (w.person("priya.n"), "bot_owner_may_not_approve"),
                (w.person("sam.o"), "not_a_code_owner:deploy/requirements.txt")]
    for proof, code in attempts:
        with pytest.raises(ApprovalRefused) as exc:
            w.desk.decide(p.proposal_id, proof, True, "looks fine")
        assert exc.value.code == code
    assert w.refusals("maintenance.approval") == [c for _, c in attempts]
    assert w.desk.get(p.proposal_id).status == "awaiting_approval"


def test_security_approves_and_the_pull_request_opens_once():
    w = World()
    p = proposed(w)
    with pytest.raises(ProposalRefused):
        w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)   # not yet approved
    assert w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "LAB-ADV-2027-0113 fixed").status == "approved"
    first = w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    again = w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    assert (first["number"], first["replayed"], again["replayed"]) == (3100, False, True)
    assert len(w.prs) == 1 and w.desk.get(p.proposal_id).pr_number == 3100


def test_an_approval_covers_one_diff_and_one_bundle():
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "ok")
    with pytest.raises(ProposalRefused) as exc:
        w.desk.open_pull_request(p.proposal_id, {**DIFF, "requirements-dev.txt": "x"}, GOOD.sha256(), w.open_pr)
    assert exc.value.code == "changed_since_approval" and w.prs == []


def test_a_denied_proposal_never_opens_and_cannot_be_decided_again():
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), False, "wait for 2.5.1 review")
    with pytest.raises(ProposalRefused):
        w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    with pytest.raises(ApprovalRefused) as exc:
        w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "changed my mind")
    assert exc.value.code == "not_pending"


def test_the_kill_switch_stops_the_bot_before_its_next_effect():
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "ok")
    w.registry.disable("maintenance-bot")
    with pytest.raises(ProposalRefused) as exc:
        w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    assert exc.value.code.startswith("revoked:") and w.prs == []
    assert w.refusals("maintenance.open_pr") == [exc.value.code]


def test_paths_and_packages_come_from_the_change_not_the_caller():
    w = World()
    lock = "sessionkeel==2.4.2 \\\n    --hash=sha256:" + "b" * 64 + "\n"
    p = w.desk.propose(w.run("VF-9"), "VF-9", "dependency-update", {"requirements.lock": lock}, [], GOOD)
    assert p.paths == ("requirements.lock",) and p.packages == ("sessionkeel",)
    # sessionkeel is sensitive, though the caller named no package: sam.o owns the path (a maintainer) and is
    # still refused, because a sensitive package needs @relay/security.
    with pytest.raises(ApprovalRefused) as exc:
        w.desk.decide(p.proposal_id, w.person("sam.o"), True, "ok")
    assert exc.value.code == "security_review_required"


def test_a_docs_proposal_is_approved_by_a_maintainer_who_is_not_the_owner():
    w = World()
    p = w.desk.propose(w.run("DU-1"), "DU-1", "docs-upkeep", {"docs/integrations.md": "fixed"}, [], GOOD)
    assert w.desk.decide(p.proposal_id, w.person("sam.o"), True, "link fixed").status == "approved"


def test_an_approval_older_than_a_day_is_stale_and_audited():
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "ok")
    w.clock.t += 3 * 24 * 3600            # approved on Monday, opened on Thursday
    with pytest.raises(ProposalRefused) as exc:
        w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    assert exc.value.code == "approval_stale" and w.prs == []
    assert w.refusals("maintenance.open_pr") == ["approval_stale"] and w.desk.get(p.proposal_id).status == "stale"


def test_a_change_proposed_again_after_a_denial_or_a_stale_approval_is_a_new_attempt():
    w = World()
    first = proposed(w)
    assert proposed(w).proposal_id == first.proposal_id          # still live: the same proposal, nothing new asked
    w.desk.decide(first.proposal_id, w.person("aisha.r"), False, "not now")
    second = proposed(w)
    assert second.proposal_id != first.proposal_id and second.approval_id != first.approval_id
    assert second.status == "awaiting_approval" and w.desk.get(first.proposal_id).status == "denied"
    assert w.desk.decide(second.proposal_id, w.person("aisha.r"), True, "now").status == "approved"


def test_one_line_hash_entries_count_and_an_unreadable_lock_line_is_refused():
    w = World()
    one_line = "sessionkeel==2.4.2 --hash=sha256:" + "c" * 64 + "\n"
    p = w.desk.propose(w.run("VF-10"), "VF-10", "dependency-update", {"requirements.lock": one_line}, [], GOOD)
    assert p.packages == ("sessionkeel",)
    with pytest.raises(ProposalRefused) as exc:
        w.desk.propose(w.run("VF-11"), "VF-11", "dependency-update", {"requirements.lock": "sessionkeel>=2.4\n"},
                       [], GOOD)
    assert exc.value.code == "unreadable_lock:requirements.lock"


def test_a_stale_approval_needs_evidence_run_again_before_a_new_attempt():
    from relay.maintenance import Bundle
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "ok")
    w.clock.t += 2 * 24 * 3600
    with pytest.raises(ProposalRefused):
        w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    with pytest.raises(ProposalRefused) as exc:
        proposed(w)                                              # the same, old evidence
    assert exc.value.code == "evidence_not_fresh"
    w.clock.t += 600
    fresh = Bundle(GOOD.items, ran_at=w.clock())                 # the checks ran again, after the approval went stale
    again = w.desk.propose(w.run("VF-1b"), "VF-1", "vulnerability-fix", DIFF, ["sessionkeel"], fresh)
    assert again.status == "awaiting_approval" and again.proposal_id != p.proposal_id


def test_a_moved_base_refuses_the_pull_request_and_each_attempt_has_its_own_effect():
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "ok")
    w.main = "d00d2"                                             # someone merged to main in the meantime
    with pytest.raises(ProposalRefused) as exc:
        w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    assert exc.value.code == "base_moved" and w.prs == []
    assert w.refusals("maintenance.open_pr") == ["base_moved"]


def test_a_second_approved_diff_for_the_same_task_opens_its_own_pull_request():
    w = World()
    p = proposed(w)
    w.desk.decide(p.proposal_id, w.person("aisha.r"), True, "ok")
    w.desk.open_pull_request(p.proposal_id, DIFF, GOOD.sha256(), w.open_pr)
    other = {"deploy/requirements.txt": LOCK.replace("23.1.0", "23.1.1")}
    q = w.desk.propose(w.run("VF-1c"), "VF-1", "vulnerability-fix", other, ["sessionkeel"], GOOD)
    w.desk.decide(q.proposal_id, w.person("aisha.r"), True, "ok")
    assert w.desk.open_pull_request(q.proposal_id, other, GOOD.sha256(), w.open_pr)["number"] == 3101
