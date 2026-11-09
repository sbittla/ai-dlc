"""Who is calling: workspace users, their projects, and token hashes.

Relay stores only hashes of tokens (Relay's docs). A request presents
`Authorization: Bearer <token>`; the directory hashes it and looks the hash
up. This is a stand-in for Relay's identity service, enough to put a real
trust boundary at the front of the HTTP service. Chapter 14 replaces it with
workload and user identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..models import Project, User


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Directory:
    workspace: str
    users: dict[int, User]
    projects: dict[int, Project]
    tokens: dict[str, int]  # sha256(token) -> user id

    def authenticate(self, token: str | None) -> User | None:
        if not token:
            return None
        uid = self.tokens.get(token_hash(token))
        return self.users.get(uid) if uid is not None else None

    @classmethod
    def from_dict(cls, data: dict) -> "Directory":
        users = {}
        tokens = {}
        for u in data["users"]:
            users[u["id"]] = User(u["id"], u["email"], u["name"], u["role"], u["tz"],
                                  frozenset(u.get("projects", ())))
            tokens[u["token_sha256"]] = u["id"]
        projects = {p["id"]: Project(p["id"], p["name"]) for p in data["projects"]}
        return cls(data["workspace"], users, projects, tokens)

    @classmethod
    def load(cls, path: str | Path) -> "Directory":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# Demo identities for local runs and tests. The tokens are not secrets: they
# open a local, in-memory demo and nothing else.
DEMO_TOKENS = {"demo-owner": 1, "demo-admin": 2, "demo-member": 3, "demo-guest": 4}


_DEMO_USERS = (
    {"id": 1, "email": "owner@example.com", "name": "Olu", "role": "Owner", "tz": "Europe/Berlin"},
    {"id": 2, "email": "admin@example.com", "name": "Ada", "role": "Admin", "tz": "UTC"},
    {"id": 3, "email": "member@example.com", "name": "Mei", "role": "Member", "tz": "Asia/Tokyo"},
    {"id": 4, "email": "guest@example.com", "name": "Gil", "role": "Guest", "tz": "Pacific/Auckland",
     "projects": [10]},
)


def demo_directory() -> Directory:
    by_id = {uid: token for token, uid in DEMO_TOKENS.items()}
    return Directory.from_dict({
        "workspace": "ws-demo",
        "projects": [{"id": 10, "name": "Rotterdam"}, {"id": 11, "name": "Hamburg"}],
        "users": [dict(u, token_sha256=token_hash(by_id[u["id"]])) for u in _DEMO_USERS],
    })
