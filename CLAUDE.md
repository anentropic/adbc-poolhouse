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

## Opening pull requests

When you open a pull request, ask the user whether it needs a review. If they say yes:

1. Mark the PR ready for review, since the review bot skips drafts.
2. Request a review from `anentropic-reviewbot`. Claude then posts inline comments and a summary on the PR.
3. Watch the PR and address the review comments and any CI failures as they come in, until CI is green and no blocking comments are left open.

To get another review after pushing fixes, request one from `anentropic-reviewbot` again.
