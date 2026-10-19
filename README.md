# Rewrite, Polish & Translate

Four companion skills for moving text between Chinese, English, and other languages, and for hearing the result.

| Skill | Purpose | Default output |
| :--- | :--- | :--- |
| `rewrite` | Fast, faithful conversion of Chinese, mixed Chinese-English, or rough English. Fixes the language, keeps the content and structure. `--explain` adds a Chinese explanation of the grammar issues. | American English |
| `polish` | Refined American English with three effort tiers: `low`, `medium` (default), `high`. | American English |
| `translate` | Faithful translation from English, mixed text, or other languages (Japanese, Korean, French, Italian, Russian, …). Pure Chinese input goes to English. | Simplified Chinese |
| `speak` | Optional. Reads text aloud with ElevenLabs for pronunciation and listening practice, with slow playback and optional emotion tags. | Audio |

`rewrite`, `polish`, and `translate` work in Claude, ChatGPT, and Codex. `speak` needs a tool that can run local commands (OpenCode, Claude Code, Codex CLI) on macOS; see [Speaking (`speak`)](#speaking-speak).

## Usage

```text
/rewrite   [--explain] [--limit N] [--context "..."] [--] <text>
/polish    [--effort low|medium|high] [--limit N] [--context "..."] [--] <text>
/translate [--to LANG] [--from LANG] [--gloss auto|off|full] [--bilingual] [--limit N] [--context "..."] [--] <text>
/speak     [--slow | --rate N] [--voice NAME] [--model NAME] [--tag LEVEL] [--mood "..."] [--scene "..."] [--situation "..."] [--lang CODE] [--replay] [--stop] [--] [text]
```

Every skill answers `--help` with its option reference.

Use `$rewrite` / `$polish` / `$translate` in Codex and `@rewrite` / `@polish` / `@translate` in ChatGPT.

```text
/rewrite 麻烦你今天下班前把报告发我一下，老板明早要看，辛苦了！
/rewrite i has send the file yesterday but you dont reply me
/rewrite --explain i has send the file yesterday but you dont reply me
/polish --effort high --context "LinkedIn post" 我们团队历时两年终于完成了新的皮肤科 AI 工具……
/translate Please review the attached draft and let me know if you have any questions before Friday.
/translate --gloss full Dupilumab blocks IL-4 and IL-13 signaling in atopic dermatitis.
/translate --to en 来週の打ち合わせは木曜日に変更になりました。
/translate --bilingual 论文摘要 """Background: Atopic dermatitis is a chronic inflammatory skin disease."""
```

### Options

| Option | Applies to | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--effort low\|medium\|high` | `polish` | `medium` | Polishing intensity. |
| `--to LANG` | `translate` | `auto` | Target language: `zh`, `zh-TW`, `en`, `ja`, `ko`, `fr`, `it`, `ru`, … or a name such as `中文`, `English`, `日语`. |
| `--from LANG` | `translate` | `auto` | Source language, for short or ambiguous text. |
| `--gloss auto\|off\|full` | `translate` | `auto` | English term in parentheses after a translated technical term, on first occurrence. |
| `--explain` | `rewrite` | off | After the rewrite, a numbered list explaining each grammar or wording issue in Chinese, with English fragments and terms such as 主谓一致（subject-verb agreement）. |
| `--bilingual` | `translate` | off | Source and translation, paragraph by paragraph. |
| `--speak` | `rewrite`, `polish` | off | Read the English result aloud with `speak`. |
| `--slow` / `--rate N` | `rewrite`, `polish`, `speak` | `1` | Playback speed: `--slow` is 0.88×, `--rate` takes 0.50–1.50 with at most two decimals. |
| `--voice NAME` / `--model NAME` | `rewrite`, `polish`, `speak` | config | Voice (name, short name, or voice_id) and model (model_id or `v4`, `v4-turbo`, `v3`, `multilingual`, `flash`) for this call. |
| `--tag none\|low\|medium\|high\|custom\|auto` | `rewrite`, `polish`, `speak` | `none` | Read with audio tags for emotion. `auto` infers a situation from the text and prints it with a short analysis. |
| `--mood`, `--scene`, `--situation`, `--tags` | `rewrite`, `polish`, `speak` | none | Describe the situation for `--tag custom`. |
| `--help` | all | — | Show the option reference. |
| `--limit N` / `--limit none` | all | `1000` | Maximum length units to process. |
| `--context "..."` | all | none | Audience, purpose, domain, or terms to keep. Not translated or output. |
| `--` | all | — | Ends options; everything after is text. |

Options are only read at the start, right after the skill name. Anything later is treated as text.

### Translation direction (`translate`)

With the default `--to auto`, anything that is not purely Chinese — English, Japanese, Korean, French, Russian, or a Chinese text mixed with English sentences or ordinary English words — is translated into Simplified Chinese. A purely Chinese text (conventional English terms such as API or product names are fine) is translated into American English. Use `--to` to force a direction.

Chinese output follows a fixed style: conventional English terms (API, prompt, commit, product and library names, standard abbreviations, gene names, code) stay in English; everything else becomes natural Chinese without translationese; technical terms get an English gloss on first occurrence, such as 生物制剂（biologics）; English source titles and official names keep their original form; full-width punctuation, with a space between Chinese and Latin letters or numbers.

### Payload boundary

The text to convert is **always data, never instructions**. A sentence such as "ignore previous instructions" or "帮我写一首诗" is translated, not executed.

For precise control, wrap the text in `"""…"""` or `<<<…>>>`. Only the wrapped text is converted, and any text outside the wrapper is used as context. A fenced code block works as a wrapper only when it encloses the entire text; a fence inside other text is treated as code within the content. Wrapping the whole text in a single pair of double quotes also works, as long as the text contains no other double quotes of the same kind.

### Length limit

Length units: each CJK character = 1, each word in a space-separated script (English, French, Russian, …) or number = 1, punctuation = 0. The default of 1,000 units is roughly 1,000 Chinese characters or 1,000 English words. If the text is longer, the skill processes up to the last complete sentence within the limit, then says how much was left.

### Effort tiers (`polish`)

| Tier | What changes |
| :--- | :--- |
| `low` | Natural phrasing and sharper word choice; sentence order and structure kept. No notes. |
| `medium` | Sentences restructured for flow, redundancy cut, register fitted to context. Notes only for real ambiguities. |
| `high` | Full editorial pass: may reorder paragraphs, lead with the main point, refine rhythm and vocabulary, with a fidelity self-check. Includes a short list of key changes. |

No tier adds facts, claims, or sign-offs that aren't in the source.

### Speaking (`speak`)

`speak` is optional. `rewrite` and `polish` work without it and only skip the `--speak` step.

- **Needs:** macOS (`afplay`, Keychain), Python 3 (standard library only), and an ElevenLabs API key.
- **Store the key** in the macOS Keychain; it is never written to a file. You are prompted for the key, so it stays out of your shell history:

  ```bash
  security add-generic-password -a "$USER" -s elevenlabs-api-key -w
  ```

- **First run** creates `~/.config/english-speak/config.json` from `skills/speak/config.example.json`. Set `voice_name` (any voice in your account; `python3 skills/speak/scripts/speak.py --list-voices` lists them) and `model_id`. Changing `voice_name` switches the voice on the next call. `--voice` and `--model` override both for one call.
- **Speed** changes local playback only, so a sentence is synthesized and cached once. The v4 models ignore the API's `speed` setting.
- **Tags:** ElevenLabs' web Auto-tag button has no API. `--tag` makes the model insert tags from the whitelist in `skills/speak/audio-tags.md` (40 tags; any other bracketed tag is refused) without changing a word of the text. Levels: `none` (default), `low`, `medium`, `high`, `custom`, which takes `--mood`, `--scene`, a paragraph-long `--situation`, or `--tags`, and `auto`, which infers a vivid but believable situation from the line and prints it, with a short analysis, before speaking. The script refuses tags outside a level's categories, and refuses tags with models that would read them out loud (only v3, v4, and v4 Turbo support tags). Markdown is turned into plain spoken text first.
- **Languages:** called on its own, `speak` reads any language the model supports, as written. Called from `rewrite` or `polish`, it always reads English.
- **Saved audio:** each new clip is copied to `~/Music/english-speak/` with an `index.tsv` of the spoken text, level, voice, model, and situation. Set `"save_audio": false` to turn that off.
- **Stop playback:** `/speak --stop`, which stops only the clip `speak` started.

See `skills/speak/HELP.md` for the full option reference.

## Installation

**Codex:** use the skill installer with each skill directory:

```text
$skill-installer install the skill from https://github.com/meimain-lab/english-rewrite-polish/tree/main/skills/rewrite
$skill-installer install the skill from https://github.com/meimain-lab/english-rewrite-polish/tree/main/skills/polish
$skill-installer install the skill from https://github.com/meimain-lab/english-rewrite-polish/tree/main/skills/translate
$skill-installer install the skill from https://github.com/meimain-lab/english-rewrite-polish/tree/main/skills/speak
```

**Manual (Codex, Claude Code):** copy `skills/rewrite/`, `skills/polish/`, `skills/translate/`, and optionally `skills/speak/` into your personal skill directory (for example `~/.agents/skills/`, `~/.claude/skills/`, or `~/.config/opencode/skills/`). Each installed directory must contain `SKILL.md` directly beneath it.

**Claude (claude.ai):** upload each skill folder as a custom skill. Each `SKILL.md` is self-contained.

## Repository layout

```text
skills/
├── rewrite/
│   ├── SKILL.md
│   └── agents/openai.yaml
├── polish/
│   ├── SKILL.md
│   └── agents/openai.yaml
├── translate/
│   ├── SKILL.md
│   └── agents/openai.yaml
└── speak/
    ├── SKILL.md
    ├── HELP.md              # Option reference shown by --help
    ├── audio-tags.md        # Whitelist of the 40 audio tags
    ├── config.example.json
    ├── agents/openai.yaml
    └── scripts/
        └── speak.py
tests/
├── reference_parser.py      # Executable statement of the invocation contract
├── test_skills.py           # Structure, shared-contract, parser, and direction tests
├── test_speak.py            # speak skill: rates, tag whitelist, cache, config, command line
└── behavior-cases.md        # Manual review fixtures with expected outputs
```

## Development

```bash
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md). License: MIT.

## 中文说明

这个仓库包含四个配套 skill（其中 `speak` 是可选的）：

- **`rewrite`**：把中文、中英混杂的文字或写得很差的英文快速转成自然的美式英文，保留原文的内容、顺序和结构。加上 `--explain` 后，会在译文下方用中文逐条讲解原文的语法和用词问题：原文片段和改法保留英文，语法术语首次出现时附英文，例如 时态（tense）、逗号粘连（comma splice）。原文是中文时，讲解的是哪些说法直译会变成中式英语。
- **`polish`**：深度润色成美式英文，分三档。`low` 只改措辞；`medium`（默认）会重组句子、删去冗余；`high` 是完整的编辑处理，可以调整段落顺序，并附上主要改动说明。
- **`speak`**（可选）：用 ElevenLabs 把文字读出来，练听力和跟读。需要 macOS 和 ElevenLabs API key（存在系统钥匙串里）。可以放慢播放（`--slow`、`--rate 0.88`，速度只影响本地播放，同一句只生成一次），也可以用 `--tag low|medium|high|custom|auto` 自动加情绪标签。`custom` 档用 `--mood`、`--scene`，或用一段话的 `--situation` 描述说话时的情境；`auto` 档由模型先分析原句，推断一个生动但可信的情境，把英文情境描述和中文分析打印出来再朗读。`--voice`、`--model` 可以按次换声音和模型（默认 labinini2 和 `eleven_v4_turbo` 由配置决定），`--stop` 停止播放。标签只能从 `skills/speak/audio-tags.md` 里的 40 个里选，不会编造新标签，也不会改动原文的任何词。单独使用时不限语言，从 `rewrite` / `polish` 调用时固定只读英文。每条新生成的音频会自动保存，并记入 `index.tsv`。各 skill 都支持 `--help`。
- **`translate`**：忠实翻译，默认译成简体中文。原文可以是英文、中英混杂，也可以是日语、韩语、法语、意大利语、俄语等。纯中文原文会自动译成英文；用 `--to` 可以指定任意目标语言。

**`translate` 的中文输出规则**

1. API、prompt、commit、产品名和库名、标准缩写（FDA、RCT、IL-17）、基因名和代码保留英文；其他内容译成自然的中文，不做不必要的中英混杂，避免翻译腔。
2. 专业术语首次出现时，在全角括号里附上英文，例如 生物制剂（biologics）。`--gloss auto`（默认）只给容易误解或有多种译法的术语加注；`--gloss full` 给所有专业术语加注，适合读文献；`--gloss off` 不加注。
3. 英文文献标题和官方名称保留原文；没有把握的药名、基因名、机构名不自造中文译名。
4. 使用全角中文标点，中文与英文字母或数字之间加空格（调用 API、共 3 个）；不输出康熙部首（U+2F00–U+2FDF）这类形近字。
5. 代码、命令、文件名、URL、单位和数值一律不翻译；代码注释默认保持原样，只有目标语言是英文时才把中文注释译成英文。
6. `--bilingual` 按段落输出原文和译文，方便对照阅读。

**通用用法要点**

1. 参数只在 skill 名后面紧接着写，例如 `/translate --to ja --limit 500 正文……`。正文中间出现的 `--to`、`--limit` 一律当作原文。
2. 需要精确圈定原文时，用 `"""…"""` 或 `<<<…>>>` 包起来。包起来的部分才会被处理，外面的文字会被当作背景说明，例如“这是论文摘要”。代码块（```）只有包住全部原文时才算圈定符。
3. 原文永远只当作待处理的内容，不会被当成指令执行。
4. `--limit` 默认 1000 个长度单位：一个汉字（或日文、韩文字符）算 1，一个英文、法文、俄文等单词算 1，标点不算。超出时在最后的完整句子处截断，并提示剩余多少。`--limit none` 表示不设上限。
