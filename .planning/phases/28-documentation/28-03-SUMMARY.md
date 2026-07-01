---
phase: 28-documentation
plan: 03
subsystem: documentation
tags: [configuration, changelog, async, experimental, docs-gate]
requires:
  - "index.md Async section listing the [async] extra + three entry points (28-01, confirmed not duplicated)"
  - "async.md guide with the experimental caveat and concurrency limits (28-01)"
provides:
  - "configuration.md documents the [async] extra and the three async entry points (DOCS-03 gap closed)"
  - "changelog.md has a v1.4.0 entry marking the async API experimental (D-28-01 changelog leg)"
affects:
  - "docs/src/guides/configuration.md (new Async pools subsection + See also link)"
  - "docs/src/changelog.md (new [1.4.0] entry)"
tech-stack:
  added: []
  patterns:
    - "Config-reference pointer pattern: name the extra + entry points + limiter-sizing, cross-link the guide rather than re-explaining it"
key-files:
  created: []
  modified:
    - "docs/src/guides/configuration.md"
    - "docs/src/changelog.md"
decisions:
  - "Async subsection placed after Pool tuning (the async CapacityLimiter is sized pool_size + max_overflow, so the existing tuning fields govern async concurrency too)"
  - "Changelog entry uses [1.4.0] - Unreleased matching the dated-section style, kept under the bare [Unreleased] marker; async explicitly marked experimental; no deferred feature listed as shipped"
  - "index.md confirmed to already cover the extra + entry points (28-01) — configuration.md cross-references rather than duplicating"
metrics:
  duration: "~10min"
  completed: "2026-06-29"
  tasks: 2
  files: 2
---

# Phase 28 Plan 03: Configuration Async Section + v1.4.0 Experimental Changelog Summary

Close the `configuration.md` async gap (DOCS-03) by documenting the `[async]` extra and the three async entry points with a limiter-sizing note and a guide cross-link, and add a v1.4.0 changelog entry marking the async API experimental (D-28-01 changelog leg).

## What Was Built

DOCS-03 is satisfied and the D-28-01 changelog leg is closed.

- `docs/src/guides/configuration.md` gained an **Async pools** subsection (placed after Pool tuning) that names the `[async]` extra and its install command, names `create_async_pool` / `managed_async_pool` / `close_async_pool` as mirrors of the sync entry points sharing the same `pool_size` / `max_overflow` / `timeout` / `recycle` / `pre_ping` defaults, states each async pool's `CapacityLimiter` is sized to `pool_size + max_overflow`, leads with a `!!! warning "Experimental"` admonition, and cross-links `async.md` from both the section and the page's existing See also list.
- `docs/src/changelog.md` gained a `## [1.4.0] - Unreleased` entry under `## [Unreleased]`, with a `### Features` subsection summarizing the async API (anyio-based extra, three entry points, `AsyncPool`/`AsyncConnection`/`AsyncCursor` with the awaited DBAPI surface incl. `fetch_arrow_table`, per-pool `CapacityLimiter`, shielded checkin, `adbc_cancel`-based cancellation), explicitly marked **experimental**, with the note that the sync path is unchanged and gains no async dependency.

`.venv/bin/mkdocs build --strict` exits 0. No async listing was added to `index.md` (28-01 already covers the extra + entry points — confirmed, not duplicated).

## How It Was Built

The configuration subsection is a config-reference pointer, not a second copy of the guide: it names the extra, the entry points, the limiter-sizing relationship to the existing tuning fields, and links `async.md` for the walkthrough and full caveat. The limiter-sizing wording (`pool_size + max_overflow`) was taken verbatim from the existing `async.md` framing (line 120) to stay consistent across pages.

The changelog entry matches the file's existing heading convention: a dated-style `## [1.4.0]` section (with `- Unreleased` consistent with the bare `## [Unreleased]` placeholder above it) and a `### Features` subsection in the existing terse bullet style. Async is marked experimental in the first bullet; no deferred feature (Arrow streaming, `adbc_ingest`, DataFrame fetches, async metadata, async prepared statements) is listed as shipped.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' automated `grep` verifications passed on first run, and `mkdocs build --strict` passed after each task.

## Notes / Observations

- `index.md` already lists the `[async]` extra, all three entry points, and the experimental flag (verified via grep at lines 67–96). The configuration page cross-references the guide rather than re-listing them, honoring the "no duplication" verification clause.
- The `mkdocs build --strict` run emits only pre-existing INFO notices about unrecognized `reference/` relative links shared by `index.md` and `async.md`; the same notice now also lists `configuration.md` because the page links `../reference/` (a pre-existing See also link, not introduced by this plan). No warnings or errors.
- The docs-author humanizer patterns were applied to the new prose: no promotional language, no AI vocabulary, second person, em dashes kept to at most one per paragraph.

## Threat Flags

None — documentation-only change, no new network endpoints, auth paths, file access, or schema changes. T-28-03-I (snippet info disclosure) honored: the only install snippet is `pip install adbc-poolhouse[async]`, no secret literals. T-28-03-T (changelog accuracy) accepted: the entry is sourced from the ROADMAP milestone scope, async marked experimental, no deferred feature listed as shipped.

## Verification

- Task 1 automated check: `[async]`, `create_async_pool`, `managed_async_pool`, `close_async_pool`, and `async.md` all present in `configuration.md` — OK.
- Task 2 automated check: `1.4.0`, `experimental` (case-insensitive), `async`, and `CapacityLimiter`/`[async]` all present in `changelog.md` — OK.
- `.venv/bin/mkdocs build --strict` exits 0 after both edits.
- No async listing duplicated into `index.md` (28-01 coverage confirmed).

## Self-Check: PASSED

- FOUND: docs/src/guides/configuration.md (modified, committed 5d03240)
- FOUND: docs/src/changelog.md (modified, committed 47674f9)
- FOUND: commit 5d03240
- FOUND: commit 47674f9
