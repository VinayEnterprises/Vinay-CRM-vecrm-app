# VECRM-S19-C — 8 GB host insufficient for vecrm full rebuild (historical)

**Status:** Active (promoted at S20 Gate 0); SUPERSEDED IN PART by VECRM-S20-A
**Earned in:** S19
**Date:** 2026-05-20 (S20 promotion)
**Superseding lock:** [VECRM-S20-A](VECRM-S20-A.md) (S20)

---

## Statement

The 8 GB Contabo host CANNOT complete a full `--no-cache` rebuild of the vecrm image, even with VEMIO stopped, swap reset, and memory re-verified. The build peaks beyond available headroom (~6 GiB total memory pressure required) and is OOM-killed at the vite step.

Operational alternatives at S19:
1. Path B: Mac amd64 buildx → tarball → docker load
2. Upgrade host tier (was: 24 GB Contabo @ ~$19/mo)

## Why it was earned

S19 attempted two consecutive `--no-cache` rebuilds on the 8 GB host. Both OOM-killed at the vite step. Vite alone peaked at ~3.5 GiB; total build pressure exceeded ~6 GiB. With VEMIO stopped, available headroom was still insufficient.

## Status update (S20)

The host has since been upgraded to 12 GB (Contabo VPS 20 SSD tier; see VECRM-S20-A). However, the **standing rebuild posture remains Path B regardless of host capacity** — see VECRM-S20-A for the reasoning.

This lock is preserved as a **historical finding**, not as live operational guidance:
- The specific 8 GB framing no longer applies (host is now 12 GB).
- The general principle ("do not assume the production host can perform rebuilds without verification") remains relevant for any future capacity questions.
- The cost calculation has shifted: S20 chose 12 GB (~moderate cost) over 24 GB (~$19/mo); 24 GB is now the deferred option, not the standing alternative.

## Why it isn't simply "closed"

The principle this lock encodes — that production-host build capacity should never be assumed — is still active. The specific facts (8 GB → vite OOM) are historical, but the architectural posture they motivated is durable. Closing this lock would discard the lesson.

## Reversal

This lock can be fully retired if AND only if:
1. Host RAM is upgraded to a tier where `--no-cache` vecrm rebuild reproducibly succeeds with ≥2 GiB headroom remaining, AND
2. There is operational reason to want production-host builds (CI/CD pipeline, Mac dependency unacceptable, etc.)

Neither condition holds at S20. See VECRM-S20-A reversal section for the full criteria.

## Related

- [VECRM-S19-D](VECRM-S19-D.md) — After 2 identical failures, pivot (meta-principle that produced this finding)
- [VECRM-S20-A](VECRM-S20-A.md) — Standing posture (supersedes the "Path B OR upgrade" framing)
