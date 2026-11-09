"""TODO 1: open_pull_request looks before it creates, so it is safe to call again after an unknown outcome."""

from faultlab.github import SimGitHub, open_pull_request

ARGS = {"branch": "agent/ht-031", "title": "HT-031: draft", "body": "b", "diff_sha256": "a" * 64}


def test_the_first_call_creates_a_draft():
    gh = SimGitHub()
    assert open_pull_request(gh, ARGS) == {"number": 5100, "existing": False}
    assert gh.pulls[0]["draft"] and gh.pulls[0]["diff_sha256"] == "a" * 64


def test_a_second_call_on_the_same_branch_returns_the_first():
    gh = SimGitHub()
    open_pull_request(gh, ARGS)
    assert open_pull_request(gh, dict(ARGS, title="again")) == {"number": 5100, "existing": True}
    assert gh.creates == 1 and gh.lookups == 2


def test_another_branch_gets_its_own():
    gh = SimGitHub()
    open_pull_request(gh, ARGS)
    assert open_pull_request(gh, dict(ARGS, branch="agent/ht-032"))["number"] == 5101


def test_a_closed_pull_request_does_not_count():
    gh = SimGitHub()
    open_pull_request(gh, ARGS)
    gh.pulls[0]["state"] = "closed"
    assert open_pull_request(gh, ARGS) == {"number": 5101, "existing": False}
