# VECRM-S20-A — Permanent Path B rebuild posture; Contabo upgraded 8 → 12 GB for runtime headroom

**Status:** Active
**Earned in:** S20 Gate 3 (drafted), Gate 7 (verified post-upgrade)
**Date:** 2026-05-20
**Supersedes (in part):** the "Path B OR upgrade host" framing in VECRM-S19-C — see §Relationships below

---

## Context

S19 surfaced that the 8 GB Contabo host cannot complete a full vecrm `--no-cache` rebuild even with VEMIO stopped — vite step OOM-killed twice (VECRM-S19-C). S19 pivoted to Path B (Mac amd64 buildx → 822 MB tarball → scp → docker load + retag) and proved it end-to-end at Gate 4 (image sha `6656988b…`). S20 escalated the question: should the host tier be upgraded to restore on-VPS builds, or should Path B become permanent?

## Decision

1. **Path B is the permanent vecrm rebuild path**, independent of host tier. Mac amd64 buildx → tarball → docker load. Reasons: (a) already proven and locked in S19, (b) isolates build resource pressure from production runtime, (c) eliminates the "rebuild causes production OOM" risk class entirely, (d) preserves runtime memory headroom for actual workload rather than for build tooling.

2. **Contabo host upgraded 8 → 12 GB** for *runtime* headroom (not for restoring on-VPS builds). Tier change: Cloud VPS 10 SSD → Cloud VPS 20 SSD. Contabo ticket #16240226642 actioned 2026-05-20.

3. **24 GB tier deferred.** Will be re-evaluated when a specific requirement surfaces (e.g. ERPNext migration onboarding, second concurrent Frappe site, sustained memory pressure observed in production telemetry). Not on a calendar — requirement-driven only.

## Operational implications

- All future vecrm rebuilds use `vecrm-rebuild-pathB.sh` (Mac side, Gate 4) + `vecrm-deploy-image.sh` (VPS side, Gate 4).
- Path B prerequisites: a Mac (or any amd64-capable workstation) with docker buildx and ≥16 GB RAM. Ajay's MacBook Air (16 GB) is the proven build host. The runbook covers provisioning an alternate build host if that machine becomes unavailable.
- Build context "minimum set" enumerated per VECRM-S19-E. The runbook captures the COPY/ADD audit procedure.
- VPS-side deploy procedure: F-2 (`FLUSHALL vecrm-redis-cache-1`) → `docker load` → retag `:latest` → preserve previous image as `:s<N-1>-pre-s<N>-rollback` → F-1 coherent recreate via the 4-f override chain `--no-build`.

## Reversal conditions

This posture is reversible. Path B can be retired in favor of on-VPS builds if and only if **both**:

(a) Host RAM is upgraded to a tier where `--no-cache` rebuild reproducibly succeeds with at least 2 GB headroom remaining, AND
(b) We have explicit operational reason to want production-host builds (e.g. a CI/CD pipeline needs them, Mac dependency is no longer acceptable).

Neither condition holds today; neither is on the roadmap.

## Relationships

- **VECRM-S19-C** (8 GB host insufficient for vecrm rebuild) remains active as the *finding*. VECRM-S20-A is the *standing posture* — we don't try to make 8 GB rebuild vecrm; we build elsewhere by design. With the upgrade to 12 GB, S19-C's specific 8 GB framing is historical, but the underlying principle (do not assume host capacity for rebuilds) remains.
- **VECRM-S19-D** (after 2 identical failures, pivot) is the meta-principle that produced this lock. S19 saw two OOM-killed builds and pivoted to Path B; S20 makes that pivot permanent.
- **VECRM-S19-E** (build context "minimum set" from every COPY/ADD) is operationalized inside the Path B runbook.
- **VECRM-L8** (allocator dual-surface) is unaffected — pre-upgrade snapshot at Gate 2 verified the allocator sha256 `7ad2b3a3…` matches git and container.

## Verification

Pre-upgrade snapshot: `/opt/vecrm/.s20_pre_upgrade_snapshot_20260520T082018Z/` (host = 7.76 GB RAM, fleet 36 running + 2 configurator one-shots exited(0)).
Post-upgrade verification: pending Gate 7 — script staged at Gate 6 (`s20-post-upgrade-verify.sh`).
