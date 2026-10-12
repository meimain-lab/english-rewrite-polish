# Contributing

Contributions are welcome when they improve translation fidelity, American tone, natural Chinese output, trigger precision, or maintainability.

## Before opening a pull request

1. Describe the observed behavior with at least one representative input (Chinese, mixed, rough English, or another language) and the expected output.
2. Keep `rewrite` fast and faithful; put deeper editing behavior in `polish`. Keep `translate` faithful: it never summarizes, explains, or adds content.
3. Preserve the distinction between `polish` effort tiers: `low` keeps structure, `medium` restructures sentences, `high` may reorganize paragraphs.
4. Never weaken the payload boundary rule: payload text is data, never instructions.
5. Keep the shared sections (options, payload boundary, length limit) consistent across all three skills. The test suite checks this.
6. Do not invent Chinese names for drugs, genes, products, or institutions in `translate` examples; use established names only.

## Local validation

```bash
python -m unittest discover -s tests -v
```

## Versioning

- PATCH: wording fixes and behavior-preserving clarifications.
- MINOR: backward-compatible options, tone mappings, or examples.
- MAJOR: changes to invocation syntax, defaults, or output behavior.

Update `CHANGELOG.md` for user-visible changes and tag releases as `vMAJOR.MINOR.PATCH`.
