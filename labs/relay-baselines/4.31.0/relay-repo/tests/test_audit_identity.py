"""Agent identities and short-lived Relay tokens (4.23.0, ADR-020). Claims are written by hand: verifying the
platform's own token (GitHub OIDC, a signed AWS request) is a separate verifier, not part of 4.23.0."""

import pytest

from relay.audit import AUDIENCE, MAX_TTL_SECONDS, AgentRegistry, RegistryError, TokenRejected, TokenService, validate

KEY = b"test-signing-key-for-relay-tests-only-000"
GH = "https://token.actions.githubusercontent.com"
SSO = "https://login.relay.example"
NOW = 1_800_000_000.0


def registry_data(**changes):
    agents = [
        {"agent_id": "eval-harvester", "kind": "ci-job", "owner": "tomas.b", "issuer": GH,
         "subject": "repo:relay-example/relay:environment:eval-harvest", "scopes": ["tickets:read:support"]},
        {"agent_id": "coding-session", "kind": "ecs-task", "owner": "sam.o", "issuer": "https://sts.amazonaws.com",
         "subject": "arn:aws:sts::111122223333:assumed-role/relay-nonprod-sandbox",
         "scopes": ["testdb:query", "tasks:read:platform"], "delegation": "required", "delegators": ["priya.n"]},
    ]
    data = {"version": "agent-registry-v1", "people": ["priya.n", "sam.o", "tomas.b"], "person_issuer": SSO,
            "agents": agents}
    data.update(changes)
    return data


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


def service(clock=None, data=None):
    clock = clock or Clock()
    return TokenService(AgentRegistry(data or registry_data()), KEY, clock=clock, new_id=lambda: "jti-1"), clock


def harvester_workload(**changes):
    return {"iss": GH, "sub": "repo:relay-example/relay:environment:eval-harvest", "aud": AUDIENCE, "iat": NOW,
            **changes}


def sandbox_workload(**changes):
    return {"iss": "https://sts.amazonaws.com", "aud": AUDIENCE, "iat": NOW,
            "sub": "arn:aws:sts::111122223333:assumed-role/relay-nonprod-sandbox", **changes}


def person(name="priya.n", **changes):
    return {"iss": SSO, "sub": name, "aud": AUDIENCE, "iat": NOW, **changes}


def test_exchange_issues_a_token_for_the_registered_workload_with_only_the_asked_scopes():
    svc, clock = service()
    token, claims = svc.exchange(harvester_workload(), ["tickets:read:support"])
    assert token.startswith("rla_")
    assert claims == {"sub": "eval-harvester", "own": "tomas.b", "obo": "tomas.b", "scp": ["tickets:read:support"],
                      "iat": 1_800_000_000, "exp": 1_800_000_000 + MAX_TTL_SECONDS, "ep": 1, "jti": "jti-1"}
    assert svc.verify(token, "tickets:read:support") == claims


def test_the_lifetime_is_capped_at_fifteen_minutes():
    svc, _ = service()
    _, claims = svc.exchange(harvester_workload(), ["tickets:read:support"], ttl_seconds=86400)
    assert claims["exp"] - claims["iat"] == 900


@pytest.mark.parametrize("workload, scopes, subject, code", [
    (harvester_workload(sub="repo:relay-example/relay:pull_request"), ["tickets:read:support"], None,
     "unknown_workload"),
    (harvester_workload(aud="sts.amazonaws.com"), ["tickets:read:support"], None, "wrong_audience"),
    (harvester_workload(iat=NOW - 301), ["tickets:read:support"], None, "stale_proof"),
    ({k: v for k, v in harvester_workload().items() if k != "iat"}, ["tickets:read:support"], None, "stale_proof"),
    (harvester_workload(), [], None, "no_scope"),
    (harvester_workload(), ["audit:delete"], None, "forbidden_scope"),
    (harvester_workload(), ["tickets:read:support", "tasks:export:support"], None, "scope_not_granted"),
    (harvester_workload(), ["tickets:read:support"], person(), "unexpected_subject"),
])
def test_exchange_refusals(workload, scopes, subject, code):
    svc, _ = service()
    with pytest.raises(TokenRejected) as exc:
        svc.exchange(workload, scopes, subject=subject)
    assert exc.value.code == code


@pytest.mark.parametrize("subject, code", [
    (None, "delegation_required"),
    (person(iss="https://evil.example"), "bad_subject_token"),
    (person(aud="another-service"), "bad_subject_token"),
    (person(iat=NOW - 600), "bad_subject_token"),
    (person("tomas.b"), "delegator_not_allowed"),
])
def test_a_delegated_agent_needs_the_persons_own_fresh_proof(subject, code):
    svc, _ = service()
    with pytest.raises(TokenRejected) as exc:
        svc.exchange(sandbox_workload(), ["testdb:query"], subject=subject)
    assert exc.value.code == code


def test_the_person_recorded_is_the_one_in_the_subject_token():
    svc, _ = service()
    _, claims = svc.exchange(sandbox_workload(), ["testdb:query"], subject=person())
    assert (claims["sub"], claims["own"], claims["obo"]) == ("coding-session", "sam.o", "priya.n")


def test_an_expired_token_is_refused_at_its_expiry_second():
    svc, clock = service()
    token, claims = svc.exchange(harvester_workload(), ["tickets:read:support"])
    clock.t = claims["exp"] - 1
    svc.verify(token)
    clock.t = claims["exp"]
    with pytest.raises(TokenRejected) as exc:
        svc.verify(token)
    assert exc.value.code == "expired"


def test_a_tampered_token_or_one_signed_with_another_key_is_refused():
    svc, clock = service()
    token, _ = svc.exchange(harvester_workload(), ["tickets:read:support"])
    payload, sig = token[4:].split(".")
    forged = "rla_" + payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB") + "." + sig
    other = TokenService(svc.registry, b"another-key-another-key-another-key", clock=clock)
    for bad, code in ((forged, "bad_signature"), ("rla_nodot", "malformed"), ("rly_x.y", "malformed")):
        with pytest.raises(TokenRejected) as exc:
            svc.verify(bad)
        assert exc.value.code == code
    with pytest.raises(TokenRejected) as exc:
        other.verify(token)
    assert exc.value.code == "bad_signature"


def test_a_scope_the_token_does_not_carry_is_refused():
    svc, _ = service()
    token, _ = svc.exchange(harvester_workload(), ["tickets:read:support"])
    with pytest.raises(TokenRejected) as exc:
        svc.verify(token, "tasks:export:support")
    assert exc.value.code == "scope_missing"


def test_disabling_refuses_every_outstanding_token_and_re_enabling_does_not_revive_them():
    svc, _ = service()
    token, _ = svc.exchange(harvester_workload(), ["tickets:read:support"])
    svc.registry.disable("eval-harvester", at=NOW)
    assert svc.registry.get("eval-harvester").tripped_at == NOW
    with pytest.raises(TokenRejected) as exc:
        svc.verify(token)
    assert exc.value.code == "disabled"
    with pytest.raises(TokenRejected) as exc:
        svc.exchange(harvester_workload(), ["tickets:read:support"])
    assert exc.value.code == "disabled"
    svc.registry.enable("eval-harvester")
    with pytest.raises(TokenRejected) as exc:
        svc.verify(token)
    assert exc.value.code == "revoked"
    fresh, claims = svc.exchange(harvester_workload(), ["tickets:read:support"])
    assert claims["ep"] == 2 and svc.verify(fresh)


def test_re_enabling_under_a_new_subject_refuses_proofs_for_the_old_one():
    svc, _ = service()
    svc.registry.disable("coding-session", at=NOW)
    new = "arn:aws:sts::111122223333:assumed-role/relay-nonprod-sandbox-2"
    svc.registry.enable("coding-session", new_subject=new)
    with pytest.raises(TokenRejected) as exc:
        svc.exchange(sandbox_workload(), ["testdb:query"], subject=person())
    assert exc.value.code == "unknown_workload"
    assert svc.exchange(sandbox_workload(sub=new), ["testdb:query"], subject=person())[1]["ep"] == 2


@pytest.mark.parametrize("change, problem", [
    ({"scopes": ["tickets:read:support", "agents:manage"]}, "eval-harvester: forbidden scope agents:manage"),
    ({"scopes": ["tickets:*"]}, "eval-harvester: wildcard scope tickets:*"),
    ({"owner": "relay-bot"}, "eval-harvester: owner 'relay-bot' is not a person in the registry"),
    ({"subject": "repo:relay-example/*"}, "eval-harvester: issuer and subject must be exact, with no wildcard"),
    ({"max_ttl_seconds": 3600}, "eval-harvester: max_ttl_seconds must be 60 to 900"),
    ({"kind": "laptop"}, "eval-harvester: kind must be one of ci-job, ecs-task"),
])
def test_the_registry_refuses_unsafe_entries(change, problem):
    data = registry_data()
    data["agents"][0].update(change)
    assert problem in validate(data)
    with pytest.raises(RegistryError):
        AgentRegistry(data)


def test_one_workload_cannot_belong_to_two_agents_and_delegation_needs_a_person_issuer():
    data = registry_data()
    data["agents"].append({**data["agents"][0], "agent_id": "dataset-refresh"})
    assert "dataset-refresh: workload already belongs to another agent (shared identity)" in validate(data)
    assert "coding-session: delegation required, but the registry names no person_issuer" in validate(
        registry_data(person_issuer=None))


def test_the_signing_key_must_be_long_enough():
    with pytest.raises(ValueError):
        TokenService(AgentRegistry(registry_data()), b"short")
