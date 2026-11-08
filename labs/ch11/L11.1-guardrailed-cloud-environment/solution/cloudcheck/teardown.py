"""Teardown checks, TD001-TD004: is this destroy plan safe and complete, and is anything left?

A teardown that has not been tested is a hope. These checks read three things a person can
produce without touching anything: the plan the environment was built from, the destroy plan
(`tofu plan -destroy` then `tofu show -json`), and afterwards the tagged-resource inventory
(`aws resourcegroupstaggingapi get-resources --tag-filters Key=env,Values=<env>`).

What they cannot see: untagged resources created by hand (the inventory lists only tagged ones),
and spend that continues after teardown, such as retained snapshots. Cost Explorer filtered on
"no env tag" covers the first; the expires tag on every retained item covers the second.
"""

from __future__ import annotations

from datetime import date

from .plan import resources
from .policy import Finding

TEARDOWN_RULES = {
    "TD001": "The destroy plan deletes everything the environment created, and changes nothing else",
    "TD002": "The destroy plan deletes nothing outside the environment",
    "TD003": "Databases: the destroy can run, and a final snapshot is taken",
    "TD004": "After teardown, nothing tagged for the environment remains except dated, retained snapshots",
}
RETAINED = (":snapshot:", ":cluster-snapshot:")


def check_teardown(apply_plan: dict, destroy_plan: dict, env: str, app: str = "relay",
                   inventory: dict | None = None, as_of: date | None = None) -> list[Finding]:
    """TODO 7. Return findings for TD001-TD004, sorted by (rule, address, message).

    TD001  For every resource in apply_plan (resources(apply_plan)) not deleted by destroy_plan
           (a resource change whose actions include "delete"): "not deleted" at its address.
           For every change in destroy_plan whose actions are not exactly ["delete"]:
           "the destroy plan also <actions joined by '/'>s it" (for example "also creates it").
    TD002  For every deleted resource whose `before` has tags_all with env != env or app != app:
           "would delete a resource tagged env=<env>, app=<app>" (use "-" for a missing tag).
           Resources without tags_all are not judged.
    TD003  For every deleted aws_db_instance (from `before`):
             deletion_protection true -> "destroy will fail: deletion protection is on"
             skip_final_snapshot true, or no final_snapshot_identifier -> "no final snapshot: the data
             is deleted with the database"
    TD004  Only if inventory is given: for every entry in inventory["ResourceTagMappingList"] whose
           tags include env=<env>, at its ResourceARN:
             not a retained kind (ARN contains one of RETAINED) -> "left behind"
             retained, no expires tag -> "retained with no expires tag"
             retained, expires earlier than as_of -> "retained past its expiry <date>"
    """
    out: list[Finding] = []
    deleted = {}
    for rc in destroy_plan.get("resource_changes", []):
        actions = rc["change"]["actions"]
        if "delete" in actions:
            deleted[rc["address"]] = rc
        if actions != ["delete"]:
            verbs = "/".join(f"{a}" for a in actions)
            out.append(Finding("TD001", rc["address"], f"the destroy plan also {verbs}s it"))
    for r in resources(apply_plan):
        if r.address not in deleted:
            out.append(Finding("TD001", r.address, "not deleted"))

    for addr, rc in deleted.items():
        before = rc["change"].get("before") or {}
        tags = before.get("tags_all")
        if tags is not None and (tags.get("env") != env or tags.get("app") != app):
            out.append(Finding("TD002", addr, f"would delete a resource tagged env={tags.get('env', '-')}, "
                                              f"app={tags.get('app', '-')}"))
        if rc["type"] == "aws_db_instance":
            if before.get("deletion_protection") is True:
                out.append(Finding("TD003", addr, "destroy will fail: deletion protection is on"))
            if before.get("skip_final_snapshot") is True or not before.get("final_snapshot_identifier"):
                out.append(Finding("TD003", addr, "no final snapshot: the data is deleted with the database"))

    if inventory is not None:
        for item in inventory.get("ResourceTagMappingList", []):
            tags = {t["Key"]: t["Value"] for t in item.get("Tags", [])}
            if tags.get("env") != env:
                continue
            arn = item["ResourceARN"]
            if not any(k in arn for k in RETAINED):
                out.append(Finding("TD004", arn, "left behind"))
            elif "expires" not in tags:
                out.append(Finding("TD004", arn, "retained with no expires tag"))
            elif as_of is not None and date.fromisoformat(tags["expires"]) < as_of:
                out.append(Finding("TD004", arn, f"retained past its expiry {tags['expires']}"))
    return sorted(out, key=lambda f: (f.rule, f.address, f.message))


def ready(findings: list[Finding]) -> bool:
    """Ready to run the destroy: no TD001-TD003 findings. TD004 is judged after it has run."""
    return not any(f.rule in ("TD001", "TD002", "TD003") for f in findings)
