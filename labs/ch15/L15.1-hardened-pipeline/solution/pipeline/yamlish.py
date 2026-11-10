"""A small parser for the YAML that GitHub Actions workflows use (provided).

Standard library only, so the lab needs no dependency. It reads block mappings and lists, list items that open a
mapping (`- uses: …`), flow mappings and lists (`{a: b}`, `[main]`), quoted and plain scalars, booleans,
integers, null, comments, and block scalars (`|`, `|-`, `>`, `>-`). It does not read anchors, aliases, tags,
multi-document files or keys spread over lines. Unlike YAML 1.1 loaders, it keeps the key `on` as the string
"on", which is what a workflow means by it.
"""

from __future__ import annotations

import re

_BLOCK = {"|", "|-", "|+", ">", ">-", ">+"}


class YamlError(ValueError):
    pass


def _strip_comment(s: str) -> str:
    """Remove a trailing ` # comment` that is outside quotes."""
    quote = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _split_top(s: str, sep: str) -> list[str]:
    """Split on `sep` outside quotes, braces and brackets."""
    out, depth, quote, cur = [], 0, None, []
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _key_split(s: str) -> tuple[str, str] | None:
    """('key', 'rest') if `s` starts a mapping entry, else None."""
    quote, depth = None, 0
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif ch == ":" and depth == 0 and (i + 1 == len(s) or s[i + 1] == " "):
            key = s[:i].strip()
            if key.startswith(("{", "[")) or not key:
                return None
            return _unquote(key), s[i + 1:].strip()
    return None


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1].replace("''", "'") if s[0] == "'" else s[1:-1]
    return s


def scalar(s: str):
    s = s.strip()
    if not s:
        return None
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for part in _split_top(s[1:-1], ","):
            if part.strip():
                kv = _key_split(part.strip()) or (part.strip(), "")
                out[kv[0]] = scalar(kv[1])
        return out
    if s.startswith("[") and s.endswith("]"):
        return [scalar(p) for p in _split_top(s[1:-1], ",") if p.strip()]
    if s[0] in "'\"":
        return _unquote(s)
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "~", "Null"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


class _Parser:
    def __init__(self, text: str):
        self.lines = text.replace("\r\n", "\n").split("\n")
        self.i = 0

    def _peek(self):
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() and not raw.lstrip().startswith("#"):
                if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                    raise YamlError(f"line {self.i + 1}: tab in indentation")
                return len(raw) - len(raw.lstrip(" ")), _strip_comment(raw.strip())
            self.i += 1
        return None

    def block(self, indent: int):
        nxt = self._peek()
        if nxt is None or nxt[0] < indent:
            return None
        ind, content = nxt
        if content == "-" or content.startswith("- "):
            return self.seq(ind)
        return self.mapping(ind)

    def _value(self, ind: int, rest: str):
        if rest in _BLOCK:
            return self.block_scalar(ind, rest)
        if rest:
            return scalar(rest)
        nxt = self._peek()
        if nxt is None:
            return None
        if nxt[0] > ind:
            return self.block(nxt[0])
        if nxt[0] == ind and (nxt[1] == "-" or nxt[1].startswith("- ")):
            return self.seq(ind)  # "key:" followed by a list at the same indentation
        return None

    def mapping(self, ind: int) -> dict:
        out: dict = {}
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] != ind or nxt[1] == "-" or nxt[1].startswith("- "):
                if nxt is not None and nxt[0] > ind:
                    raise YamlError(f"line {self.i + 1}: unexpected indentation")
                return out
            kv = _key_split(nxt[1])
            if kv is None:
                raise YamlError(f"line {self.i + 1}: expected 'key: value', got {nxt[1]!r}")
            self.i += 1
            out[kv[0]] = self._value(ind, kv[1])

    def seq(self, ind: int) -> list:
        out = []
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] != ind or not (nxt[1] == "-" or nxt[1].startswith("- ")):
                return out
            rest = nxt[1][1:].strip()
            if not rest:
                self.i += 1
                inner = self._peek()
                out.append(self.block(inner[0]) if inner and inner[0] > ind else None)
            elif _key_split(rest) and not rest.startswith(("{", "[", "'", '"')):
                # "- key: value" opens a mapping whose keys sit two columns in
                raw = self.lines[self.i]
                pos = len(raw) - len(raw.lstrip(" ")) + 1
                pos += len(raw[pos:]) - len(raw[pos:].lstrip(" "))
                self.lines[self.i] = " " * pos + raw[pos:]
                out.append(self.mapping(pos))
            else:
                self.i += 1
                out.append(scalar(rest))

    def block_scalar(self, ind: int, style: str) -> str:
        body = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= ind:
                break
            body.append(raw)
            self.i += 1
        while body and not body[-1].strip():
            body.pop()
        if not body:
            return ""
        cut = min(len(b) - len(b.lstrip(" ")) for b in body if b.strip())
        lines = [b[cut:] for b in body]
        text = "\n".join(lines) if style.startswith("|") else " ".join(ln.strip() for ln in lines if ln.strip())
        return text if style.endswith("-") else text + "\n"


def loads(text: str):
    parser = _Parser(text)
    first = parser._peek()
    if first is None:
        return {}
    doc = parser.block(first[0])
    if parser._peek() is not None:
        raise YamlError(f"line {parser.i + 1}: content after the document ended")
    return doc
