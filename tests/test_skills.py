from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reference_parser import (  # noqa: E402
    DEFAULT_LIMIT,
    count_units,
    parse,
    truncate_to_limit,
)

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
SKILL_NAMES = ("rewrite", "polish")


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
                self.assertIn("American English", description)
                self.assertIn("Not for code", description)
                self.assertNotIn("<", description)

    def test_metadata_invokes_the_skill(self) -> None:
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                metadata = (SKILLS_DIR / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
                for key in ("display_name:", "short_description:", "default_prompt:"):
                    self.assertIn(key, metadata)
                self.assertIn(f"${name}", metadata)


class SharedContractTests(unittest.TestCase):
    """Both skills must document the same invocation contract."""

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
        "each Latin-script word or number = 1 unit",
        "Never cut mid-sentence.",
        "Options are recognized **only at the very start**",
        "American spelling",
        "Please kindly…",
    )

    def test_shared_phrases_present_in_both(self) -> None:
        for name in SKILL_NAMES:
            text = skill_text(name)
            for phrase in self.SHARED_PHRASES:
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

    def test_rewrite_redirects_effort_to_polish(self) -> None:
        self.assertIn("`--effort` belongs to `polish`", skill_text("rewrite"))

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


class LengthLimitTests(unittest.TestCase):
    def test_count_units_mixed(self) -> None:
        self.assertEqual(count_units("这个 feature 下周 release"), 6)
        self.assertEqual(count_units("I has send the file, ok?"), 6)
        self.assertEqual(count_units("，。！ ... "), 0)

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
