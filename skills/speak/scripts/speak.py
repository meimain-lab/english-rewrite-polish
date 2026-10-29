#!/usr/bin/env python3
"""Read text from stdin, synthesize it with ElevenLabs TTS, and play it.

Usage:
  echo "Hello there." | speak.py [--rate N | --slow] [--voice NAME] [--model NAME]
                                 [--lang CODE] [--tag LEVEL] [--situation TEXT] [--save]
  speak.py --replay [--rate N | --slow]
  speak.py --stop
  speak.py --list-voices | --list-models | --help

Playback speed is applied locally with afplay, so a sentence is synthesized and
cached once no matter how fast or slow it is played.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1"
SKILL_DIR = Path(__file__).resolve().parent.parent
TAGS_FILE = SKILL_DIR / "audio-tags.md"
HELP_FILE = SKILL_DIR / "HELP.md"
EXAMPLE_CONFIG = SKILL_DIR / "config.example.json"
CONFIG_PATH = Path("~/.config/english-speak/config.json").expanduser()
LEGACY_CONFIG_PATH = Path("~/.config/opencode/speak.json").expanduser()
KEYCHAIN_SERVICE = "elevenlabs-api-key"
# Total text per call; longer text is split into requests within the model's limit.
MAX_CHARS = 10000
# Longest single request. Long requests are slow to generate, so cap below the model limit.
CHUNK_CHARS = 2500
# Per-request character limits, used until /models has been fetched and cached.
MODEL_CHAR_LIMITS = {
    "eleven_v4": 10000,
    "eleven_v4_turbo": 10000,
    "eleven_v3": 5000,
    "eleven_multilingual_v2": 10000,
    "eleven_flash_v2_5": 40000,
}
DEFAULT_MODEL_CHAR_LIMIT = 5000
REQUEST_TIMEOUT_SECONDS = 120
MIN_RATE, MAX_RATE = 0.50, 1.50
DEFAULT_SLOW_RATE = 0.88
TAG_LEVELS = ("none", "low", "medium", "high", "custom", "auto")
LIST_CACHE_SECONDS = 24 * 60 * 60
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRY_DELAY_SECONDS = 2

MODEL_ALIASES = {
    "v4": "eleven_v4",
    "v4-turbo": "eleven_v4_turbo",
    "v3": "eleven_v3",
    "multilingual": "eleven_multilingual_v2",
    "flash": "eleven_flash_v2_5",
}
# Only these models understand audio tags; others read "[sighing]" out loud.
TAG_CAPABLE_MODELS = {"eleven_v3", "eleven_v4", "eleven_v4_turbo"}
# These models reject or ignore language_code.
NO_LANGUAGE_CODE_MODELS = {"eleven_multilingual_v2"}

# Tags each fixed level may use; custom and auto may use every whitelisted tag.
LOW_LEVEL_TAGS = {"softly", "slowly", "pause", "chuckling", "sighing", "clears throat"}
LEVEL_CATEGORIES = {
    "medium": ("Emotion",),
    "high": ("Emotion", "Vocalizations", "Delivery"),
}

# A sentence: text up to and including its closing punctuation, plus closing quotes or brackets.
SENTENCE_PATTERN = re.compile(r"[^.!?\u3002\uff01\uff1f]*[.!?\u3002\uff01\uff1f]+[\"'\u201d\u2019)]*\s*|[^.!?\u3002\uff01\uff1f]+$")
# MPEG-1 Layer III bitrates (kbps) by header index, and sample rates by index.
MP3_BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
MP3_SAMPLE_RATES = (44100, 48000, 32000)
CJK_SENTENCE_ENDS = ("\u3002", "\uff01", "\uff1f")
RATE_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")
# A bracketed item that is not a Markdown link target.
BRACKET_PATTERN = re.compile(r"\[([^\[\]]*)\](?!\()")
# Tag-like content: one to four words of letters.
TAG_LIKE_PATTERN = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+){0,3}$")
TAG_LINE_PATTERN = re.compile(r"^- \[([^\[\]]+)\]\s*$")
CATEGORY_LINE_PATTERN = re.compile(r"^## (.+?)\s*$")
LANG_PATTERN = re.compile(r"^[a-z]{2}$")
VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{20}$")
# Letters beyond Latin Extended-B (U+024F) belong to another script: CJK, Cyrillic, Arabic, ...
LATIN_LIMIT = 0x24F


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def parse_rate(value):
    """Playback rate with at most two decimals, between MIN_RATE and MAX_RATE."""
    if not RATE_PATTERN.match(value):
        raise argparse.ArgumentTypeError(f"语速必须是最多两位小数的数字，比如 0.88（收到：{value}）")
    rate = float(value)
    if not MIN_RATE <= rate <= MAX_RATE:
        raise argparse.ArgumentTypeError(f"语速必须在 {MIN_RATE:.2f} 到 {MAX_RATE:.2f} 之间（收到：{value}）")
    return rate


def parse_lang(value):
    """ISO 639-1 code, or auto (let the model detect the language)."""
    value = value.strip().lower()
    if value == "auto":
        return None
    if not LANG_PATTERN.match(value):
        raise argparse.ArgumentTypeError(f"语言必须是两位 ISO 639-1 代码（比如 en、zh、ja）或 auto（收到：{value}）")
    return value


def normalize_model(value):
    """Full model_id for an alias such as v4-turbo; other values are returned as given."""
    value = value.strip()
    return MODEL_ALIASES.get(value.lower(), value)


def load_tag_categories(path=TAGS_FILE):
    """Whitelisted tags by category, lowercase and without brackets, from audio-tags.md."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        fail(f"找不到标签白名单：{path}")
    categories, current = {}, None
    for line in lines:
        heading = CATEGORY_LINE_PATTERN.match(line)
        if heading:
            current = heading.group(1)
            continue
        tag = TAG_LINE_PATTERN.match(line)
        if tag and current:
            categories.setdefault(current, set()).add(tag.group(1).strip().casefold())
    if not categories:
        fail(f"标签白名单里没有任何标签：{path}")
    return categories


def load_allowed_tags(path=TAGS_FILE):
    """Every whitelisted tag."""
    return set().union(*load_tag_categories(path).values())


def level_tags(level, categories):
    """Tags a level may use, or None when the level is not restricted."""
    if level == "low":
        return set(LOW_LEVEL_TAGS)
    if level in LEVEL_CATEGORIES:
        allowed = set().union(*(categories.get(name, set()) for name in LEVEL_CATEGORIES[level]))
        return allowed | (LOW_LEVEL_TAGS if level == "medium" else set())
    return None


def find_tags(text):
    """Tag-like bracketed items in order of appearance, as written."""
    return [m.group(0) for m in BRACKET_PATTERN.finditer(text) if TAG_LIKE_PATTERN.match(m.group(1).strip())]


def find_unsupported_tags(text, allowed):
    """Tag-like bracketed items that are not in `allowed`, each listed once."""
    bad = []
    for tag in find_tags(text):
        if tag[1:-1].strip().casefold() not in allowed and tag not in bad:
            bad.append(tag)
    return bad


def tag_support_error(model_id, level, text):
    """Error message when tags would be read out loud by a model that does not support them."""
    if (level != "none" or find_tags(text)) and model_id not in TAG_CAPABLE_MODELS:
        capable = "、".join(sorted(TAG_CAPABLE_MODELS))
        return f"模型 {model_id} 不支持音频标签，会把标签直接念出来。请换用 {capable}，或去掉 --tag 和文本里的标签。"
    return None


def non_latin_letters(text):
    """Distinct letters outside the Latin script, in order of appearance."""
    found = []
    for ch in text:
        if ch.isalpha() and ord(ch) > LATIN_LIMIT and ch not in found:
            found.append(ch)
    return found


def normalize_text(raw):
    return " ".join(raw.split())


def split_long_sentence(sentence, limit):
    """Pieces of at most `limit` characters, cut at spaces outside [tags] where possible."""
    pieces = []
    while len(sentence) > limit:
        depth, cut = 0, -1
        for i, ch in enumerate(sentence[:limit + 1]):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth = max(depth - 1, 0)
            elif ch == " " and depth == 0 and i > 0:
                cut = i
        if cut <= 0:
            cut = limit
        pieces.append(sentence[:cut].strip())
        sentence = sentence[cut:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces


def split_text(text, limit):
    """Chunks of at most `limit` characters, packed from whole sentences."""
    if len(text) <= limit:
        return [text]
    sentences = []
    for match in SENTENCE_PATTERN.finditer(text):
        sentence = match.group(0).strip()
        if sentence:
            sentences.extend(split_long_sentence(sentence, limit))
    chunks, current = [], ""
    for sentence in sentences:
        # CJK sentences follow each other without a space.
        separator = "" if current.endswith(CJK_SENTENCE_ENDS) else " "
        joined = f"{current}{separator}{sentence}" if current else sentence
        if len(joined) <= limit:
            current = joined
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def strip_id3(data):
    """MP3 bytes without a leading ID3v2 tag, so parts can be joined into one stream."""
    if data[:3] != b"ID3" or len(data) < 10:
        return data
    size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
    return data[10 + size:]


def strip_info_frame(data):
    """MP3 frames without a leading Xing/Info frame, whose frame count only describes one part."""
    if len(data) < 4 or data[0] != 0xFF or data[1] & 0xFE != 0xFA:
        return data  # Not MPEG-1 Layer III; leave it alone.
    bitrate_index, rate_index, padding = data[2] >> 4, (data[2] >> 2) & 3, (data[2] >> 1) & 1
    if not 0 < bitrate_index < 15 or rate_index == 3:
        return data
    length = 144 * MP3_BITRATES[bitrate_index] * 1000 // MP3_SAMPLE_RATES[rate_index] + padding
    if b"Xing" in data[4:40] or b"Info" in data[4:40]:
        return data[length:]
    return data


def join_mp3(parts):
    """One MP3 stream from parts with the same format.

    Only the first ID3 tag is kept. Every Xing/Info frame is dropped: each one counts the frames
    of its own part, so players would report, or stop at, the length of the first part.
    """
    if len(parts) == 1:
        return parts[0]
    first = parts[0]
    header = first[:len(first) - len(strip_id3(first))]
    return header + b"".join(strip_info_frame(strip_id3(part)) for part in parts)


def looks_like_mp3(data):
    """True for an ID3 header or an MPEG audio frame sync at the start."""
    if len(data) < 128:
        return False
    return data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)


def cache_digest(text, voice_id, model_id, settings, language=None):
    parts = [text, voice_id, model_id, settings]
    if language:
        parts.append(language)
    material = json.dumps(parts, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def match_voices(voices, query):
    """Voices whose full name, or short name before " - ", equals query (case-insensitive)."""
    key = query.strip().casefold()
    exact = [v for v in voices if v["name"].casefold() == key]
    if exact:
        return exact
    return [v for v in voices if v["name"].split(" - ", 1)[0].strip().casefold() == key]


def unique_path(path):
    """path, or path with -2, -3, ... before the suffix when it already exists."""
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"文件不是合法的 JSON：{path}（{e}）")


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config():
    """Load the config, creating it on first run (migrating the old OpenCode config if present)."""
    if CONFIG_PATH.exists():
        config = read_json(CONFIG_PATH)
    elif LEGACY_CONFIG_PATH.exists():
        config = read_json(LEGACY_CONFIG_PATH)
        # Keep existing clips where they already are.
        config.setdefault("save_dir", "~/Music/opencode-speak")
        config.setdefault("cache_dir", "~/.cache/opencode-speak")
        write_json(CONFIG_PATH, config)
        print(f"已把旧配置迁移到 {CONFIG_PATH}", file=sys.stderr)
    else:
        config = read_json(EXAMPLE_CONFIG)
        write_json(CONFIG_PATH, config)
        print(f"已创建默认配置 {CONFIG_PATH}，可以在里面修改声音和模型。", file=sys.stderr)
    for key, value in read_json(EXAMPLE_CONFIG).items():
        config.setdefault(key, value)
    # v4 models ignore speed and style; playback speed is handled locally.
    for key in ("speed", "style"):
        config.get("voice_settings", {}).pop(key, None)
    # Tagging is done by the model, which never read this setting.
    config.pop("default_tag", None)
    return config


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        fail(
            "没有找到 ElevenLabs API key。请先在终端运行：\n"
            f'security add-generic-password -a "$USER" -s {KEYCHAIN_SERVICE} -w'
        )
    return result.stdout.strip()


def ssl_context():
    """Default context, falling back to macOS system roots when Python ships without CA certs."""
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] == 0:
        pem = subprocess.run(
            ["security", "find-certificate", "-a", "-p",
             "/System/Library/Keychains/SystemRootCertificates.keychain"],
            capture_output=True, text=True,
        ).stdout
        if pem:
            context.load_verify_locations(cadata=pem)
    return context


def request(method, path, body=None):
    """Response body of an API call, retrying once on rate limits and server errors."""
    data = json.dumps(body).encode() if body is not None else None
    for attempt in (1, 2):
        req = urllib.request.Request(f"{API}{path}", data=data, method=method)
        req.add_header("xi-api-key", api_key())
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS, context=ssl_context()) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if attempt == 1 and e.code in RETRY_STATUS:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            fail(describe_http_error(e))
        except urllib.error.URLError as e:
            fail(f"网络错误，无法连接 ElevenLabs：{e.reason}")


def describe_http_error(error):
    raw = error.read().decode("utf-8", "replace")
    status, message = "", raw
    try:
        detail = json.loads(raw).get("detail", raw)
        if isinstance(detail, dict):
            status = detail.get("status", "")
            message = detail.get("message", raw)
        else:
            message = str(detail)
    except (json.JSONDecodeError, AttributeError):
        pass
    if error.code == 401 and status != "quota_exceeded":
        return f"API key 无效或权限不足（401）：{message}"
    if status == "quota_exceeded":
        return f"ElevenLabs credits 不足：{message}"
    if error.code == 404 or status in ("voice_not_found", "model_not_found"):
        return f"voice 或 model 不存在（{error.code}）：{message}"
    if error.code == 429:
        return f"请求太频繁，重试后仍失败（429）：{message}"
    return f"ElevenLabs 返回错误 {error.code} {status}：{message}"


def cached_list(cache_dir, name, fetch, refresh=False):
    """A list from the API, cached in cache_dir for LIST_CACHE_SECONDS."""
    path = cache_dir / f"{name}.json"
    if not refresh and path.exists():
        cached = read_json(path)
        if time.time() - cached.get("fetched", 0) < LIST_CACHE_SECONDS:
            return cached["items"]
    items = fetch()
    write_json(path, {"fetched": time.time(), "items": items})
    return items


def fetch_voices():
    voices = json.loads(request("GET", "/voices")).get("voices", [])
    return [{"voice_id": v["voice_id"], "name": v["name"], "category": v.get("category", "")} for v in voices]


def fetch_models():
    return [
        {"model_id": m["model_id"], "name": m.get("name", ""),
         "max_chars": m.get("maximum_text_length_per_request")}
        for m in json.loads(request("GET", "/models")) if m.get("can_do_text_to_speech")
    ]


def model_char_limit(model_id, cache_dir):
    """Characters one request may carry: from the cached model list, else the built-in table."""
    path = cache_dir / "models.json"
    if path.exists():
        for m in read_json(path).get("items", []):
            if m.get("model_id") == model_id and m.get("max_chars"):
                return int(m["max_chars"])
    return MODEL_CHAR_LIMITS.get(model_id, DEFAULT_MODEL_CHAR_LIMIT)


def synthesize(chunks, voice_id, model_id, settings, language):
    """One MP3 for all chunks. Neighboring text is sent along so the parts sound continuous."""
    parts = []
    for i, chunk in enumerate(chunks):
        body = {"text": chunk, "model_id": model_id, "voice_settings": settings}
        if language:
            body["language_code"] = language
        if len(chunks) > 1:
            print(f"正在生成第 {i + 1}/{len(chunks)} 段……", file=sys.stderr)
            if i > 0:
                body["previous_text"] = chunks[i - 1]
            if i < len(chunks) - 1:
                body["next_text"] = chunks[i + 1]
        audio = request("POST", f"/text-to-speech/{voice_id}?output_format=mp3_44100_128", body)
        if not looks_like_mp3(audio):
            fail(f"ElevenLabs 返回的不是音频（{len(audio)} 字节），没有缓存。请稍后重试。")
        parts.append(audio)
    return join_mp3(parts)


def find_voice(query, cache_dir):
    """(voice_id, name) for a voice name, short name, or voice_id."""
    for refresh in (False, True):
        voices = cached_list(cache_dir, "voices", fetch_voices, refresh)
        by_id = [v for v in voices if v["voice_id"] == query.strip()]
        matches = by_id or match_voices(voices, query)
        if len(matches) == 1:
            return matches[0]["voice_id"], matches[0]["name"]
        if len(matches) > 1:
            names = "；".join(v["name"] for v in matches)
            fail(f"有多个声音匹配 {query}：{names}。请写完整名字。")
    if VOICE_ID_PATTERN.match(query.strip()):
        return query.strip(), query.strip()
    fail(f"在你的 ElevenLabs 账户里找不到声音 {query}。运行 speak.py --list-voices 查看。")


def check_model(model_id, cache_dir):
    """Fail unless model_id is a text-to-speech model in the account."""
    for refresh in (False, True):
        models = cached_list(cache_dir, "models", fetch_models, refresh)
        if any(m["model_id"] == model_id for m in models):
            return
    names = "、".join(m["model_id"] for m in models)
    aliases = "、".join(MODEL_ALIASES)
    fail(f"找不到模型 {model_id}。可用模型：{names}。也可以用简写：{aliases}。")


def default_voice(config, cache_dir):
    """The configured voice, re-resolved whenever voice_name changed since voice_id was stored."""
    name = config.get("voice_name")
    if config.get("voice_id") and (not name or config.get("voice_id_name") == name):
        return config["voice_id"], name or config["voice_id"]
    if not name:
        fail(f"配置里没有 voice_name。请在 {CONFIG_PATH} 里设置。")
    voice_id, full_name = find_voice(name, cache_dir)
    config["voice_id"], config["voice_id_name"] = voice_id, name
    write_json(CONFIG_PATH, config)
    return voice_id, full_name


def stop_playback(pid_file):
    """Stop the afplay process this script started last. True if one was stopped."""
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return False
    command = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True).stdout.strip()
    stopped = False
    if command.endswith("afplay"):
        try:
            os.kill(pid, signal.SIGTERM)
            stopped = True
        except ProcessLookupError:
            pass
    pid_file.unlink(missing_ok=True)
    return stopped


def play(path, rate, pid_file):
    """Play in the background at `rate`, replacing any clip this script is playing."""
    stop_playback(pid_file)
    try:
        process = subprocess.Popen(
            ["afplay", "-r", f"{rate:g}", "-q", "1", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except FileNotFoundError:
        fail("找不到 afplay。speak 需要在 macOS 上运行。")
    pid_file.write_text(str(process.pid))


def clean_field(value):
    return normalize_text(value or "")


def archive(path, text, tag, save_dir, voice_name="", model_id="", situation=""):
    """Copy a clip to save_dir under a readable name and log it in index.tsv."""
    save_dir.mkdir(parents=True, exist_ok=True)
    slug = "-".join(re.sub(r"\[[^\]]*\]", " ", text).lower().split()[:6])
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:50] or "speech"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    saved = unique_path(save_dir / f"{stamp}-{slug}.mp3")
    shutil.copyfile(path, saved)
    fields = [stamp, saved.name, tag, text, clean_field(voice_name), clean_field(model_id), clean_field(situation)]
    with open(save_dir / "index.tsv", "a", encoding="utf-8") as f:
        f.write("\t".join(fields) + "\n")
    return saved


def build_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    rate = parser.add_mutually_exclusive_group()
    rate.add_argument("--rate", "--speed", dest="rate", type=parse_rate)
    rate.add_argument("--slow", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--voice")
    parser.add_argument("--model", type=normalize_model)
    parser.add_argument("--lang", type=parse_lang, default=None)
    parser.add_argument("--tag", choices=TAG_LEVELS, default="none")
    parser.add_argument("--situation", default="")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--list-models", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()

    if args.help:
        print(HELP_FILE.read_text(encoding="utf-8"))
        return

    config = load_config()
    cache_dir = Path(config["cache_dir"]).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    pid_file = cache_dir / "player.pid"
    last_file = cache_dir / "last"

    if args.stop:
        print("已停止播放。" if stop_playback(pid_file) else "现在没有正在播放的音频。")
        return
    if args.list_voices:
        for v in cached_list(cache_dir, "voices", fetch_voices, refresh=True):
            print(f"{v['voice_id']}\t{v['category']}\t{v['name']}")
        return
    if args.list_models:
        for m in cached_list(cache_dir, "models", fetch_models, refresh=True):
            print(f"{m['model_id']}\t{m['name']}")
        return

    rate = args.rate if args.rate is not None else (config["slow_rate"] if args.slow else 1.0)
    if not MIN_RATE <= rate <= MAX_RATE:
        fail(f"配置里的 slow_rate 必须在 {MIN_RATE:.2f} 到 {MAX_RATE:.2f} 之间。")

    if args.replay:
        if not last_file.exists() or not Path(last_file.read_text().strip()).is_file():
            fail("没有可以重放的上一条音频。")
        path = Path(last_file.read_text().strip())
        play(path, rate, pid_file)
        print(f"正在重放（{rate:g}×）：{path}")
        return

    text = normalize_text(sys.stdin.read())
    if not text:
        fail("没有要朗读的文本（请通过 stdin 传入）。")
    if len(text) > MAX_CHARS:
        fail(f"文本有 {len(text)} 个字符，超过单次上限 {MAX_CHARS}。请先读前一部分，再读剩下的。")

    categories = load_tag_categories()
    unsupported = find_unsupported_tags(text, set().union(*categories.values()))
    if unsupported:
        fail(f"不支持的标签：{' '.join(unsupported)}。只能使用 {TAGS_FILE.name} 里列出的标签。")
    allowed_for_level = level_tags(args.tag, categories)
    if allowed_for_level is not None:
        off_level = find_unsupported_tags(text, allowed_for_level)
        if off_level:
            fail(f"--tag {args.tag} 不能用这些标签：{' '.join(off_level)}。换用 high、custom 或 auto 档。")

    if args.lang == "en":
        foreign = non_latin_letters(text)
        if foreign:
            fail(f"--lang en 只读英文，但文本里有非英文字符：{''.join(foreign[:10])}。请去掉这些部分，或不要加 --lang en。")

    model_id = args.model or config["model_id"]
    if args.model:
        check_model(model_id, cache_dir)
    tag_error = tag_support_error(model_id, args.tag, text)
    if tag_error:
        fail(tag_error)

    voice_id, voice_name = find_voice(args.voice, cache_dir) if args.voice else default_voice(config, cache_dir)
    settings = dict(config.get("voice_settings", {}))
    language = args.lang if model_id not in NO_LANGUAGE_CODE_MODELS else None

    path = cache_dir / f"{cache_digest(text, voice_id, model_id, settings, language)}.mp3"
    source = "缓存"
    chunk_count = 1
    if not path.exists():
        chunks = split_text(text, min(CHUNK_CHARS, model_char_limit(model_id, cache_dir)))
        chunk_count = len(chunks)
        audio = synthesize(chunks, voice_id, model_id, settings, language)
        tmp = path.with_suffix(".mp3.part")
        tmp.write_bytes(audio)
        os.replace(tmp, path)
        source = "新生成"

    # New clips are archived by default; cached replays are only copied again with --save.
    if args.save or (source == "新生成" and config["save_audio"]):
        saved = archive(path, text, args.tag, Path(config["save_dir"]).expanduser(),
                        voice_name, model_id, args.situation)
        print(f"已保存：{saved}")

    last_file.write_text(str(path))
    play(path, rate, pid_file)
    parts = f"，分 {chunk_count} 段生成后合成一个文件" if chunk_count > 1 else ""
    print(f"正在播放（{len(text)} 字符{parts}，{source}，{rate:g}×，{voice_name} / {model_id}）：{path}")


if __name__ == "__main__":
    main()
