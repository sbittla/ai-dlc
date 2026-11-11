"""Relay's tools/admit.py and tools/security_gate.py, the command-line tools pipeline.yml runs.

They live in relay-repo/tools/ but are tested here, so Relay's own suite (959 tests) is unchanged. admit.py is
driven with a FAKE cosign: nothing here runs cosign, contacts a registry or Sigstore. The fake answers as we read
cosign's documentation (exit status, and one DSSE envelope per line for verify-attestation); a real attestation
has not been checked (Chapter 15's editor review, item 24).
"""

import base64
import importlib.util
import json
import re
import sys

import pytest

from conftest import RELAY

POLICY_PATH = RELAY / "deploy" / "admission" / "policy.json"
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
GATES_PATH = RELAY / "security" / "gates.json"
VERSION = "4.29.0"
IDENTITY = f"https://github.com/relay-example/relay/.github/workflows/release.yml@refs/tags/v{VERSION}"
ISSUER = "https://token.actions.githubusercontent.com"
RELAY_DIGEST = "sha256:" + "a" * 64
PROXY_DIGEST = "sha256:" + "b" * 64
OTHER_DIGEST = "sha256:" + "c" * 64
GATE_TYPE = POLICY["gate_results"]["type"]
ALL_PASSED = {"test": "success", "eval": "success", "adversarial": "success", "scan": "success"}
NO_MATCH = "Error: no matching attestations: none found\n"
WRONG_ID = ("Error: none of the expected identities matched what was in the certificate, got subjects "
            "[https://github.com/relay-example/relay/.github/workflows/release.yml@refs/heads/agent/rly-2741]\n")


def load_tool(name):
    spec = importlib.util.spec_from_file_location(f"relay_tool_{name}", RELAY / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


admit_tool = load_tool("admit")
gate_tool = load_tool("security_gate")


def envelope(ptype, digest, predicate=None):
    statement = {"_type": "https://in-toto.io/Statement/v1", "predicateType": ptype,
                 "subject": [{"name": "registry.relay.example/relay", "digest": {"sha256": digest[7:]}}],
                 "predicate": predicate or {}}
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    return json.dumps({"payloadType": "application/vnd.in-toto+json", "payload": payload, "signatures": [{}]})


class FakeCosign:
    """Answers cosign verify and verify-attestation for one release, with faults set per image."""

    def __init__(self, signer=IDENTITY, missing=(), predicate_as=None, subject=None, gates=ALL_PASSED,
                 unsigned=()):
        self.signer, self.missing, self.predicate_as = signer, set(missing), predicate_as or {}
        self.subject, self.gates, self.unsigned = subject, gates, set(unsigned)
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        assert cmd[0] == "cosign"
        ref = cmd[-1]
        image, digest = ref.rsplit("/", 1)[-1].split("@")
        identity = cmd[cmd.index("--certificate-identity") + 1]
        assert cmd[cmd.index("--certificate-oidc-issuer") + 1] == ISSUER
        assert "--certificate-identity-regexp" not in cmd
        if image in self.unsigned:
            return 1, "", "Error: no signatures found\n"
        if identity != self.signer:
            return 1, "", WRONG_ID
        if cmd[1] == "verify":
            return 0, json.dumps([{"critical": {"image": {"docker-manifest-digest": digest}}}]), ""
        assert cmd[1] == "verify-attestation"
        wanted = cmd[cmd.index("--type") + 1]
        ptype = {"cyclonedx": "https://cyclonedx.org/bom", "slsaprovenance1": "https://slsa.dev/provenance/v1"}.get(
            wanted, wanted)
        if ptype == "https://slsa.dev/provenance/v1" and "--new-bundle-format" not in cmd:
            return 1, "", NO_MATCH  # the provenance is a Sigstore bundle stored as an OCI referrer
        if ptype in self.missing:
            return 1, "", NO_MATCH
        written = self.predicate_as.get(ptype, ptype)
        predicate = self.gates if ptype == GATE_TYPE else {}
        return 0, envelope(written, self.subject or digest, predicate) + "\n", ""


def run_admit(fake, *args):
    argv = ["--policy", str(POLICY_PATH), "--registry", "registry.relay.example", *args]
    return admit_tool.main(argv, run=fake)


def digests(**images):
    return json.dumps(images or {"relay": RELAY_DIGEST, "relay-egress-proxy": PROXY_DIGEST})


def rules(capsys):
    return re.findall(r"^(AD\d{3}) ", capsys.readouterr().out, re.M)


def test_a_good_release_is_admitted_with_exact_identity_and_new_bundle_format_for_provenance(capsys):
    fake = FakeCosign()
    assert run_admit(fake, "--version", VERSION, "--digests", digests()) == 0
    assert "release 4.29.0 admitted, 0 finding(s)" in capsys.readouterr().out
    for image, digest in (("relay", RELAY_DIGEST), ("relay-egress-proxy", PROXY_DIGEST)):
        ref = f"registry.relay.example/{image}@{digest}"
        mine = [c for c in fake.calls if c[-1] == ref]
        assert mine[0] == ["cosign", "verify", "--certificate-identity", IDENTITY,
                           "--certificate-oidc-issuer", ISSUER, ref]
        assert ["cosign", "verify-attestation", "--new-bundle-format", "--type", "slsaprovenance1",
                "--certificate-identity", IDENTITY, "--certificate-oidc-issuer", ISSUER, ref] in mine
        assert [c[c.index("--type") + 1] for c in mine[1:]] == [
            "cyclonedx", "https://relay.example/attestations/ai-bom/v1", "slsaprovenance1", GATE_TYPE]


def test_the_desired_state_form_admits_production_json(capsys):
    production = RELAY / "deploy" / "gitops" / "production.json"
    release = json.loads(production.read_text(encoding="utf-8"))["release"]
    fake = FakeCosign(signer=POLICY["identity"].format(version=release))
    assert run_admit(fake, "--desired", str(production)) == 0
    assert {c[-1].split("@")[0] for c in fake.calls} == {"registry.relay.example/relay",
                                                         "registry.relay.example/relay-egress-proxy"}


def test_a_missing_provenance_attestation_is_refused(capsys):
    fake = FakeCosign(missing={"https://slsa.dev/provenance/v1"})
    assert run_admit(fake, "--version", VERSION, "--digests", digests(relay=RELAY_DIGEST)) == 1
    out = capsys.readouterr().out
    assert re.search(r"^AD006 relay: https://slsa.dev/provenance/v1: ", out, re.M) and "refused" in out


def test_a_signature_from_an_agents_branch_is_refused_as_ad003(capsys):
    fake = FakeCosign(signer="https://github.com/relay-example/relay/.github/workflows/release.yml"
                             "@refs/heads/agent/rly-2741")
    assert run_admit(fake, "--version", VERSION, "--digests", digests(relay=RELAY_DIGEST)) == 1
    assert rules(capsys) == ["AD003"]
    assert len(fake.calls) == 1  # nothing more is checked for an image whose signature fails


def test_a_provenance_of_the_wrong_predicate_type_is_refused(capsys):
    fake = FakeCosign(predicate_as={"https://slsa.dev/provenance/v1": "https://spdx.dev/Document/v2.3"})
    assert run_admit(fake, "--version", VERSION, "--digests", digests(relay=RELAY_DIGEST)) == 1
    assert rules(capsys) == ["AD006"]


def test_an_unsigned_image_is_refused_as_ad002(capsys):
    fake = FakeCosign(unsigned={"relay"})
    assert run_admit(fake, "--version", VERSION, "--digests", digests()) == 1
    assert rules(capsys) == ["AD002"]


def test_attestations_bound_to_another_digest_are_refused_as_ad005(capsys):
    fake = FakeCosign(subject=OTHER_DIGEST)
    assert run_admit(fake, "--version", VERSION, "--digests", digests(relay=RELAY_DIGEST)) == 1
    assert rules(capsys) == ["AD005", "AD008"]


def test_an_image_signed_after_a_failed_gate_is_refused_as_ad008(capsys):
    fake = FakeCosign(gates={**ALL_PASSED, "eval": "failure"})
    assert run_admit(fake, "--version", VERSION, "--digests", digests(relay=RELAY_DIGEST)) == 1
    out = capsys.readouterr().out
    assert "AD008 relay: gates that did not succeed: eval" in out


@pytest.mark.parametrize("case,expected", [
    ({"version": VERSION, "images": {"relay": "4.29.0"}}, ["AD001"]),
    ({"version": VERSION, "images": {"redis": RELAY_DIGEST}}, ["AD007"]),
    ({"version": "train-2027.04.27", "images": {"relay": RELAY_DIGEST}}, ["AD003"]),
])
def test_tags_unknown_images_and_non_release_versions_are_refused(case, expected, capsys):
    fake = FakeCosign(signer=POLICY["identity"].format(version=case["version"]))
    assert run_admit(fake, "--version", case["version"], "--digests", json.dumps(case["images"])) == 1
    assert rules(capsys) == expected


def test_a_revoked_release_is_refused_as_ad009(tmp_path, capsys):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({**POLICY, "revoked_releases": [VERSION]}), encoding="utf-8")
    argv = ["--policy", str(policy), "--version", VERSION, "--digests", digests(relay=RELAY_DIGEST)]
    assert admit_tool.main(argv, run=FakeCosign()) == 1
    assert capsys.readouterr().out.startswith("AD009 *: release 4.29.0 is revoked")


# ---- tools/security_gate.py ----------------------------------------------------------------------------------

def sarif(tool, results=(), runs=True):
    doc = {"version": "2.1.0", "runs": []}
    if runs:
        doc["runs"].append({"tool": {"driver": {"name": tool}}, "results": list(results)})
    return doc


def result(rule, severity, fingerprint="fp1", level="warning"):
    return {"ruleId": rule, "level": level, "message": {"text": rule},
            "properties": {"security-severity": str(severity)} if severity is not None else {},
            "partialFingerprints": {"primaryLocationLineHash": fingerprint},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/relay/api.py"},
                                                "region": {"startLine": 7}}}]}


def write_reports(tmp, semgrep=(), gitleaks=(), trivy=(), image=(), empty=()):
    out = []
    for name, tool, res in (("semgrep", "Semgrep", semgrep), ("gitleaks", "gitleaks", gitleaks),
                            ("trivy", "Trivy", trivy), ("trivy-image", "Trivy", image)):
        p = tmp / f"{name}.sarif"
        p.write_text(json.dumps(sarif(tool, res, runs=name not in empty)), encoding="utf-8")
        out.append(str(p))
    return out


def gate(tmp, reports, *extra, suppressions=()):
    sup = tmp / "suppressions.json"
    sup.write_text(json.dumps({"suppressions": list(suppressions)}), encoding="utf-8")
    return gate_tool.main(["--policy", str(GATES_PATH), "--suppressions", str(sup), "--as-of", "2027-04-01",
                           *extra, *reports])


def test_gate_passes_four_clean_reports_and_finds_the_policys_suppressions_file(tmp_path, capsys):
    reports = write_reports(tmp_path, semgrep=[result("py.low", 3.1)])
    assert gate(tmp_path, reports, "--require-reports") == 0
    assert gate_tool.main(["--policy", str(GATES_PATH), "--require-reports", *reports]) == 0  # Relay's own file
    assert "warn  semgrep py.low" in capsys.readouterr().out


def test_gate_blocks_a_secret_and_a_high_finding(tmp_path):
    assert gate(tmp_path, write_reports(tmp_path, gitleaks=[result("aws-key", None)]), "--require-reports") == 1
    assert gate(tmp_path, write_reports(tmp_path, image=[result("CVE-2027-1", 7.5)]), "--require-reports") == 1


def test_gate_cannot_check_an_empty_or_missing_report_or_one_from_another_tool(tmp_path, capsys):
    reports = write_reports(tmp_path, empty={"trivy"})
    assert gate(tmp_path, reports, "--require-reports") == 2
    assert "no runs: an empty report is not a clean one" in capsys.readouterr().out
    assert gate(tmp_path, reports) == 0  # 4.28.0's behaviour without the flag: the March incident
    assert gate(tmp_path, write_reports(tmp_path)[:1] + write_reports(tmp_path)[2:], "--require-reports") == 2
    other = tmp_path / "other.sarif"
    other.write_text(json.dumps(sarif("Snyk")), encoding="utf-8")
    assert gate(tmp_path, write_reports(tmp_path) + [str(other)], "--require-reports") == 2


def test_gate_applies_only_a_valid_suppression(tmp_path):
    reports = write_reports(tmp_path, semgrep=[result("py.sqli", 8.0, fingerprint="abc")])
    sup = {"id": "SUP-1", "rule": "py.sqli", "fingerprint": "abc", "reason": "parameterised upstream",
           "author": "dev.k", "reviewed_by": "sam.o", "created": "2027-03-20", "expires": "2027-05-20"}
    assert gate(tmp_path, reports, "--require-reports", suppressions=[sup]) == 0
    assert gate(tmp_path, reports, "--require-reports", suppressions=[{**sup, "reviewed_by": "dev.k"}]) == 1
    assert gate(tmp_path, reports, "--require-reports", suppressions=[{**sup, "expires": "2027-03-31"}]) == 1


# ---- the workflows name only tools that exist ------------------------------------------------------------------

NOT_VENDORED = {"tools/reconcile.py"}  # deploy.yml's reconciler drives ECS; it is not in this snapshot


def test_every_tool_the_workflows_run_exists():
    named = set()
    for wf in sorted((RELAY / ".github" / "workflows").glob("*.yml")):
        named |= set(re.findall(r"\b(tools/[a-z_]+\.py)\b", wf.read_text(encoding="utf-8")))
    pipeline = (RELAY / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    assert {"tools/admit.py", "tools/security_gate.py"} <= set(re.findall(r"tools/[a-z_]+\.py", pipeline))
    missing = sorted(t for t in named - NOT_VENDORED if not (RELAY / t).is_file())
    assert missing == []
