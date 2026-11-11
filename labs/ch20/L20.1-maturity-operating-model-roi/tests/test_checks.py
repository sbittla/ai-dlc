"""Hand-checkable tests for the four TODOs and the provided operating-model check."""

import copy
import json

import pytest

from conftest import DATA_DIR

from adoption.catalog import check_aup, check_catalog
from adoption.maturity import criterion_met
from adoption.roi import REQUIRED, check_inputs, evaluate, tornado, values
from adoption.tom import check_tom

# --- TODO 1: evidence rules ---------------------------------------------------------------------------------------

CRIT = {"id": "X3.1", "level": 3, "text": "t", "accepts": ["measurement"], "max_age_days": 90,
        "threshold": {"field": "share", "op": ">=", "value": 0.9}}


def item(**kw):
    base = {"team": "mobile", "criterion": "X3.1", "type": "measurement", "ref": "report", "date": "2027-05-01",
            "owner": "lena.k", "share": 0.95}
    base.update(kw)
    return base


@pytest.mark.parametrize("kw, met, reason", [
    ({}, True, "met by report"),
    ({"team": "*"}, True, "met by report"),
    ({"team": "analytics"}, False, "no evidence"),
    ({"criterion": "X3.2"}, False, "no evidence"),
    ({"type": "opinion"}, False, "opinion is not evidence"),
    ({"type": "survey"}, False, "survey not accepted"),
    ({"owner": ""}, False, "no reference or owner"),
    ({"date": "2027-06-12"}, False, "dated after the assessment"),
    ({"date": "2027-02-01"}, False, "older than 90 days"),
    ({"share": 0.89}, False, "share 0.89 fails >= 0.9"),
    ({"share": None}, False, "share None fails >= 0.9"),
])
def test_one_item(kw, met, reason):
    assert criterion_met(CRIT, [item(**kw)], "mobile", "2027-06-11") == (met, reason)


def test_any_admissible_item_is_enough_and_reasons_are_distinct_and_sorted():
    assert criterion_met(CRIT, [item(type="opinion"), item(ref="newer", date="2027-06-01")], "mobile",
                         "2027-06-11") == (True, "met by newer")
    got = criterion_met(CRIT, [item(type="opinion"), item(share=0.5), item(type="opinion", date="2027-04-01")],
                        "mobile", "2027-06-11")
    assert got == (False, "opinion is not evidence; share 0.5 fails >= 0.9")


def test_threshold_free_criterion_and_the_age_boundary():
    crit = {"id": "X2.1", "level": 2, "accepts": ["artifact", "record"], "max_age_days": 10}
    ok = {"team": "relay", "criterion": "X2.1", "type": "record", "ref": "r", "date": "2027-06-01", "owner": "sam.o"}
    assert criterion_met(crit, [ok], "relay", "2027-06-11")[0] is True        # exactly 10 days old
    assert criterion_met(crit, [ok], "relay", "2027-06-12")[0] is False


# --- provided: target operating model ------------------------------------------------------------------------------

def test_operating_model_rules():
    reviewed = json.loads((DATA_DIR / "operating-model" / "tom-reviewed.json").read_text(encoding="utf-8"))
    assert check_tom(reviewed) == []
    draft = json.loads((DATA_DIR / "operating-model" / "tom-draft.json").read_text(encoding="utf-8"))
    assert {f.rule for f in check_tom(draft)} == {"TOM001", "TOM002", "TOM003", "TOM004", "TOM005", "TOM006"}


def test_operating_model_probes():
    tom = json.loads((DATA_DIR / "operating-model" / "tom-reviewed.json").read_text(encoding="utf-8"))
    caps = {c["id"]: c for c in tom["capabilities"]}
    caps["CAP08"]["approvers"].append("engineering-director")       # the sponsor approves the readout
    caps["CAP01"]["security_veto"] = ["sam.o"]                        # a veto held outside security
    caps["CAP02"]["approvers"].append("approvals-bot")               # an approver who is not a person
    assert [(f.rule, f.subject) for f in check_tom(tom)] == [("TOM002", "CAP02"), ("TOM003", "CAP08"),
                                                             ("TOM006", "CAP01")]


# --- TODO 2: the catalog ------------------------------------------------------------------------------------------

def load(name):
    return json.loads((DATA_DIR / "catalog" / name).read_text(encoding="utf-8"))


@pytest.fixture()
def cat():
    return load("catalog-reviewed.json")


RELAY = {"mcp": load("relay-4.30.0/mcp.json"), "comps": load("relay-4.30.0/ai-components.json"),
         "agents": load("relay-4.30.0/agents.json"), "security": ["aisha.r"], "cases": []}
CASE = {"id": "SSC-1", "status": "approved", "approved_by": ["aisha.r", "priya.n"], "approved_on": "2027-06-10"}


def findings(c, as_of="2027-06-15", **over):
    r = dict(RELAY, **over)
    return [(f.rule, f.subject) for f in check_catalog(c, r["mcp"], r["comps"], r["agents"], as_of, r["security"],
                                                       r["cases"])]


def entry(c, tid):
    return next(t for t in c["tools"] if t["id"] == tid)


def test_reviewed_catalog_passes(cat):
    assert findings(cat) == []


@pytest.mark.parametrize("change, expected", [
    (lambda c: entry(c, "ide-completion").update(owner="someone.else"), [("CAT001", "ide-completion")]),
    (lambda c: entry(c, "ide-completion").update(security_approver="lead.marketplace"),
     [("CAT002", "ide-completion")]),
    (lambda c: entry(c, "ide-completion").update(security_approver="sam.o"), [("CAT002", "ide-completion")]),
    (lambda c: entry(c, "chat-assistant-enterprise").update(max_data_class="Restricted"),
     [("CAT003", "chat-assistant-enterprise")]),
    (lambda c: entry(c, "consumer-chat-personal").update(alternative="docs-browser-mcp"),
     [("CAT004", "consumer-chat-personal")]),
    (lambda c: entry(c, "ide-completion").update(review_by="2027-06-14"), [("CAT005", "ide-completion")]),
    (lambda c: entry(c, "docs-browser-mcp")["launch"].update(sha256=""), [("CAT006", "docs-browser-mcp")]),
    (lambda c: entry(c, "docs-browser-mcp")["launch"].update(sha256="lab-stand-in"), [("CAT006", "docs-browser-mcp")]),
    (lambda c: entry(c, "ide-completion").update(security_approver="priya.n"), [("CAT002", "ide-completion")]),
    (lambda c: entry(c, "relay-db-readonly")["launch"].update(sha256="0" * 64), [("CAT006", "relay-db-readonly")]),
    (lambda c: entry(c, "autonomous-maintenance-agent").update(status="trial"),
     [("CAT007", "autonomous-maintenance-agent")]),
    (lambda c: entry(c, "ide-completion").update(runs_unattended=True), [("CAT007", "ide-completion")]),
    (lambda c: entry(c, "ide-completion").pop("runs_unattended"), [("CAT007", "ide-completion")]),
    (lambda c: entry(c, "docs-browser-mcp").update(reviewed_on="2027-06-16"), [("CAT009", "docs-browser-mcp")]),
])
def test_each_rule_alone(cat, change, expected):
    change(cat)
    assert findings(cat) == expected


def test_relay_servers_must_be_in_the_catalog_as_launched(cat):
    entry(cat, "relay-db-readonly").update(status="under-review")
    assert findings(cat) == [("CAT006", "relay-db-readonly")]
    cat2 = load("catalog-reviewed.json")
    mcp = copy.deepcopy(RELAY["mcp"])
    mcp["mcpServers"]["relay-db-readonly"]["args"].append("--write")
    assert findings(cat2, mcp=mcp) == [("CAT006", "relay-db-readonly")]


def _with_agent(agent):
    agents = copy.deepcopy(RELAY["agents"])
    agents["agents"].append(agent)
    return agents


def test_autonomous_agent_needs_its_own_approved_case_and_its_own_registry_identity(cat):
    tid = "autonomous-maintenance-agent"
    e = entry(cat, tid)
    e.update(status="approved", safety_case="SSC-1", registry_identity=tid)
    own = _with_agent({"agent_id": tid, "owner": "sam.o"})
    case = dict(CASE, subject=tid)
    assert findings(cat, cases=[case], agents=own) == []
    bad = [("CAT007", tid)]
    e.update(safety_case="tbd")
    assert findings(cat, cases=[case], agents=own) == bad                                  # not a case record
    e.update(safety_case="SSC-1")
    assert findings(cat, cases=[dict(case, subject="docs-browser-mcp")], agents=own) == bad  # another tool's case
    assert findings(cat, cases=[dict(case, status="draft")], agents=own) == bad             # not approved
    assert findings(cat, cases=[dict(case, approved_by=["priya.n", "lena.k"])], agents=own) == bad  # no security
    assert findings(cat, cases=[dict(case, approved_by=["aisha.r", "sam.o"])], agents=own) == bad   # the owner
    assert findings(cat, cases=[dict(case, approved_by=["aisha.r"])], agents=own) == bad            # one approver
    assert findings(cat, cases=[dict(case, approved_by=["aisha.r", "approvals-bot"])], agents=own) == bad  # not a person
    e.update(registry_identity="spec-to-pr-helper")                     # same owner, but another tool's identity
    assert findings(cat, cases=[case], agents=own) == bad
    e.update(registry_identity="maint-7")
    assert findings(cat, cases=[case], agents=_with_agent({"agent_id": "maint-7", "owner": "sam.o",
                                                            "catalogue_entry": tid})) == []
    assert findings(cat, cases=[case], agents=_with_agent({"agent_id": "maint-7", "owner": "lena.k",
                                                            "catalogue_entry": tid})) == bad    # owner differs


def test_a_scheduled_tool_cannot_declare_itself_attended(cat):
    entry(cat, "ide-completion").update(triggers=["person", "schedule"])
    assert findings(cat) == [("CAT007", "ide-completion")]
    cat2 = load("catalog-reviewed.json")
    entry(cat2, "ide-completion").pop("triggers")
    assert findings(cat2) == [("CAT007", "ide-completion")]


def test_data_classes_are_case_insensitive_and_external_is_required(cat):
    entry(cat, "chat-assistant-enterprise").update(max_data_class="restricted")
    assert findings(cat) == [("CAT003", "chat-assistant-enterprise")]
    cat2 = load("catalog-reviewed.json")
    entry(cat2, "ide-completion").pop("external")
    assert findings(cat2) == [("CAT003", "ide-completion")]


def test_an_unknown_data_class_is_a_finding(cat):
    entry(cat, "chat-assistant-enterprise").update(max_data_class="Secret")
    assert findings(cat) == [("CAT003", "chat-assistant-enterprise")]


def test_a_relabelled_tool_server_is_still_pinned(cat):
    e = entry(cat, "docs-browser-mcp")
    e.update(kind="completion")
    e["launch"].update(sha256="not-a-hash")
    assert findings(cat) == [("CAT006", "docs-browser-mcp")]


def test_an_agent_with_a_harmless_kind_still_needs_a_case_if_it_runs_unattended(cat):
    e = entry(cat, "coding-agent-enterprise")
    e.update(runs_unattended=True)
    assert findings(cat) == [("CAT007", "coding-agent-enterprise")]


def test_the_security_list_comes_from_the_operating_model_not_the_catalogue(cat):
    cat["security_approvers"] = ["lead.marketplace"]
    entry(cat, "ide-completion").update(security_approver="lead.marketplace")
    assert findings(cat) == [("CAT002", "ide-completion")]


def test_the_february_catalogue_passes_on_its_own_date():
    feb = load("catalog-2027-02.json")
    assert findings(feb, as_of=feb["approved_on"]) == []
    assert len(feb["tools"]) == 5


def test_lapsed_reviews_matter_only_for_live_entries(cat):
    entry(cat, "autonomous-maintenance-agent").update(review_by="2020-01-01")
    assert findings(cat) == []


def test_policy_names_its_catalog_and_has_every_section():
    sections = load("aup-sections.json")["sections"]
    text = (DATA_DIR / "catalog" / "aup-reviewed.md").read_text(encoding="utf-8")
    assert check_aup(text, sections, "2027.06.1") == []
    assert [f.rule for f in check_aup(text, sections, "2027.03.1")] == ["CAT008"]
    v1 = (DATA_DIR / "catalog" / "aup-v1.md").read_text(encoding="utf-8")
    assert check_aup(v1, sections, "2027.02.1") == []


# --- TODO 3 and 4: ROI inputs and the tornado ---------------------------------------------------------------------

def inp(iid, value=1.0, low=0.5, high=1.5, status="projected", kind="estimate", ref="x", label="l"):
    return {"id": iid, "label": label, "value": value, "low": low, "high": high, "unit": "u", "status": status,
            "source": {"kind": kind, "ref": ref}}


def full():
    return [inp(r) for r in REQUIRED]


def rules_of(inputs):
    return [(f.rule, f.subject) for f in check_inputs(inputs)]


def test_complete_inputs_pass():
    assert rules_of(full()) == []


@pytest.mark.parametrize("override, expected", [
    ({"status": ""}, [("ROI001", "realization")]),
    ({"status": "measured", "kind": "estimate"}, [("ROI002", "realization")]),
    ({"status": "measured", "kind": "pilot", "ref": " "}, [("ROI002", "realization")]),
    ({"status": "projected", "kind": "vendor-claim"}, [("ROI003", "realization")]),
    ({"status": "measured", "kind": "vendor-claim"}, [("ROI002", "realization"), ("ROI003", "realization")]),
    ({"value": 2.0}, [("ROI004", "realization")]),
    ({"low": 1.0, "high": 1.0}, [("ROI004", "realization")]),
    ({"label": "Prompts per engineer"}, [("ROI005", "realization")]),
    ({"kind": "vendor"}, [("ROI008", "realization")]),
    ({"ref": "vendor benchmark, 38% faster"}, [("ROI003", "realization")]),
    ({"status": "measured", "kind": "pilot", "ref": "vendor benchmark, 38% faster"},
     [("ROI002", "realization"), ("ROI003", "realization")]),
    ({"status": "measured", "kind": "pilot", "ref": "Lab 20.2: python -m experiment.report roi-inputs",
      "low": 1.0, "high": 1.0}, [("ROI004", "realization")]),
])
def test_input_rules(override, expected):
    inputs = full()
    i = next(x for x in inputs if x["id"] == "realization")
    for k, v in override.items():
        if k in ("kind", "ref"):
            i["source"][k] = v
        else:
            i[k] = v
    assert rules_of(inputs) == expected


def test_measured_exact_values_are_fine_and_missing_or_unknown_inputs_are_found():
    inputs = full()
    inputs[0].update(status="measured", low=1.0, high=1.0)
    inputs[0]["source"].update(kind="contract", ref="signed order form, 2027-02-24")
    assert rules_of(inputs) == []
    assert rules_of(inputs[1:] + [inp("lines_of_code")]) == [("ROI005", "lines_of_code"),
                                                              ("ROI006", REQUIRED[0]), ("ROI007", "lines_of_code")]


def test_tornado_by_hand():
    inputs = json.loads((DATA_DIR / "roi" / "inputs-reviewed.json").read_text(encoding="utf-8"))["inputs"]
    rows = tornado(inputs)
    ids = [r[0] for r in rows]
    assert "engineers" not in ids and "seat_usd_per_engineer_month" not in ids   # no range, no bar
    assert [r[3] for r in rows] == sorted((r[3] for r in rows), reverse=True)
    base = values(inputs)
    for iid, lo, hi, swing in rows:
        i = next(x for x in inputs if x["id"] == iid)
        assert lo == pytest.approx(evaluate(dict(base, **{iid: i["low"]}))["net"])
        assert hi == pytest.approx(evaluate(dict(base, **{iid: i["high"]}))["net"])
        assert swing == pytest.approx(abs(hi - lo))


def test_tornado_passes_options_through():
    inputs = json.loads((DATA_DIR / "roi" / "inputs-reviewed.json").read_text(encoding="utf-8"))["inputs"]
    one = {r[0]: r for r in tornado(inputs, months=1, include_training=False)}
    assert "training_hours_per_engineer" in one and one["training_hours_per_engineer"][3] == 0
