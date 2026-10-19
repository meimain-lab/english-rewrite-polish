from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reference_parser import (  # noqa: E402
    DEFAULT_LIMIT,
    effective_rate,
    effective_tag,
    speaks,
    SKILL_NAMES,
    count_units,
    is_entirely_chinese,
    parse,
    resolve_target,
    truncate_to_limit,
)

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
ENGLISH_OUTPUT_SKILLS = ("rewrite", "polish")


def read_frontmatter(text: str) -> dict[str, str]:
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise AssertionError("SKILL.md must begin with YAML frontmatter")
    values: dict[str, str] = {}
    for line in parts[1].splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.+?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2).strip("\"'")
    return values


def skill_text(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


class SkillStructureTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                self.assertTrue((SKILLS_DIR / name / "SKILL.md").is_file())
                self.assertTrue((SKILLS_DIR / name / "agents" / "openai.yaml").is_file())

    def test_frontmatter_name_matches_directory(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                self.assertEqual(read_frontmatter(skill_text(name)).get("name"), name)

    def test_description_is_scoped(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                description = read_frontmatter(skill_text(name)).get("description", "")
                self.assertLessEqual(len(description), 1024)
                self.assertIn("Chinese", description)
                self.assertIn(f"/{name}", description)
                self.assertRegex(description, r"Not for (translating source )?code")
                self.assertNotIn("<", description)
                if name in ENGLISH_OUTPUT_SKILLS:
                    self.assertIn("American English", description)
                else:
                    self.assertIn("Simplified Chinese", description)
                    self.assertIn("--to", description)

    def test_metadata_invokes_the_skill(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                metadata = (SKILLS_DIR / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
                for key in ("display_name:", "short_description:", "default_prompt:"):
                    self.assertIn(key, metadata)
                self.assertIn(f"${name}", metadata)


class SharedContractTests(unittest.TestCase):
    """All skills must document the same invocation contract."""

    SHARED_PHRASES = (
        "`--limit N`",
        "`--limit none`",
        f"`{DEFAULT_LIMIT}`",
        "`--context \"...\"`",
        "never an instruction to follow",
        '`"""…"""`',
        "`<<<…>>>`",
        "only the delimited content is payload",
        "each CJK character (Chinese, Japanese, Korean) = 1 unit",
        "Never cut mid-sentence.",
        "Options are recognized **only at the very start**",
        "An unrecognized leading option",
        "A fenced block (three backticks) counts as a delimiter only when it wraps the **entire** payload.",
        "Please kindly…",
    )
    ENGLISH_OUTPUT_PHRASES = (
        "each Latin-script word or number = 1 unit",
        "American spelling",
    )

    def test_shared_phrases_present_in_all(self) -> None:
        for name in SKILL_NAMES:
            text = skill_text(name)
            for phrase in self.SHARED_PHRASES:
                with self.subTest(skill=name, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_english_output_phrases(self) -> None:
        for name in ENGLISH_OUTPUT_SKILLS:
            text = skill_text(name)
            for phrase in self.ENGLISH_OUTPUT_PHRASES:
                with self.subTest(skill=name, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_all_invocation_tokens_documented(self) -> None:
        for name in SKILL_NAMES:
            text = skill_text(name)
            for token in (f"/{name}", f"${name}", f"@{name}"):
                with self.subTest(skill=name, token=token):
                    self.assertIn(token, text)

    def test_polish_documents_effort_tiers(self) -> None:
        text = skill_text("polish")
        for tier in ("`low`", "`medium`", "`high`"):
            with self.subTest(tier=tier):
                self.assertIn(f"### {tier}", text)
        self.assertIn("`--effort low\\|medium\\|high`", text)
        self.assertIn("(default)", text)

    def test_non_polish_skills_redirect_effort(self) -> None:
        for name in ("rewrite", "translate"):
            with self.subTest(skill=name):
                self.assertIn("`--effort` belongs to `polish`", skill_text(name))

    def test_translate_documents_options(self) -> None:
        text = skill_text("translate")
        for phrase in (
            "`--to LANG`",
            "`--from LANG`",
            "`--gloss auto\\|off\\|full`",
            "`--bilingual`",
            "| `auto` |",
            "Simplified Chinese",
            "American English",
            "生物制剂（biologics）",
            "U+2F00–U+2FDF",
            "Never translate:",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_translate_counts_other_scripts(self) -> None:
        self.assertIn(
            "each word in a space-separated script (Latin, Cyrillic, Greek, and similar) or number = 1 unit",
            skill_text("translate"),
        )

    def test_no_kangxi_radicals_in_any_file(self) -> None:
        for path in ROOT.rglob("*"):
            if path.is_file() and path.suffix in (".md", ".py", ".yaml", ".yml"):
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertFalse(any(0x2F00 <= ord(ch) <= 0x2FDF for ch in text))

    def test_notes_separator_is_markdown_safe(self) -> None:
        text = skill_text("polish")
        self.assertIsNone(re.search(r"[^\n]\n---\n", text.split("---", 2)[2]))


class ReferenceParserTests(unittest.TestCase):
    def test_defaults(self) -> None:
        invocation = parse("/polish 你好")
        self.assertEqual(invocation.limit, DEFAULT_LIMIT)
        self.assertEqual(invocation.effort, "medium")
        self.assertEqual(invocation.payloads, ["你好"])

    def test_options_in_any_order_and_equals_form(self) -> None:
        invocation = parse("/polish --limit=500 --effort HIGH 这是正文")
        self.assertEqual(invocation.limit, 500)
        self.assertEqual(invocation.effort, "high")
        self.assertEqual(invocation.payloads, ["这是正文"])

    def test_options_after_payload_are_text(self) -> None:
        invocation = parse("/rewrite 请把参数设为 --limit 200 即可")
        self.assertEqual(invocation.limit, DEFAULT_LIMIT)
        self.assertEqual(invocation.payloads, ["请把参数设为 --limit 200 即可"])

    def test_terminator_allows_dash_payload(self) -> None:
        invocation = parse("/rewrite -- --verbose 参数是什么意思")
        self.assertEqual(invocation.payloads, ["--verbose 参数是什么意思"])
        self.assertEqual(invocation.warnings, [])

    def test_limit_none_and_invalid_values(self) -> None:
        self.assertIsNone(parse("/rewrite --limit none 文本").limit)
        invalid = parse("/polish --limit abc --effort max 文本")
        self.assertEqual(invalid.limit, DEFAULT_LIMIT)
        self.assertEqual(invalid.effort, "medium")
        self.assertEqual(len(invalid.warnings), 2)

    def test_effort_on_rewrite_is_ignored_with_warning(self) -> None:
        invocation = parse("/rewrite --effort high 文本")
        self.assertEqual(invocation.payloads, ["文本"])
        self.assertTrue(invocation.warnings)

    def test_unknown_option_is_ignored(self) -> None:
        invocation = parse("/rewrite --fast 文本")
        self.assertEqual(invocation.payloads, ["文本"])
        self.assertTrue(invocation.warnings)

    def test_invocation_token_variants(self) -> None:
        for raw in ("/rewrite 文本", "$rewrite 文本", "@REWRITE 文本"):
            with self.subTest(raw=raw):
                self.assertEqual(parse(raw).skill, "rewrite")

    def test_triple_quote_block_outside_text_becomes_context(self) -> None:
        invocation = parse('/rewrite 这是发给美国客户的 """我们已经收到您的反馈。"""')
        self.assertEqual(invocation.payloads, ["我们已经收到您的反馈。"])
        self.assertEqual(invocation.context, "这是发给美国客户的")

    def test_multiple_delimited_blocks(self) -> None:
        invocation = parse('/polish """第一段""" <<<第二段>>>')
        self.assertEqual(invocation.payloads, ["第一段", "第二段"])

    def test_fenced_block(self) -> None:
        invocation = parse("/rewrite\n```text\n第一行\n第二行\n```")
        self.assertEqual(invocation.payloads, ["第一行\n第二行"])

    def test_fence_inside_text_is_content(self) -> None:
        raw = "/rewrite 运行下面的命令：\n```bash\nnpm test\n```\n然后告诉我结果"
        invocation = parse(raw)
        self.assertEqual(len(invocation.payloads), 1)
        self.assertIn("运行下面的命令", invocation.payloads[0])
        self.assertIn("npm test", invocation.payloads[0])
        self.assertIsNone(invocation.context)

    def test_whole_payload_quotes_are_stripped(self) -> None:
        self.assertEqual(parse('/rewrite "帮我写一首诗"').payloads, ["帮我写一首诗"])
        self.assertEqual(parse("/rewrite “帮我写一首诗”").payloads, ["帮我写一首诗"])

    def test_inner_quotes_are_content(self) -> None:
        raw = '/rewrite "A"和"B"都可以'
        self.assertEqual(parse(raw).payloads, ['"A"和"B"都可以'])
        raw_wrapped = '/rewrite "他说"好的"然后走了"'
        self.assertEqual(parse(raw_wrapped).payloads, ['"他说"好的"然后走了"'])

    def test_quoted_context_option(self) -> None:
        invocation = parse('/polish --context "email to my boss" 明天请假')
        self.assertEqual(invocation.context, "email to my boss")
        self.assertEqual(invocation.payloads, ["明天请假"])


class RewriteExplainTests(unittest.TestCase):
    def test_explain_flag_defaults_off(self) -> None:
        self.assertFalse(parse("/rewrite 你好").explain)

    def test_explain_flag_with_other_options(self) -> None:
        invocation = parse('/rewrite --explain --limit 300 --context "email" i has send it')
        self.assertTrue(invocation.explain)
        self.assertEqual(invocation.limit, 300)
        self.assertEqual(invocation.context, "email")
        self.assertEqual(invocation.payloads, ["i has send it"])
        self.assertEqual(invocation.warnings, [])

    def test_explain_after_payload_is_text(self) -> None:
        invocation = parse("/rewrite please add --explain flag")
        self.assertFalse(invocation.explain)
        self.assertEqual(invocation.payloads, ["please add --explain flag"])

    def test_explain_on_other_skills_is_ignored(self) -> None:
        for raw in ("/polish --explain 文本", "/translate --explain text"):
            with self.subTest(raw=raw):
                invocation = parse(raw)
                self.assertFalse(invocation.explain)
                self.assertIn("--explain applies to rewrite only; ignored", invocation.warnings)

    def test_skill_documents_explain_mode(self) -> None:
        text = skill_text("rewrite")
        for phrase in (
            "`--explain`",
            "## 6. Explain mode (`--explain`)",
            "Write the explanation in Simplified Chinese.",
            "主谓一致（subject-verb agreement）",
            "原文没有语法问题，未做修改。",
            "At most 10 items",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_explain_separator_is_markdown_safe(self) -> None:
        body = skill_text("rewrite").split("---", 2)[2]
        self.assertIsNone(re.search(r"[^\n]\n---\n", body))


class SpeakOptionParserTests(unittest.TestCase):
    def test_defaults_do_not_speak(self) -> None:
        for skill in ("rewrite", "polish"):
            invocation = parse(f"/{skill} 你好")
            self.assertFalse(speaks(invocation))
            self.assertEqual(effective_tag(invocation), "none")
            self.assertEqual(effective_rate(invocation), 1.0)

    def test_speak_flag_and_rates(self) -> None:
        invocation = parse("/polish --speak --slow hello")
        self.assertTrue(speaks(invocation))
        self.assertEqual(effective_rate(invocation), 0.88)
        self.assertEqual(effective_rate(parse("/rewrite --rate 0.75 hello")), 0.75)
        self.assertEqual(effective_rate(parse("/rewrite --slow --rate 0.9 hello")), 0.9)

    def test_invalid_rates_fall_back_with_warning(self) -> None:
        for value in ("0.885", "0.4", "2", "fast"):
            with self.subTest(value=value):
                invocation = parse(f"/rewrite --rate {value} hello")
                self.assertEqual(effective_rate(invocation), 1.0)
                self.assertEqual(invocation.warnings, [f"invalid --rate {value!r}; using 1"])

    def test_tag_levels(self) -> None:
        for level in ("none", "low", "medium", "high", "auto"):
            with self.subTest(level=level):
                invocation = parse(f"/rewrite --tag {level} hello")
                self.assertEqual(effective_tag(invocation), level)
                self.assertEqual(speaks(invocation), level != "none")

    def test_custom_without_hints_means_auto(self) -> None:
        invocation = parse("/rewrite --tag custom hello")
        self.assertEqual(effective_tag(invocation), "auto")
        self.assertTrue(speaks(invocation))
        self.assertEqual(effective_tag(parse("/rewrite --tag custom --mood tired hello")), "custom")

    def test_auto_ignores_custom_options(self) -> None:
        invocation = parse("/polish --tag auto --scene office hello")
        self.assertEqual(effective_tag(invocation), "auto")
        self.assertIsNone(invocation.scene)
        self.assertEqual(invocation.warnings, ["--scene is used only with --tag custom; ignored"])

    def test_voice_and_model(self) -> None:
        invocation = parse('/rewrite --speak --voice "Alice" --model v4 hello')
        self.assertEqual((invocation.voice, invocation.model), ("Alice", "v4"))
        self.assertEqual(invocation.payloads, ["hello"])
        self.assertEqual(invocation.warnings, [])
        ignored = parse("/translate --voice alice hello")
        self.assertIsNone(ignored.voice)
        self.assertEqual(ignored.warnings, ["--voice applies to rewrite/polish only; ignored"])
        self.assertEqual(effective_tag(parse("/polish --tag=high hello")), "high")

    def test_bare_tag_means_medium_and_keeps_text(self) -> None:
        invocation = parse("/rewrite --tag 我们下周发布")
        self.assertEqual(effective_tag(invocation), "medium")
        self.assertEqual(invocation.payloads, ["我们下周发布"])
        self.assertTrue(speaks(invocation))

    def test_custom_options_imply_custom(self) -> None:
        for raw in (
            "/rewrite --mood tired hello",
            "/polish --scene \"rainy night office\" hello",
            "/rewrite --situation \"深夜加班，很累\" hello",
            "/rewrite --tags \"[tired] [sighing]\" hello",
            "/rewrite --tag --mood tired hello",
        ):
            with self.subTest(raw=raw):
                invocation = parse(raw)
                self.assertEqual(effective_tag(invocation), "custom")
                self.assertTrue(speaks(invocation))
                self.assertEqual(invocation.payloads, ["hello"])

    def test_custom_options_are_ignored_with_a_fixed_level(self) -> None:
        invocation = parse("/rewrite --tag low --mood tired hello")
        self.assertEqual(effective_tag(invocation), "low")
        self.assertIsNone(invocation.mood)
        self.assertEqual(invocation.warnings, ["--mood is used only with --tag custom; ignored"])

    def test_situation_value_is_kept(self) -> None:
        invocation = parse('/rewrite --tag custom --situation "深夜加班，很累，窗外下雨" It broke.')
        self.assertEqual(invocation.situation, "深夜加班，很累，窗外下雨")
        self.assertEqual(invocation.payloads, ["It broke."])

    def test_options_after_payload_are_text(self) -> None:
        invocation = parse("/rewrite please add --speak and --tag low")
        self.assertFalse(speaks(invocation))
        self.assertEqual(invocation.payloads, ["please add --speak and --tag low"])

    def test_speak_options_on_translate_are_ignored(self) -> None:
        invocation = parse("/translate --speak --tag low --rate 0.9 --slow hello")
        self.assertFalse(speaks(invocation))
        self.assertEqual(effective_rate(invocation), 1.0)
        self.assertEqual(len(invocation.warnings), 4)

    def test_help_flag_on_every_skill(self) -> None:
        for skill in ("rewrite", "polish", "translate"):
            with self.subTest(skill=skill):
                invocation = parse(f"/{skill} --help")
                self.assertTrue(invocation.help)
                self.assertEqual(invocation.payloads, [])

    def test_skills_document_speak_options_and_help(self) -> None:
        for name in ("rewrite", "polish"):
            text = skill_text(name)
            for phrase in ("`--speak`", "`--slow` / `--rate N`", "`--tag LEVEL`", "`--situation", "`--help`",
                           "`--voice NAME` / `--model NAME`", "`auto`", "推断的情境：",
                           "## 9. Speaking the result", "## 10. Help (`--help`)", "朗读版本："):
                with self.subTest(skill=name, phrase=phrase):
                    self.assertIn(phrase, text)
        self.assertIn("## 10. Help (`--help`)", skill_text("translate"))
        self.assertNotIn("`--speak`", skill_text("translate"))


class TranslateParserTests(unittest.TestCase):
    def test_defaults(self) -> None:
        invocation = parse("/translate Hello there.")
        self.assertEqual(invocation.target, "auto")
        self.assertEqual(invocation.source, "auto")
        self.assertEqual(invocation.gloss, "auto")
        self.assertFalse(invocation.bilingual)
        self.assertEqual(invocation.limit, DEFAULT_LIMIT)
        self.assertEqual(invocation.payloads, ["Hello there."])

    def test_all_options(self) -> None:
        invocation = parse(
            '/translate --to=ja --from en --gloss FULL --bilingual --limit 800 --context "clinical" -- --dry-run mode'
        )
        self.assertEqual(invocation.target, "ja")
        self.assertEqual(invocation.source, "en")
        self.assertEqual(invocation.gloss, "full")
        self.assertTrue(invocation.bilingual)
        self.assertEqual(invocation.limit, 800)
        self.assertEqual(invocation.context, "clinical")
        self.assertEqual(invocation.payloads, ["--dry-run mode"])
        self.assertEqual(invocation.warnings, [])

    def test_language_names_and_codes(self) -> None:
        cases = {"中文": "zh-CN", "zh": "zh-CN", "ZH-TW": "zh-TW", "English": "en", "日语": "ja", "ko": "ko", "nl": "nl"}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse(f"/translate --to {value} text").target, expected)

    def test_invalid_values_fall_back(self) -> None:
        invocation = parse("/translate --to xyz --gloss maybe 文本")
        self.assertEqual(invocation.target, "auto")
        self.assertEqual(invocation.gloss, "auto")
        self.assertEqual(len(invocation.warnings), 2)

    def test_effort_on_translate_is_ignored(self) -> None:
        invocation = parse("/translate --effort high Hello")
        self.assertEqual(invocation.payloads, ["Hello"])
        self.assertIn("--effort applies to polish only; ignored", invocation.warnings)

    def test_translate_options_on_other_skills_are_ignored(self) -> None:
        invocation = parse("/rewrite --to ja --bilingual 你好")
        self.assertEqual(invocation.payloads, ["你好"])
        self.assertEqual(len(invocation.warnings), 2)

    def test_option_after_payload_is_text(self) -> None:
        invocation = parse("/translate Set --to ja in the config.")
        self.assertEqual(invocation.target, "auto")
        self.assertEqual(invocation.payloads, ["Set --to ja in the config."])


class TranslateDirectionTests(unittest.TestCase):
    def target_for(self, raw: str) -> str:
        invocation = parse(raw)
        return resolve_target(invocation, invocation.payloads[0])

    def test_non_chinese_goes_to_chinese(self) -> None:
        for raw in (
            "/translate Please review the attached draft.",
            "/translate 来週の打ち合わせは木曜日に変更になりました。",
            "/translate 이번 업데이트에서 로그인 오류가 수정되었습니다.",
            "/translate Merci pour votre retour rapide.",
            "/translate Спасибо за отзыв.",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.target_for(raw), "zh-CN")

    def test_mixed_with_ordinary_english_goes_to_chinese(self) -> None:
        self.assertEqual(self.target_for("/translate 这个 PR 的 main concern 是 performance"), "zh-CN")
        self.assertEqual(self.target_for("/translate 这个 feature 我们下周 release"), "zh-CN")

    def test_pure_chinese_goes_to_english(self) -> None:
        self.assertEqual(self.target_for("/translate 我们已经收到您的反馈。"), "en")
        self.assertEqual(self.target_for("/translate 我们用 React 调用 API，抑制 IL-17 通路。"), "en")

    def test_explicit_target_wins(self) -> None:
        self.assertEqual(self.target_for("/translate --to zh 我们已经收到您的反馈。"), "zh-CN")
        self.assertEqual(self.target_for("/translate --to fr Please review."), "fr")

    def test_is_entirely_chinese_rejects_kana_and_hangul(self) -> None:
        self.assertFalse(is_entirely_chinese("会議は木曜日です"))
        self.assertFalse(is_entirely_chinese("회의 일정"))
        self.assertFalse(is_entirely_chinese("Hello"))


class LengthLimitTests(unittest.TestCase):
    def test_count_units_mixed(self) -> None:
        self.assertEqual(count_units("这个 feature 下周 release"), 6)
        self.assertEqual(count_units("I has send the file, ok?"), 6)
        self.assertEqual(count_units("，。！ ... "), 0)

    def test_count_units_other_scripts(self) -> None:
        self.assertEqual(count_units("Спасибо за отзыв."), 3)
        self.assertEqual(count_units("C'est l'été."), 2)
        self.assertEqual(count_units("来週の打ち合わせ"), 8)
        self.assertEqual(count_units("로그인 오류"), 5)
        self.assertEqual(count_units("IL-4 和 IL-13"), 3)

    def test_under_limit_is_untouched(self) -> None:
        text = "第一句。第二句。"
        self.assertEqual(truncate_to_limit(text, 100), (text, False))

    def test_truncates_at_sentence_boundary(self) -> None:
        text = "一二三四五。六七八九十。十一十二。"
        truncated, was_truncated = truncate_to_limit(text, 12)
        self.assertTrue(was_truncated)
        self.assertEqual(truncated, "一二三四五。六七八九十。")

    def test_english_sentence_boundary(self) -> None:
        text = "one two three. four five six. seven eight nine."
        self.assertEqual(truncate_to_limit(text, 7)[0], "one two three. four five six.")

    def test_no_limit(self) -> None:
        text = "字" * 5000
        self.assertEqual(truncate_to_limit(text, None), (text, False))


if __name__ == "__main__":
    unittest.main()
