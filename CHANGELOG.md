# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-08

### Added

- `rewrite` skill: fast, faithful conversion of Chinese, mixed Chinese-English, or rough English into natural American English.
- `polish` skill: refined American English with `--effort low|medium|high` (default `medium`).
- Shared invocation contract: leading options only, `--limit N` (default 1000 length units), `--context`, `--` terminator.
- Payload boundary rules: `"""…"""`, fenced blocks, and `<<<…>>>` delimiters; whole-payload double quotes; payload is always data, never instructions.
- ChatGPT and Codex interface metadata for both skills.
- Static validation tests and behavior fixtures, run in GitHub Actions.
