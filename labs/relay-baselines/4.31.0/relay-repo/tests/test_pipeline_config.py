"""The delivery pipeline's configuration (4.29.0, ADR-044 to ADR-047), checked as text: Relay has no YAML parser
and adds no dependency for one. Lab 15.1's pipeline lint parses the workflows fully."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
UNTRUSTED = ("pull_request_target", "issue_comment", "issues:", "workflow_run")


def jobs(text):
    """{job name: its text}, for the top-level `jobs:` mapping (two-space indented keys)."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_every_workflow_starts_with_no_permissions_and_has_no_untrusted_trigger():
    for wf in sorted(WF.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        head = "\n".join(ln for ln in text.split("\njobs:\n", 1)[0].splitlines() if not ln.lstrip().startswith("#"))
        assert not any(t in head for t in UNTRUSTED), wf.name
        assert re.search(r"(?m)^permissions:\s*(\{\}|\n  contents: read)", head), wf.name


def test_id_token_only_in_jobs_bound_to_an_environment_or_calling_the_release():
    for wf in sorted(WF.glob("*.yml")):
        for name, body in jobs(wf.read_text(encoding="utf-8")).items():
            if "id-token: write" in body:
                assert "environment:" in body or "uses: ./.github/workflows/release.yml" in body, (wf.name, name)


def test_checkout_never_persists_credentials():
    for wf in sorted(WF.glob("*.yml")):
        lines = wf.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "uses: actions/checkout@" in line:
                assert "persist-credentials: false" in lines[i + 1], (wf.name, i + 1)


def test_release_runs_only_when_the_pipeline_calls_it():
    text = (WF / "release.yml").read_text(encoding="utf-8")
    assert "workflow_call:" in text and "tags:" not in text.split("\njobs:\n", 1)[0]


def test_deliver_mode_needs_every_gate_to_succeed_and_nothing_deploys_unless_mode_is_deliver():
    js = jobs((WF / "pipeline.yml").read_text(encoding="utf-8"))
    for gate in ("test", "eval", "adversarial", "scan"):
        assert f"needs.{gate}.result == 'success'" in js["release"]
        assert "needs: build" in js[gate]
    assert "production" not in js  # deployment is deploy.yml, on the desired state's merge
    assert "gates:" in js["release"] and all(f"needs.{g}.result" in js["release"].split("gates:")[1]
                                               for g in ("test", "eval", "adversarial", "scan"))


def test_production_deploys_only_from_the_desired_state_on_main_in_deliver_mode():
    text = (WF / "deploy.yml").read_text(encoding="utf-8")
    head = text.split("\njobs:\n", 1)[0]
    assert "branches: [main]" in head and 'paths: ["deploy/gitops/**"]' in head and "tags" not in head
    job = jobs(text)["production"]
    assert "vars.RELAY_PIPELINE_MODE == 'deliver'" in job and "environment: production" in job
    assert job.index("admit.py") < job.index("reconcile.py")


def test_release_always_attests_the_gate_results_and_tags_must_start_with_a_digit():
    rel = (WF / "release.yml").read_text(encoding="utf-8")
    assert "gate-results/v1" in rel and "inputs.gates" in rel
    assert 'tags: ["v[0-9]*"]' in (WF / "pipeline.yml").read_text(encoding="utf-8")
    pol = load("deploy/admission/policy.json")
    assert pol["version_pattern"] == "^[0-9]+\\.[0-9]+\\.[0-9]+$"
    assert set(pol["gate_results"]["required"].values()) == {"success"} and pol["revoked_releases"] == []


def test_the_guard_is_not_defined_in_the_repository_it_guards():
    assert not any("pipeline-guard:" in wf.read_text(encoding="utf-8") for wf in WF.glob("*.yml"))
    req = load("governance/required-workflows.json")["required_workflows"]
    assert [r["check"] for r in req] == ["pipeline-guard"]
    assert req[0]["repository"] != "relay-example/relay" and re.fullmatch(r"[0-9a-f]{40}", req[0]["ref"])
    assert req[0]["reads_policy_from"] == "base" and "merge_group" in req[0]["events"]
    assert load("governance/branch-protection.json")["required_merge_queue"]["enabled"] is True


def test_every_required_check_is_a_job_that_runs_on_every_pull_request_without_a_condition():
    required = load("governance/branch-protection.json")["required_status_checks"]["contexts"]
    external = {r["check"] for r in load("governance/required-workflows.json")["required_workflows"]}
    pr_jobs = {}
    for wf in sorted(WF.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        if "pull_request" in text.split("\njobs:\n", 1)[0]:
            assert "paths:" not in text.split("\njobs:\n", 1)[0], wf.name
            pr_jobs.update(jobs(text))
    for check in required:
        if check in external:
            continue
        assert check in pr_jobs, check
        assert not re.search(r"(?m)^    if:", pr_jobs[check]), check
        assert "continue-on-error" not in pr_jobs[check], check
    assert {"pr-check", "triage-eval", "coverage-gate", "pipeline-guard"} <= set(required)


def test_admission_expects_the_release_workflow_at_the_versions_own_tag():
    policy = load("deploy/admission/policy.json")
    assert policy["identity"] == ("https://github.com/relay-example/relay/.github/workflows/release.yml"
                                  "@refs/tags/v{version}")
    assert policy["issuer"] == "https://token.actions.githubusercontent.com"
    assert policy["refuse_tags"] is True and policy["require_tlog"] is True and len(policy["attestations"]) == 3


def test_production_desired_state_is_this_release_by_digest():
    desired = load("deploy/gitops/production.json")
    version = re.search(r'version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))[1]
    assert desired["release"] == version
    assert set(desired["images"]) == set(load("deploy/admission/policy.json")["images"])
    assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", d) for d in desired["images"].values())
    assert desired["mode"] in {"verify-only", "deliver"}


def test_the_canary_watches_real_slos_and_real_flags():
    canary = load("deploy/rollout/canary.json")
    slos = {s["slo_id"] for s in load("docs/slo/slos.json")["slos"]}
    flags = load("deploy/flags.json")["features"]
    assert set(canary["signals"]) | set(canary["ai_feature_signals"]) <= slos
    assert set(canary["ai_feature_signals"].values()) <= set(flags)
    assert [s["percent"] for s in canary["steps"]] == [5, 25, 50, 100]
    assert canary["rollback_burn_rate"] == 14.4 and canary["min_events_per_window"] >= 100


def test_the_guard_covers_the_pipeline_and_its_own_policy():
    guard = load("governance/pipeline-guard.json")
    paths = guard["pipeline_paths"]
    for p in (".github/", "governance/", "deploy/", "security/", "supply-chain/", "infra/", "evals/",
              "docs/slo/", "tools/"):
        assert p in paths
    assert sorted(guard["rules"]) == ["PG001", "PG002", "PG003", "PG004"]
    for p in ("docs/slo/", "tools/admit.py", "tools/reconcile.py", "tools/security_gate.py", "tools/lint.py",
              "evals/", "security/", "deploy/rollout/", "deploy/admission/"):
        assert p in guard["gate_config_paths"], p


def test_a_tag_must_name_a_commit_on_main():
    build = jobs((WF / "pipeline.yml").read_text(encoding="utf-8"))["build"]
    assert "git merge-base --is-ancestor \"$GITHUB_SHA\" origin/main" in build and "fetch-depth: 0" in build
    assert build.index("merge-base") < build.index("docker build")


def test_codeowners_names_an_owner_for_every_new_pipeline_file():
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for line in ("/deploy/admission/  @relay/security", "/deploy/test-sandbox/  @relay/security",
                 "/tools/sandbox_run.py  @relay/security", "/src/relay/release/  @relay/security",
                 "/governance/pipeline-guard.json  @relay/security @relay/platform-leads",
                 "/evals/            @relay/security"):
        assert line in owners, line


def test_deploy_from_main_rechecks_that_the_release_tag_is_on_main():
    job = jobs((WF / "deploy.yml").read_text(encoding="utf-8"))["production"]
    assert 'git merge-base --is-ancestor "refs/tags/v$RELEASE" origin/main' in job and "fetch-depth: 0" in job
    assert job.index("merge-base") < job.index("admit.py") < job.index("reconcile.py")
