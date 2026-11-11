"""Golden tests: every number Chapter 19 quotes from Lab 19.1. A change that moves one must fail here.

The data is generated with a fixed seed and configured (scripts/generate_data.py); the sandbox checks run real,
inert processes, and every quoted outcome of them is a category (pass, fail) or a fixed message."""

from mainlab.report import (render_controls, render_demo, render_dst, render_incident, render_month, render_replay,
                            render_worked)


def has(text, lines):
    for s in lines:
        assert s in text, s


def test_incident():
    has(render_incident(), [
        "New version first served: 14:02 UTC; to every user from 14:47; sign-ins restored 16:47.",
        "Minutes with some users locked out: 165; with every user locked out: 120.",
        "Failed sign-in attempts while affected: 161,348 (baseline failure share before: 3.0%).",
        "Accounts that tried to sign in during the full lockout: 50,174.",
        "From the SD-001 page to restored sign-ins: 117 minutes.",
        "sessionkeel 2.5.0: released 2027-05-06, served from 2027-05-13",
        "2027-05-10  the dependency bot's rule widened to merge minor updates when checks pass",
        "13:41  the bot opens and merges the bump sessionkeel 2.4.1 to 2.5.0; every check green",
        "14:50  SD-001 pages security on-call aisha.r", "15:30  tomas.b reports a flood of tickets",
        "16:05  aisha.r: failures from every network and every account; not an attack",
        "16:20  sam.o links the failures to the release", "16:31  deploy.rollback approved by priya.n (platform on-call) and sam.o"])


def test_controls():
    has(render_controls(), [
        "Plan on 2027-05-20: sessionkeel 2.4.1 -> 2.5.0 (minor); reviews: pinned-defaults, tests, scan, security.",
        "App tests on 2.5.0: pass (4 app tests passed).",
        "Round trip on 2.5.0: fail (a token sign-in issued was refused).",
        "Pinned defaults on 2.5.0: fail (verify(require_audience): pinned False, now True).",
        "Guard on the 5% stage: tripped at 14:02 (canary failures 100.0%, stable 3.4%); canary sign-ins refused "
        "before the trip: 60."])


def test_worked_example():
    has(render_worked(), [
        "sessionkeel 2.4.2: released 2027-06-08, served from 2027-06-08 (released early by aisha.r)",
        "Triage: ADV-0113 -> vulnerability-fix (LAB-ADV-2027-0113; locked 2.4.1, fixed 2.4.2; untrusted: True).",
        "Plan: sessionkeel 2.4.1 -> 2.4.2 (patch); reviews: pinned-defaults, tests, scan, security.",
        "Reproduction: before fail (expired token accepted); after pass (expired token refused); outcome fixed.",
        "| E1 | the advisory's test fails on 2.4.1 and passes on the fix | verified | pass | reproduction-after |",
        "| E4 | security-relevant defaults are unchanged | verified | pass | pinned-defaults |",
        "| E6 | no scanner finding on the diff | modelled | pass | security-gates record |",
        "Refused approvals: bad_person_proof, bot_owner_may_not_approve, not_a_code_owner:requirements.lock.",
        "Approved by aisha.r: approved. Pull request #412 opened (replayed: False).",
        "Audit records: 8, of which refusals: 3."])


def test_demo():
    has(render_demo(), [
        "app-tests pass; round-trip fail; pinned-defaults fail.",
        "sessionkeel 2.4.3: released 2027-06-21, served from 2027-06-28.",
        "Proposal refused: evidence_blocking:E3,E4; audited: True.",
        "run tainted: True; refusals: path_not_allowed, path_not_allowed, unknown_tool, unknown_tool.",
        "Files changed: none. The desk, asked for the workflow path: protected_path:.github/workflows/maintenance.yml.",
        "Plan: 2.4.2 -> 2.4.3 (patch); guard tripped at canary minute 2 (canary failures 28.6%, stable 3.3%, z 7.13).",
        "Canary sign-ins refused before the trip: 10. Reverted to 2.4.2; lock matches the mirror: pass.",
        "Cause: on 2.4.3 fail (token from a clock 5 s ahead refused); on 2.4.2 pass (token from a clock 5 s ahead "
        "accepted)."])


def test_replay():
    has(render_replay(), [
        "Regression reached all users: old rule 4 (U17, U33, U41, U58); new policy 1 (U33).",
        "Discordant: old only 3, new only 0; exact McNemar p = 0.250.",
        "Stopped by: guard 1, pinned-defaults 2.",
        "Merged with no person under the old rule: 42; sent to @relay/security under the new policy: 21."])


def test_month():
    has(render_month(), [
        "A simulated month, 9 June to 9 July 2027: the runs the bot would have made (configured outcomes).",
        "| dependency-update | T2 | 22 | 15/22 (68.2%, 47.3-83.6) | 1/16 (6.2%, 1.1-28.3) | 8/22 (36.4%, 19.7-57.0) | 0 "
        "| 0.0000 | not eligible (A1, A2, A4, A5, A6) |",
        "| vulnerability-fix | T2 | 2 | 2/2 (100.0%, 34.2-100.0) | 0/2 (0.0%, 0.0-65.8) | 0/2 (0.0%, 0.0-65.8) | 0 | "
        "0.0000 | not eligible (A1, A2, A4, A5, A6) |",
        "| docs-upkeep | T2 | 14 | 11/14 (78.6%, 52.4-92.4) | 0/11 (0.0%, 0.0-25.9) | 3/14 (21.4%, 7.6-47.6) | 4 | "
        "0.0454 | not eligible (A1, A2, A3, A4, A5, A6) |",
        "| bug-reproduction | T1 | 5 | 0/5 (0.0%, 0.0-43.4) | - | 5/5 (100.0%, 56.6-100.0) | 0 | 0.0534 | "
        "not eligible (A1, A2, A4, A5, A6) |",
        "| table-extension | T2 | 1 | 0/1 (0.0%, 0.0-79.3) | - | 1/1 (100.0%, 20.7-100.0) | 0 | 0.0000 | "
        "not eligible (A1, A2, A5, A6) |",
        "Runs: 44; total cost $0.90. A 5% upper bound at zero harms needs 73 merged changes."])


def test_dst():
    has(render_dst(), [
        "Run SCH-0701 (2027-07-01); rules relay-dst-rules-v1 reviewed by sam.o on 2027-06-14.",
        "Rules reproduce the reviewed table: 20 of 20 transitions (2026-2027).",
        "Transitions added for 2028: 10.",
        "Approved tests that pin the old end (3): tests/escalation/test_escalation_engine.py, "
        "tests/escalation/test_escalation_hours.py, tests/escalation/test_escalation_zones.py.",
        "Proposal: evidence_blocking:E3."])
