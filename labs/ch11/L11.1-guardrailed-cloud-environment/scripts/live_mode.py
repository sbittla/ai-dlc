"""OPTIONAL live mode for Lab 11.1: real `tofu plan`, `apply` and `destroy` in YOUR sandbox account.

    python scripts/live_mode.py plan    --account-id 123456789012 --email you@example.com
    python scripts/live_mode.py apply   --account-id 123456789012 --email you@example.com \
        --max-usd 5 --hours 2 --i-accept-charges --execute
    python scripts/live_mode.py destroy --account-id 123456789012 --email you@example.com --execute

It costs money and the Core lab does not need it. Without --execute it only prints the commands
it would run. With --execute it also requires:

  - the environment variable LAB11_LIVE=1, OpenTofu (`tofu`) on PATH, and credentials for a
    sandbox account you own, that is not shared and holds nothing you care about;
  - for apply: --i-accept-charges, a ceiling --max-usd of at most 10, and a planned run time
    --hours of at most 4. The script estimates the real plan's fixed cost with the lab's own
    estimator (solution/cloudcheck) and refuses to apply if hours x hourly cost exceeds the ceiling.

What it changes, so the ceiling holds: the three ECS services start with 0 tasks (no image is
pushed), and the HTTPS listener is excluded (it needs a certificate). State is local, in
evidence/live/, without the remote backend or state encryption of infra/versions.tf.
The database has deletion protection: before `destroy`, set deletion_protection = false in
evidence/live/infra/data.tf and run apply once more (runbook infra/runbooks/teardown.md, step 2).
The destroy keeps a final snapshot; delete it afterwards or it is billed for storage.

Errors from AWS or OpenTofu are recorded in evidence/live/live-log.jsonl as outcomes, never hidden.
The authors have not run this script against a real account for the book; treat it as a
procedure to review before you run it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
INFRA = LAB / "relay-repo" / "infra"
WORK = LAB / "evidence" / "live"
MAX_CEILING_USD = 10.0
MAX_HOURS = 4.0
LIVE_VERSIONS = """terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
  backend "local" {
    path = "live.tfstate"
  }
}
"""


class Refused(Exception):
    """The live mode will not run with these inputs."""


def overrides(args) -> list[str]:
    return ["-var-file=nonprod.tfvars", f"-var=account_id={args.account_id}",
            f"-var=budget_emails=[\"{args.email}\"]", "-var=service_desired_count=0",
            "-var=worker_desired_count=0", "-var=proxy_desired_count=0", "-exclude=aws_lb_listener.https"]


def commands(args) -> list[list[str]]:
    if args.action == "plan":
        return [["tofu", "init", "-input=false"], ["tofu", "plan", "-input=false", "-out=live.tfplan", *overrides(args)],
                ["tofu", "show", "-json", "live.tfplan"]]
    if args.action == "apply":
        return [["tofu", "init", "-input=false"], ["tofu", "plan", "-input=false", "-out=live.tfplan", *overrides(args)],
                ["tofu", "show", "-json", "live.tfplan"], ["tofu", "apply", "-input=false", "live.tfplan"]]
    return [["tofu", "plan", "-destroy", "-input=false", "-out=destroy.tfplan", *overrides(args)],
            ["tofu", "show", "-json", "destroy.tfplan"], ["tofu", "apply", "-input=false", "destroy.tfplan"]]


def preflight(args, env: dict, which=shutil.which) -> None:
    if not args.account_id.isdigit() or len(args.account_id) != 12 or args.account_id == "111122223333":
        raise Refused("--account-id must be your own 12-digit sandbox account, not the book's example")
    if not args.execute:
        return
    if env.get("LAB11_LIVE") != "1":
        raise Refused("set LAB11_LIVE=1 to confirm you mean to change a real account")
    if which("tofu") is None:
        raise Refused("OpenTofu (`tofu`) is not on PATH")
    if args.action == "apply":
        if not args.i_accept_charges:
            raise Refused("apply needs --i-accept-charges")
        if args.max_usd is None or not 0 < args.max_usd <= MAX_CEILING_USD:
            raise Refused(f"apply needs --max-usd between 0 and {MAX_CEILING_USD:g}")
        if not 0 < args.hours <= MAX_HOURS:
            raise Refused(f"--hours must be between 0 and {MAX_HOURS:g}")


def within_ceiling(plan_json: dict, hours: float, max_usd: float) -> tuple[bool, float]:
    sys.path.insert(0, str(LAB / "solution"))
    from cloudcheck.cost import estimate  # noqa: E402
    prices = json.loads((LAB / "data" / "prices" / "aws-us-east-1-2026-11.json").read_text(encoding="utf-8"))
    cost = estimate(plan_json, prices).hourly * hours
    return cost <= max_usd, cost


def log(event: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    event = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
    with open(WORK / "live-log.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event) + "\n")


def run(args) -> int:  # pragma: no cover - never run in the lab's tests or CI
    work_infra = WORK / "infra"
    if args.action != "destroy" or not work_infra.exists():
        shutil.copytree(INFRA, work_infra, dirs_exist_ok=True, ignore=shutil.ignore_patterns("org", "*.tfstate*"))
        (work_infra / "versions.tf").write_text(LIVE_VERSIONS, encoding="utf-8")
    for cmd in commands(args):
        out = subprocess.run(cmd, cwd=work_infra, capture_output=True, text=True)
        log({"command": " ".join(cmd[:3]), "exit": out.returncode, "stderr_tail": out.stderr[-2000:]})
        if out.returncode != 0:
            sys.stderr.write(f"stopped: {' '.join(cmd)} exited {out.returncode}; see {WORK / 'live-log.jsonl'}\n")
            return out.returncode
        if cmd[:2] == ["tofu", "show"]:
            (WORK / f"{args.action}.plan.json").write_text(out.stdout, encoding="utf-8")
            if args.action == "apply":
                ok, cost = within_ceiling(json.loads(out.stdout), args.hours, args.max_usd)
                log({"estimate_usd": round(cost, 2), "ceiling_usd": args.max_usd, "hours": args.hours})
                if not ok:
                    sys.stderr.write(f"refused: estimated ${cost:.2f} for {args.hours:g} h exceeds ${args.max_usd:g}\n")
                    return 3
    return 0


def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python scripts/live_mode.py", description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["plan", "apply", "destroy"])
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--email", required=True, help="where budget alerts go")
    ap.add_argument("--max-usd", type=float)
    ap.add_argument("--hours", type=float, default=2.0)
    ap.add_argument("--i-accept-charges", action="store_true")
    ap.add_argument("--execute", action="store_true", help="without it, only print the commands")
    args = ap.parse_args(argv)
    try:
        preflight(args, os.environ if env is None else env)
    except Refused as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 2
    if not args.execute:
        for cmd in commands(args):
            sys.stdout.write("would run: " + " ".join(cmd) + "\n")
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
