"""The pipeline's stages and what each does on failure (TODO 3 in starter/).

A candidate (`data/candidates/*.json`, `data/train/*.json`) carries the evidence each stage reads: test results,
the evaluation gate's report with item-level labels, the coverage gate's report, three SARIF reports, signed
bundles, the desired state and, after a deployment, what runs. All of it is GENERATED.

Each stage returns pass, fail (exit 1: the gate said no) or error (exit 2: the gate could not decide). An error
is a failure. Order and modes follow ADR-044 and `.github/workflows/pipeline.yml`:

    build -> test, eval, adversarial, scan -> release -> admit -> deploy -> verify

- deliver: release runs only if every gate passed; deploy only if admit passed; verify only after deploy.
- verify-only: every gate, release and admit run and are recorded; deploy and verify are "skipped".
- anything else: like deliver, but deploy and verify are "skipped" (fail closed: nothing is deployed).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from relay.release import GradedItem, MissingHumanLabel, release_verdicts

from .admission import admit

GATES = ("test", "eval", "adversarial", "scan")
SCANNERS = {"semgrep": "Semgrep", "gitleaks": "gitleaks", "trivy": "Trivy"}
BLOCK_SEVERITY = 7.0


@dataclass(frozen=True)
class Stage:
    name: str
    status: str            # pass | fail | error | skipped
    detail: str = ""


@dataclass
class Run:
    candidate: str
    mode: str
    stages: list[Stage] = field(default_factory=list)

    def status(self, name: str) -> str:
        return next((s.status for s in self.stages if s.name == name), "absent")

    @property
    def first_failure(self) -> Stage | None:
        return next((s for s in self.stages if s.status in ("fail", "error")), None)

    @property
    def outcome(self) -> str:
        bad = self.first_failure
        if self.mode == "verify-only":
            return f"would block at {bad.name}" if bad else "would deploy"
        if bad:
            return f"blocked at {bad.name}" + (" (cannot decide)" if bad.status == "error" else "")
        return "deployed" if self.status("deploy") == "pass" else "not deployed (mode not set)"


def stage_test(c: dict) -> Stage:
    t = c.get("tests")
    if not t or not isinstance(t.get("passed"), int):
        return Stage("test", "error", "no test report")
    if t.get("failed"):
        return Stage("test", "fail", f"{len(t['failed'])} failed: {', '.join(t['failed'][:2])}")
    return Stage("test", "pass", f"{t['passed']} passed")


def stage_eval(c: dict) -> Stage:
    raise NotImplementedError("TODO 3: stage_eval")


def stage_adversarial(c: dict) -> Stage:
    r = c.get("coverage")
    if not r or "passed" not in r:
        return Stage("adversarial", "error", "no coverage report")
    if r.get("release") != c["version"]:
        return Stage("adversarial", "error", f"report is for {r.get('release')}, not {c['version']}")
    if not r["passed"]:
        return Stage("adversarial", "fail", "; ".join(r.get("reasons", [])[:3]))
    return Stage("adversarial", "pass", f"{r['policy']} passes")


def _sarif_problem(name: str, report) -> str | None:
    if not isinstance(report, dict) or report.get("version") != "2.1.0":
        return "missing or not SARIF 2.1.0"
    runs = report.get("runs")
    if not runs:
        return "no runs: an empty report is not a clean one"
    if any(((r.get("tool") or {}).get("driver") or {}).get("name") != SCANNERS[name] for r in runs):
        return f"not written by {SCANNERS[name]}"
    return None


def stage_scan(c: dict) -> Stage:
    raise NotImplementedError("TODO 3: stage_scan")


def run_pipeline(c: dict, mode: str, policy: dict, trust: dict) -> Run:
    """Run every stage for candidate `c` under `mode`, with Relay's admission policy and the trust root."""
    raise NotImplementedError("TODO 3: run_pipeline")
