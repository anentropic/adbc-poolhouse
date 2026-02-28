---
phase: quick-3
plan: 1
subsystem: docs
tags: [docs, guides, foundry, hyperlink]
dependency_graph:
  requires: []
  provides: []
  affects: [docs/src/guides/databricks.md, docs/src/guides/redshift.md, docs/src/guides/trino.md, docs/src/guides/mssql.md, docs/src/guides/teradata.md]
tech_stack:
  added: []
  patterns: []
key_files:
  created: []
  modified:
    - docs/src/guides/databricks.md
    - docs/src/guides/redshift.md
    - docs/src/guides/trino.md
    - docs/src/guides/mssql.md
    - docs/src/guides/teradata.md
decisions: []
metrics:
  duration: ~2 min
  completed: 2026-02-28
---

# Quick Task 3: Foundry Driver Guide Hyperlinks Summary

**One-liner:** Hyperlinked "Foundry installation guide" text in all five Foundry driver pages pointing to https://arrow.apache.org/adbc/current/driver/installation.html

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add Foundry installation guide hyperlinks to all warehouse guides | 061de45 | databricks.md, redshift.md, trino.md, mssql.md, teradata.md |

## What Was Done

Replaced the plain-text "Follow your Foundry installation guide to install it" with a markdown hyperlink in four files (databricks.md, redshift.md, trino.md, mssql.md). For teradata.md, the sentence was missing entirely — it was added after the existing "distributed via the ADBC Driver Foundry, not PyPI." line.

All five files now contain the linked text:
`Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using ...`

`uv run mkdocs build --strict` passed with no errors.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing content] teradata.md lacked the "Follow your Foundry installation guide" sentence entirely**
- **Found during:** Task 1
- **Issue:** The plan referenced replacing line 8 in teradata.md with the same text as the other four files, but the sentence was absent — teradata.md only had the "distributed via Foundry" sentence without the install instruction sentence.
- **Fix:** Added the hyperlinked install instruction sentence after "The Teradata ADBC driver is distributed via the ADBC Driver Foundry, not PyPI."
- **Files modified:** docs/src/guides/teradata.md
- **Commit:** 061de45

## Self-Check

- [x] docs/src/guides/databricks.md contains hyperlink
- [x] docs/src/guides/redshift.md contains hyperlink
- [x] docs/src/guides/trino.md contains hyperlink
- [x] docs/src/guides/mssql.md contains hyperlink
- [x] docs/src/guides/teradata.md contains hyperlink
- [x] mkdocs build --strict passes
- [x] Commit 061de45 exists

## Self-Check: PASSED
