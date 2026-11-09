"""The allowlisted-content egress path (4.26.0, ADR-035): on the content hosts, only Relay's repository.

These read the committed configuration; they do not start a proxy. The URL patterns are checked here with
Python's `re`, which agrees with Squid's POSIX extended regular expressions on the simple syntax they use
(anchors, escaped dots, groups and alternation). What these tests cannot see: whether the deployed sandbox
trusts the bump CA, and DNS lookups through the VPC resolver (ADR-013's first gap).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROXY = ROOT / "deploy" / "egress-proxy"


def entries(name: str) -> list[str]:
    lines = (PROXY / name).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def conf_lines(prefix: str) -> list[str]:
    text = (PROXY / "squid.conf").read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(prefix)]


def allowed(url: str) -> bool:
    return any(re.search(pattern, url) for pattern in entries("content-urls.txt"))


def test_content_hosts_are_the_three_github_names_and_all_are_allowlisted():
    hosts = entries("content-hosts.txt")
    assert sorted(hosts) == ["api.github.com", "codeload.github.com", "github.com"]
    assert set(hosts) <= set(entries("allowlist.txt"))


def test_every_url_pattern_is_anchored_https_on_a_content_host_and_names_relays_repository():
    hosts = set(entries("content-hosts.txt"))
    for pattern in entries("content-urls.txt"):
        assert pattern.startswith("^https://")
        host = pattern[len("^https://"):].split("/", 1)[0].replace("\\.", ".")
        assert host in hosts
        assert "/relay-example/relay" in pattern


@pytest.mark.parametrize("url", [
    "https://github.com/relay-example/relay.git/info/refs?service=git-upload-pack",
    "https://github.com/relay-example/relay/pull/2417",
    "https://api.github.com/repos/relay-example/relay/pulls",
    "https://api.github.com/repos/relay-example/relay",
    "https://codeload.github.com/relay-example/relay/tar.gz/refs/heads/main",
])
def test_relays_own_repository_is_reachable(url):
    assert allowed(url)


@pytest.mark.parametrize("url", [
    "https://api.github.com/repos/attacker-example/drop/issues",     # the red team's exfiltration path
    "https://api.github.com/gists",
    "https://api.github.com/graphql",
    "https://api.github.com/search/code?q=relay",
    "https://github.com/attacker-example/instructions/raw/main/next.md",
    "https://github.com/relay-example/relay-evil",                   # a lookalike name under the same owner
    "https://api.github.com/repos/relay-example/relayx/issues",
    "https://codeload.github.com/attacker-example/drop/zip/main",
    "https://evil.example/https://api.github.com/repos/relay-example/relay",  # pattern must be anchored
])
def test_everything_else_on_the_content_hosts_is_refused(url):
    assert not allowed(url)


def test_only_the_content_hosts_are_decrypted_and_everything_else_is_spliced():
    assert conf_lines("ssl_bump") == ["ssl_bump peek step1", "ssl_bump bump content_sni", "ssl_bump splice all"]
    assert 'acl content_sni ssl::server_name "/etc/squid/content-hosts.txt"' in conf_lines("acl")


def test_decrypted_requests_need_both_a_content_host_and_a_reviewed_url():
    rules = conf_lines("http_access")
    assert "http_access allow decrypted content_hosts relay_content" in rules
    assert rules.index("http_access allow decrypted content_hosts relay_content") == len(rules) - 2
    assert 'acl relay_content url_regex "/etc/squid/content-urls.txt"' in conf_lines("acl")
    assert "acl decrypted proto HTTPS" in conf_lines("acl")


def test_the_image_has_sslbump_and_copies_both_lists_but_no_ca_key():
    text = (PROXY / "Containerfile").read_text(encoding="utf-8")
    assert "squid-openssl" in text
    for name in ("content-hosts.txt", "content-urls.txt"):
        assert f"COPY deploy/egress-proxy/{name} /etc/squid/{name}" in text
    assert not any(p.suffix in (".key", ".pem") for p in PROXY.iterdir())
