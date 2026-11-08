"""The versioned dataset: loading, pinning, slices and leakage checks (reference solution)."""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

SLICE_KEYS = ("kind", "language", "source", "difficulty")


def load_tickets(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canonical_sha256(path: Path) -> str:
    """SHA-256 of the file's text with newlines normalised (a CRLF checkout hashes the same)."""
    return hashlib.sha256(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Pin:
    ok: bool
    detail: str


def verify_pin(data_dir: Path, name: str, version: str) -> Pin:
    """Check that data/ holds exactly the dataset version a policy pins."""
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["name"], manifest["version"]) != (name, version):
        return Pin(False, f"policy pins {name} {version}; data is {manifest['name']} {manifest['version']}")
    actual = canonical_sha256(data_dir / "tickets.jsonl")
    if actual != manifest["files"]["tickets.jsonl"]:
        return Pin(False, f"tickets.jsonl hash {actual[:12]}… does not match the manifest")
    return Pin(True, f"{name} {version}, sha256 {actual[:12]}…")


def split(tickets: list[dict], name: str) -> list[dict]:
    return [t for t in tickets if t["split"] == name]


def slices_of(ticket: dict) -> list[str]:
    """Slice names a ticket belongs to, such as 'kind:overstated' or 'language:de'."""
    return [f"{k}:{ticket[k]}" for k in SLICE_KEYS]


# ------------------------------------------------------------------ leakage

def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    """Word n-grams of lower-cased text, punctuation ignored. Texts shorter than n give one shingle."""
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def containment(a: str, b: str) -> float:
    """Share of a's shingles that also appear in b (0 when a has none)."""
    sa = shingles(a)
    return len(sa & shingles(b)) / len(sa) if sa else 0.0


@dataclass(frozen=True)
class Leakage:
    family_overlap: list[str]                    # families present in both dev and held-out
    prompt_hits: list[tuple[str, float]]         # held-out ticket ids found in the prompt, with containment
    cross_split: list[tuple[str, str, float]]    # (held-out id, dev id, containment) near-duplicates

    @property
    def clean(self) -> bool:
        return not (self.family_overlap or self.prompt_hits or self.cross_split)


def check_leakage(prompt_text: str, dev: list[dict], heldout: list[dict], threshold: float = 0.5) -> Leakage:
    """Three checks that keep held-out tickets out of everything that is tuned.

    1. family_overlap: sorted family ids that occur in both dev and heldout.
    2. prompt_hits: for each held-out ticket (in held-out order) whose
       containment(ticket text, prompt_text) >= threshold, (id, containment
       rounded to 2 places).
    3. cross_split: for each held-out ticket (in order), the dev ticket with
       the highest containment(held-out text, dev text), if it is >= threshold:
       (held-out id, dev id, containment rounded to 2 places). Ties go to the
       first dev ticket in dev order.
    """
    dev_families = {t["family"] for t in dev}
    overlap = sorted(dev_families & {t["family"] for t in heldout})
    hits = [(t["id"], round(c, 2)) for t in heldout if (c := containment(t["text"], prompt_text)) >= threshold]
    cross = []
    for h in heldout:
        best, best_id = 0.0, None
        for d in dev:
            c = containment(h["text"], d["text"])
            if c > best:
                best, best_id = c, d["id"]
        if best >= threshold:
            cross.append((h["id"], best_id, round(best, 2)))
    return Leakage(overlap, hits, cross)


def row_split(tickets: list[dict], n_dev: int, seed: int = 3) -> tuple[list[dict], list[dict]]:
    """The tempting alternative: shuffle the generated tickets and cut, ignoring families."""
    pool = [t for t in tickets if t["source"] != "chapter-2"]
    rng = random.Random(seed)
    order = sorted(pool, key=lambda t: t["id"])
    rng.shuffle(order)
    return order[:n_dev], order[n_dev:]
