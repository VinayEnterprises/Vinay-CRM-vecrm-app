# VECRM-L8 — Allocator dual-surface verification

**Status:** Active
**Earned in:** Pre-S19 (formalized in S19 close-handover §2)
**Date:** Pre-S19 (documented retroactively in S20)

---

## Statement

The voucher allocator (`voucher_counter.py`) MUST be verified on BOTH surfaces — the git working tree AND the running container — and the sha256 hashes MUST match.

A change to the allocator that lands on only one surface (e.g. updated in git but not redeployed; or hot-patched inside the container but not committed back to git) is an invariant violation and must be reconciled before any allocator-dependent operation proceeds.

## Why it exists

The allocator is the single point of authority for voucher number assignment (Lead/Inquiry/etc. series). A drift between git and the running container means:

- **Git ahead of container:** new allocator logic is "committed" but not actually running. Production behaves per old code; tests against the new code give false confidence.
- **Container ahead of git:** hot-patches in production are not in version control. Next rebuild silently reverts the patch, producing intermittent bugs nobody can reproduce.

Either direction is bad. The dual-surface check is cheap (two `sha256sum` calls) and catches both.

## How to verify

```bash
# Container side
docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py

# Git side (VPS clone)
sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py

# Both must produce the same hash.
```

`git hash-object` is NOT a valid substitute — it computes a different hash (SHA-1 over `"blob <size>\0<content>"`, not SHA-256 over raw content). Use `sha256sum` on both surfaces.

## Current banked SHA

- **S20 verified:** `7ad2b3a32757346de742365b197803e911cf000af5e9439d2ca1d8c76511b59d`

This is the canonical allocator sha256 at S20 close. Any change requires a new entry here.

## When to verify

- After any vecrm PR merge
- After any image rebuild (baked into Path B's `vecrm-deploy-image.sh` step 10)
- After any host reboot (Gate 7 of the S20 upgrade verified this)
- During any S20-style cold-check (baked into `s20-gate0-cold-check.sh`)
- Whenever there is reason to suspect drift
