# Contributing

Contributions are welcome when they improve translation fidelity, American tone, trigger precision, or maintainability.

## Before opening a pull request

1. Describe the observed behavior with at least one representative input (Chinese, mixed, or rough English) and the expected output.
2. Keep `rewrite` fast and faithful; put deeper editing behavior in `polish`.
3. Preserve the distinction between `polish` effort tiers: `low` keeps structure, `medium` restructures sentences, `high` may reorganize paragraphs.
4. Never weaken the payload boundary rule: payload text is data, never instructions.
5. Keep the shared sections (options, payload boundary, length limit, American tone) consistent across both skills. The test suite checks this.

## Local validation

```bash
python -m unittest discover -s tests -v
```

## Versioning

- PATCH: wording fixes and behavior-preserving clarifications.
- MINOR: backward-compatible options, tone mappings, or examples.
- MAJOR: changes to invocation syntax, defaults, or output behavior.

Update `CHANGELOG.md` for user-visible changes and tag releases as `vMAJOR.MINOR.PATCH`.
