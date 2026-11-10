"""TODO 1 (pipeline lint) and TODO 2 (gate diff and review rules), on small hand-checkable workflows."""

import pytest

from pipeline import yamlish
from pipeline.guard import decision, gate_diff, guard
from pipeline.lint import lint

SHA = "@" + "a" * 40
GOOD = f"""
name: ok
on: [pull_request]
permissions: {{}}
jobs:
  tests:
    runs-on: ubuntu-latest
    permissions: {{contents: read}}
    steps:
      - uses: actions/checkout{SHA}  # v4
        with: {{persist-credentials: false}}
      - name: Unit tests
        run: python -m pytest -q
      - name: Scan
        run: >-
          docker run --rm scanner@sha256:{"b" * 64}
          scan --output /src/scan.sarif /src
"""


def rules(text):
    return [f.rule for f in lint(yamlish.loads(text), "w.yml")]


# --- the provided parser ----------------------------------------------------------------------------------

def test_the_parser_reads_what_workflows_use():
    doc = yamlish.loads(GOOD)
    assert doc["on"] == ["pull_request"] and doc["permissions"] == {}
    steps = doc["jobs"]["tests"]["steps"]
    assert steps[0]["with"] == {"persist-credentials": False}
    assert steps[2]["run"].startswith("docker run --rm scanner@sha256:") and "\n" not in steps[2]["run"]
    assert yamlish.loads("a: |\n  x\n  y\nb: 'it''s'\n") == {"a": "x\ny\n", "b": "it's"}
    assert yamlish.loads("k:\n- 1\n- two\n") == {"k": [1, "two"]}


# --- TODO 1 ------------------------------------------------------------------------------------------------

def test_a_hardened_workflow_has_no_findings():
    assert rules(GOOD) == []


@pytest.mark.parametrize("change, expected", [
    (("actions/checkout" + SHA, "actions/checkout@v4"), ["PL001"]),
    (("permissions: {}\njobs", "jobs"), ["PL002"]),
    (("permissions: {}\njobs", "permissions: write-all\njobs"), ["PL002"]),
    (("permissions: {contents: read}", "permissions: {contents: read, id-token: write}"), ["PL003"]),
    (("permissions: {contents: read}", "permissions: write-all"), ["PL003"]),
    (("run: python -m pytest -q", "run: echo \"${{ github.event.pull_request.title }}\""), ["PL006"]),
    (("with: {persist-credentials: false}", "with: {fetch-depth: 0}"), ["PL007"]),
    (("runs-on: ubuntu-latest", "runs-on: [self-hosted, linux]"), ["PL008"]),
    (("run: python -m pytest -q", "run: python -m pytest -q\n        continue-on-error: true"), ["PL009"]),
    (("run: python -m pytest -q", "run: python -m pytest -q\n        continue-on-error: ${{ true }}"), ["PL009"]),
    (("runs-on: ubuntu-latest", "runs-on: [self-hosted, relay-sandbox, ephemeral]"), []),
    (("scanner@sha256:" + "b" * 64, "scanner:latest"), ["PL010"]),
])
def test_each_rule_finds_its_one_problem(change, expected):
    assert rules(GOOD.replace(*change)) == expected


def test_id_token_with_a_protected_environment_is_allowed():
    text = GOOD.replace("permissions: {contents: read}",
                        "environment: production\n    permissions: {contents: read, id-token: write}")
    assert rules(text) == []


def test_untrusted_trigger_only_matters_with_power():
    weak = GOOD.replace("on: [pull_request]", "on: [pull_request_target]")
    assert rules(weak) == []
    assert rules(weak.replace("permissions: {contents: read}", "permissions: {contents: write}")) == ["PL004"]


def test_cloud_keys_are_found_in_env_with_and_run():
    text = GOOD.replace("run: python -m pytest -q", "run: deploy\n        env: {K: \"${{ secrets.AWS_SECRET_ACCESS_KEY }}\"}")
    assert rules(text) == ["PL005"]
    text = GOOD.replace("with: {persist-credentials: false}",
                        "with: {persist-credentials: false, aws-access-key-id: x}")
    assert rules(text) == ["PL005"]


# --- TODO 2: gate diff --------------------------------------------------------------------------------------

def diff(head_text, base_text=GOOD):
    return [f.rule for f in gate_diff(yamlish.loads(base_text), yamlish.loads(head_text), ["tests"], "w.yml")]


@pytest.mark.parametrize("change, expected", [
    (("  tests:\n", "  unit:\n"), ["GD001"]),
    (("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    if: github.actor != 'x'\n"), ["GD002"]),
    (("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    continue-on-error: true\n"), ["GD003"]),
    (("run: python -m pytest -q", "run: python -m pytest -q || true"), ["GD004"]),
    (("run: python -m pytest -q", "run: set +e; python -m pytest -q"), ["GD004"]),
    (("scan --output /src/scan.sarif /src", "scan --output /src/scan.sarif /src || echo '{}' > scan.sarif"),
     ["GD004", "GD005"]),
    (("on: [pull_request]", "on:\n  pull_request:\n    paths: [\"src/**\"]"), ["GD006"]),
    (("      - name: Unit tests\n        run: python -m pytest -q\n", ""), ["GD007"]),
    (("permissions: {contents: read}", "permissions: {contents: write}"), ["GD008"]),
    (("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    continue-on-error: ${{ true }}\n"), ["GD003"]),
    (("run: python -m pytest -q", "run: echo tests skipped"), ["GD009"]),
])
def test_each_weakening_is_named(change, expected):
    assert diff(GOOD.replace(*change)) == expected


def test_a_pin_bump_is_not_a_gate_change_but_any_other_command_change_is():
    assert diff(GOOD.replace("a" * 40, "c" * 40)) == []
    assert diff(GOOD.replace("python -m pytest -q", "python -m pytest -q -W error")) == ["GD009"]
    assert diff(GOOD, GOOD.replace("tests:", "other:")) == []  # no required check in base: nothing to weaken


# --- TODO 2: review rules -----------------------------------------------------------------------------------

POLICY = {"pipeline_paths": [".github/", "deploy/", "security/"], "gate_config_paths": ["security/"],
          "owner_team": "@leads", "weakening_team": "@sec"}
TEAMS = {"@leads": ["lead1", "lead2"], "@sec": ["sec1"], "agents": ["coding-session"]}


def pr(files=(".github/workflows/w.yml",), approvals=(), agent=None, head=None, description=""):
    return {"number": 1, "author": "dev", "agent": agent, "files": list(files),
            "workflows": {".github/workflows/w.yml": [GOOD, head or GOOD]},
            "approvals": [{"by": b, "after_last_push": after} for b, after in approvals],
            "description": description}


def g(p, teams=TEAMS):
    return [f.rule for f in guard(p, POLICY, teams, ["tests"])]


def test_only_pipeline_changes_are_guarded():
    assert g(pr(files=["src/x.py"])) == []


def test_two_people_after_the_last_push_one_from_the_owner_team():
    assert g(pr(approvals=[("lead1", True), ("dev2", True)])) == []
    assert g(pr(approvals=[("lead1", True)])) == ["PG002"]
    assert g(pr(approvals=[("lead1", False), ("dev2", True)])) == ["PG002"]
    assert g(pr(approvals=[("dev2", True), ("dev3", True)])) == ["PG002"]
    assert g(pr(approvals=[("dev", True), ("lead1", True)])) == ["PG002"]           # the author
    assert g(pr(approvals=[("coding-session", True), ("lead1", True)])) == ["PG002"]  # an agent
    asked = {"agent_id": "coding-session", "requester": "lead2"}
    assert g(pr(approvals=[("lead2", True), ("lead1", True)], agent=asked)) == ["PG002"]  # the requester


def test_mixed_pull_requests_are_refused():
    assert g(pr(files=[".github/workflows/w.yml", "src/x.py"], approvals=[("lead1", True), ("d", True)])) == ["PG001"]


def test_a_weakening_needs_security_and_a_reason():
    head = GOOD.replace("python -m pytest -q", "python -m pytest -q || true")
    ok = [("lead1", True), ("sec1", True)]
    assert g(pr(head=head, approvals=[("lead1", True), ("d", True)])) == ["GD004", "PG003"]
    assert g(pr(head=head, approvals=ok)) == ["GD004", "PG003"]
    reason = "Gate change: RLY-9: tests that need the network are reported, not failed"
    assert g(pr(head=head, approvals=ok, description=reason)) == ["GD004"]
    findings = guard(pr(head=head, approvals=ok, description=reason), POLICY, TEAMS, ["tests"])
    assert decision(findings) == ("pass", 0)


def test_unknown_membership_cannot_pass():
    findings = guard(pr(approvals=[("lead1", True), ("d", True)]), POLICY, None, ["tests"])
    assert [f.rule for f in findings] == ["PG004"] and decision(findings) == ("cannot decide", 2)


def test_gate_configuration_changes_need_security():
    p = pr(files=["security/gates.json"], approvals=[("lead1", True), ("d", True)])
    p["workflows"] = {}
    assert g(p) == ["GD010", "PG003"]


# --- the round-1 review's probes, on Relay's own files ----------------------------------------------------------

from pipeline.report import guard_policy, required, teams  # noqa: E402

TRIVY = "          fs --offline-scan --scanners vuln,misconfig --format sarif --output /src/trivy.sarif /src"


def relay_guard(head, path=".github/workflows/ci.yml", base=None, files=None):
    from pipeline import DATA
    base = base if base is not None else (DATA / "incident" / "ci-before.yml").read_text(encoding="utf-8")
    p = {"number": 1, "author": "engineer-1", "agent": None, "description": "", "files": files or [path],
         "approvals": [{"by": "sam.o", "after_last_push": True}, {"by": "priya.n", "after_last_push": True}],
         "workflows": {path: (base, head)} if head is not None else {}}
    found = guard(p, guard_policy(), teams(), required())
    return decision(found)[0], [f.rule for f in found]


def _base():
    from pipeline import DATA
    return (DATA / "incident" / "ci-before.yml").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["expression", "echo", "if-not", "guard-job"])
def test_review_probes_each_weakening_is_blocked_without_security(name):
    base = _base()
    if name == "expression":
        head = base.replace("  security-gates:\n    runs-on: ubuntu-latest\n",
                            "  security-gates:\n    runs-on: ubuntu-latest\n    continue-on-error: ${{ true }}\n")
    elif name == "echo":
        head = base.replace("run: python tools/security_gate.py --policy security/gates.json semgrep.sarif "
                            "gitleaks.sarif trivy.sarif", "run: echo gate skipped")
    elif name == "if-not":
        head = base.replace("        run: >-\n          docker run --rm -v \"$PWD:/src\"",
                            "        run: >-\n          if ! docker run --rm -v \"$PWD:/src\"").replace(
            TRIVY, TRIVY + "; then cp security/empty.sarif trivy.sarif; fi")
    else:
        from conftest import CANONICAL, RELAY
        old = (RELAY / ".github" / "workflows" / "pr-gates.yml").read_text(encoding="utf-8")
        old += ("\n  pipeline-guard:\n    runs-on: ubuntu-latest\n    permissions: {contents: read}\n    steps:\n"
                "      - run: python -m pipeline.report guard\n")
        head = old.replace("run: python -m pipeline.report guard", "run: 'true'")
        verdict, rules = relay_guard(head, ".github/workflows/pr-gates.yml", base=old)
        assert verdict == "block" and "PG003" in rules
        return
    assert head != base
    verdict, rules = relay_guard(head)
    assert verdict == "block" and "PG003" in rules and any(r.startswith("GD") for r in rules)


def test_review_probe_policy_and_label_files_are_pipeline_paths():
    assert relay_guard(None, files=["security/gates.json"]) == ("block", ["GD010", "PG003"])
    from pipeline.guard import is_pipeline_path
    assert is_pipeline_path("evals/human-labels.json", guard_policy())
    p = {"number": 1, "author": "engineer-1", "agent": None, "description": "", "files": ["evals/human-labels.json"],
         "approvals": [{"by": "reviewer-1", "after_last_push": True}], "workflows": {}}
    assert decision(guard(p, guard_policy(), teams(), required()))[0] == "block"


@pytest.mark.parametrize("path", ["docs/slo/slos.json", "tools/admit.py", "tools/reconcile.py",
                                  "tools/security_gate.py", "tools/lint.py"])
def test_review_round_2_probe_files_the_gates_run_are_gate_configuration(path):
    """Round-2 review: each of these, changed with one approval, passed the guard. Lowering SLO-API-AVAIL from
    99.9% to 99% lets Lab 15.2's R2 promote after 518 bad answers instead of rolling back after 7."""
    from pipeline.guard import is_pipeline_path
    assert is_pipeline_path(path, guard_policy())
    p = {"number": 1, "author": "engineer-1", "agent": None, "description": "", "files": [path],
         "approvals": [{"by": "reviewer-1", "after_last_push": True}], "workflows": {}}
    found = guard(p, guard_policy(), teams(), required())
    assert decision(found)[0] == "block" and [f.rule for f in found] == ["GD010", "PG002", "PG003"]
    two = dict(p, approvals=[{"by": "sam.o", "after_last_push": True}, {"by": "priya.n", "after_last_push": True}])
    assert [f.rule for f in guard(two, guard_policy(), teams(), required())] == ["GD010", "PG003"]
