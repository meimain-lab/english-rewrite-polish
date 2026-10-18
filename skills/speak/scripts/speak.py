#!/usr/bin/env python3
"""Read English text from stdin, synthesize it with ElevenLabs TTS, and play it.

Usage:
  echo "Hello there." | speak.py [--rate N | --slow] [--save] [--voice ID] [--lang CODE] [--tag LEVEL]
  speak.py --replay [--rate N | --slow]
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
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1"
SKILL_DIR = Path(__file__).resolve().parent.parent
PLAYER = SKILL_DIR / "scripts" / "play-audio.sh"
TAGS_FILE = SKILL_DIR / "audio-tags.md"
HELP_FILE = SKILL_DIR / "HELP.md"
EXAMPLE_CONFIG = SKILL_DIR / "config.example.json"
CONFIG_PATH = Path("~/.config/english-speak/config.json").expanduser()
LEGACY_CONFIG_PATH = Path("~/.config/opencode/speak.json").expanduser()
KEYCHAIN_SERVICE = "elevenlabs-api-key"
MAX_CHARS = 1000
MIN_RATE, MAX_RATE = 0.50, 1.50
DEFAULT_SLOW_RATE = 0.88
TAG_LEVELS = ("none", "low", "medium", "high", "custom")
RATE_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")
BRACKET_PATTERN = re.compile(r"\[([^\[\]]*)\]")
TAG_LINE_PATTERN = re.compile(r"^- \[([^\[\]]+)\]\s*$")
LANG_PATTERN = re.compile(r"^[a-z]{2}$")
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


def load_allowed_tags(path=TAGS_FILE):
    """Whitelisted audio tags (lowercase, without brackets) from audio-tags.md."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        fail(f"找不到标签白名单：{path}")
    tags = {m.group(1).strip().casefold() for m in map(TAG_LINE_PATTERN.match, lines) if m}
    if not tags:
        fail(f"标签白名单里没有任何标签：{path}")
    return tags


def find_unsupported_tags(text, allowed):
    """Bracketed items in text that are not in the whitelist, in order of appearance."""
    bad = []
    for match in BRACKET_PATTERN.finditer(text):
        if match.group(1).strip().casefold() not in allowed and match.group(0) not in bad:
            bad.append(match.group(0))
    return bad


def parse_lang(value):
    """ISO 639-1 code, or auto (let the model detect the language)."""
    value = value.strip().lower()
    if value == "auto":
        return None
    if not LANG_PATTERN.match(value):
        raise argparse.ArgumentTypeError(f"语言必须是两位 ISO 639-1 代码（比如 en、zh、ja）或 auto（收到：{value}）")
    return value


def non_latin_letters(text):
    """Distinct letters outside the Latin script, in order of appearance."""
    found = []
    for ch in text:
        if ch.isalpha() and ord(ch) > LATIN_LIMIT and ch not in found:
            found.append(ch)
    return found


def normalize_text(raw):
    return " ".join(raw.split())


def cache_digest(text, voice_id, model_id, settings, language=None):
    parts = [text, voice_id, model_id, settings]
    if language:
        parts.append(language)
    material = json.dumps(parts, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"配置文件不是合法的 JSON：{path}（{e}）")


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
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("xi-api-key", api_key())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
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
    return f"ElevenLabs 返回错误 {error.code} {status}：{message}"


def list_voices():
    voices = json.loads(request("GET", "/voices")).get("voices", [])
    for v in voices:
        print(f"{v['voice_id']}\t{v.get('category', '')}\t{v['name']}")


def list_models():
    for m in json.loads(request("GET", "/models")):
        if m.get("can_do_text_to_speech"):
            print(f"{m['model_id']}\t{m.get('name', '')}")


def resolve_voice_id(config):
    """Return voice_id, looking it up by voice_name once and caching it in the config."""
    if config.get("voice_id"):
        return config["voice_id"]
    name = config.get("voice_name")
    if not name:
        fail("配置里没有 voice_id 或 voice_name。")
    voices = json.loads(request("GET", "/voices")).get("voices", [])
    matches = [v for v in voices if v["name"] == name]
    if not matches:
        fail(f"在你的 ElevenLabs 账户里找不到名为 {name} 的声音。运行 speak.py --list-voices 查看，再改 {CONFIG_PATH}。")
    config["voice_id"] = matches[0]["voice_id"]
    write_json(CONFIG_PATH, config)
    return config["voice_id"]


def archive(path, text, tag, save_dir):
    """Copy a clip to save_dir under a readable name and log it in index.tsv."""
    save_dir.mkdir(parents=True, exist_ok=True)
    slug = "-".join(re.sub(r"\[[^\]]*\]", " ", text).lower().split()[:6])
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:50] or "speech"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    saved = save_dir / f"{stamp}-{slug}.mp3"
    shutil.copyfile(path, saved)
    with open(save_dir / "index.tsv", "a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{saved.name}\t{tag}\t{text}\n")
    return saved


def play(path, rate):
    result = subprocess.run([str(PLAYER), str(path), f"{rate:g}"], capture_output=True, text=True)
    if result.returncode != 0:
        fail(result.stderr.strip() or "播放失败。")


def build_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    rate = parser.add_mutually_exclusive_group()
    rate.add_argument("--rate", "--speed", dest="rate", type=parse_rate)
    rate.add_argument("--slow", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--voice")
    parser.add_argument("--lang", type=parse_lang, default=None)
    parser.add_argument("--tag", choices=TAG_LEVELS, default="none")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--list-models", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()

    if args.help:
        print(HELP_FILE.read_text(encoding="utf-8"))
        return
    if args.list_voices:
        return list_voices()
    if args.list_models:
        return list_models()

    config = load_config()
    cache_dir = Path(config["cache_dir"]).expanduser()
    last_file = cache_dir / "last"
    rate = args.rate if args.rate is not None else (config["slow_rate"] if args.slow else 1.0)
    if not MIN_RATE <= rate <= MAX_RATE:
        fail(f"配置里的 slow_rate 必须在 {MIN_RATE:.2f} 到 {MAX_RATE:.2f} 之间。")

    if args.replay:
        if not last_file.exists() or not Path(last_file.read_text().strip()).is_file():
            fail("没有可以重放的上一条音频。")
        path = Path(last_file.read_text().strip())
        play(path, rate)
        print(f"正在重放（{rate:g}×）：{path}")
        return

    text = normalize_text(sys.stdin.read())
    if not text:
        fail("没有要朗读的文本（请通过 stdin 传入）。")
    if len(text) > MAX_CHARS:
        fail(f"文本有 {len(text)} 个字符，超过上限 {MAX_CHARS}。请分段朗读。")
    unsupported = find_unsupported_tags(text, load_allowed_tags())
    if unsupported:
        fail(f"不支持的标签：{' '.join(unsupported)}。只能使用 {TAGS_FILE.name} 里列出的标签。")

    if args.lang == "en":
        foreign = non_latin_letters(text)
        if foreign:
            fail(f"--lang en 只读英文，但文本里有非英文字符：{''.join(foreign[:10])}。请去掉这些部分，或不要加 --lang en。")

    voice_id = args.voice or resolve_voice_id(config)
    model_id = config["model_id"]
    settings = dict(config.get("voice_settings", {}))

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{cache_digest(text, voice_id, model_id, settings, args.lang)}.mp3"

    source = "缓存"
    if not path.exists():
        body = {"text": text, "model_id": model_id, "voice_settings": settings}
        if args.lang:
            body["language_code"] = args.lang
        audio = request("POST", f"/text-to-speech/{voice_id}?output_format=mp3_44100_128", body)
        tmp = path.with_suffix(".mp3.part")
        tmp.write_bytes(audio)
        os.replace(tmp, path)
        source = "新生成"

    # New clips are archived by default; cached replays are only copied again with --save.
    if args.save or (source == "新生成" and config["save_audio"]):
        saved = archive(path, text, args.tag, Path(config["save_dir"]).expanduser())
        print(f"已保存：{saved}")

    last_file.write_text(str(path))
    play(path, rate)
    print(f"正在播放（{len(text)} 字符，{source}，{rate:g}×）：{path}")


if __name__ == "__main__":
    main()
