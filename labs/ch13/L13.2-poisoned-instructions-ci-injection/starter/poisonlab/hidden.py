"""Characters a reviewer cannot see but a model reads (TODO 1 in starter/)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}
BIDI = {0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}
VS_BMP = range(0xFE00, 0xFE10)        # variation selectors 1-16
VS_SUPPLEMENT = range(0xE0100, 0xE01F0)  # variation selectors 17-256
BLANK = {0x2800, 0x115F, 0x1160, 0x3164, 0xFFA0}  # braille pattern blank and Hangul fillers: letters that render empty


@dataclass(frozen=True)
class Hidden:
    line: int        # 1-based
    col: int         # 1-based, in characters
    codepoint: str   # "U+E0041"
    kind: str        # tag, zero-width, bidi, variation-selector, blank or format


def find_hidden(text: str) -> list[Hidden]:
    """Every invisible or reordering character in `text`, in order.

    kind is "tag" for U+E0000-U+E007F; "zero-width" for ZERO_WIDTH; "bidi" for BIDI; "variation-selector"
    for VS_SUPPLEMENT always, and for VS_BMP unless it is a single selector directly after a character of
    category So (an emoji's own style choice, such as U+FE0F); and "format" for any other character of
    category Cf. Variation selectors are category Mn, so a check that looks only at Cf misses them, and a run
    of them can carry one byte each. One more exception: a zero-width joiner (U+200D) between two characters
    of category So (emoji sequences such as a person and a laptop) is not reported. "blank" is for BLANK:
    characters that are not format characters but render as empty space.
    """
    raise NotImplementedError("TODO 1: find invisible and reordering characters")


def vs_byte(ch: str) -> int | None:
    """The byte a variation selector encodes (provided): U+FE00-FE0F are 0-15, U+E0100-E01EF are 16-255."""
    cp = ord(ch)
    if cp in VS_BMP:
        return cp - 0xFE00
    if cp in VS_SUPPLEMENT:
        return cp - 0xE0100 + 16
    return None


def reveal_tags(text: str) -> str:
    """Decode text smuggled as tag characters or as a run of variation selectors, shown in [[...]] (provided)."""
    out, run, vs = [], [], []

    def flush():
        if run:
            out.append("[[" + "".join(run) + "]]")
            run.clear()
        if len(vs) > 1:
            out.append("[[" + bytes(vs).decode("utf-8", "replace") + "]]")
        vs.clear()

    for ch in text + "\0":
        cp = ord(ch)
        if 0xE0020 <= cp <= 0xE007E:
            run.append(chr(cp - 0xE0000))
            continue
        b = vs_byte(ch)
        if b is not None:
            vs.append(b)
            continue
        flush()
        if ch != "\0":
            out.append(ch)
    return "".join(out)


def rendered(text: str) -> str:
    """Roughly what a reviewer sees in a rendered Markdown view: no format characters, no variation selectors,
    no HTML comments (provided)."""
    no_comments = re.sub(r"<!--.*?-->\n?", "", text, flags=re.S)
    return "".join(ch for ch in no_comments if unicodedata.category(ch) != "Cf" and vs_byte(ch) is None)
