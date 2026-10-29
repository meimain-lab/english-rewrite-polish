# speak 速查

用 ElevenLabs 把文字读出来，用来练听力和跟读。单独使用 `@speak` 时不限语言，模型支持的语言都能读（英文、中文、日语、韩语等），按原文读，不翻译；从 `@rewrite` / `@polish` 调用时固定只读英文。

```text
@speak [选项] [文本]
```

不写文本时，读上一条 `@rewrite` / `@polish` 的英文结果（不读 `---` 之后的讲解）。音频标签永远是英文，不管正文是什么语言。选项只在最前面识别，写在文本后面的一律当作文本。文本里的 Markdown 会先转成纯文字：链接只读文字；网址按人的读法念（`github.com/meimain-lab` 读作 “github dot com slash meimain dash lab”，不读 `https://`）；`@` 读作 “at”；文件路径和代码块会跳过并说明。

一次最多读 10,000 个字符。长文本由脚本按句子切开分段生成，再合成一个文件，一次播放完，不会被后一段打断。

## 选项

| 选项 | 作用 | 默认 |
| :--- | :--- | :--- |
| `--slow` | 用 `slow_rate` 放慢播放 | 关；`slow_rate` 默认 0.88 |
| `--rate N` | 播放语速，0.50–1.50，最多两位小数，比如 `0.88`。`--speed` 是它的别名。和 `--slow` 同时写时以 `--rate` 为准 | 1 |
| `--voice NAME` | 这次用哪个声音：完整名字、“ - ”前面的短名（`alice` 对应 “Alice - Clear, Engaging Educator”）或 voice_id，不区分大小写 | 配置里的 `voice_name`（labinini2） |
| `--model NAME` | 这次用哪个模型：model_id，或简写 `v4`、`v4-turbo`、`v3`、`multilingual`、`flash`。只有 `v4`、`v4-turbo`、`v3` 支持音频标签 | 配置里的 `model_id`（`eleven_v4_turbo`） |
| `--lang CODE` | 指定语言（两位 ISO 639-1 代码，如 `en`、`zh`、`ja`）；`--lang en` 只读英文，文本里有其他文字会报错。`auto` 表示让模型自己判断 | `auto` |
| `--tag LEVEL` | 自动加音频标签，档位见下表。只写 `--tag` 不带档位等于 `medium` | `none` |
| `--mood "…"` | custom：情绪，比如 `tired` | — |
| `--scene "…"` | custom：环境，比如 `rainy night office` | — |
| `--situation "…"` | custom：用一段话描述说话时的情境和状态，最多 500 字 | — |
| `--tags "[…] […]"` | custom：手动指定必须用到的标签 | — |
| `--replay` | 重放上一条音频，不调用 API、不耗 credits。可以配合 `--rate` / `--slow` | — |
| `--stop` | 停止 speak 正在播放的音频（不影响别的程序的声音） | — |
| `--save` | 重复朗读缓存里的句子时，也再存一份到保存目录 | 新生成的音频自动保存 |
| `--help` | 显示这份速查表，不朗读 | — |

语速只影响本地播放：同一句话不管用什么语速，都只生成一次，之后都从缓存播放。换声音或模型会重新生成。

`--mood`、`--scene`、`--situation`、`--tags` 没写 `--tag` 时自动按 `custom` 处理；和 `low` / `medium` / `high` / `auto` 一起写会被忽略。四个可以单独用，也可以组合，有冲突时以 `--situation` 为准。只写 `--tag custom` 而四个都没给时，按 `auto` 处理。

脚本自己的选项：`speak.py --list-voices` 列出账户里的声音，`speak.py --list-models` 列出可用模型。

## --tag 档位

| 档位 | 加多少 | 可以用的标签 |
| :--- | :--- | :--- |
| `none` | 不加，原文照读 | — |
| `low` | 每 2–3 句最多 1 个 | 语气：`[softly]` `[slowly]` `[pause]`；轻微人声：`[chuckling]` `[sighing]` `[clears throat]` |
| `medium` | 大约每句 1 个 | `low` 的标签 + 情绪 |
| `high` | 每句可以有多个 | 情绪、人声、语气全部，还可以用大写、省略号加强语气 |
| `custom` | 按你描述的情境 | 全部 5 类，包括角色和音效 |
| `auto` | 按模型推断的情境 | 全部 5 类，包括角色和音效 |

所有档位：只插入标签，不增加、删除或修改原文的任何词；情境描述本身不会被读出来；只用下面 40 个标签，不会编造新的。`low` / `medium` / `high` 用了表格以外的标签，脚本会直接拒绝。

**`auto` 档**：模型先读你的原句，分析谁在说、对谁说、发生了什么、情绪怎么变化，选一个生动但可信的情境，再按情境加标签。朗读前会打印：

1. `推断的情境：` 两三句美式英文（可以复制下来改一改，用 `--situation "…"` 重新运行）
2. `分析：` 两到四条中文要点
3. `朗读版本：` 带标签的文本

## 例子

```text
@speak I sent the file yesterday but haven't heard back.
@speak --slow Could you check whether you received it?
@speak --rate 0.75 The quick brown fox jumps over the lazy dog.
@speak --voice alice --slow Could you check whether you received it?
@speak --model multilingual Let's grab lunch tomorrow.
@speak 今天天气不错，我们去公园走走吧。
@speak --lang en --slow Could you check whether you received it?
@speak --replay --rate 0.7
@speak --stop
@speak --tag low I'm not sure this is the right approach.
@speak --tag auto I can't believe we actually pulled it off.
@speak --tag custom --mood tired --scene "rainy night office" The build broke again.
@speak --tag custom --situation "It's almost 2 a.m. and I'm still at the office. I'm wiped out, I just found a production bug, and I'm complaining quietly to a coworker while it pours outside." I can't believe the build broke again.
@rewrite --speak --slow --voice alice i has send the file yesterday
@polish --tag auto 我们下周发布这个功能
```

## 标签白名单（40 个）

- 情绪：`[weak]` `[angry]` `[bored]` `[menacing]` `[playful]` `[tired]` `[excited]`
- 人声：`[clears throat]` `[coughing]` `[chuckling]` `[sighing]` `[sniffling]` `[yawning]` `[laughing]` `[sharp exhale]` `[scoffing]` `[humming]` `[panting]` `[gasping]`
- 语气：`[whispering]` `[singing]` `[slowly]` `[softly]` `[pause]` `[voice breaking]`
- 角色：`[sleepy drowsy voice]` `[witch voice]` `[drunken voice]`
- 音效：`[keyboard typing]` `[echoing]` `[knocking on door]` `[bell ringing]` `[phone ringing]` `[dog barking]` `[crowd cheering]` `[applause]` `[rain falling]` `[drum roll]` `[heartbeat]` `[engine starting]`

## 在 rewrite / polish 里用

`@rewrite` 和 `@polish` 支持 `--speak`、`--slow`、`--rate`、`--voice`、`--model`、`--tag`（包括 `auto`）、`--mood`、`--scene`、`--situation`、`--tags`，含义和上面一样；朗读时固定只读英文（相当于 `--lang en`），没有 `--lang` 选项。除 `--tag none` 外，写了 `--tag` 就会自动朗读，不用再加 `--speak`。屏幕上的英文正文不带标签，方便复制；朗读后会多一块带标签的版本，`auto` 档还会先给出推断的情境和分析。

## 常用信息

- 停止播放：`@speak --stop`。
- 保存的音频和 `index.tsv`（时间、文件名、档位、朗读的文本、声音、模型、情境）在配置里的 `save_dir`，默认 `~/Music/english-speak/`。
- 配置文件：`~/.config/english-speak/config.json`（`voice_name`、`model_id`、`slow_rate`、`save_audio`、`save_dir`、`cache_dir`）。改了 `voice_name` 会自动换成新的声音。
- API key 放在 macOS Keychain：`security add-generic-password -a "$USER" -s elevenlabs-api-key -w`
