"""Golden tests: every number Chapter 13 quotes from Lab 13.1. A change that moves one must fail here."""

from secloop.report import render_alarms, render_catch, render_fixes, render_incident, render_release


def test_incident():
    text = render_incident()
    assert "Package age at install: 42 days." in text
    assert "Install to exfiltration: 7 s." in text
    assert "Stolen App token usable for 43 min 24 s (issued 10:02:31, one hour)." in text
    assert "Install to discovery: 22 h 53 min." in text
    assert "Stolen Relay agent token: 12 min 55 s left, never used." in text
    assert "Install to the agent's pull request: 17 min 12 s." in text
    assert "- DEP004: jwt-oidc-verify is not pinned" in text
    assert ("- DEP001: jwt-oidc-verify is not admitted to the mirror; on the public index since 2026-12-02, "
            "3 version(s), source distribution only, no source repository") in text
    for stamp in ("Wed 2026-12-02 18:40:00 UTC", "Thu 2027-01-14 10:02:31 UTC", "Thu 2027-01-14 10:19:00 UTC",
                  "Thu 2027-01-14 10:19:07 UTC  setup script posts", "Thu 2027-01-14 10:26:40 UTC  attacker clones",
                  "Thu 2027-01-14 10:32:02 UTC  stolen Relay agent token expires",
                  "Thu 2027-01-14 10:36:12 UTC  agent opens draft PR #2417",
                  "Thu 2027-01-14 10:48:05 UTC  attacker's push to .github/workflows/ refused",
                  "Thu 2027-01-14 11:02:31 UTC  stolen App token expires",
                  "Thu 2027-01-14 11:15:12 UTC  attacker's next push refused: 401",
                  "Fri 2027-01-15 09:12:00 UTC  sam.o, reviewing #2417", "Fri 2027-01-15 09:31:00 UTC"):
        assert stamp in text, stamp


def test_catch_rates():
    text = render_catch()
    for row in ("| sql-injection | 12 | 11 | 0 | 1 |", "| broken-authorization | 12 | 2 | 0 | 10 |",
                "| hardcoded-secret | 12 | 11 | 0 | 1 |", "| weak-crypto | 8 | 7 | 0 | 1 |",
                "| unsafe-deserialization | 8 | 8 | 0 | 0 |", "| command-injection | 8 | 8 | 0 | 0 |",
                "| path-traversal | 8 | 4 | 0 | 4 |", "| vulnerable-dependency | 8 | 0 | 8 | 0 |",
                "| hallucinated-package | 8 | 8 | 0 | 0 |", "| typosquat | 6 | 6 | 0 | 0 |",
                "| dependency-confusion | 6 | 6 | 0 | 0 |", "| iac-misconfiguration | 4 | 0 | 4 | 0 |",
                "| all seeded | 100 | 71 | 12 | 17 |"):
        assert row in text
    assert "Caught at either stage: 83/100 (83%; 95% interval 74.5-89.1%)." in text
    assert "Caught before commit: 71/100 (71%; 95% interval 61.5-79.0%)." in text
    assert "depgate 20, gitleaks 10, semgrep 43, trivy 12." in text
    assert "Without the dependency gate (scanners only): 63/100 (63%; 95% interval 53.2-71.8%); 20 seeded" in text
    assert "Clean changes blocked: 2 of 60." in text


def test_false_alarms_and_suppressions():
    text = render_alarms()
    assert "Clean changes with any finding: 7 of 60." in text
    assert "Blocked without suppressions: 5; with the reviewed suppressions: 2; warnings only: 2." in text
    for row in ("| Retry jitter | semgrep relay.random-not-for-secrets | 4.0 | warning |",
                "| Shuffle a demo list | semgrep relay.random-not-for-secrets | 4.0 | warning |",
                "| Table name from a constant | semgrep relay.sql-built-from-strings | 8.8 | suppressed |",
                "| Column list from a constant | semgrep relay.sql-built-from-strings | 8.8 | suppressed |",
                "| ETag for an export | semgrep relay.weak-hash-or-random-for-secrets | 7.4 | blocked |",
                "| Test vector | gitleaks generic-api-key | 9.0 | suppressed |",
                "| Docs example token | gitleaks relay-token | 9.0 | blocked |"):
        assert row in text, row
    assert "Suppressions proposed: 6; proposed by the agent: 5; reviewed by the agent: 2." in text
    assert "| SUP-03 | AC151 (ETag for an export) | coding-session | sam.o | no | expired on 2027-01-10 |" in text
    assert "| SUP-06 | AC008 (seeded weakness) | coding-session | coding-session | no |" in text
    assert text.count("| yes |") == 3
    assert "| no | expired on 2027-01-10 |" in text
    assert text.count("is not a person on the policy's list") == 2
    assert "(seeded weakness) |" in text


def test_fix_reverification():
    text = render_fixes()
    assert "Fix attempts: 83, every one claimed as fixed." in text
    for row in ("| claim | 83 | 23 |", "| rescan | 77 | 17 |", "| rescan+tests | 74 | 14 |", "| full policy | 60 | 0 |"):
        assert row in text
    assert ("Kinds: breaks-tests 3, partial 2, proper 60, scanner-config 3, suppression-marker 7, swapped-package 4, "
            "weakened-test 4.") in text
    assert "Refusal reasons: adds marker 7, changes protected path 7, rescan still finds 6, tests fail 3." in text


def test_release_candidates():
    text = render_release()
    for row in ("| RC-1 | none | deploy |", "| RC-2 | REL005 | refuse |", "| RC-3 | REL002 | refuse |",
                "| RC-4 | REL007, REL008 | refuse |", "| RC-5 | REL006 | refuse |", "| RC-6 | REL003 | refuse |"):
        assert row in text
    assert "RC-4 REL007: AI-BOM incomplete: prompt:triage-v3.1" in text
    assert "RC-5 REL006: SBOM incomplete: pkg:pypi/packaging@25.0" in text
