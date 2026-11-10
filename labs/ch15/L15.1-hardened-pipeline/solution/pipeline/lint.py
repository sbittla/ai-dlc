"""Policy checks over a workflow file (TODO 1 in starter/).

    PL001  an action is not pinned to a full commit SHA (a remote reusable workflow too; docker:// by digest)
    PL002  the workflow has no top-level `permissions`, or they grant write anywhere (write-all included)
    PL003  a job asks for `write-all`, or for `id-token: write` without a protected `environment`
           (a job that only calls a local reusable workflow is checked in that workflow instead)
    PL004  an untrusted trigger (pull_request_target, issue_comment, issues, workflow_run) in a workflow
           where any job can write, mint an OIDC token or read a secret
    PL005  a long-lived cloud credential: a secret whose name is a cloud key, or a key passed to an action
    PL006  event or input text pasted into a `run:` script (script injection)
    PL007  actions/checkout without `persist-credentials: false`
    PL008  a self-hosted runner without the `ephemeral` label (Relay's one runner group registers only
           one-job runners and gives them that label; the label is all a workflow file can show)
    PL009  `continue-on-error` set to anything other than literal `false` (an expression counts)
    PL010  a container image by tag, not digest: `docker run`/`docker pull` in a script, a job `container`,
           or a `services` image

Relay's own workflows must have none. Lab 15.1 also lints a pipeline an agent drafted (`data/drafts/`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import yamlish

SHA = re.compile(r"@[0-9a-f]{40}$")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")
UNTRUSTED = {"pull_request_target", "issue_comment", "issues", "workflow_run"}
CLOUD_KEY = re.compile(r"AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|ACCESS_KEY|SERVICE_ACCOUNT_KEY|GOOGLE_CREDENTIALS|"
                       r"GCP_CREDENTIALS|AZURE_CLIENT_SECRET|AZURE_CREDENTIALS", re.IGNORECASE)
KEY_INPUTS = {"aws-access-key-id", "aws-secret-access-key", "credentials_json", "client-secret", "creds"}
INJECTION = re.compile(r"\$\{\{\s*(github\.event\.|inputs\.|github\.head_ref)")
DOCKER_IMAGE = re.compile(r"docker\s+(?:run|pull)\b[^\n]*?\s([a-z0-9][\w./-]*:[\w.-]+)(?=\s|$)")


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    message: str


def triggers(doc: dict) -> set[str]:
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(t) for t in on}
    if isinstance(on, dict):
        return {str(t) for t in on}
    return set()


def _writes(perms) -> bool:
    if perms == "write-all":
        return True
    return isinstance(perms, dict) and any(v == "write" for v in perms.values())


def _steps(job: dict) -> list[dict]:
    return [s for s in job.get("steps") or [] if isinstance(s, dict)]


def _images(text: str) -> list[str]:
    return [m for m in DOCKER_IMAGE.findall(text) if not DIGEST.search(m)]


def lint(doc: dict, path: str = "workflow") -> list[Finding]:
    """Every finding for one parsed workflow, in rule order, then job order, then step order."""
    jobs = doc.get("jobs") or {}
    found: dict[str, list[Finding]] = {f"PL{n:03d}": [] for n in range(1, 11)}

    def add(rule, where, message):
        found[rule].append(Finding(rule, f"{path}:{where}", message))

    top = doc.get("permissions")
    if top is None:
        add("PL002", "permissions", "no top-level permissions: the token gets the repository's default")
    elif _writes(top):
        add("PL002", "permissions", f"top-level permissions grant write: {top}")
    any_power = False
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        perms = job.get("permissions")
        uses = job.get("uses")
        if isinstance(uses, str) and not uses.startswith("./") and not SHA.search(uses):
            add("PL001", name, f"reusable workflow not pinned to a commit SHA: {uses}")
        if perms == "write-all":
            add("PL003", name, "job asks for write-all")
        elif isinstance(perms, dict) and perms.get("id-token") == "write" and "environment" not in job \
                and not (isinstance(uses, str) and uses.startswith("./")):
            add("PL003", name, "id-token: write without a protected environment")
        text = repr(job)
        if _writes(perms) or "secrets." in text or (top is not None and _writes(top)):
            any_power = True
        runs_on = job.get("runs-on")
        labels = runs_on if isinstance(runs_on, list) else [str(runs_on)]
        if "self-hosted" in labels and "ephemeral" not in labels:
            add("PL008", name, "self-hosted runner: it keeps state between jobs unless built to serve one")
        if job.get("continue-on-error") not in (None, False):
            add("PL009", name, "continue-on-error on the job")
        container = job.get("container")
        image = container.get("image") if isinstance(container, dict) else container
        if isinstance(image, str) and not DIGEST.search(image):
            add("PL010", name, f"job container by tag: {image}")
        for svc, spec in (job.get("services") or {}).items():
            img = spec.get("image") if isinstance(spec, dict) else spec
            if isinstance(img, str) and not DIGEST.search(img):
                add("PL010", f"{name}.services.{svc}", f"service image by tag: {img}")
        for i, step in enumerate(_steps(job), 1):
            where = f"{name}.steps[{i}]"
            act = step.get("uses")
            if isinstance(act, str):
                if act.startswith("docker://"):
                    if not DIGEST.search(act):
                        add("PL001", where, f"container action not pinned by digest: {act}")
                elif not act.startswith("./") and not SHA.search(act):
                    add("PL001", where, f"action not pinned to a commit SHA: {act}")
                if act.startswith("actions/checkout@") and (step.get("with") or {}).get("persist-credentials") \
                        is not False:
                    add("PL007", where, "checkout leaves the token in .git/config (persist-credentials)")
                keys = sorted(KEY_INPUTS & set(step.get("with") or {}))
                if keys:
                    add("PL005", where, "long-lived credential passed to an action: " + ", ".join(keys))
            for env_name, value in list((step.get("env") or {}).items()) + list((step.get("with") or {}).items()):
                for secret in re.findall(r"secrets\.([A-Za-z0-9_]+)", str(value)):
                    if CLOUD_KEY.search(secret):
                        add("PL005", where, f"cloud key stored as a secret: {secret}")
            run = step.get("run")
            if isinstance(run, str):
                if INJECTION.search(run):
                    add("PL006", where, "event or input text pasted into the script; pass it through env")
                for img in _images(run):
                    add("PL010", where, f"image by tag in a script: {img}")
                for secret in re.findall(r"secrets\.([A-Za-z0-9_]+)", run):
                    if CLOUD_KEY.search(secret):
                        add("PL005", where, f"cloud key stored as a secret: {secret}")
            if step.get("continue-on-error") not in (None, False):
                add("PL009", where, "continue-on-error on the step")
        if isinstance(perms, dict) and perms.get("id-token") == "write":
            any_power = True
    bad = sorted(UNTRUSTED & triggers(doc))
    if bad and any_power:
        add("PL004", "on", f"untrusted trigger {', '.join(bad)} in a workflow with write, OIDC or secrets")
    return [f for rule in sorted(found) for f in found[rule]]


def lint_text(text: str, path: str = "workflow") -> list[Finding]:
    return lint(yamlish.loads(text), path)
