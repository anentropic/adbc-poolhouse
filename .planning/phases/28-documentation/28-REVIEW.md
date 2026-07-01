---
phase: 28-documentation
reviewed: 2026-06-29T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - docs/scripts/gen_ref_pages.py
  - docs/src/guides/async.md
  - docs/src/guides/configuration.md
  - docs/src/index.md
  - docs/src/changelog.md
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-06-29T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the one executable file (`docs/scripts/gen_ref_pages.py`) and four
Markdown doc surfaces changed in the async-documentation phase.

The generator change is **correct and safe**. The appended `_ASYNC_REFERENCE_BLOCK`
targets the real module paths (`adbc_poolhouse._async._pool.AsyncPool`,
`._async._connection.AsyncConnection`, `._async._cursor.AsyncCursor`) — all three
classes exist at exactly those paths. The code comment's claim that the per-block
`filters: ["!^__"]` **replaces** (not merges with) the global `mkdocs.yml` filter
`["!^_"]` is accurate mkdocstrings semantics, and `mkdocs.yml` does carry the
`!^_` global filter as documented. There are no path-traversal, injection, or
secret-handling concerns: the script only reads `src/**/*.py` and writes into the
in-memory `mkdocs_gen_files` virtual FS; no user input, no shell, no eval.

`uv run mkdocs build --strict` (via `.venv/bin/mkdocs build --strict`) **exits 0**.
The only console noise is a third-party vendor advertising banner (ProperDocs) and
pre-existing INFO-level notes about the auto-generated `reference/` relative links;
neither fails the strict gate.

Doc-accuracy auditing surfaced one substantive factual inaccuracy (a method call
that does not exist on the documented type) plus minor link-precision and
changelog-hygiene nits. No credential/secret literals beyond the intentional
`password="s3cret"` masking demo, and no RST-vs-Markdown docstring leakage in the
async source.

All 18 distinct `[...][adbc_poolhouse.SYM]` cross-references in the changed Markdown
resolve to members of the package `__all__`.

## Warnings

### WR-01: `pool.checkedout()` is documented but does not exist on `AsyncPool`

**File:** `docs/src/guides/async.md:198`
**Issue:** The cancellation section states:

> "The connection count stays correct, so `pool.checkedout()` never reports a
> connection that the pool has already reclaimed."

`AsyncPool` exposes only `__init__`, `connect`, and `close`
(`src/adbc_poolhouse/_async/_pool.py:67,89,104`). There is no `checkedout()`
method on the async wrapper — `checkedout()` lives on the underlying SQLAlchemy
`QueuePool` (referenced internally in `_async/_connection.py:257,301` as "the sync
pool's `checkedout()`"), which the async surface does not re-expose. A reader who
copies `pool.checkedout()` against an `AsyncPool` will hit `AttributeError`. This
is a factual/technical-accuracy defect in consumer-facing prose, not a build break.
**Fix:** Either reword to describe the invariant without naming a non-existent API,
e.g.

```
The pool's internal checkout count stays correct, so it never reports a
connection that the pool has already reclaimed.
```

or, if exposing the accessor is intended, add a `checkedout()` passthrough to
`AsyncPool` so the doc matches the code.

## Info

### IN-01: `AsyncConnection.invalidate` link points to the same page's "See also", not the symbol

**File:** `docs/src/guides/async.md:196`
**Issue:** `[`AsyncConnection.invalidate`](#see-also)` links the symbol name to the
in-page `## See also` section rather than to the generated API-reference entry for
`invalidate`. The anchor resolves (a `## See also` heading exists, line 211), so it
is not a broken link, but the link target is misleading: clicking a method name
jumps to a list of related pages instead of that method's docs.
**Fix:** Point it at the reference page anchor for the method, e.g.
`[`AsyncConnection.invalidate`](../reference/adbc_poolhouse.md#adbc_poolhouse._async._connection.AsyncConnection.invalidate)`,
or drop the link and leave the name as inline code if a stable anchor is not
available.

### IN-02: "See also" entry links a method to the bare reference index, not its anchor

**File:** `docs/src/guides/async.md:217-219`
**Issue:** The See-also bullet links
`[`AsyncConnection.invalidate`](../reference/)` to the reference *index root*
rather than to the method's own anchor. mkdocs reports this as an "unrecognized
relative link" (INFO, non-fatal). The reader lands on the reference landing page
and must hunt for the method.
**Fix:** Link to the concrete generated anchor (same target suggested in IN-01) so
the deep-link actually lands on `AsyncConnection.invalidate`.

### IN-03: Changelog has both an empty `## [Unreleased]` and a `## [1.4.0] - Unreleased`

**File:** `docs/src/changelog.md:5-7`
**Issue:** Two stacked unreleased headings — an empty `## [Unreleased]` immediately
followed by `## [1.4.0] - Unreleased`. The empty `## [Unreleased]` renders as a
content-less section and is redundant now that the concrete `1.4.0` block carries
the unreleased work. Minor hygiene / reader-confusion issue.
**Fix:** Remove the empty `## [Unreleased]` placeholder, or fold it so there is a
single unreleased section. Keep one convention.

### IN-04: Index async example omits the "synchronous: no await" cue present in the guide

**File:** `docs/src/index.md:79`
**Issue:** `pool = create_async_pool(DuckDBConfig(...))` on the homepage drops the
clarifying `# synchronous: no await` comment that the guide carries
(`docs/src/guides/async.md:53`). The code is correct, but the homepage is the
highest-traffic surface and is exactly where a reader is most likely to wrongly
`await create_async_pool(...)`. Consistency nit, not a correctness defect.
**Fix:** Add the same inline cue:
`pool = create_async_pool(DuckDBConfig(database="/tmp/warehouse.db"))  # synchronous: no await`

---

_Reviewed: 2026-06-29T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
