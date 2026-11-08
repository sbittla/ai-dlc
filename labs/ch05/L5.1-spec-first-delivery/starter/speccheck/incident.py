"""Chapter 5's opening incident: what three agents built from three prompts, against the contract.

    python -m speccheck.incident --incident ../data/incident --contract relay-repo/specs/001-escalation-rules/contracts/escalation-rules.schema.json

Each data/incident/agent-*.json records one agent's prompt, the signature it
chose, and one rule document and one evaluation document from its tests. The
report lists every field name each design uses, the names any two designs
share, and each document's errors against the contract. Validation uses the
contract validator in relay-repo/src/relay/escalation/contract.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "relay-repo" / "src"))
from relay.escalation.contract import validate  # noqa: E402


def field_names(document) -> set[str]:
    """Every key used anywhere in a JSON document."""
    if isinstance(document, dict):
        return set(document) | {k for v in document.values() for k in field_names(v)}
    if isinstance(document, list):
        return {k for v in document for k in field_names(v)}
    return set()


def load(folder: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(folder).glob("agent-*.json"))]


def compare(agents: list[dict], schema: dict) -> dict:
    names = {a["agent"]: field_names(a["rule_example"]) | field_names(a["evaluation_example"]) for a in agents}
    contract = set()
    for name in ("Rule", "Step", "Evaluation", "StepDecision"):
        contract |= set(schema["$defs"][name]["properties"])
    shared = {f"{x}+{y}": sorted(names[x] & names[y]) for x, y in combinations(sorted(names), 2)}
    rows = []
    for a in agents:
        rule_errors = validate(a["rule_example"], {"$ref": "#/$defs/Rule"}, schema)
        eval_errors = validate(a["evaluation_example"], {"$ref": "#/$defs/Evaluation"}, schema)
        rows.append({"agent": a["agent"], "signature": a["signature"], "fields": sorted(names[a["agent"]]),
                     "in_contract": sorted(names[a["agent"]] & contract),
                     "rule_errors": rule_errors, "evaluation_errors": eval_errors})
    distinct = set().union(*names.values())
    return {"rows": rows, "shared": shared, "distinct": len(distinct),
            "in_all_three": sorted(set.intersection(*names.values()))}


def render(result: dict) -> str:
    out = ["# Three prompts, three designs", "", "| Agent | Signature | Field names | Names also in the contract | "
           "Rule document errors | Evaluation document errors |", "| --- | --- | --- | --- | ---: | ---: |"]
    for r in result["rows"]:
        out.append(f"| {r['agent']} | `{r['signature']}` | {', '.join(r['fields'])} | "
                   f"{', '.join(r['in_contract']) or '–'} | {len(r['rule_errors'])} | {len(r['evaluation_errors'])} |")
    out += ["", f"Distinct field names across the three designs: {result['distinct']}",
            f"Field names used by all three: {len(result['in_all_three'])}"]
    out += [f"Field names shared by {pair}: {', '.join(names) or 'none'}" for pair, names in result["shared"].items()]
    valid = sum(not r["rule_errors"] and not r["evaluation_errors"] for r in result["rows"])
    out += [f"Designs whose documents both conform to the contract: {valid} of {len(result['rows'])}", ""]
    for r in result["rows"]:
        out.append(f"## Agent {r['agent']}: contract errors")
        out += [f"- rule: {e}" for e in r["rule_errors"]] + [f"- evaluation: {e}" for e in r["evaluation_errors"]]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="speccheck.incident")
    ap.add_argument("--incident", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    args = ap.parse_args(argv)
    schema = json.loads(args.contract.read_text(encoding="utf-8"))
    sys.stdout.write(render(compare(load(args.incident), schema)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
