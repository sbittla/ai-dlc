"""Rendering text that a customer or a model wrote (added in 4.26.0; ADR-032).

Relay's web client shows two kinds of text that Relay did not write: what a customer typed into a ticket,
and what a model wrote about it (the triage summary). Either may carry an attacker's instructions, and
the February 2027 incident (Chapter 12) showed the cheapest way out for stolen data: a Markdown image
whose address holds the data. The browser fetches the image as soon as the text is shown, so nobody has
to click anything.

`render_text` is the only way such text becomes HTML. Its rules, in order:

1. Hidden characters are removed and counted: zero-width and joiner characters, bidirectional controls,
   Unicode tag characters, variation selectors, the soft hyphen, the byte-order mark and the braille
   blank. What a reader cannot see must not reach a reader's screen or a model's context unseen.
2. Everything is HTML-escaped. No markup in the input survives as markup.
3. An image is never rendered. Markdown image syntax becomes the words "[image not shown: host]".
   Relay itself emits no <img> element for untrusted text, whatever the host.
4. A link is clickable only if it points into Relay (`link_base`) and carries no query string or
   fragment. Every other address is shown as inert text with its host visible, and is listed in
   `external` so the caller can audit it.

The function reads no clock and no network, and the client must show its output as HTML as it is: running
a Markdown renderer over it again would undo rule 3.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

# Characters that change what a reader sees without being seen (ADR-032; Chapter 13's INS rules list them too).
HIDDEN_RANGES = (
    (0x00AD, 0x00AD),    # soft hyphen
    (0x180E, 0x180E),    # Mongolian vowel separator
    (0x200B, 0x200F),    # zero-width space, joiners, direction marks
    (0x202A, 0x202E),    # bidirectional embeddings and overrides
    (0x2060, 0x2064),    # word joiner and invisible operators
    (0x2066, 0x2069),    # bidirectional isolates
    (0x2800, 0x2800),    # braille pattern blank
    (0xFE00, 0xFE0F),    # variation selectors
    (0xFEFF, 0xFEFF),    # byte-order mark
    (0xE0000, 0xE007F),  # tag characters
    (0xE0100, 0xE01EF),  # variation selectors supplement
)

_IMAGE = re.compile(r"!\[([^\]\n]*)\]\(\s*([^)\s]+)[^)]*\)")
_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*([^)\s]+)[^)]*\)")
_HOST = re.compile(r"\A(?:[a-z][a-z0-9+.-]*://|//)?(?:[^@/?#\s]*@)?(\[[^\]]*\]|[^/?#:\s]+)", re.I)
_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>()\"']+", re.I)


@dataclass(frozen=True)
class Rendered:
    html: str
    hidden_removed: int              # how many hidden characters were removed
    images_removed: tuple[str, ...]  # the host of each image that was not shown
    external: tuple[str, ...]        # every address shown as inert text, in order


def is_hidden(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in HIDDEN_RANGES)


def strip_hidden(text: str) -> tuple[str, int]:
    """The text without hidden characters, and how many were removed."""
    kept = [ch for ch in text if not is_hidden(ch)]
    return "".join(kept), len(text) - len(kept)


def host_of(url: str) -> str:
    """The host an address names, lower case; '?' if it has none Relay can read.

    A small parser of its own: `urllib` is a network package under AR4, and this is a domain module.
    """
    match = _HOST.match(url.strip())
    host = match.group(1).lower().rstrip(".") if match else ""
    return host or "?"


def is_relay_link(url: str, link_base: str) -> bool:
    """True for an address inside Relay: under an https `link_base`, with no query, fragment or user part."""
    base = link_base.rstrip("/") + "/"
    if not base.startswith("https://") or not url.startswith(base):
        return False
    return not any(ch in url for ch in "?#@\\") and host_of(url) == host_of(base)


def render_text(text: str, link_base: str) -> Rendered:
    """Untrusted text as safe HTML for Relay's client (rules in the module docstring)."""
    clean, hidden = strip_hidden(text)
    images: list[str] = []
    external: list[str] = []
    pieces: list[str] = []
    pos = 0
    tokens = sorted([(m.start(), m.end(), "image", m) for m in _IMAGE.finditer(clean)]
                    + [(m.start(), m.end(), "link", m) for m in _LINK.finditer(clean)]
                    + [(m.start(), m.end(), "url", m) for m in _URL.finditer(clean)])
    for start, end, kind, match in tokens:
        if start < pos:  # inside a token already handled (a URL inside a link, a link inside an image)
            continue
        pieces.append(html.escape(clean[pos:start]))
        if kind == "image":
            host = host_of(match.group(2))
            images.append(host)
            pieces.append(html.escape(f"[image not shown: {host}]"))
        else:
            label, url = (match.group(1), match.group(2)) if kind == "link" else (match.group(0), match.group(0))
            if is_relay_link(url, link_base):
                pieces.append(f'<a href="{html.escape(url)}" rel="noopener noreferrer">{html.escape(label)}</a>')
            else:
                external.append(url)
                shown = label if kind == "url" else f"{label} ({host_of(url)})"
                pieces.append(f'<span class="external-address">{html.escape(shown)}</span>')
        pos = end
    pieces.append(html.escape(clean[pos:]))
    return Rendered("".join(pieces), hidden, tuple(images), tuple(external))
