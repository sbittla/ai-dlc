"""Lab 10.2's report: every drill, its outcome and its verdict (provided).

    python -m faultlab.report

Run from starter/ or solution/. The model and GitHub are simulated; the runtime is Relay 4.24.0's code.
"""

from __future__ import annotations

from .drills import run_all, run_blind


def report() -> str:
    lines = ["# Failure-injection drills on Relay 4.24.0's agent runtime", "",
             "Simulated model and GitHub; prices are assumptions as of 2027-01-12.", "",
             "| Drill | Fault | Ended | Reason | PRs | GitHub creates | Resumes | Approval requests | Refused calls |"
             " Cost | Audit records | Verdict |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |"]
    passed = 0
    results = run_all()
    for o, problems in results:
        passed += not problems
        refused = ", ".join(o["refusals"]) or "none"
        verdict = "pass" if not problems else "FAIL: " + "; ".join(problems)
        lines.append(f"| {o['id']} | {o['title']} | {o['status']} | {o['reason']} | {o['pulls']} | "
                     f"{o['github_creates']} | {o['resumes']} | {o['approval_requests']} | {refused} | "
                     f"${o['usd']:.3f} | {o['audit_records']} | {verdict} |")
    blind = run_blind("D02")
    lines += ["", f"Drills passed: {passed} of {len(results)}.",
              f"D02 with a handler that creates without looking first: {blind['pulls']} pull requests, "
              f"{blind['github_creates']} creates."]
    return "\n".join(lines)


def main() -> None:
    print(report())


if __name__ == "__main__":
    main()
