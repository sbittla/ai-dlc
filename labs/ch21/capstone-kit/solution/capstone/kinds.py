"""What "well-formed" means for each kind of evidence item, and what counts as a failing result.

Each validator returns three lists of messages:

    malformed  the item is not the evidence it claims to be (EV004): a missing field, a verdict that does not
               follow from the item's own data, a claim the item does not contain
    failing    the item is well formed and records a result that does not meet its bar (EV011): a gate that
               fails, a review that says "not ready", a drill that failed
    content    the item carries a field that could hold attack text (EV012)

These checks are about form and about consistency with the item's own data. They cannot tell whether an SLO is
the right one or a threat model is complete; the panel judges that. Chapter 21 says so where it uses them.
"""

from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path

from . import LABELS, coverage as cov
from .redteam import validate as validate_log

AC_ID = re.compile(r"\b[A-Z][A-Z0-9]*-AC\d+\b")
OWASP_LLM = re.compile(r"^LLM(0[1-9]|10)$")
OWASP_AGENTIC = re.compile(r"^T([1-9]|1[0-5])$")
ATLAS = re.compile(r"^AML\.T\d{4}(\.\d{3})?$")
FORBIDDEN_TOOL = re.compile(r"merge|deploy|approve|push", re.I)
VARIANT_KEYS = {"id", "label", "placeholder", "shape"}
MAX_LABEL = 80


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _headings(text: str) -> list[str]:
    return [line.lstrip("#").strip().lower() for line in text.splitlines() if line.startswith("#")]


def _need_headings(text: str, needed: list[str]) -> list[str]:
    heads = _headings(text)
    return [f"no heading '{h}'" for h in needed if not any(h.lower() in x for x in heads)]


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval (Chapter 2), as fractions."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


# --- A and B -------------------------------------------------------------------------------------------------

def v_spec(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    bad = _need_headings(text, ["acceptance criteria"])
    if not AC_ID.search(text):
        bad.append("no acceptance-criterion ID such as ESC-AC01")
    if not re.search(r"^(Status: approved|Approved:)", text, re.M | re.I):
        bad.append("no approval line ('Status: approved' or 'Approved:')")
    return bad, [], []


def v_adr(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    bad = [f"no '{k}' line" for k in ("Status:", "Date:", "Decided by:", "Reviewed by:")
           if not re.search(rf"^{re.escape(k)}", text, re.M)]
    bad += _need_headings(text, ["context", "decision", "consequences"])
    heads = _headings(text)
    if not any("options considered" in h or "rejected alternatives" in h for h in heads):
        bad.append("no options considered or rejected alternatives")
    status = re.search(r"^Status:\s*(\S+)", text, re.M)
    failing = [f"status is '{status[1]}', not accepted"] if status and status[1].lower() != "accepted" else []
    return bad, failing, []


def v_threat_model(path, item, ctx):
    tm = _json(path)
    bad, failing = [], []
    for key in ("system", "components", "boundaries", "threats"):
        if not tm.get(key):
            bad.append(f"no {key}")
    boundaries = {b["id"] for b in tm.get("boundaries", [])}
    for t in tm.get("threats", []):
        tid = t.get("id", "?")
        if t.get("boundary") not in boundaries:
            bad.append(f"{tid}: boundary {t.get('boundary')!r} is not in the model")
        if not OWASP_LLM.match(str(t.get("owasp_llm", ""))):
            bad.append(f"{tid}: no OWASP LLM Top 10 ID")
        if not ATLAS.match(str(t.get("atlas", ""))):
            bad.append(f"{tid}: no MITRE ATLAS technique ID")
        if ctx["track"] == "D" and not OWASP_AGENTIC.match(str(t.get("owasp_agentic", ""))):
            bad.append(f"{tid}: no OWASP Agentic threat ID")
        if not t.get("controls"):
            failing.append(f"{tid}: no control")
    covered = {t.get("boundary") for t in tm.get("threats", [])}
    failing += [f"boundary {b}: no threat analysed" for b in sorted(boundaries - covered)]
    return bad, failing, []


def v_eval_record(path, item, ctx):
    r = _json(path)
    bad = [f"no {k}" for k in ("dataset", "version", "metric", "n", "successes", "runs", "interval", "threshold")
           if k not in r]
    if bad:
        return bad, [], []
    if r["runs"] < 2:
        bad.append(f"runs {r['runs']}: repeat runs are required")
    if not 0 <= r["successes"] <= r["n"]:
        bad.append("successes outside 0..n")
        return bad, [], []
    lo, hi = wilson(r["successes"], r["n"])
    if abs(lo - r["interval"][0]) > 0.0015 or abs(hi - r["interval"][1]) > 0.0015:
        bad.append(f"interval {r['interval']} is not the Wilson 95% interval ({lo:.3f}, {hi:.3f})")
    if r.get("simulated") and item.get("label") in ("verified", "deployed"):
        bad.append("simulated results labelled " + item["label"])
    rate = r["successes"] / r["n"]
    failing = [f"{r['metric']} {rate:.1%} below threshold {r['threshold']:.1%}"] if rate < r["threshold"] else []
    return bad, failing, []


PASSED = re.compile(r"passed: (\d+) of (\d+)", re.I)


def v_lab_report(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    bad = [] if text.strip() else ["empty report"]
    for key in ("lab", "command", "title"):
        if not item.get(key):
            bad.append(f"no {key}: a snapshot names the lab and command that printed it")
    for claim in item.get("claims", []):
        if claim not in text:
            bad.append(f"claim not in the report: {claim!r}")
    if "simulated" in text.lower() and item.get("label") in ("verified", "deployed"):
        bad.append("the report says simulated; labelled " + item["label"])
    failing = [f"passed {m[1]} of {m[2]}" for m in PASSED.finditer(text) if m[1] != m[2]]
    return bad, failing, []


def v_coverage_report(path, item, ctx):
    r = _json(path)
    bad = [f"no {k}" for k in ("policy", "release", "controls", "classes", "claimed") if k not in r]
    if bad:
        return bad, [], []
    unknown = sorted({c["control"] for cls in r["classes"] for c in cls["cells"]} - set(r["controls"]))
    bad += [f"cell names control {u!r}, not in the report's controls" for u in unknown]
    bad += [f"{cls['id']}: status {c['status']!r}" for cls in r["classes"] for c in cls["cells"]
            if c["status"] not in ("verified", "failed", "mitigating", "latent", "absent")]
    if bad:
        return bad, [], []
    passed, reasons = cov.gate(r)
    computed = cov.coverage(r["classes"], r["controls"])
    claimed = r["claimed"]
    if claimed.get("gate") != ("PASS" if passed else "FAIL"):
        bad.append(f"claims gate {claimed.get('gate')}; recomputed {'PASS' if passed else 'FAIL'}")
    for cid, n in claimed.get("coverage", {}).items():
        if computed.get(cid) != n:
            bad.append(f"{cid}: claims coverage {n}; recomputed {computed.get(cid)}")
    failing = list(reasons)
    gaps = cov.deployment_gaps(r, ctx["as_of"])
    failing += [f"{c}: counted, but no passing deployment record by {ctx['as_of']}" for c in gaps]
    return bad, failing, []


def v_redteam_log(path, item, ctx):
    result = validate_log(_json(path), ctx.get("members"), ctx.get("team"))
    bad = [f.line() for f in result["findings"] if f.code not in ("RT005", "RT006")]
    failing = [f.line() for f in result["findings"] if f.code == "RT005"]
    content = [f.line() for f in result["findings"] if f.code == "RT006"]
    return bad, failing, content


def v_test_record(path, item, ctx):
    r = _json(path)
    bad = [f"no {k}" for k in ("suite", "commit", "passed", "failed", "date") if k not in r]
    if not bad and r["passed"] < 1:
        bad.append("records no passing test")
    failing = [f"{r['failed']} failed"] if not bad and r["failed"] else []
    return bad, failing, []


def v_cyclonedx(path, item, ctx):
    b = _json(path)
    bad = []
    if b.get("bomFormat") != "CycloneDX":
        bad.append("bomFormat is not CycloneDX")
    if not b.get("specVersion"):
        bad.append("no specVersion")
    comp = b.get("metadata", {}).get("component", {})
    if not comp.get("name") or not comp.get("version"):
        bad.append("no metadata.component name and version")
    if not (b.get("components") or b.get("services")):
        bad.append("lists no components or services")
    return bad, [], []


def v_signature(path, item, ctx):
    s = _json(path)
    bad = [f"no {k}" for k in ("artefact", "digest", "identity", "log_entry", "verified_by", "date") if k not in s]
    if s.get("digest") and not re.match(r"^sha256:[0-9a-f]{64}$", s["digest"]):
        bad.append("digest is not sha256:<64 hex>")
    failing = ["verification did not pass"] if not bad and s.get("verified") is not True else []
    return bad, failing, []


def v_identity(path, item, ctx):
    reg = _json(path)
    subject = item.get("subject")
    entry = next((a for a in reg.get("agents", []) if a.get("agent_id") == subject), None)
    if entry is None:
        return [f"no registry entry for {subject!r}"], [], []
    bad = [f"{subject}: no {k}" for k in ("owner", "scopes", "max_ttl_seconds", "issuer") if not entry.get(k)]
    failing = []
    if entry.get("max_ttl_seconds", 10**9) > 900:
        failing.append(f"{subject}: tokens live {entry.get('max_ttl_seconds')} s (more than 900)")
    app = entry.get("github_app")
    if app:
        info = reg.get("github_apps", {}).get(app) or (reg.get("github") if reg.get("github", {}).get("app") == app
                                                       else None)
        if info is None:
            bad.append(f"{subject}: app {app!r} not recorded")
        elif info.get("bypass_branch_protection") or info.get("code_owner"):
            failing.append(f"{subject}: app {app} can bypass branch protection or own code")
    return bad, failing, []


def v_slo(path, item, ctx):
    d = _json(path)
    bad = []
    if not d.get("slos"):
        bad.append("no slos")
    for s in d.get("slos", []):
        sid = s.get("slo_id") or s.get("id") or "?"
        if not 0 < s.get("target", 0) < 1:
            bad.append(f"{sid}: target not a fraction")
        for k in ("owner", "period_days", "sli"):
            if not s.get(k):
                bad.append(f"{sid}: no {k}")
    return bad, [], []


def v_runbook(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    bad = []
    if not text.startswith("# "):
        bad.append("no title line")
    if len(re.findall(r"^\s*(\d+\.|-) \S", text, re.M)) < 2:
        bad.append("fewer than two steps")
    return bad, [], []


def v_cost_report(path, item, ctx):
    r = _json(path)
    bad = [f"no {k}" for k in ("unit", "cost_per_run", "cost_per_success", "prices_as_of", "target") if k not in r]
    if bad:
        return bad, [], []
    if r["cost_per_success"] < r["cost_per_run"]:
        bad.append("cost per success below cost per run")
    if "token" in r["unit"].lower():
        bad.append("cost per token is not a cost per task")
    failing = [f"${r['cost_per_success']} per success above target ${r['target']}"] \
        if r["cost_per_success"] > r["target"] else []
    return bad, failing, []


def v_readiness_review(path, item, ctx):
    r = _json(path)
    bad = [f"no {k}" for k in ("date", "reviewers", "rows", "decision") if k not in r]
    if bad:
        return bad, [], []
    if len(r["reviewers"]) < 2 or not any(x.get("security") for x in r["reviewers"]):
        bad.append("needs two reviewers, one from security")
    for row in r["rows"]:
        if row.get("status") not in ("met", "not met", "not applicable"):
            bad.append(f"row {row.get('n')}: status {row.get('status')!r}")
        elif row["status"] == "met" and not row.get("evidence"):
            bad.append(f"row {row.get('n')}: met with no evidence")
    if r["decision"] not in ("ready", "ready with conditions", "not ready"):
        bad.append(f"decision {r['decision']!r}")
    for c in r.get("conditions", []):
        if not c.get("owner") or not c.get("due"):
            bad.append(f"condition without owner and date: {c.get('what')}")
    not_met = [row["n"] for row in r["rows"] if row.get("status") == "not met"]
    failing = []
    if r["decision"] == "not ready":
        failing.append(f"decision 'not ready' on {r['date']} (rows not met: {', '.join(map(str, not_met))})")
    return bad, failing, []


def _section_words(text: str) -> dict[str, int]:
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("#"):
            cur = line.lstrip("#").strip().lower()
            out[cur] = 0
        elif cur is not None:
            out[cur] += len(line.split())
    return out


def v_disclosure(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    needed = ["tools and agents", "what each produced", "how it was checked"]
    bad = _need_headings(text, needed)
    words = _section_words(text)
    for h in needed:
        n = sum(v for k, v in words.items() if h in k)
        if not bad and n < 5:
            bad.append(f"section '{h}' is nearly empty ({n} words)")
    return bad, [], []


def _contracts_from_python(text: str) -> list[dict]:
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ToolContract" and node.args:
            name = node.args[0].value if isinstance(node.args[0], ast.Constant) else "?"
            effect = node.args[3].value if len(node.args) > 3 and isinstance(node.args[3], ast.Constant) else "?"
            approval = next((k.value.value for k in node.keywords if k.arg == "approval"
                             and isinstance(k.value, ast.Constant)), None)
            out.append({"name": name, "effect": effect, "approval": approval})
    return out


def v_tool_contracts(path, item, ctx):
    tools = _contracts_from_python(path.read_text(encoding="utf-8")) if path.suffix == ".py" \
        else _json(path).get("tools", [])
    if not tools:
        return ["no tool contracts"], [], []
    bad = [f"{t.get('name')}: no effect" for t in tools if t.get("effect") not in ("read", "write", "external")]
    failing = [f"{t['name']}: a merge, deploy, approve or push tool exists" for t in tools
               if FORBIDDEN_TOOL.search(t["name"])]
    failing += [f"{t['name']}: external effect without an approval rule" for t in tools
                if t.get("effect") == "external" and not t.get("approval")]
    return bad, failing, []


def v_drill_report(path, item, ctx):
    r = _json(path)
    bad = [] if r.get("clock") in ("simulated", "real") else ["no clock (simulated or real)"]
    if r.get("clock") == "simulated" and item.get("label") in ("verified", "deployed"):
        bad.append("simulated clock labelled " + item["label"])
    for d in r.get("drills", []):
        if not d.get("expected"):
            bad.append(f"{d.get('id')}: no expected outcome written before the drill")
    if not r.get("drills"):
        bad.append("no drills")
    failing = [f"{d['id']}: {d.get('verdict')}" for d in r.get("drills", []) if d.get("verdict") != "pass"]
    return bad, failing, []


def v_safety_case(path, item, ctx):
    c = _json(path)
    bad = [f"no {k}" for k in ("case", "claims", "defeaters", "recommendation") if k not in c]
    if bad:
        return bad, [], []
    ids = ctx["item_ids"]
    failing = []
    for cl in c["claims"]:
        for ev in cl.get("evidence", []):
            if ev not in ids:
                bad.append(f"{cl['id']}: evidence {ev!r} is not an item in the pack")
        if cl.get("status") != "supported":
            failing.append(f"{cl['id']}: {cl.get('status')}")
    for d in c["defeaters"]:
        if d.get("status") == "open" and not (d.get("owner") and d.get("due")):
            failing.append(f"{d['id']}: open with no owner and date")
    if c["recommendation"] not in ("go", "no-go", "go with conditions"):
        bad.append(f"recommendation {c['recommendation']!r}")
    return bad, failing, []


# --- D -------------------------------------------------------------------------------------------------------

def v_playbook(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    return _need_headings(text, ["detection", "containment", "kill switch", "communication", "recovery"]), [], []


def v_attack_catalogue(path, item, ctx):
    cat = _json(path)
    bad, content = [], []
    if not cat.get("classes"):
        bad.append("no classes")
    for cls in cat.get("classes", []):
        cid = cls.get("id", "?")
        for k in ("harm", "owasp_llm", "atlas"):
            if not cls.get(k):
                bad.append(f"{cid}: no {k}")
        if not cls.get("variants"):
            bad.append(f"{cid}: no variants")
        for v in cls.get("variants", []):
            extra = sorted(set(v) - VARIANT_KEYS)
            if extra:
                content.append(f"{cid}/{v.get('id')}: field(s) {', '.join(extra)} could carry attack text")
            if v.get("placeholder") is not True:
                content.append(f"{cid}/{v.get('id')}: not marked as an inert placeholder")
            if len(str(v.get("label", ""))) > MAX_LABEL:
                content.append(f"{cid}/{v.get('id')}: label longer than {MAX_LABEL} characters")
    return bad, [], content


def v_hardening_prs(path, item, ctx):
    r = _json(path)
    bad, failing = [], []
    if not r.get("prs"):
        bad.append("no pull requests")
    for pr in r.get("prs", []):
        pid = pr.get("id", "?")
        if not pr.get("reviewers"):
            bad.append(f"{pid}: no reviewer")
        elif pr.get("author") in pr["reviewers"]:
            bad.append(f"{pid}: reviewed by its own author")
        if not pr.get("merged"):
            failing.append(f"{pid}: not merged")
        if not pr.get("classes"):
            bad.append(f"{pid}: names no attack class")
        better = [c for c in pr.get("classes", []) if pr.get("after", {}).get(c, 0) > pr.get("before", {}).get(c, 0)]
        if pr.get("classes") and not better:
            failing.append(f"{pid}: coverage of its classes did not rise")
    return bad, failing, []


def v_detection_rules(path, item, ctx):
    r = _json(path)
    bad, failing = [], []
    rules = r.get("rules", [])
    min_rules = r.get("min_rules", 5)
    if len(rules) < min_rules:
        failing.append(f"{len(rules)} rules; at least {min_rules} needed")
    for rule in rules:
        if not rule.get("tests"):
            bad.append(f"{rule.get('id')}: no tests against recorded traces")
        for t in rule.get("tests", []):
            if t.get("fired") != t.get("expected"):
                failing.append(f"{rule['id']}: {t.get('trace')} fired={t.get('fired')} expected={t.get('expected')}")
    drill = r.get("drill")
    if not drill:
        bad.append("no live drill record")
    else:
        fired = set(drill.get("rules_fired", []))
        failing += [f"{rule['id']}: did not fire in the live drill" for rule in rules if rule["id"] not in fired]
        if drill.get("time_to_contain_s", 10**9) > drill.get("target_s", 0):
            failing.append(f"contained in {drill.get('time_to_contain_s')} s, target {drill.get('target_s')} s")
    return bad, failing, []


def v_ci_gate(path, item, ctx):
    r = _json(path)
    bad = [f"no {k}" for k in ("workflow", "context", "required_contexts") if k not in r]
    failing = [] if bad or r["context"] in r["required_contexts"] else [f"{r['context']} is not a required check"]
    return bad, failing, []


# Kinds whose evidence is bound to one release: the file itself must say which (evidence.check, EV008).
def file_release(kind: str, path: Path) -> str | None:
    if kind == "cyclonedx":
        return _json(path).get("metadata", {}).get("component", {}).get("version")
    if kind in VERSION_BOUND:
        return _json(path).get("release")
    return None


VERSION_BOUND = {"coverage-report", "readiness-review", "test-record", "signature", "eval-record", "cyclonedx"}


ASR_KEYS = {"system", "system_owner", "ethics_agreement", "attack_set", "configuration", "runs", "attempts",
            "successes", "interval", "date", "measured_by"}


def v_live_asr(path, item, ctx):
    r = _json(path)
    content = [f"field {k!r} is not allowed: attack text stays in the course repository" for k in sorted(set(r) - ASR_KEYS)]
    content += [f"attack_set field {k!r} is not allowed" for k in sorted(set(r.get("attack_set", {})) - {"held_in", "sha256", "version", "cases"})]
    bad = [f"no {k}" for k in sorted(ASR_KEYS) if k not in r]
    if r.get("system_owner") and r["system_owner"] != ctx["team"]:
        bad.append(f"measured on {r['system_owner']}'s system; only a system the team owns")
    if r.get("ethics_agreement") and ctx["resolve"](r["ethics_agreement"]) is None:
        bad.append("ethics agreement does not resolve")
    if not bad and r["attempts"]:
        lo, hi = wilson(r["successes"], r["attempts"])
        if abs(lo - r["interval"][0]) > 0.0015 or abs(hi - r["interval"][1]) > 0.0015:
            bad.append("interval is not the Wilson 95% interval")
    return bad, [], content


# --- C -------------------------------------------------------------------------------------------------------

def v_maturity(path, item, ctx):
    from adoption.maturity import assess
    r = _json(path)
    model, register = ctx["resolve"](r.get("model", "")), ctx["resolve"](r.get("register", ""))
    if model is None or register is None:
        return ["model or register does not resolve"], [], []
    levels = assess(_json(model), _json(register))
    bad = []
    for team, dims in r.get("claimed", {}).items():
        for dim, level in dims.items():
            got = levels.get(team, {}).get(dim, (None,))[0]
            if got != level:
                bad.append(f"{team}/{dim}: claims level {level}; the evidence gives {got}")
    if not r.get("claimed"):
        bad.append("no claimed levels")
    return bad, [], []


def v_operating_model(path, item, ctx):
    from adoption.tom import check_tom
    return [], [f"{f.rule} {f.subject}: {f.message}" for f in check_tom(_json(path))], []


# Lab 20.1's rules that do not depend on its company's model: ROI002 (its known references), ROI006 and ROI007
# (its fixed list of inputs) are about Lab 20.1's own model and are not applied to a capstone's.
ROI_RULES = {"ROI001", "ROI003", "ROI004", "ROI005", "ROI008"}


def v_roi_model(path, item, ctx):
    from adoption.roi import check_inputs
    inputs = _json(path).get("inputs", [])
    bad = [] if inputs else ["no inputs"]
    bad += [f"{i.get('id')}: measured with no source reference" for i in inputs
            if i.get("status") == "measured" and not (i.get("source") or {}).get("ref")]
    failing = [f"{f.rule} {f.subject}: {f.message}" for f in check_inputs(inputs) if f.rule in ROI_RULES]
    return bad, failing, []


def v_kpi_framework(path, item, ctx):
    r = _json(path)
    bad = []
    if len(r.get("outcomes", [])) < 3:
        bad.append("fewer than three outcome KPIs")
    bad += [f"{o.get('id')}: no baseline with a source" for o in r.get("outcomes", [])
            if not (o.get("baseline") and o["baseline"].get("source"))]
    if len(r.get("guardrails", [])) < 2:
        bad.append("fewer than two guardrail metrics")
    bad += [f"{g.get('id')}: no threshold" for g in r.get("guardrails", []) if "threshold" not in g]
    for k in ("stop", "scale"):
        if not r.get("triggers", {}).get(k):
            bad.append(f"no {k} trigger")
    return bad, [], []


def v_pilot_analysis(path, item, ctx):
    r = _json(path)
    bad = []
    pre = r.get("pre_registration", {})
    target = ctx["resolve"](pre.get("ref", ""))
    from . import sha256_file
    if target is None:
        bad.append("pre-registration does not resolve")
    elif sha256_file(target) != pre.get("sha256"):
        bad.append("pre-registration changed after it was frozen (hash differs)")
    p = r.get("primary", {})
    if not all(k in p for k in ("measure", "estimate", "interval", "null", "wording")):
        bad.append("primary outcome needs measure, estimate, interval, null and wording")
    else:
        lo, hi = p["interval"]
        if lo <= p["null"] <= hi and "no clear change" not in p["wording"].lower():
            bad.append(f"interval {lo} to {hi} includes {p['null']}, but the wording claims an effect")
    return bad, [], []


def v_roadmap(path, item, ctx):
    r = _json(path)
    stages = r.get("stages", [])
    bad = [] if stages else ["no stages"]
    failing = []
    if stages and stages[0].get("share", 1) >= 1:
        failing.append("the first stage covers everyone: a big-bang rollout")
    failing += [f"{s.get('id')}: no gate evidence" for s in stages if not s.get("gate_evidence")]
    return bad, failing, []


def v_markdown(path, item, ctx):
    text = path.read_text(encoding="utf-8")
    bad = [] if text.startswith("# ") else ["no title line"]
    return bad + _need_headings(text, ctx["requirement"].get("headings", [])), [], []


VALIDATORS = {
    "spec": v_spec, "adr": v_adr, "threat-model": v_threat_model, "eval-record": v_eval_record,
    "lab-report": v_lab_report, "coverage-report": v_coverage_report, "redteam-log": v_redteam_log,
    "test-record": v_test_record, "cyclonedx": v_cyclonedx, "signature": v_signature, "identity": v_identity,
    "slo": v_slo, "runbook": v_runbook, "cost-report": v_cost_report, "readiness-review": v_readiness_review,
    "disclosure": v_disclosure, "tool-contracts": v_tool_contracts, "drill-report": v_drill_report,
    "safety-case": v_safety_case, "playbook": v_playbook, "attack-catalogue": v_attack_catalogue,
    "hardening-prs": v_hardening_prs, "detection-rules": v_detection_rules, "ci-gate": v_ci_gate,
    "live-asr": v_live_asr, "maturity": v_maturity, "operating-model": v_operating_model,
    "roi-model": v_roi_model, "kpi-framework": v_kpi_framework, "pilot-analysis": v_pilot_analysis,
    "roadmap": v_roadmap, "markdown": v_markdown,
}

def n_coverage_report(path, item, ctx):
    """Notes (EV013, a warning): deployment evidence that is a generated record rather than an observation."""
    r = _json(path)
    counted = cov.counted(r)
    gen = sorted({d["control"] for d in r.get("deployments", []) if "generated" in str(d.get("observed", ""))
                  and d["control"] in counted})
    if not gen:
        return []
    return [f"{len(gen)} of {len(counted)} counted controls' deployment records are generated, not observed"]


NOTES = {"coverage-report": n_coverage_report}

assert set(LABELS) == {"verified", "modelled", "deployed", "open"}
