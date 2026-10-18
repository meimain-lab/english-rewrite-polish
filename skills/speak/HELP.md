# speak 速查

用 ElevenLabs 把文字读出来，用来练听力和跟读。单独使用 `@speak` 时不限语言，模型支持的语言都能读（英文、中文、日语、韩语等），按原文读，不翻译；从 `@rewrite` / `@polish` 调用时固定只读英文。

```text
@speak [选项] [文本]
```

不写文本时，读上一条 `@rewrite` / `@polish` 的英文结果（不读 `---` 之后的讲解）。音频标签永远是英文，不管正文是什么语言。选项只在最前面识别，写在文本后面的一律当作文本。

## 选项

| 选项 | 作用 | 默认 |
| :--- | :--- | :--- |
| `--slow` | 用 `slow_rate` 放慢播放 | 关；`slow_rate` 默认 0.88 |
| `--rate N` | 播放语速，0.50–1.50，最多两位小数，比如 `0.88`。`--speed` 是它的别名。和 `--slow` 同时写时以 `--rate` 为准 | 1 |
| `--replay` | 重放上一条音频，不调用 API、不耗 credits。可以配合 `--rate` / `--slow` | — |
| `--save` | 重复朗读缓存里的句子时，也再存一份到保存目录 | 新生成的音频自动保存 |
| `--voice ID` | 这次改用另一个 voice_id | 配置里的声音 |
| `--lang CODE` | 指定语言（两位 ISO 639-1 代码，如 `en`、`zh`、`ja`）；`--lang en` 只读英文，文本里有其他文字会报错。`auto` 表示让模型自己判断 | `auto` |
| `--tag LEVEL` | 自动加音频标签，档位见下表。只写 `--tag` 不带档位等于 `medium` | `none` |
| `--mood "…"` | custom：情绪，比如 `tired` | — |
| `--scene "…"` | custom：环境，比如 `rainy night office` | — |
| `--situation "…"` | custom：用一段话描述说话时的情境和状态，最多 500 字 | — |
| `--tags "[…] […]"` | custom：手动指定必须用到的标签 | — |
| `--help` | 显示这份速查表，不朗读 | — |

语速只影响本地播放：同一句话不管用什么语速，都只生成一次，之后都从缓存播放。

`--mood`、`--scene`、`--situation`、`--tags` 没写 `--tag` 时自动按 `custom` 处理；和 `low` / `medium` / `high` 一起写会被忽略。四个可以单独用，也可以组合，有冲突时以 `--situation` 为准。

脚本自己的选项：`speak.py --list-voices` 列出账户里的声音，`speak.py --list-models` 列出可用模型。

## --tag 档位

| 档位 | 加多少 | 可以用的标签 |
| :--- | :--- | :--- |
| `none` | 不加，原文照读 | — |
| `low` | 每 2–3 句最多 1 个 | 语气：`[softly]` `[slowly]` `[pause]`；轻微人声：`[chuckling]` `[sighing]` `[clears throat]` |
| `medium` | 大约每句 1 个 | `low` 的标签 + 情绪 |
| `high` | 每句可以有多个 | 情绪、人声、语气全部，还可以用大写、省略号加强语气 |
| `custom` | 按你描述的情境 | 全部 5 类，包括角色和音效 |

所有档位：只插入标签，不增加、删除或修改原文的任何词；情境描述本身不会被读出来；只用下面 40 个标签，不会编造新的。

## 例子

```text
@speak I sent the file yesterday but haven't heard back.
@speak --slow Could you check whether you received it?
@speak --rate 0.75 The quick brown fox jumps over the lazy dog.
@speak 今天天气不错，我们去公园走走吧。
@speak --lang en --slow Could you check whether you received it?
@speak --replay --rate 0.7
@speak --tag low I'm not sure this is the right approach.
@speak --tag custom --mood tired --scene "rainy night office" The build broke again.
@speak --tag custom --situation "深夜加班到两点，很累，刚发现线上 bug，小声跟同事抱怨，窗外在下雨" I can't believe the build broke again.
@rewrite --speak --slow i has send the file yesterday
@polish --tag medium 我们下周发布这个功能
```

## 标签白名单（40 个）

- 情绪：`[weak]` `[angry]` `[bored]` `[menacing]` `[playful]` `[tired]` `[excited]`
- 人声：`[clears throat]` `[coughing]` `[chuckling]` `[sighing]` `[sniffling]` `[yawning]` `[laughing]` `[sharp exhale]` `[scoffing]` `[humming]` `[panting]` `[gasping]`
- 语气：`[whispering]` `[singing]` `[slowly]` `[softly]` `[pause]` `[voice breaking]`
- 角色：`[sleepy drowsy voice]` `[witch voice]` `[drunken voice]`
- 音效：`[keyboard typing]` `[echoing]` `[knocking on door]` `[bell ringing]` `[phone ringing]` `[dog barking]` `[crowd cheering]` `[applause]` `[rain falling]` `[drum roll]` `[heartbeat]` `[engine starting]`

## 在 rewrite / polish 里用

`@rewrite` 和 `@polish` 支持 `--speak`、`--slow`、`--rate`、`--tag`、`--mood`、`--scene`、`--situation`、`--tags`，含义和上面一样；朗读时固定只读英文（相当于 `--lang en`），没有 `--lang` 选项。除 `--tag none` 外，写了 `--tag` 就会自动朗读，不用再加 `--speak`。屏幕上的英文正文不带标签，方便复制；朗读后会多一行带标签的版本。

## 常用命令

```bash
pkill -x afplay
```

- 停止播放：运行上面的命令。
- 保存的音频和 `index.tsv`（时间、文件名、档位、朗读的文本）在配置里的 `save_dir`，默认 `~/Music/english-speak/`。
- 配置文件：`~/.config/english-speak/config.json`（声音、模型、`slow_rate`、`default_tag`、`save_audio`）。
- API key 放在 macOS Keychain：`security add-generic-password -a "$USER" -s elevenlabs-api-key -w`
