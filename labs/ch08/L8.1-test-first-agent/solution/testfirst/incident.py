"""The opening incident, replayed: the agent's tests against the agent's code, then the approved tests.

The agent wrote data/agent-pr/src (engine.py, delivery.py, hours.py) and
data/agent-pr/tests in one session. This module measures four things:

1. the agent's tests against the agent's code (they all pass);
2. the line coverage those tests give the agent's delivery.py and hours.py;
3. the oracle check on the agent's tests (testfirst.oracle);
4. the tests the team wrote and approved first from the spec, plus the spec's
   policy tests, against the agent's code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .grade import MODULES_UNDER_TEST, TEST_FILES, Run, run_variant, statements
from .oracle import Finding, check_files

AGENT_FILES = ("src/relay/escalation/engine.py", "src/relay/escalation/delivery.py", "src/relay/escalation/hours.py")
AGENT_TESTS = "tests/escalation/test_agent_delivery.py"
POLICY_TESTS = "tests/escalation/test_escalation_policy.py"
COVERED = ("relay/escalation/delivery.py", "relay/escalation/hours.py")


@dataclass
class Incident:
    agent_on_agent: Run
    coverage: dict[str, tuple[int, int]]  # file -> (statements run, statements)
    findings: list[Finding]
    approved_on_agent: Run
    approved_on_reference: Run


def replay(repo: Path, data: Path) -> Incident:
    agent = data / "agent-pr"
    overlay = {rel: agent / rel for rel in AGENT_FILES}
    overlay[AGENT_TESTS] = agent / AGENT_TESTS
    own = run_variant(repo, overlay, [AGENT_TESTS], "agent code, agent tests", cover=COVERED)
    coverage = {}
    for suffix in COVERED:
        lines = statements(agent / "src" / suffix)
        coverage[suffix.rsplit("/", 1)[1]] = (len(lines & set(own.covered.get(suffix, []))), len(lines))
    findings = check_files([agent / AGENT_TESTS], MODULES_UNDER_TEST)
    approved = [TEST_FILES["hours"], TEST_FILES["delivery"], POLICY_TESTS]
    code_only = {rel: agent / rel for rel in AGENT_FILES}
    on_agent = run_variant(repo, code_only, approved, "agent code, approved tests")
    on_reference = run_variant(repo, {}, approved, "reference code, approved tests")
    return Incident(own, coverage, findings, on_agent, on_reference)


SECTIONS = {"test_escalation_hours.py": "B3", "test_escalation_delivery.py": "B5"}


def criteria_of(test: str, file: str = "") -> str:
    """'test_ESC_AC27_no_part...' -> 'ESC-AC27'; 'test_SEC04_...' -> 'SEC-04'; others -> their spec section."""
    if test.startswith("test_ESC_AC"):
        return "ESC-" + test[len("test_ESC_"):].split("_")[0]
    if test.startswith("test_SEC"):
        return "SEC-" + test[len("test_SEC"):].split("_")[0]
    return SECTIONS.get(file, "spec")
