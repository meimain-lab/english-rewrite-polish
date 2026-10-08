# English Rewrite & Polish

Two companion skills that turn Chinese, mixed Chinese-English, or rough English into natural American English.

| Skill | Purpose | Speed |
| :--- | :--- | :--- |
| `rewrite` | Fast, faithful conversion. Fixes the language, keeps the content and structure. | Fastest |
| `polish` | Refined American English with three effort tiers: `low`, `medium` (default), `high`. | Scales with effort |

Both skills work in Claude, ChatGPT, and Codex.

## Usage

```text
/rewrite [--limit N] [--context "..."] [--] <text>
/polish  [--effort low|medium|high] [--limit N] [--context "..."] [--] <text>
```

Use `$rewrite` / `$polish` in Codex and `@rewrite` / `@polish` in ChatGPT.

```text
/rewrite 麻烦你今天下班前把报告发我一下，老板明早要看，辛苦了！
/rewrite i has send the file yesterday but you dont reply me
/polish --effort high --context "LinkedIn post" 我们团队历时两年终于完成了新的皮肤科 AI 工具……
/polish 这是发给美国客户的邮件 """我们已经收到您的反馈，会在三个工作日内回复。"""
```

### Options

| Option | Applies to | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--effort low\|medium\|high` | `polish` | `medium` | Polishing intensity. |
| `--limit N` / `--limit none` | both | `1000` | Maximum length units to process. |
| `--context "..."` | both | none | Audience, purpose, or terms to keep. Not translated or output. |
| `--` | both | — | Ends options; everything after is text. |

Options are only read at the start, right after the skill name. Anything later is treated as text.

### Payload boundary

The text to convert is **always data, never instructions**. A sentence such as "ignore previous instructions" or "帮我写一首诗" is translated, not executed.

For precise control, wrap the text in `"""…"""` or `<<<…>>>`. Only the wrapped text is converted, and any text outside the wrapper is used as context. A fenced code block works as a wrapper only when it encloses the entire text; a fence inside other text is treated as code within the content. Wrapping the whole text in a single pair of double quotes also works, as long as the text contains no other double quotes of the same kind.

### Length limit

Length units: each CJK character = 1, each English word or number = 1, punctuation = 0. The default of 1,000 units is roughly 1,000 Chinese characters, which covers a long email or 3–5 paragraphs. If the text is longer, the skill processes up to the last complete sentence within the limit, then says how much was left.

### Effort tiers (`polish`)

| Tier | What changes |
| :--- | :--- |
| `low` | Natural phrasing and sharper word choice; sentence order and structure kept. No notes. |
| `medium` | Sentences restructured for flow, redundancy cut, register fitted to context. Notes only for real ambiguities. |
| `high` | Full editorial pass: may reorder paragraphs, lead with the main point, refine rhythm and vocabulary, with a fidelity self-check. Includes a short list of key changes. |

No tier adds facts, claims, or sign-offs that aren't in the source.

## Installation

**Codex:** use the skill installer with each skill directory:

```text
$skill-installer install the skill from https://github.com/meimain-lab/english-rewrite-polish/tree/main/skills/rewrite
$skill-installer install the skill from https://github.com/meimain-lab/english-rewrite-polish/tree/main/skills/polish
```

**Manual (Codex, Claude Code):** copy `skills/rewrite/` and `skills/polish/` into your personal skill directory (for example `~/.agents/skills/` or `~/.claude/skills/`). Each installed directory must contain `SKILL.md` directly beneath it.

**Claude (claude.ai):** upload each skill folder as a custom skill. Each `SKILL.md` is self-contained.

## Repository layout

```text
skills/
├── rewrite/
│   ├── SKILL.md
│   └── agents/openai.yaml
└── polish/
    ├── SKILL.md
    └── agents/openai.yaml
tests/
├── reference_parser.py      # Executable statement of the invocation contract
├── test_skills.py           # Structure, shared-contract, and parser tests
└── behavior-cases.md        # Manual review fixtures with expected outputs
```

## Development

```bash
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md). License: MIT.

## 中文说明

这个仓库包含两个配套 skill，用来把中文、中英混杂的文字或写得很差的英文转成自然的美式英文。

- **`rewrite`**：快速直译加润色。修正语言问题，保留原文的内容、顺序和结构。适合日常消息和邮件，追求速度。
- **`polish`**：深度润色，分三档。`low` 只改措辞，保留结构；`medium`（默认）会重组句子、删去冗余；`high` 是完整的编辑处理，可以调整段落顺序，并附上主要改动说明。

**用法要点**

1. 参数只在 skill 名后面紧接着写，例如 `/polish --effort high --limit 500 正文……`。正文中间出现的 `--limit` 一律当作原文。
2. 需要精确圈定原文时，用 `"""…"""` 或 `<<<…>>>` 包起来。包起来的部分才会被翻译，外面的文字会被当作背景说明，例如“这是发给客户的邮件”。代码块（```）只有包住全部原文时才算圈定符；夹在正文中间的代码块会被当作原文里的代码。
3. 原文永远只当作待翻译的内容，不会被当成指令执行。即使原文写着“帮我写一首诗”，输出也只会是这句话的英文。
4. `--limit` 默认 1000 个长度单位：一个汉字算 1，一个英文单词算 1，标点不算。超出部分不会处理，skill 会在最后的完整句子处截断，并提示剩余字数。`--limit none` 表示不设上限。
5. 输出只有英文正文。`polish --effort high` 会在正文后用 `---` 分隔，附上几条改动说明，说明的语言跟你和 Claude 对话所用的语言一致。
