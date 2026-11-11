"""Typed tool contracts (added in 4.24.0; ADR-025).

A contract is what the code around a model promises about one tool: its typed parameters, the effect
it has, the Relay scope it needs, whether a person must approve each call, which arguments make a call
the same call (for idempotency), and how much of its result may reach the model. The model sees the
name, description and parameters. Everything else is enforced by `relay.agents.boundary`, never by
asking the model to behave.

Effects, from least to most consequential:
  read      reads the repository or Relay; changes nothing
  write     changes the run's own sandbox branch; nothing outside it sees the change
  external  visible outside the sandbox: a pushed branch, a pull request, a comment

A contract also says whether the tool's result is untrusted: text an outsider can write, such as a
ticket, an issue comment or a web page (`untrusted_result`, from 4.26.0; ADR-034). Once a run has read
such text, the boundary treats the run as steerable and refuses any external effect that no person
approves.

Paths are checked twice. Every path must be relative, use forward slashes, contain no `..` and avoid the
paths no agent may read (secrets and the agent's own governance). A path argument of a `write` tool must
also be in the task's list of files, which the boundary passes in.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass

EFFECTS = ("read", "write", "external")
TYPES = ("str", "int", "bool", "path", "enum", "text")
APPROVERS = ("requester", "another_person")

# No agent reads these, whatever its task: secrets, and the files that govern agents themselves.
NEVER_READ = ("*.env", ".env*", "*.pem", "*.key", "governance/agents.json", "infra/agents.tf",
              "infra/detection/*")


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    required: bool = True
    max_len: int | None = None
    choices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.type not in TYPES:
            raise ValueError(f"unknown parameter type {self.type!r}")
        if self.type == "enum" and not self.choices:
            raise ValueError("an enum parameter needs choices")


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    params: tuple[Param, ...]
    effect: str
    scope: str | None = None          # the Relay scope the call needs; None still needs a valid token
    approval: str | None = None       # who approves each call: requester, another_person, or no one
    idem_fields: tuple[str, ...] = ()  # arguments that make two calls the same call; () means all of them
    derived: tuple[str, ...] = ()     # arguments the boundary computes from the real state; never the model's
    returns_paths: bool = False       # the result is a list of paths, filtered by NEVER_READ
    idempotent: bool = False          # the handler is safe to run again after an unknown outcome
    max_result_chars: int = 4000
    untrusted_result: bool = False    # 4.26.0: the result holds text an outsider can write (ADR-034)

    def __post_init__(self) -> None:
        if self.effect not in EFFECTS:
            raise ValueError(f"unknown effect {self.effect!r}")
        if self.approval is not None and self.approval not in APPROVERS:
            raise ValueError(f"unknown approver rule {self.approval!r}")
        names = [p.name for p in self.params]
        if len(set(names)) != len(names):
            raise ValueError("duplicate parameter")
        if set(self.derived) & set(names):
            raise ValueError("a derived argument is not a parameter the model may set")
        if not set(self.idem_fields) <= set(names) | set(self.derived):
            raise ValueError("idem_fields must name parameters or derived arguments")
        if self.effect == "external" and self.approval is None and not self.idempotent:
            raise ValueError("an external effect needs an approval or an idempotent handler")

    def schema(self) -> dict:
        """What the model is shown: name, description and a JSON-schema-like parameter list."""
        kinds = {"str": "string", "text": "string", "path": "string", "enum": "string", "int": "integer",
                 "bool": "boolean"}
        props = {}
        for p in self.params:
            prop: dict = {"type": kinds[p.type]}
            if p.choices:
                prop["enum"] = list(p.choices)
            if p.max_len:
                prop["maxLength"] = p.max_len
            props[p.name] = prop
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": props,
                                 "required": [p.name for p in self.params if p.required],
                                 "additionalProperties": False}}


def path_problem(path: str) -> str | None:
    """Why a path may not be used at all, or None. Checked for every path parameter of every tool."""
    if not path or path.startswith("/") or "\\" in path or ":" in path:
        return "path must be relative, with forward slashes"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "path must not contain empty, '.' or '..' parts"
    if any(fnmatch.fnmatch(path, pattern) for pattern in NEVER_READ):
        return "path is never readable by an agent"
    return None


def validate_args(contract: ToolContract, args: dict, write_paths: frozenset[str] | None = None) -> list[str]:
    """Problems with one call's arguments, in a stable order. An empty list means the call may proceed.

    Unknown arguments, then each parameter in contract order: missing, wrong type, too long, not a
    choice, bad path; and for a `write` tool, a path outside `write_paths`.
    """
    if not isinstance(args, dict):
        return ["arguments must be an object"]
    known = {p.name for p in contract.params}
    problems = [f"unknown argument {k!r}" for k in sorted(args) if k not in known]
    for p in contract.params:
        if p.name not in args:
            if p.required:
                problems.append(f"{p.name}: missing")
            continue
        value = args[p.name]
        expected = {"int": int, "bool": bool}.get(p.type, str)
        if type(value) is not expected:
            problems.append(f"{p.name}: expected {p.type}")
            continue
        if p.max_len is not None and isinstance(value, str) and len(value) > p.max_len:
            problems.append(f"{p.name}: longer than {p.max_len}")
        if p.type == "enum" and value not in p.choices:
            problems.append(f"{p.name}: not one of {', '.join(p.choices)}")
        if p.type == "path":
            why = path_problem(value)
            if why:
                problems.append(f"{p.name}: {why}")
            elif contract.effect == "write" and value.startswith("tests/"):
                problems.append(f"{p.name}: path must not be a test file; approved tests are not the agent's")
            elif contract.effect == "write" and write_paths is not None and value not in write_paths:
                problems.append(f"{p.name}: not in the task's file list")
    return problems


def canonical(args: dict) -> str:
    return json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def args_sha256(args: dict) -> str:
    return hashlib.sha256(canonical(args).encode("utf-8")).hexdigest()


def idempotency_key(run_id: str, contract: ToolContract, args: dict) -> str | None:
    """The key that makes a repeated call the same call, or None for a `read` tool (reads may repeat).

    It covers the run, the tool and the contract's idem_fields (all arguments if none are named), so a
    call repeated after a crash or a retry maps to the step already recorded.
    """
    if contract.effect == "read":
        return None
    fields = contract.idem_fields or tuple(sorted(args))
    basis = {"run": run_id, "tool": contract.name, "args": {k: args.get(k) for k in fields}}
    return hashlib.sha256(canonical(basis).encode("utf-8")).hexdigest()
