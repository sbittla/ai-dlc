"""The requirements checker (reference solution).

Five functions are the lab's TODOs in starter/: check_provenance,
find_vague_terms, check_criteria, find_contradictions and check_traceability.
The others are provided. Each docstring is the specification, and
tests/test_checks.py checks each one on inputs small enough to verify by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .core import Finding, Lexicon, finding
from .prd import PRD, Requirement, SourceRef
from .sources import Source, normalize, word_count


# ------------------------------------------------------------------ TODO 1

def check_provenance(item_id: str, refs: list[SourceRef], sources: dict[str, Source],
                     min_words: int) -> list[Finding]:
    """Check that an item (a requirement or a goal) is grounded in its sources.

    - No refs at all: one RQ001 finding.
    - For each ref, in order:
      - ref.doc is not a key of `sources`: RQ002 (and nothing else for that ref);
      - normalize(ref.quote) is not a substring of normalize(source.text): RQ003;
      - otherwise, if word_count(ref.quote) < min_words: RQ004.
    Quotes are matched verbatim: same words, same case, same punctuation, with
    only whitespace and blockquote markers normalized. A paraphrase fails.
    """
    if not refs:
        return [finding("RQ001", item_id, "no Source line")]
    out = []
    for ref in refs:
        if ref.doc not in sources:
            out.append(finding("RQ002", item_id, f"unknown source {ref.doc!r}"))
        elif normalize(ref.quote) not in normalize(sources[ref.doc].text):
            out.append(finding("RQ003", item_id, f"not found verbatim in {ref.doc}: {ref.quote!r}"))
        elif word_count(ref.quote) < min_words:
            out.append(finding("RQ004", item_id, f"{word_count(ref.quote)}-word quote from {ref.doc}: {ref.quote!r}"))
    return out


# ------------------------------------------------------------------ TODO 2

def term_pattern(term: str) -> re.Pattern:
    """Case-insensitive match of `term` as a whole word or phrase: it may not be
    preceded or followed by a letter or digit ("fast" does not match "breakfast";
    "etc." and "and/or" match as written)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def find_vague_terms(item_id: str, text: str, terms: tuple[str, ...]) -> list[Finding]:
    """RQ010 for each vague term that occurs in `text` (see term_pattern).

    One finding per distinct term, ordered by where the term first occurs in
    the text (ties: the longer term first). The message names the term as it
    appears in `terms`, for example: vague term 'quickly'.
    """
    hits = []
    for term in terms:
        m = term_pattern(term).search(text)
        if m:
            hits.append((m.start(), -len(term), term))
    return [finding("RQ010", item_id, f"vague term {term!r}") for _, _, term in sorted(hits)]


# ------------------------------------------------------------------ TODO 3

GWT = re.compile(r"^given\s+\S.*?\bwhen\s+\S.*?\bthen\s+\S", re.IGNORECASE | re.DOTALL)


def check_criteria(req: Requirement) -> list[Finding]:
    """Acceptance criteria a machine can check.

    - No criteria: one RQ020 finding for the requirement.
    - Each criterion whose text is not Given/When/Then: RQ021, with the
      criterion's id as the item. Given/When/Then means: the text starts with
      "Given", and the words "when" and then "then" follow, in that order, each
      followed by at least one more word (case-insensitive; the GWT pattern).
    """
    if not req.criteria:
        return [finding("RQ020", req.id, "no Criteria")]
    return [finding("RQ021", c.id, f"not Given/When/Then: {c.text!r}")
            for c in req.criteria if not GWT.match(c.text)]


# ------------------------------------------------------------------ TODO 4

def find_contradictions(reqs: list[Requirement]) -> list[Finding]:
    """RQ030 when two requirements set the same Value key to different values.

    Compare every pair of requirements (in PRD order) that both set a key; a
    pair whose values differ after stripping whitespace is one finding. The
    item is "<first id> vs <second id>" and the message is
    "<key>: <first value> vs <second value>". Findings are ordered by key,
    in order of each key's first appearance, then by pair.
    """
    by_key: dict[str, list[tuple[str, str]]] = {}
    for r in reqs:
        for key, value in r.values:
            by_key.setdefault(key, []).append((r.id, value.strip()))
    out = []
    for key, entries in by_key.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                (a, va), (b, vb) = entries[i], entries[j]
                if va != vb:
                    out.append(finding("RQ030", f"{a} vs {b}", f"{key}: {va} vs {vb}"))
    return out


# ------------------------------------------------------------------ TODO 5

def check_traceability(prd: PRD) -> list[Finding]:
    """Goal -> requirement -> decision -> criterion links, in this order:

    1. RQ064 for each identifier used more than once across goals, decisions,
       requirements and criteria (one finding per duplicated id, in first-use order).
    2. For each goal in order: RQ062 if any of measure, baseline or target is
       empty (one finding naming the missing fields, e.g. "missing baseline, target").
    3. For each requirement in order:
       - RQ061 if it has no Goal, or cites a goal id that does not exist
         (one finding; the message names the unknown ids, or says "no Goal");
       - RQ063 for each cited decision id that is not recorded;
       - RQ065 for each Depends on id that is not a requirement.
    4. RQ060 for each goal that no requirement cites, in goal order.
    """
    out = []
    seen, dupes = set(), []
    ids = ([g.id for g in prd.goals] + [d.id for d in prd.decisions] + [r.id for r in prd.requirements]
           + [c.id for r in prd.requirements for c in r.criteria])
    for i in ids:
        if i in seen and i not in dupes:
            dupes.append(i)
        seen.add(i)
    out += [finding("RQ064", i, "identifier used more than once") for i in dupes]

    for g in prd.goals:
        missing = [name for name in ("measure", "baseline", "target") if not getattr(g, name).strip()]
        if missing:
            out.append(finding("RQ062", g.id, "missing " + ", ".join(missing)))

    goal_ids = {g.id for g in prd.goals}
    decision_ids = {d.id for d in prd.decisions}
    req_ids = {r.id for r in prd.requirements}
    for r in prd.requirements:
        unknown = [g for g in r.goals if g not in goal_ids]
        if not r.goals:
            out.append(finding("RQ061", r.id, "no Goal"))
        elif unknown:
            out.append(finding("RQ061", r.id, "unknown goal " + ", ".join(unknown)))
        out += [finding("RQ063", r.id, f"decision {d} is not recorded") for d in r.decisions if d not in decision_ids]
        out += [finding("RQ065", r.id, f"depends on unknown {d}") for d in r.depends_on if d not in req_ids]

    cited = {g for r in prd.requirements for g in r.goals}
    out += [finding("RQ060", g.id, "no requirement cites this goal") for g in prd.goals if g.id not in cited]
    return out


# ------------------------------------------------------------------ provided

def check_testability(req: Requirement, lexicon: Lexicon) -> list[Finding]:
    """RQ011 for each weak modal in the statement; RQ012 for an NFR whose statement
    matches none of the lexicon's measurable patterns (a quantity with a unit, a
    named standard, or a prohibition)."""
    out = [finding("RQ011", req.id, f"weak modal {m!r}")
           for m in lexicon.weak_modals if term_pattern(m).search(req.statement)]
    if req.kind == "nfr" and not any(re.search(p, req.statement) for p in lexicon.measurable_patterns):
        out.append(finding("RQ012", req.id, "no number with a unit, named standard or prohibition"))
    return out


def concepts_used(text: str, lexicon: Lexicon) -> list[str]:
    """Concepts (lexicon keys) whose terms occur in `text`, in lexicon order.
    Terms are matched like vague terms, but case-sensitively for upper-case
    terms such as P1 and SMS."""
    used = []
    for concept, terms in lexicon.concepts.items():
        for term in terms:
            flags = 0 if term.isupper() or any(ch.isdigit() for ch in term) else re.IGNORECASE
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, flags):
                used.append(concept)
                break
    return used


def check_dependencies(prd: PRD, lexicon: Lexicon) -> list[Finding]:
    """Hidden dependencies. A requirement whose statement or criteria use a concept
    Relay 4.17.2 lacks gets RQ040 if no requirement introduces it, or RQ041 if
    another requirement introduces it and this one does not list that requirement
    under Depends on."""
    introduced_by = {c: r.id for r in prd.requirements for c in r.introduces}
    out = []
    for r in prd.requirements:
        text = " ".join([r.statement] + [c.text for c in r.criteria])
        for concept in concepts_used(text, lexicon):
            owner = introduced_by.get(concept)
            if owner is None:
                out.append(finding("RQ040", r.id, f"uses {concept}, which Relay lacks and no requirement introduces"))
            elif owner != r.id and owner not in r.depends_on:
                out.append(finding("RQ041", r.id, f"uses {concept} from {owner} without Depends on"))
    return out


def check_nfr_coverage(prd: PRD, lexicon: Lexicon) -> list[Finding]:
    """RQ050 for each required non-functional category with no NFR."""
    covered = {r.category for r in prd.requirements if r.kind == "nfr"}
    return [finding("RQ050", "PRD", f"no NFR in category {c!r}")
            for c in lexicon.required_nfr_categories if c not in covered]


@dataclass(frozen=True)
class Flag:
    doc: str
    first_line: int   # 1-based, inclusive
    last_line: int
    text: str


def scan_sources(sources: dict[str, Source], lexicon: Lexicon) -> list[Flag]:
    """Blocks of source text that address an AI system with instructions.

    A block is a run of consecutive non-blank lines. A block is flagged if any
    injection pattern matches it. Flags are evidence for a person to read, not
    proof of an attack: the text may be a test, a joke or a template.
    """
    flags = []
    for doc, src in sources.items():
        start = None
        for i, line in enumerate(list(src.lines) + [""]):
            if line.strip() and start is None:
                start = i
            elif not line.strip() and start is not None:
                block = "\n".join(src.lines[start:i])
                if any(re.search(p, block) for p in lexicon.injection_patterns):
                    flags.append(Flag(doc, start + 1, i, block))
                start = None
    return flags


def check_untrusted_quotes(prd: PRD, flags: list[Flag]) -> list[Finding]:
    """RQ071 for each requirement or goal source quote found inside a flagged block."""
    out = []
    items = [(g.id, g.sources) for g in prd.goals] + [(r.id, r.sources) for r in prd.requirements]
    for item_id, refs in items:
        for ref in refs:
            q = normalize(ref.quote)
            for f in flags:
                if f.doc == ref.doc and q and q in normalize(f.text):
                    out.append(finding("RQ071", item_id, f"quotes flagged text in {f.doc} lines {f.first_line}-{f.last_line}"))
    return out


AGENT_NAMES = re.compile(r"(?i)\b(agent|assistant|bot|model|claude|gpt|copilot)\b")


def check_approval(prd: PRD) -> list[Finding]:
    """RQ080 unless Status is approved, a product owner is named, Approved by is
    that same person (not an agent or assistant), and Approved on is a date."""
    problems = []
    if prd.status.lower() != "approved":
        problems.append(f"status is {prd.status or 'empty'!r}")
    if not prd.product_owner:
        problems.append("no product owner named")
    if not prd.approved_by:
        problems.append("Approved by is empty")
    elif AGENT_NAMES.search(prd.approved_by):
        problems.append("approved by an agent")
    elif prd.approved_by != prd.product_owner:
        problems.append(f"approved by {prd.approved_by}, not the product owner")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prd.approved_on):
        problems.append("Approved on is not a date")
    return [finding("RQ080", "PRD", "; ".join(problems))] if problems else []


@dataclass(frozen=True)
class Result:
    findings: tuple[Finding, ...]
    flags: tuple[Flag, ...]


def run_checks(prd: PRD, sources: dict[str, Source], lexicon: Lexicon) -> Result:
    """Every check, in catalogue order of areas; deterministic."""
    out: list[Finding] = []
    for g in prd.goals:
        out += check_provenance(g.id, g.sources, sources, lexicon.min_quote_words)
    for r in prd.requirements:
        out += check_provenance(r.id, r.sources, sources, lexicon.min_quote_words)
    for r in prd.requirements:
        out += find_vague_terms(r.id, r.statement, lexicon.vague_terms)
        for c in r.criteria:
            out += find_vague_terms(c.id, c.text, lexicon.vague_terms)
    for r in prd.requirements:
        out += check_testability(r, lexicon)
    for r in prd.requirements:
        out += check_criteria(r)
    out += find_contradictions(prd.requirements)
    out += check_dependencies(prd, lexicon)
    out += check_nfr_coverage(prd, lexicon)
    out += check_traceability(prd)
    flags = scan_sources(sources, lexicon)
    out += check_untrusted_quotes(prd, flags)
    out += check_approval(prd)
    return Result(tuple(out), tuple(flags))
