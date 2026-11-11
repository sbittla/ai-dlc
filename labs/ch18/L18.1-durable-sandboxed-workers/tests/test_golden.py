"""Golden tests: every number Chapter 18 quotes from Lab 18.1. A change that moves one must fail here.

The pilot's data is generated with a fixed seed; the drills run on a simulated clock; the escape attempts run
real processes, but every quoted outcome is a category (refused, reached, stopped), not a time."""

from opslab.report import render_drills, render_escapes, render_incident, render_layers, render_trace


def test_incident():
    t = render_incident()
    for s in ("Billing tickets: 160; real duplicate charges (eligible for a refund): 130.",
              "Queue deliveries: 190 for 160 tickets.",
              "Deliveries whose processing passed the 60 s visibility timeout: 22 of 190.",
              "Refunds issued: 151 for 130 eligible charges.",
              "Duplicate refunds: 21 on 16 charges, $2,928 refunded twice.",
              "Duplicate refunds by cause: visibility timeout 15, webhook duplicate 6."):
        assert s in t, s


def test_layers():
    t = render_layers()
    for s in ("| none (the pilot) | 151 | 21 | $2,928 | visibility timeout 15, webhook duplicate 6 |",
              "| dedup | 145 | 15 | $2,163 | visibility timeout 15 |",
              "| heartbeat | 136 | 6 | $765 | webhook duplicate 6 |",
              "| ledger | 130 | 0 | $0 | - |",
              "| dedup + heartbeat | 130 | 0 | $0 | - |",
              "| dedup + heartbeat + ledger | 130 | 0 | $0 | - |"):
        assert s in t, s


def test_escapes():
    t = render_escapes()
    for s in ("| E01 | read a secret from the environment | reached | nothing | - |",
              "| E03 | open Relay's database file | reached | refused | refused:import:sqlite3 |",
              "| E04 | connect to an internal service | reached | refused | refused:network |",
              "| E05 | connect to the cloud metadata address | not run | refused | refused:network |",
              "| E09 | load native code | reached | refused | refused:import:ctypes |",
              "| E12 | run forever | not run | stopped | - |",
              "| E14 | walk the frames, rebind the sandbox's rules, then read outside | not run | refused | refused:open:read |",
              "| E15 | find the sandbox's policy through the garbage collector | not run | refused | refused:introspection |",
              "| E16 | load ctypes' C core under another name | reached | refused | refused:import:_ctypes |",
              "| E17 | read another database through SQLite's ATTACH | reached | refused | refused:import:sqlite3 |",
              "| E18 | erase the record of a refusal | not run | refused | refused:os.truncate:descriptor |",
              "| E19 | learn whether something exists outside the working directory | reached | reached | - |",
              "| E20 | change the sandbox's Policy class through the frames, then read outside | not run | refused | "
              "refused:open:read |",
              "| E21 | reach the hook's own frame from a finalizer, rewrite its rules, then read outside | not run | "
              "reached | - |",
              "| L01 | legitimate: compare two invoice lines from a file it was given | ok | ok | - |",
              "Escape attempts: 21. Run the pilot's way: 12, of which reached what they tried: 12.",
              "In the sandbox: refused 16, stopped by a limit 2, found nothing 1; contained 19 of 21.",
              "Legitimate attempts that still work in the sandbox: 1 of 1."):
        assert s in t, s


def test_drills():
    t = render_drills()
    for s in ("| F0 | none (baseline) | done | finished (pull request opened) | 1 | waiting, done, idle | pass |",
              "| F1 | the worker dies after the code host created the pull request | done | finished (pull request "
              "opened) | 1 | waiting, crashed, done, idle | pass |",
              "| F3 | the model provider times out on every call | dead (attempts_exhausted) | running | 0 |",
              "| F5 | the agent's code tries a shell command and the metadata address | done | handed_back "
              "(agent:tests_failed) | 0 | done, idle | pass |",
              "| F6 | the monitor trips the helper's kill switch while its tests run | dead (revoked) | revoked "
              "(disabled) | 0 | dead, idle | pass |",
              "| F7 | the requester cancels the job while its tests run | cancelled | stopped (cancelled) | 0 |",
              "| F8 | the job's payload has no task | dead (poison_payload) | - | 0 | dead, idle | pass |",
              "Drills passed: 9 of 9.",
              "F1: attempts 2; the ledger repeated the pull request call 1 time",
              "F2: second delivery created a new job: False; a second worker polling during the 100 s test step got: "
              "idle (lease 120 s, extended between steps).",
              "F3: retry delays 10.8 s, 23.8 s, 31.5 s; attempts 4.",
              "F4: calls refused with 429: 4; worker passes paused by the breaker: 24; breaker: open -> half_open -> "
              "open -> half_open -> closed.",
              "F5: sandbox refusals refused:process, refused:network.",
              "F6: refused tool open_pull_request (revoked:disabled), 102 simulated seconds after the trip."):
        assert s in t, s


def test_trace():
    t = render_trace()
    for s in ("Attempts (process_job spans): 2, each linked to the request's span: yes.", "Tool calls traced: 5.",
              "Queue wait 3.0 s; agent working 119.0 s, of which the test step 102.0 s; waiting for approval 600.0 s;"
              " total 724.0 s."):
        assert s in t, s
