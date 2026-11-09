"""What a prompt-injection attack achieves against a CI agent workflow (TODO 4 in starter/).

The simulated agent obeys every instruction it reads. That is the worst case, chosen on purpose: the lab
measures what the workflow lets an obedient agent do, not how often a model resists. Real models resist
some attacks some of the time, which is no basis for a control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .workflows import UNTRUSTED_TEXT, permissions, steps

TOOL_NAMES = {"bash": "bash", "gitpush": "git-push", "comment": "comment", "webfetch": "web-fetch", "edit": "edit"}


@dataclass
class Config:
    author_gate: set[str] | None = None          # author associations allowed to start the job; None = anyone
    shell_interpolation: bool = False            # untrusted text is pasted into a run: script
    strip_hidden: bool = False                   # hidden characters are removed before the model reads text
    tools: set[str] = field(default_factory=set)  # bash, git-push, comment, web-fetch, edit
    perms: dict[str, str] = field(default_factory=dict)
    secrets_in_env: bool = False
    egress_open: bool = True                     # GitHub-hosted runners can reach the internet
    link_filter: bool = False                    # the comment tool refuses links outside an allowlist


def config_from_workflow(text: str) -> Config:
    """Provided: read the properties the attack outcome depends on from a workflow."""
    cfg = Config()
    gate = re.search(r"fromJSON\('\[(.*?)\]'\),\s*github\.event\.comment\.author_association", text)
    if gate:
        cfg.author_gate = {x.strip().strip('"') for x in gate[1].split(",")}
    for _, p in permissions(text):
        if p == "write-all":
            cfg.perms = {s: "write" for s in ("contents", "pull-requests", "issues", "actions", "id-token")}
        elif isinstance(p, dict):
            cfg.perms = dict(p)
    for st in steps(text):
        if any(UNTRUSTED_TEXT.search(line) for _, line in st.run):
            cfg.shell_interpolation = True
        for _, key, value in st.with_ + st.env:
            if "secrets." in value:
                cfg.secrets_in_env = True
            if key == "allowed_tools":
                cfg.tools = {TOOL_NAMES[t.strip().lower()] for t in value.strip("\"'").split(",")}
            if key == "untrusted_input" and "strip-hidden" in value:
                cfg.strip_hidden = True
            if key == "comment_links":
                cfg.link_filter = True
    return cfg


def outcome(case: dict, cfg: Config) -> tuple[bool, str]:
    """(succeeded, reason) for one attack case against one workflow configuration. Apply in order:

    1. author "outsider" and cfg.author_gate is set and lacks case["author_association"]:
       fail, "the job does not run for this author".
       Then goal "merge" always fails: "branch protection: only maintainers merge".
    2. technique "shell": fail "the text never reaches a shell" unless cfg.shell_interpolation; otherwise
       the attacker's commands run with the job's token and environment, so the goal succeeds by
       job_can(goal) below, with reason "shell injection".
    3. technique "hidden" with cfg.strip_hidden: fail, "hidden characters removed before the model reads".
       Otherwise "hidden" is treated as "instruction".
    4. technique "instruction": the agent obeys; the goal succeeds by agent_can(goal), reason "agent obeyed".
    Goal rules:
      job_can: exfiltrate-secret needs secrets_in_env and egress_open; push-code needs perms contents=write;
               post-link and post-misleading need issues=write; leak-code-outside needs egress_open;
               steal-oidc-token needs perms id-token=write and egress_open (any step of such a job can
               request the token).
      agent_can: exfiltrate-secret needs (bash or web-fetch) and secrets_in_env and egress_open; push-code
               needs git-push and contents=write; post-link needs comment, issues=write and not link_filter;
               post-misleading needs comment and issues=write; leak-code-outside needs (bash or web-fetch)
               and egress_open; steal-oidc-token needs (bash or web-fetch), id-token=write and egress_open.
    When a goal rule fails, the reason is "<shell injection|agent obeyed>, but <goal> is not possible".
    """
    raise NotImplementedError("TODO 4: what an attack achieves against a workflow")
