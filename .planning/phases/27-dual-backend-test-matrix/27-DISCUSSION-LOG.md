# Phase 27: Dual-Backend Test Matrix - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 27-Dual-Backend Test Matrix
**Areas discussed:** EDGE-27 retrofit scope, Snowflake cassette matrix, Arrow stability metric, Limiter-stress design

---

The user opted to review all gray-area assumptions in a single pass ("Just show me
assumptions so we can do it all at once") rather than a turn-by-turn discussion.
Recommended assumptions were presented for all four areas plus cross-cutting
discretion items; the user did not override any, accepting them as-is.

---

## EDGE-27 retrofit scope (A1)

| Option | Description | Selected |
|--------|-------------|----------|
| Light touch + meta-guard | Add EDGE-27 source-scan meta-test; fix only violators; leave existing ×20-stable EDGE tests as-is | ✓ |
| Full normalization sweep | Rewrite all ~10 existing EDGE files to one uniform parametrization shape | |

**User's choice:** Light touch + meta-guard (accepted assumption).
**Notes:** A blanket sweep risks reintroducing the lost-wakeup / MockClock-autojump
landmines those tests were hardened against. EDGE-27 requires the guard, not uniform structure.

---

## Snowflake cassette matrix (A2)

| Option | Description | Selected |
|--------|-------------|----------|
| Cassette = read-path surface only | Cross-product on lifecycle + fetch surface; stub-gated mechanics stay DuckDB+stub | ✓ |
| Full 2×2 cross-product | Force every EDGE test through the cassette too | |

**User's choice:** Read-path surface only (accepted assumption).
**Notes:** The `ReplayCursor` is replay-only — cannot block-gate a worker and lacks
`adbc_cancel` (Phase 25) — so it cannot back deterministic gating tests.

---

## Arrow stability metric (A3)

| Option | Description | Selected |
|--------|-------------|----------|
| `pyarrow.total_allocated_bytes()` delta | Deterministic pyarrow-native signal across N≥100 cycles; + reset-event count | ✓ |
| Process RSS | Measure resident memory growth | |
| Reset-event count only | Only assert `_release_arrow_allocators` fired per checkin | |

**User's choice:** `total_allocated_bytes` delta + reset-event belt-and-braces (accepted assumption).
**Notes:** RSS is non-deterministic → forces a flaky tolerance.

---

## Limiter-stress design (A4)

| Option | Description | Selected |
|--------|-------------|----------|
| Stub-gated deterministic flood + real-clock watchdog | EDGE-12 pattern; running-max == bound; real-DuckDB smoke flood; `time.monotonic()` watchdog | ✓ |
| Real-DuckDB stress as primary | Drive the flood entirely through a live in-proc pool | |

**User's choice:** Stub-gated flood + real-clock watchdog (accepted assumption).
**Notes:** Never `anyio.fail_after` for deadlock detection — it autojumps under the
trio MockClock (Phase 24/25 landmine).

---

## Claude's Discretion

- EDGE-30: extend the harness guard to ban positive-duration `sleep(...)` literals in
  `tests/async/` timeout/cancel tests (`sleep(0)` checkpoints allowed).
- ×20 loop-stability gate on every new/touched test before phase completion.
- Test file naming and CI wiring (dual-backend job; excluded from the PKG-04 no-anyio job).

## Deferred Ideas

None — discussion stayed within phase scope.
</content>
