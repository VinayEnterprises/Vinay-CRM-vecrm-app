# VECRM-S20-A — VPS-side `docker build` from /opt/vecrm/ is the rebuild path; Contabo upgraded 8 → 12 GB for runtime headroom

**Status:** Active (revised in S21 — see §Revision history)
**Earned in:** S20 Gate 3 (drafted with drift), Gate 7 (12 GB upgrade verified), S21 PD-S20-DOCS-DRIFT (drift corrected)
**Date:** 2026-05-20 (original), 2026-05-20 (S21 revision)
**Supersedes (in part):** the "Path B OR upgrade host" framing in VECRM-S19-C — see §Relationships below

---

## Context

S19 surfaced that the 8 GB Contabo host could not complete a full vecrm `--no-cache` rebuild even with VEMIO stopped — vite step OOM-killed twice (VECRM-S19-C). S19 pivoted to Path B (Mac amd64 buildx → 822 MB tarball → scp → docker load + retag) as a tactical workaround and proved it end-to-end at Gate 4 (image sha `6656988b…`).

S20 escalated the question: should the host tier be upgraded to restore on-VPS builds, or should Path B (Mac buildx) become permanent?

S20 took two actions: upgraded Contabo 8 → 12 GB (ticket #16240226642) to restore runtime headroom, AND drafted this lock (original version) framing Path B as "permanent rebuild path independent of host tier."

The S20 actual build (PR #5 and PR #6 deploys) was VPS-side `docker build`, not Mac buildx — invalidating the "Path B permanent" framing the same day it was drafted. Recon during S21 PD-S20-DOCS-DRIFT closure confirmed that VPS-side `docker build` has been the canonical build mechanism since S5. Mac buildx was an S19 OOM-driven contingency that never matched production reality.

## Decision

1. **VPS-side `docker build` from `/opt/vecrm/` is the canonical vecrm rebuild path.** This is what has been done from S5 through S20 (with S19 as the OOM-driven exception). The runbook at `docs/runbooks/rebuild/` captures the procedure. Future builds use this mechanism unless host capacity constraints force a temporary contingency.

2. **Contabo host upgraded 8 → 12 GB** for runtime headroom. Tier change: Cloud VPS 10 SSD → Cloud VPS 20 SSD. Contabo ticket #16240226642 actioned 2026-05-20. RAM 7.76 → 11.68 GiB (+3.92 GiB). CPU 4 → 6 cores (bonus from tier shift). Swap usage eliminated.

3. **24 GB tier deferred.** Re-evaluated when a specific requirement surfaces (ERPNext migration, second concurrent Frappe site, sustained memory pressure). Requirement-driven, not calendar-driven.

4. **Mac buildx (the original "Path B" workflow) is retired as a documented procedure.** Preserved in git history (PR #4 commit `fe0e98d`) for archeological reference. If a future host-capacity crisis recreates the S19 OOM condition, the first response is host tier upgrade, not workflow change.

## Operational implications

- All future vecrm rebuilds use the procedure at `docs/runbooks/rebuild/README.md`, executed on the VPS in `/opt/vecrm/`.
- Build context: `/opt/vecrm/` (Containerfile at `images/custom/Containerfile`).
- apps.json pins `frappe_crm` at v1.71.3 only. vecrm itself is COPYed via Containerfile's `S13-COPY-NOT-CLONE` directive from `/opt/vecrm/vecrm-src/`.
- Containerfile asserts `VECRM_FETCH_GATE` (COPYed source has 6 controller files) and `VECRM_POSTINSTALL_GATE` (voucher_counter.py sha256 = `7ad2b3a3…`). Build fails fast if either gate fails.
- Build args: `FRAPPE_BRANCH=v16.18.2` and `FRAPPE_PATH=https://github.com/frappe/frappe` set on the command line (Containerfile default `version-16` is OVERRIDDEN by the invocation pin).
- Build runtime: ~4 min on 12 GB host with current ~80 MB build context (see PD-S21-CTXBLOAT pendency for context-bloat optimization opportunity).
- Deploy procedure: F-2 (`FLUSHALL vecrm-redis-cache-1`) → preserve previous `:latest` as `:s<N-1>-pre-s<N>-rollback` → retag new image as `:latest` → F-1 coherent recreate via the 4-f override chain `--no-build`.
- Three-tier rollback ladder maintained at session boundaries: `:latest`, `:s<N>-pre-fix-rollback` (intra-session), `:s<N-1>-pre-s<N>-rollback` (previous session).

## Reversal conditions

This posture is reversible. The VPS-side build path can be retired if **any** of:

(a) Host RAM falls below the threshold required for reproducible `--no-cache` rebuild with at least 2 GB headroom, OR
(b) An operational reason emerges to remove Mac/local dependency from any build path, OR
(c) The Frappe ecosystem's build tooling changes in a way that breaks the current Containerfile pattern.

None of (a)–(c) holds today or is on the roadmap.

## Relationships

- **VECRM-S19-C** (8 GB host insufficient) — finding remains valid; specific 8 GB framing is historical now that the host is 12 GB.
- **VECRM-S19-D** (after 2 identical failures, pivot) — the S19 pivot was contingent, not permanent. S20 made the inverse correction.
- **VECRM-S19-E** (build context "minimum set") — operationalized in the new runbook; basis for PD-S21-CTXBLOAT.
- **VECRM-S19-F** (verify against source not handover prose) — the original S20-A drafting violated this principle. The S21 revision applies S19-F retroactively to S20-A itself.
- **VECRM-S20-E** (own-session output drift) — earned from this lock's own original drift. See `VECRM-S20-E.md`.
- **VECRM-L8** (allocator dual-surface) — preserved across rebuilds; post-rebuild verification of voucher_counter.py sha is part of the deploy procedure.

## Revision history

- **2026-05-20 (S20 Gate 3 original):** Drafted as "Path B (Mac amd64 buildx) is the permanent vecrm rebuild path, independent of host tier." This framing was invalidated the same day by S20's actual VPS-side build for PR #5 and PR #6 deploys. Drift filed as PD-S20-DOCS-DRIFT.
- **2026-05-20 (S21 PD-S20-DOCS-DRIFT closure):** Decision section rewritten to reflect actual production mechanism. 12 GB upgrade and 24 GB deferral facts preserved. Mac buildx framed as retired contingency. Cross-references to `docs/runbooks/rebuild/` and `VECRM-S20-E.md` added.

## Verification

Pre-upgrade snapshot: `/opt/vecrm/.s20_pre_upgrade_snapshot_20260520T082018Z/`.
Post-upgrade verification: `/opt/vecrm/.s20_gate7_verify_20260520T084337Z.log` — all criteria PASS.
S20 production builds: `build-s20-20260520T111024Z.log` (PR #5 image `47aa9e51…`), `build-s20-fix-20260520T132259Z.log` (PR #6 image `31383918a699…`). Both built VPS-side.
S21 PD-S20-DOCS-DRIFT closure: revision in PR #8.
