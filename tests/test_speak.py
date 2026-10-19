import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEAK_DIR = ROOT / "skills" / "speak"
SCRIPT = SPEAK_DIR / "scripts" / "speak.py"

_spec = importlib.util.spec_from_file_location("speak_script", SCRIPT)
speak = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(speak)

ALLOWED = speak.load_allowed_tags()
TAG_TOKEN = re.compile(r"\[([a-z][a-z ]*)\]")
# Bracketed words in the docs that are usage placeholders, not audio tags.
PLACEHOLDERS = {"options", "text", "xxx", "sic"}


def option_names(markdown: str) -> set[str]:
    """Option names such as --slow found in the first column of an options table."""
    names: set[str] = set()
    for line in markdown.splitlines():
        if line.startswith("| `--"):
            first_cell = line.split("|")[1]
            names.update(re.findall(r"`--([a-z]+)", first_cell))
    return names


class ParseRateTests(unittest.TestCase):
    def test_valid_rates(self) -> None:
        for raw, expected in (("0.88", 0.88), ("1", 1.0), ("0.5", 0.5), ("1.50", 1.5), ("0.75", 0.75)):
            with self.subTest(raw=raw):
                self.assertEqual(speak.parse_rate(raw), expected)

    def test_invalid_rates(self) -> None:
        for raw in ("0.885", "abc", "0.49", "1.51", "-1", ".5", "1.", "2", ""):
            with self.subTest(raw=raw):
                with self.assertRaises(argparse.ArgumentTypeError):
                    speak.parse_rate(raw)


class ParseLangTests(unittest.TestCase):
    def test_codes_and_auto(self) -> None:
        self.assertEqual(speak.parse_lang("en"), "en")
        self.assertEqual(speak.parse_lang("ZH"), "zh")
        self.assertIsNone(speak.parse_lang("auto"))

    def test_invalid_codes(self) -> None:
        for raw in ("eng", "e", "zh-CN", "12", ""):
            with self.subTest(raw=raw):
                with self.assertRaises(argparse.ArgumentTypeError):
                    speak.parse_lang(raw)

    def test_non_latin_letters(self) -> None:
        self.assertEqual(speak.non_latin_letters("Hello, café! [softly] 100%"), [])
        self.assertEqual(speak.non_latin_letters("Hello 你好 你"), ["你", "好"])
        self.assertEqual(speak.non_latin_letters("Привет"), ["П", "р", "и", "в", "е", "т"])


class TagWhitelistTests(unittest.TestCase):
    def test_whitelist_has_the_forty_tags(self) -> None:
        self.assertEqual(len(ALLOWED), 40)
        for tag in ("excited", "clears throat", "whispering", "witch voice", "engine starting"):
            self.assertIn(tag, ALLOWED)

    def test_supported_tags_pass(self) -> None:
        self.assertEqual(speak.find_unsupported_tags("[tired] I can't. [Sighing] Not again. [pause]", ALLOWED), [])
        self.assertEqual(speak.find_unsupported_tags("No tags here.", ALLOWED), [])

    def test_invented_tags_are_reported_once_in_order(self) -> None:
        text = "[happy] Hi [excited] there [happy] [very sad]"
        self.assertEqual(speak.find_unsupported_tags(text, ALLOWED), ["[happy]", "[very sad]"])

    def test_every_tag_in_docs_is_whitelisted(self) -> None:
        for name in ("HELP.md", "SKILL.md"):
            text = (SPEAK_DIR / name).read_text(encoding="utf-8")
            used = set(TAG_TOKEN.findall(text)) - PLACEHOLDERS
            with self.subTest(file=name):
                self.assertEqual(used - ALLOWED, set())

    def test_help_lists_every_whitelisted_tag(self) -> None:
        help_text = (SPEAK_DIR / "HELP.md").read_text(encoding="utf-8")
        for tag in sorted(ALLOWED):
            with self.subTest(tag=tag):
                self.assertIn(f"`[{tag}]`", help_text)


class TagLevelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.categories = speak.load_tag_categories()

    def test_categories(self) -> None:
        self.assertEqual(
            {name: len(tags) for name, tags in self.categories.items()},
            {"Emotion": 7, "Vocalizations": 12, "Delivery": 6, "Character": 3, "Sound effects": 12},
        )

    def test_level_tags(self) -> None:
        low = speak.level_tags("low", self.categories)
        medium = speak.level_tags("medium", self.categories)
        high = speak.level_tags("high", self.categories)
        self.assertEqual(low, {"softly", "slowly", "pause", "chuckling", "sighing", "clears throat"})
        self.assertEqual(medium, low | self.categories["Emotion"])
        self.assertTrue(medium <= high)
        self.assertNotIn("rain falling", high)
        self.assertNotIn("witch voice", high)
        for level in ("none", "custom", "auto"):
            self.assertIsNone(speak.level_tags(level, self.categories))

    def test_off_level_tags_are_found(self) -> None:
        low = speak.level_tags("low", self.categories)
        self.assertEqual(speak.find_unsupported_tags("[softly] Hi. [excited] [rain falling] Go!", low),
                         ["[excited]", "[rain falling]"])


class TagDetectionTests(unittest.TestCase):
    def test_markdown_links_and_non_words_are_not_tags(self) -> None:
        text = "See [the docs](https://x.io), note [1], and [tired] [Sighing] [x2]."
        self.assertEqual(speak.find_tags(text), ["[tired]", "[Sighing]"])

    def test_long_bracket_text_is_not_a_tag(self) -> None:
        self.assertEqual(speak.find_tags("[this is far too long to be a tag]"), [])

    def test_tag_support_by_model(self) -> None:
        for model in ("eleven_v4", "eleven_v4_turbo", "eleven_v3"):
            with self.subTest(model=model):
                self.assertIsNone(speak.tag_support_error(model, "high", "[excited] Hi."))
        self.assertIsNone(speak.tag_support_error("eleven_multilingual_v2", "none", "Hi."))
        self.assertIsNotNone(speak.tag_support_error("eleven_multilingual_v2", "low", "Hi."))
        self.assertIsNotNone(speak.tag_support_error("eleven_flash_v2_5", "none", "[excited] Hi."))


class VoiceAndModelTests(unittest.TestCase):
    VOICES = [
        {"voice_id": "a" * 20, "name": "Alice - Clear, Engaging Educator"},
        {"voice_id": "b" * 20, "name": "labinini2"},
        {"voice_id": "c" * 20, "name": "Chris - Charming"},
        {"voice_id": "d" * 20, "name": "Chris - Deep"},
    ]

    def names(self, query: str) -> list[str]:
        return [v["name"] for v in speak.match_voices(self.VOICES, query)]

    def test_full_name_and_short_name(self) -> None:
        self.assertEqual(self.names("LABININI2"), ["labinini2"])
        self.assertEqual(self.names("alice"), ["Alice - Clear, Engaging Educator"])
        self.assertEqual(self.names("Alice - Clear, Engaging Educator"), ["Alice - Clear, Engaging Educator"])

    def test_ambiguous_and_missing(self) -> None:
        self.assertEqual(self.names("chris"), ["Chris - Charming", "Chris - Deep"])
        self.assertEqual(self.names("bob"), [])

    def test_exact_name_wins_over_short_name(self) -> None:
        voices = self.VOICES + [{"voice_id": "e" * 20, "name": "Alice"}]
        self.assertEqual([v["name"] for v in speak.match_voices(voices, "alice")], ["Alice"])

    def test_model_aliases(self) -> None:
        self.assertEqual(speak.normalize_model("v4"), "eleven_v4")
        self.assertEqual(speak.normalize_model("V4-Turbo"), "eleven_v4_turbo")
        self.assertEqual(speak.normalize_model("v3"), "eleven_v3")
        self.assertEqual(speak.normalize_model("multilingual"), "eleven_multilingual_v2")
        self.assertEqual(speak.normalize_model("flash"), "eleven_flash_v2_5")
        self.assertEqual(speak.normalize_model("eleven_turbo_v2_5"), "eleven_turbo_v2_5")


class AudioAndFilesTests(unittest.TestCase):
    def test_looks_like_mp3(self) -> None:
        self.assertTrue(speak.looks_like_mp3(b"ID3" + b"\0" * 200))
        self.assertTrue(speak.looks_like_mp3(b"\xff\xfb" + b"\0" * 200))
        self.assertFalse(speak.looks_like_mp3(b'{"detail": "error"}' + b" " * 200))
        self.assertFalse(speak.looks_like_mp3(b""))
        self.assertFalse(speak.looks_like_mp3(b"ID3"))

    def test_unique_path_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            clip = folder / "clip.mp3"
            clip.write_bytes(b"ID3" + b"\0" * 200)
            save_dir = folder / "saved"
            first = speak.archive(clip, "[tired] Hello there.", "auto", save_dir, "labinini2",
                                  "eleven_v4_turbo", "Late\tnight at\nthe office.")
            second = speak.archive(clip, "[tired] Hello there.", "auto", save_dir)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file() and second.is_file())
            rows = [line.split("\t") for line in (save_dir / "index.tsv").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(rows[0]), 7)
            self.assertEqual(rows[0][2:], ["auto", "[tired] Hello there.", "labinini2", "eleven_v4_turbo",
                                           "Late night at the office."])
            self.assertEqual(speak.unique_path(save_dir / "new.mp3"), save_dir / "new.mp3")

    def test_stop_playback_only_stops_afplay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "player.pid"
            self.assertFalse(speak.stop_playback(pid_file))
            pid_file.write_text(str(os.getpid()))
            self.assertFalse(speak.stop_playback(pid_file))
            self.assertFalse(pid_file.exists())
            pid_file.write_text("not a pid")
            self.assertFalse(speak.stop_playback(pid_file))


class CacheTests(unittest.TestCase):
    def test_digest_is_stable_and_sensitive(self) -> None:
        base = speak.cache_digest("Hello.", "voice", "model", {"stability": 0.5})
        self.assertEqual(base, speak.cache_digest("Hello.", "voice", "model", {"stability": 0.5}))
        for args in (
            ("Hello!", "voice", "model", {"stability": 0.5}),
            ("Hello.", "other", "model", {"stability": 0.5}),
            ("Hello.", "voice", "other", {"stability": 0.5}),
            ("Hello.", "voice", "model", {"stability": 0.6}),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(base, speak.cache_digest(*args))

    def test_language_changes_digest_only_when_set(self) -> None:
        base = speak.cache_digest("Hello.", "voice", "model", {})
        self.assertEqual(base, speak.cache_digest("Hello.", "voice", "model", {}, None))
        self.assertNotEqual(base, speak.cache_digest("Hello.", "voice", "model", {}, "en"))

    def test_normalize_text_collapses_whitespace(self) -> None:
        self.assertEqual(speak.normalize_text("  a \n\n b\t c "), "a b c")


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((SPEAK_DIR / "config.example.json").read_text(encoding="utf-8"))

    def test_example_has_no_personal_data(self) -> None:
        self.assertEqual(self.config["voice_id"], "")

    def test_speed_is_not_sent_to_the_api(self) -> None:
        self.assertNotIn("speed", self.config["voice_settings"])
        self.assertNotIn("style", self.config["voice_settings"])

    def test_defaults(self) -> None:
        self.assertEqual(self.config["model_id"], "eleven_v4_turbo")
        self.assertNotIn("default_tag", self.config)
        self.assertTrue(self.config["save_audio"])
        self.assertTrue(speak.MIN_RATE <= self.config["slow_rate"] <= speak.MAX_RATE)
        self.assertEqual(self.config["slow_rate"], speak.DEFAULT_SLOW_RATE)


class SkillFilesTests(unittest.TestCase):
    def test_required_files(self) -> None:
        for relative in (
            "SKILL.md", "HELP.md", "audio-tags.md", "config.example.json",
            "agents/openai.yaml", "scripts/speak.py",
        ):
            with self.subTest(file=relative):
                self.assertTrue((SPEAK_DIR / relative).is_file())

    def test_scripts_are_executable(self) -> None:
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_frontmatter(self) -> None:
        text = (SPEAK_DIR / "SKILL.md").read_text(encoding="utf-8")
        parts = text.split("---", 2)
        self.assertEqual(parts[0].strip(), "")
        self.assertIn("name: speak", parts[1])
        description = re.search(r"^description:\s*(.+)$", parts[1], re.MULTILINE).group(1)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("<", description)
        for phrase in ("/speak", "@speak", "--tag", "--slow"):
            self.assertIn(phrase, description)

    def test_openai_metadata(self) -> None:
        metadata = (SPEAK_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        for key in ("display_name:", "short_description:", "default_prompt:"):
            self.assertIn(key, metadata)
        self.assertIn("$speak", metadata)

    def test_help_covers_every_documented_option(self) -> None:
        documented = option_names((SPEAK_DIR / "SKILL.md").read_text(encoding="utf-8"))
        in_help = option_names((SPEAK_DIR / "HELP.md").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(documented), 10)
        self.assertEqual(documented - {"help"}, in_help - {"help"})
        self.assertIn("help", in_help)

    def test_five_tag_levels_documented(self) -> None:
        text = (SPEAK_DIR / "SKILL.md").read_text(encoding="utf-8")
        for level in speak.TAG_LEVELS:
            with self.subTest(level=level):
                self.assertIn(f"| `{level}` |", text)

    def test_auto_level_is_documented(self) -> None:
        text = (SPEAK_DIR / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("### `auto`", "vivid but believable", "推断的情境：", "分析：", "朗读版本：",
                       "`--tag custom` with none of them means `--tag auto`", "### Prepare the text for speech"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        help_text = (SPEAK_DIR / "HELP.md").read_text(encoding="utf-8")
        for phrase in ("`auto`", "推断的情境：", "--voice NAME", "--model NAME", "--stop"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, help_text)

    def test_language_rules_are_documented(self) -> None:
        text = (SPEAK_DIR / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "never translate it",
            "always English only. Pass `--lang en`",
            "The `--lang` option does not exist in those skills.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_rewrite_and_polish_force_english(self) -> None:
        for name in ("rewrite", "polish"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=name):
                self.assertIn("always called with `--lang en`", text)
                self.assertIn("（未安装 speak skill，已跳过朗读。）", text)


class CommandLineTests(unittest.TestCase):
    """Argument handling that exits before any config, network, or audio is touched."""

    def run_script(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), *args],
            input=stdin, capture_output=True, text=True, timeout=30,
        )

    def test_help_prints_help_file(self) -> None:
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("# speak 速查", result.stdout)

    def test_rejects_bad_rate(self) -> None:
        for bad in ("0.885", "2", "abc"):
            with self.subTest(rate=bad):
                result = self.run_script("--rate", bad)
                self.assertEqual(result.returncode, 2)
                self.assertIn("语速", result.stderr)

    def test_rate_and_slow_conflict(self) -> None:
        self.assertEqual(self.run_script("--rate", "0.9", "--slow").returncode, 2)

    def test_rejects_unknown_tag_level_and_language(self) -> None:
        self.assertEqual(self.run_script("--tag", "loud").returncode, 2)
        self.assertEqual(self.run_script("--lang", "english").returncode, 2)


if __name__ == "__main__":
    unittest.main()
