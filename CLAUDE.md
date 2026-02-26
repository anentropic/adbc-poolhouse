# adbc-poolhouse — Project Instructions

## Documentation Quality Gate

For all plans in phases >= 7, include the docs-author skill in `<execution_context>`:

```
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
```

Documentation is a completion requirement for every phase from Phase 7 onwards, not only plans explicitly labelled as documentation tasks. A phase is not complete until:

- All new public symbols have Google-style docstrings (Args/Returns/Raises)
- Key entry points have an Examples block
- Any new consumer-facing behaviour is reflected in the relevant guide
- `uv run mkdocs build --strict` passes
- Humanizer pass applied to all new or substantially rewritten prose
