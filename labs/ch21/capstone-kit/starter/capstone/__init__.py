"""The capstone kit (Chapter 21): checks for evidence packs, the rubric, the defense draw and the red-team log.

Nothing here contacts a network, a model or a code host. The kit reads files: a pack's manifest (`pack.json`),
the items it lists, and the sources those items trace to, which may live in the pack, in Relay's canonical
4.31.0 tree or in other labs of this repository. It never changes any of them.

Hashes are taken over text with CRLF turned into LF, so a Windows checkout and a Linux checkout agree.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
REPO = LAB.parents[2]          # labs/ch21/capstone-kit -> the repository root
VENDOR = LAB / "vendor"        # Lab 20.1's checks, vendored (tests/test_sync.py keeps them equal)
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

LABELS = ("verified", "modelled", "deployed", "open")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str        # "block" or "warn"
    where: str           # an item, requirement, criterion, member or finding ID
    message: str

    def line(self) -> str:
        return f"{self.code} [{self.severity}] {self.where}: {self.message}"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalized_bytes(path: Path) -> bytes:
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(normalized_bytes(path)).hexdigest()


def canonical_sha256(obj) -> str:
    """SHA-256 of an object's canonical JSON (sorted keys, no spaces): what a frozen record is bound to."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
