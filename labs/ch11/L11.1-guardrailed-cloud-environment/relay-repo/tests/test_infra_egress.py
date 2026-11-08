"""Egress fitness checks (4.21.0, ADR-013): the proxy allows HTTPS to the reviewed domains and nothing else.

These read the committed configuration; they do not start a proxy. What they cannot see:
a domain on the allowlist that serves attacker content, and DNS lookups, which the VPC
resolver answers without passing through the proxy or the security groups (ADR-013).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROXY = ROOT / "deploy" / "egress-proxy"
REVIEWED = {"github.com", "api.github.com", "codeload.github.com", "pypi.org", "files.pythonhosted.org"}


def allowlist() -> list[str]:
    lines = (PROXY / "allowlist.txt").read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def access_rules() -> list[str]:
    text = (PROXY / "squid.conf").read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("http_access")]


def test_allowlist_is_exactly_the_reviewed_domains():
    assert sorted(allowlist()) == sorted(REVIEWED)


def test_no_wildcard_or_bare_top_level_domain():
    assert [d for d in allowlist() if "*" in d or d.count(".") < 1 or d.startswith(".")] == []


def test_proxy_denies_everything_it_does_not_allow():
    rules = access_rules()
    assert rules[-1] == "http_access deny all"
    allows = [r for r in rules if r.startswith("http_access allow")]
    assert allows == ["http_access allow CONNECT allowed_domains"]


def test_only_the_sandbox_subnet_and_port_443():
    text = (PROXY / "squid.conf").read_text(encoding="utf-8")
    assert re.search(r"^acl sandbox src 10\.40\.21\.0/24$", text, re.M)
    assert re.search(r"^acl https_port port 443$", text, re.M)
    assert "http_access deny !sandbox" in access_rules()


def test_one_security_group_rule_reaches_the_internet_and_it_is_the_proxy():
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "infra").glob("*.tf")))
    blocks = re.findall(r'resource "aws_vpc_security_group_egress_rule" "(\w+)" \{(.*?)\n\}', text, re.S)
    open_rules = [name for name, body in blocks if '"0.0.0.0/0"' in body or '"::/0"' in body]
    assert open_rules == ["proxy_https_internet"]
