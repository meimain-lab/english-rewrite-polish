# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-14

### Added

- `rewrite --explain`: after the rewritten text, a numbered list explains each grammar, spelling, or wording issue in Simplified Chinese, keeping source fragments, corrections, and grammar terms in English (主谓一致（subject-verb agreement）). Chinese input gets notes on the expressions that a literal translation would get wrong.
- Reference parser and tests for the `--explain` flag; behavior cases R11–R14.

## [0.2.0] - 2026-10-12

### Added

- `translate` skill: faithful translation into natural Simplified Chinese by default, from English, mixed Chinese-English, or other languages (Japanese, Korean, French, Italian, Russian, and more).
- Automatic direction: purely Chinese input is translated into American English; `--to` forces any target, including `zh-TW` and `zh-HK`.
- Translate options: `--to`, `--from`, `--gloss auto|off|full`, and `--bilingual`.
- Chinese output conventions: conventional English terms kept, first-occurrence English glosses, original source titles and official names, full-width punctuation, Chinese-Latin spacing, no Kangxi radical look-alikes.
- Reference parser support for translate options and direction; tests for language aliases, direction, multi-script length counting, and Kangxi radicals.
- Behavior cases T1–T14.

### Changed

- Repository title is now "Rewrite, Polish & Translate". The repository name is unchanged.
- The reference parser now counts words in any space-separated script (Latin, Cyrillic, Greek) as length units. `rewrite` and `polish` behavior is unchanged.

## [0.1.0] - 2026-10-08

### Added

- `rewrite` skill: fast, faithful conversion of Chinese, mixed Chinese-English, or rough English into natural American English.
- `polish` skill: refined American English with `--effort low|medium|high` (default `medium`).
- Shared invocation contract: leading options only, `--limit N` (default 1000 length units), `--context`, `--` terminator.
- Payload boundary rules: `"""…"""`, fenced blocks, and `<<<…>>>` delimiters; whole-payload double quotes; payload is always data, never instructions.
- ChatGPT and Codex interface metadata for both skills.
- Static validation tests and behavior fixtures, run in GitHub Actions.
