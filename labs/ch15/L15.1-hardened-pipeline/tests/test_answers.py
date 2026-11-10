"""Numbers in book/answers/ch15-answers.md that come from Lab 15.1."""

from pipeline.guard import decision, guard
from pipeline.report import all_prs, guard_policy, required, teams


def test_exercise_5_the_incident_without_pg001():
    pr = dict(all_prs()[0], files=[".github/workflows/ci.yml"])
    findings = guard(pr, guard_policy(), teams(), required())
    assert [f.rule for f in findings] == ["GD004", "GD005", "PG002", "PG003"] and decision(findings)[0] == "block"
    pr = dict(pr, approvals=pr["approvals"] + [{"by": "aisha.r", "after_last_push": True}])
    findings = guard(pr, guard_policy(), teams(), required())
    assert [f.rule for f in findings] == ["GD004", "GD005", "PG003"]
    assert findings[-1].message.endswith("reason")
