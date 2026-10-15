"""Reference implementation of the invocation contract documented in SKILL.md.

The skills themselves are instructions for a language model; this module is an
executable statement of the same rules so the test suite can pin down edge
cases (option parsing, payload delimiters, length counting, truncation, and the
translate skill's automatic direction).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_LIMIT = 1000
DEFAULT_EFFORT = "medium"
EFFORT_LEVELS = ("low", "medium", "high")
DEFAULT_GLOSS = "auto"
GLOSS_MODES = ("auto", "off", "full")
SKILL_NAMES = ("rewrite", "polish", "translate")

# Options that take a value, and which skills accept them.
VALUED_OPTIONS = {
    "limit": SKILL_NAMES,
    "context": SKILL_NAMES,
    "effort": ("polish",),
    "to": ("translate",),
    "from": ("translate",),
    "gloss": ("translate",),
}
# Options that take no value.
FLAG_OPTIONS = {
    "bilingual": ("translate",),
    "explain": ("rewrite",),
}

LANGUAGE_ALIASES = {
    "auto": "auto",
    "zh": "zh-CN", "zh-cn": "zh-CN", "zh-hans": "zh-CN", "chinese": "zh-CN",
    "中文": "zh-CN", "简体中文": "zh-CN", "汉语": "zh-CN",
    "zh-tw": "zh-TW", "zh-hant": "zh-TW", "繁体中文": "zh-TW", "繁體中文": "zh-TW",
    "zh-hk": "zh-HK",
    "en": "en", "en-us": "en", "english": "en", "英文": "en", "英语": "en",
    "ja": "ja", "japanese": "ja", "日语": "ja", "日文": "ja",
    "ko": "ko", "korean": "ko", "韩语": "ko", "韩文": "ko",
    "fr": "fr", "french": "fr", "法语": "fr",
    "it": "it", "italian": "it", "意大利语": "it",
    "ru": "ru", "russian": "ru", "俄语": "ru",
    "es": "es", "spanish": "es", "西班牙语": "es",
    "de": "de", "german": "de", "德语": "de",
    "pt": "pt", "portuguese": "pt", "葡萄牙语": "pt",
}
GENERIC_LANGUAGE_CODE = re.compile(r"^[a-z]{2}(?:-[a-z]{2,4})?$")

INVOCATION_PATTERN = re.compile(r"^\s*[/$@](rewrite|polish|translate)\b", re.IGNORECASE)
OPTION_NAMES = "|".join(sorted(VALUED_OPTIONS, key=len, reverse=True))
VALUED_OPTION_PATTERN = re.compile(
    rf'^\s*--({OPTION_NAMES})(?:=|\s+)("[^"]*"|“[^”]*”|\S+)',
    re.IGNORECASE,
)
FLAG_OPTION_PATTERN = re.compile(r"^\s*--(bilingual|explain)(?=\s|$)", re.IGNORECASE)
UNKNOWN_OPTION_PATTERN = re.compile(r"^\s*--([A-Za-z][\w-]*)(?=\s|$)")
TERMINATOR_PATTERN = re.compile(r"^\s*--(?=\s|$)")
DELIMITED_BLOCK_PATTERN = re.compile(r'"""(.*?)"""|<<<(.*?)>>>', re.DOTALL)
WHOLE_FENCE_PATTERN = re.compile(r"^```[^\n]*\n(.*?)\n?```$", re.DOTALL)

HAN_PATTERN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
KANA_PATTERN = re.compile(r"[぀-ヿ]")
HANGUL_PATTERN = re.compile(r"[가-힯ᄀ-ᇿ㄰-㆏]")
CJK_PATTERN = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")
# A word in any space-separated script (Latin, Cyrillic, Greek, ...) or a number.
WORD_PATTERN = re.compile(r"[^\W_]+(?:['’.-][^\W_]+)*")
SENTENCE_END_PATTERN = re.compile(r"[。！？!?；;…]+[”\"』」）)]*|\.(?=\s|$)|\n\s*\n")
QUOTE_PAIRS = {'"': '"', "“": "”"}


@dataclass
class Invocation:
    skill: str
    limit: int | None = DEFAULT_LIMIT
    effort: str = DEFAULT_EFFORT
    context: str | None = None
    target: str = "auto"
    source: str = "auto"
    gloss: str = DEFAULT_GLOSS
    bilingual: bool = False
    explain: bool = False
    payloads: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def count_units(text: str) -> int:
    """CJK character = 1 unit, word in a space-separated script or number = 1 unit, rest = 0."""
    cjk_count = len(CJK_PATTERN.findall(text))
    word_count = len(WORD_PATTERN.findall(CJK_PATTERN.sub(" ", text)))
    return cjk_count + word_count


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


def normalize_language(value: str) -> str | None:
    key = value.strip().lower()
    if key in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[key]
    if GENERIC_LANGUAGE_CODE.match(key):
        return key
    return None


def is_entirely_chinese(text: str) -> bool:
    """Approximate the translate skill's "entirely Chinese" test.

    Chinese text may contain conventional English terms (API, React, IL-17),
    which are written as acronyms, capitalized names, or contain digits.
    A lowercase ordinary word ("feature", "release") counts as non-Chinese content.
    """
    if not HAN_PATTERN.search(text) or KANA_PATTERN.search(text) or HANGUL_PATTERN.search(text):
        return False
    for word in WORD_PATTERN.findall(CJK_PATTERN.sub(" ", text)):
        if word[0].islower() and not any(ch.isdigit() for ch in word):
            return False
    return True


def resolve_target(invocation: Invocation, payload: str) -> str:
    """Target language for translate: explicit --to, else Chinese unless the payload is already Chinese."""
    if invocation.target != "auto":
        return invocation.target
    return "en" if is_entirely_chinese(payload) else "zh-CN"


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


def _apply_valued_option(invocation: Invocation, name: str, value: str) -> None:
    if invocation.skill not in VALUED_OPTIONS[name]:
        owner = "/".join(VALUED_OPTIONS[name])
        invocation.warnings.append(f"--{name} applies to {owner} only; ignored")
        return
    if name == "limit":
        if value.lower() == "none":
            invocation.limit = None
        elif value.isdigit() and int(value) > 0:
            invocation.limit = int(value)
        else:
            invocation.warnings.append(f"invalid --limit {value!r}; using {DEFAULT_LIMIT}")
    elif name == "effort":
        if value.lower() in EFFORT_LEVELS:
            invocation.effort = value.lower()
        else:
            invocation.warnings.append(f"invalid --effort {value!r}; using {DEFAULT_EFFORT}")
    elif name == "gloss":
        if value.lower() in GLOSS_MODES:
            invocation.gloss = value.lower()
        else:
            invocation.warnings.append(f"invalid --gloss {value!r}; using {DEFAULT_GLOSS}")
    elif name in ("to", "from"):
        language = normalize_language(value)
        if language is None:
            invocation.warnings.append(f"invalid --{name} {value!r}; using auto")
        elif name == "to":
            invocation.target = language
        else:
            invocation.source = language
    else:
        invocation.context = value


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
        flag = FLAG_OPTION_PATTERN.match(rest)
        if flag:
            name = flag.group(1).lower()
            rest = rest[flag.end():]
            if invocation.skill in FLAG_OPTIONS[name]:
                setattr(invocation, name, True)
            else:
                owner = "/".join(FLAG_OPTIONS[name])
                invocation.warnings.append(f"--{name} applies to {owner} only; ignored")
            continue
        option = VALUED_OPTION_PATTERN.match(rest)
        if option:
            rest = rest[option.end():]
            _apply_valued_option(invocation, option.group(1).lower(), option.group(2).strip('"“”'))
            continue
        unknown = UNKNOWN_OPTION_PATTERN.match(rest)
        if not unknown:
            break
        invocation.warnings.append(f"unknown option --{unknown.group(1)}; ignored")
        rest = rest[unknown.end():]

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
