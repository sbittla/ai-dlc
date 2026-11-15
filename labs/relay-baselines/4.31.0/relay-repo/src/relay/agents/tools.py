"""The spec-to-PR helper's tool contracts (added in 4.24.0; ADR-025 and ADR-027).

These are the only tools the helper's agent step may call. Each is a scoped capability in Chapter 3's
sense: it does one job for this task, not general access to the repository, the shell or GitHub.

- No tool runs a shell command. Tests run through `run_tests`, which runs the approved tests or the
  suite in the sandbox and returns a summary.
- `edit_file` changes only files in the task's list (the boundary enforces it), and never a test file:
  approved tests are committed before the code (Chapter 9) and are not the agent's to change.
- `open_pull_request` is the one external effect, and the one tool that reaches the network (GitHub). It opens
  a draft pull request from the run's own branch after the requester approves that exact diff, and never merges
  or approves anything. The diff's hash is computed by the boundary from the branch, never sent by the model.
- From 4.26.0 (ADR-034) `read_file` and `search_code` declare `untrusted_result`: a repository file can hold
  text that came from a ticket, an issue or a contributor, and Chapter 10's drill D12 put an instruction in
  one. The helper's run is therefore tainted after its first read, and its one external tool already needs
  the requester's approval.
- `edit_file`'s idempotency key includes the file's hash before the edit, also computed by the boundary, so
  editing a file to A, then B, then A again is three edits, not a replay.
"""

from __future__ import annotations

from .contracts import Param, ToolContract

READ_TASK = ToolContract(
    "read_task", "Read the Relay task this run serves: its spec section, file list and approved tests.",
    (Param("task_id", "str", max_len=40),), "read", scope="tasks:read:platform")
READ_FILE = ToolContract(
    "read_file", "Read one file of the repository at the task's base commit.",
    (Param("path", "path", max_len=200),), "read", max_result_chars=12000, untrusted_result=True)
SEARCH_CODE = ToolContract(
    "search_code", "Find files that mention a name. Returns at most 20 paths.",
    (Param("pattern", "str", max_len=120),), "read", max_result_chars=4000, returns_paths=True,
    untrusted_result=True)
EDIT_FILE = ToolContract(
    "edit_file", "Replace the content of one file in the task's file list on the run's branch.",
    (Param("path", "path", max_len=200), Param("content", "text", max_len=60000)), "write",
    derived=("before_sha256",), idem_fields=("path", "content", "before_sha256"))
RUN_TESTS = ToolContract(
    "run_tests", "Run the approved tests or the whole suite in the sandbox. Returns a summary of failures.",
    (Param("target", "enum", choices=("approved", "suite")),), "read", max_result_chars=6000)
RUN_PRCHECK = ToolContract(
    "run_prcheck", "Run Relay's pre-review check (PR01 to PR10) on the run's branch.", (), "read")
OPEN_PULL_REQUEST = ToolContract(
    "open_pull_request", "Open a draft pull request from the run's branch. Needs the requester's approval.",
    (Param("branch", "str", max_len=100), Param("title", "str", max_len=120), Param("body", "text", max_len=8000)),
    "external", approval="requester", derived=("diff_sha256",), idem_fields=("branch",), idempotent=True)

# The contract any agent uses to recall long-term memory (4.26.0; ADR-034). Its result may hold facts first
# read in untrusted text, so a recall taints the run. It lives here, with the other contracts, and not in
# relay.agents.memory, so that the memory store and the taint that guards what a recalled fact asks for
# do not share a module.
RECALL_MEMORY = ToolContract(
    "recall_memory", "Recall accepted facts on one topic, each with its source and trust.",
    (Param("topic", "str", max_len=80),), "read", untrusted_result=True)

HELPER_TOOLS = {c.name: c for c in (READ_TASK, READ_FILE, SEARCH_CODE, EDIT_FILE, RUN_TESTS, RUN_PRCHECK,
                                    OPEN_PULL_REQUEST)}
