# VECRM-S19-D — After 2 identical failures, do not retry; pivot

**Status:** Active (promoted from candidate to active at S20 Gate 0 adjudication)
**Earned in:** S19
**Date:** 2026-05-20 (S20 promotion)

---

## Statement

If the same approach fails twice with the same root cause, do not retry a third time. Pivot to a fundamentally different approach.

The third attempt's expected outcome is identical to the first two. The information-theoretic value of running it is zero. The cost is time and (in production contexts) operational risk.

## Why it exists

S19 saw two consecutive `--no-cache` vecrm rebuilds on the 8 GB host. Both OOM-killed at the vite step. The natural next step would have been a third attempt with some minor tweak ("more swap", "stop more containers", "smaller chunk size"). That third attempt would almost certainly have produced the same OOM.

The correct response was to pivot — to Path B (Mac amd64 buildx → tarball → load) — which sidesteps the failure mode entirely. The pivot succeeded at the first attempt.

## How to apply

After any 2 consecutive failures of the same operation with the same root cause:

1. **Stop.** Do not retry without changing something fundamental.
2. **State the root cause explicitly.** Not "the build failed" but "vite was OOM-killed at memory peak 3.5 GiB on a host with 4.9 GiB available."
3. **Generate at least 2 alternative approaches** that DO NOT share the failure-mode-relevant constraint.
4. **Pick one. Adjudicate before running.**
5. **If the pivot also fails, the problem may be at a higher level** — escalate analysis, not retry frequency.

## What this is NOT

This lock does NOT prohibit retries when the root cause is **non-deterministic** (network timeout, transient API rate-limit, race condition). Those are legitimate retry candidates. The lock applies when the failure is **structurally deterministic** — when the third attempt's expected outcome is the same as the first two.

The distinction is whether the underlying cause was identified as deterministic. "Both attempts OOM-killed at vite" = deterministic = pivot. "Both attempts timed out talking to GitHub" = non-deterministic = retry with backoff is fine.

## Meta-principle

This lock is itself an application of the recon-first discipline: spend more time understanding why something failed before throwing more resources at making it succeed.

## Related

- [VECRM-S19-C](VECRM-S19-C.md) — The 8 GB rebuild failure that produced this lock
- [VECRM-S20-A](VECRM-S20-A.md) — The pivot (Path B) made permanent
