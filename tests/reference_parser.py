"""Reference implementation of the invocation contract documented in SKILL.md.

The skills themselves are instructions for a language model; this module is an
executable statement of the same rules so the test suite can pin down edge
cases (option parsing, payload delimiters, length counting, truncation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_LIMIT = 1000
DEFAULT_EFFORT = "medium"
EFFORT_LEVELS = ("low", "medium", "high")

INVOCATION_PATTERN = re.compile(r"^\s*[/$@](rewrite|polish)\b", re.IGNORECASE)
OPTION_PATTERN = re.compile(
    r'^\s*--(limit|effort|context)(?:=|\s+)("[^"]*"|“[^”]*”|\S+)',
    re.IGNORECASE,
)
UNKNOWN_OPTION_PATTERN = re.compile(r"^\s*--([A-Za-z][\w-]*)(?=\s|$)")
TERMINATOR_PATTERN = re.compile(r"^\s*--(?=\s|$)")
DELIMITED_BLOCK_PATTERN = re.compile(r'"""(.*?)"""|<<<(.*?)>>>', re.DOTALL)
WHOLE_FENCE_PATTERN = re.compile(r"^```[^\n]*\n(.*?)\n?```$", re.DOTALL)
CJK_PATTERN = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")
LATIN_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*")
SENTENCE_END_PATTERN = re.compile(r"[。！？!?；;…]+[”\"』」）)]*|\.(?=\s|$)|\n\s*\n")
QUOTE_PAIRS = {'"': '"', "“": "”"}


@dataclass
class Invocation:
    skill: str
    limit: int | None = DEFAULT_LIMIT
    effort: str = DEFAULT_EFFORT
    context: str | None = None
    payloads: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def count_units(text: str) -> int:
    """CJK character = 1 unit, Latin word or number = 1 unit, rest = 0."""
    cjk_count = len(CJK_PATTERN.findall(text))
    latin_count = len(LATIN_WORD_PATTERN.findall(CJK_PATTERN.sub(" ", text)))
    return cjk_count + latin_count


def truncate_to_limit(text: str, limit: int | None) -> tuple[str, bool]:
    """Return the longest prefix ending at a sentence boundary within the limit."""
    if limit is None or count_units(text) <= limit:
        return text, False
    best_end = 0
    for match in SENTENCE_END_PATTERN.finditer(text):
        if count_units(text[: match.end()]) > limit:
            break
        best_end = match.end()
    return text[:best_end].rstrip(), True


def _strip_whole_quotes(payload: str) -> str:
    stripped = payload.strip()
    if len(stripped) < 2:
        return payload
    opening = stripped[0]
    closing = QUOTE_PAIRS.get(opening)
    if closing is None or stripped[-1] != closing:
        return payload
    inner = stripped[1:-1]
    if opening in inner or closing in inner:
        return payload
    return inner


def parse(raw: str) -> Invocation:
    match = INVOCATION_PATTERN.match(raw)
    if not match:
        raise ValueError("input does not start with an invocation token")
    invocation = Invocation(skill=match.group(1).lower())
    rest = raw[match.end():]

    while True:
        terminator = TERMINATOR_PATTERN.match(rest)
        if terminator:
            rest = rest[terminator.end():]
            break
        option = OPTION_PATTERN.match(rest)
        if not option:
            unknown = UNKNOWN_OPTION_PATTERN.match(rest)
            if not unknown:
                break
            invocation.warnings.append(f"unknown option --{unknown.group(1)}; ignored")
            rest = rest[unknown.end():]
            continue
        name = option.group(1).lower()
        value = option.group(2).strip('"“”')
        rest = rest[option.end():]
        if name == "limit":
            if value.lower() == "none":
                invocation.limit = None
            elif value.isdigit() and int(value) > 0:
                invocation.limit = int(value)
            else:
                invocation.warnings.append(f"invalid --limit {value!r}; using {DEFAULT_LIMIT}")
        elif name == "effort":
            if invocation.skill != "polish":
                invocation.warnings.append("--effort applies to polish only; ignored")
            elif value.lower() in EFFORT_LEVELS:
                invocation.effort = value.lower()
            else:
                invocation.warnings.append(f"invalid --effort {value!r}; using {DEFAULT_EFFORT}")
        else:
            invocation.context = value

    rest = rest.strip("\n ")
    whole_fence = WHOLE_FENCE_PATTERN.match(rest)
    if whole_fence:
        invocation.payloads = [whole_fence.group(1)]
        return invocation
    blocks = list(DELIMITED_BLOCK_PATTERN.finditer(rest))
    if blocks:
        invocation.payloads = [next(g for g in block.groups() if g is not None).strip("\n") for block in blocks]
        outside = DELIMITED_BLOCK_PATTERN.sub(" ", rest).strip()
        if outside:
            invocation.context = " ".join(filter(None, [invocation.context, outside]))
    elif rest:
        invocation.payloads = [_strip_whole_quotes(rest)]
    return invocation
