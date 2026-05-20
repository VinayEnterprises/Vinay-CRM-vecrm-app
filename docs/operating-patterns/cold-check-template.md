# Canonical cold-check patterns for VECRM session Gate 0

**Purpose:** Reusable verification patterns for the session-open cold check.
**Authority:** This document is canonical over any prior handover §3 "Gate 0" prose.

## Fleet count by compose project

The VPS runs three compose projects with distinct container name prefixes:

| Project | Prefix | Expected count |
|---|---|---|
| vecrm | `vecrm-` | 9 running + 1 configurator exited(0) |
| vemio | `vemio-` | 18 running (1 known-benign unhealthy: vemio-freeradius) |
| frappe-helpdesk | `frappe-helpdesk-` | 9 running + 1 configurator exited(0) |

**Total:** 36 running + 2 exited configurators.

### Correct grep pattern

```bash
ssh root@217.216.58.117 'docker ps --format "{{.Names}}\t{{.Status}}" | grep -E "^(vecrm-|vemio-|frappe-helpdesk-)"'
```

**Note:** `frappe-helpdesk-` (with trailing hyphen) — NOT `^helpdesk` (anchored, no prefix) which misses all 9 helpdesk containers. The S21 Gate 0 cold-check used `^helpdesk` and produced a false-FAIL for fleet count = 27.

Alternative (substring match, looser):
```bash
ssh root@217.216.58.117 'docker ps --format "{{.Names}}" | grep -E "(vecrm|vemio|helpdesk)"'
```

This works because unanchored `helpdesk` is a substring of `frappe-helpdesk-*`. The original S20 session scripts (`s20-gate0-cold-check.sh`) use this unanchored pattern correctly.

### Exited configurator check (separate)

```bash
ssh root@217.216.58.117 'docker ps -a --filter "status=exited" --format "{{.Names}}\t{{.Status}}" | grep -E "(vecrm|frappe-helpdesk).*configurator"'
```

Expected: 2 lines (`vecrm-configurator-1`, `frappe-helpdesk-configurator-1`).

## Whitelist decorator count in api.py

```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 grep -cE "^@frappe\.whitelist" /home/frappe/frappe-bench/apps/vecrm/vecrm/api.py'
```

**Note:** Anchor at line start (`^`). The unanchored pattern `grep -c "@frappe.whitelist"` also matches docstring lines that reference the decorator literally (e.g. "Every function in this module is decorated with @frappe.whitelist()"), producing an inflated count. As of PR #6, expected count = 1.

## Allocator dual-surface verification

```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py'
ssh root@217.216.58.117 'sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py'
```

Both must equal `7ad2b3a32757346de742365b197803e911cf000af5e9439d2ca1d8c76511b59d` (VECRM-L8 lock).

**Critical:** Use the same algorithm (`sha256sum`) on both surfaces. The original S20 Gate 0 mixed `git hash-object` (SHA-1) with `sha256sum` (SHA-256) and produced a guaranteed mismatch. Different algorithms never match.

## Three-surface git HEAD verification

```bash
# Mac
git -C ~/Documents/GitHub/vecrm fetch origin
git -C ~/Documents/GitHub/vecrm rev-parse origin/main
git -C ~/Documents/GitHub/vecrm rev-parse main

# VPS
ssh root@217.216.58.117 'git -C /opt/vecrm/vecrm-src rev-parse HEAD'
```

All three should return the same SHA at session-open Gate 0.

## Image inventory

```bash
ssh root@217.216.58.117 'docker images vecrm-custom --no-trunc --format "table {{.Tag}}\t{{.ID}}"'
```

Expected (post-S20): at least 3 active tags — `latest`, `s<N>-pre-fix-rollback` (intra-session iteration), `s<N-1>-pre-s<N>-rollback` (previous session). Additional tags from older sessions (v0.x.y, s<earlier>-mac-build) are non-blocking bookkeeping.

## Counter read

See `docs/operating-patterns/mariadb-probe.md` for the canonical pattern. Quick form:

```bash
ssh root@217.216.58.117 "printf '%s\n' \"SELECT name, last_value FROM \\\`tabVECRM Voucher Counter\\\` WHERE name IN ('LEAD-26-27','INQ-26-27');\" | docker exec -i vecrm-db-1 bash -lc 'mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" _02c50791cf17d9de'"
```

## Provenance

- Authored: S21 PD-S20-DOCS-DRIFT closure, 2026-05-20
- Earned-from: S21 Gate 0 cold-check surfaced 3 documentation drift bugs (helpdesk grep, MariaDB auth, whitelist grep)
- Authority over: S20-close-handover §3, S21-open-handover §3 (both supersede patterns documented here)
