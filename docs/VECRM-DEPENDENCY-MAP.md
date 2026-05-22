# VECRM-DEPENDENCY-MAP

**Created:** 2026-05-22 (S23 close, NEW document)
**Updated:** 2026-05-22
**Maintained by:** Session-close handovers
**Purpose:** Single source of truth for infrastructure versions, repo paths, container names, environment variables, allocator anchor sha, deploy patterns, and dependency relationships. Replaces ad-hoc references scattered across prior session handovers.

---

## 1. Repository topology

### 1.1 VECRM repositories (`VinayEnterprises` org, all private)

| Repo | Purpose | Last commit (S23 close) | Branch policy |
|---|---|---|---|
| `Vinay-CRM-vecrm-app` | Frappe app: doctypes, controllers, allocator, voucher counter, audit log | `dc52c43` (PR #12) | main; feature branches squash-merged |
| `Vinay-CRM-config` | Historical handover store (S3-era convention) | (separate; superseded S22+ by in-app docs/) | main; doc-only commits |
| `vecrm-portal` | Next.js 16 PWA frontend; deployed to crm.vinayenterprises.co.in subpath or app.vinayenterprises.co.in | `d880eda` (PR #4) | main; feature branches squash-merged |

### 1.2 VEMIO repositories (referenced for context; NOT touched by VECRM work)

| Repo | Purpose |
|---|---|
| `VinayEnterprises/vemio-dashboard` | Vercel-deployed Next.js dashboard; vemio.vinayenterprises.co.in |
| `VinayEnterprises/vemio-infra` | Docker workers, compose files, VPS infra |
| `VinayEnterprises/vemio-helpdesk-config` | Frappe HD customizations (separate Frappe site) |

**Critical separation:** VECRM and VEMIO share the same Contabo VPS but are isolated at the Docker network level and the Frappe site level. **VECRM sessions MUST NOT touch any vemio-* container, vemio_db / glpi_db schemas, the vemio.vinayenterprises.co.in site config, or anything under `/opt/vemio/`.** This is enforced by VECRM-LOCK-VPS-DESTRUCTIVE-OPS.

### 1.3 Local development paths

| Path | Purpose |
|---|---|
| `~/Documents/GitHub/vecrm/` | Backend Frappe app local clone |
| `~/Documents/GitHub/vecrm-portal/` | Portal Next.js local clone |
| `~/Downloads/` | Operator-side artifact staging (dispatches, diagnostic scripts) |
| `/mnt/user-data/outputs/` | Dispatcher-side artifact staging (Claude's outputs) |
| `~/Documents/GitHub/Vinay-CRM-config/` | Historical handover store (may exist locally) |

---

## 2. Infrastructure stack

### 2.1 Production VPS

| Property | Value |
|---|---|
| Provider | Contabo |
| Region | Mumbai |
| Hostname | vemio-primary (same host as VEMIO production) |
| Public IP | 217.216.58.117 |
| Working directory | `/opt/vemio/docker` (VEMIO conventions; predates VECRM) |
| OS | Ubuntu 24 LTS |
| SSH | `root@217.216.58.117` (operator-managed credentials) |

### 2.2 Docker / containers

VECRM-specific containers (9 total, all named `vecrm-*`):

| Container | Purpose |
|---|---|
| `vecrm-backend-1` | Frappe backend (gunicorn, scheduler tasks, bench execute target) |
| `vecrm-frontend-1` | Frappe Desk frontend (nginx; Desk UI at crm.vinayenterprises.co.in) |
| `vecrm-websocket` | Realtime push (socket.io) |
| `vecrm-queue-short` | Short-task queue worker |
| `vecrm-queue-long` | Long-task queue worker |
| `vecrm-scheduler` | Frappe scheduler |
| `vecrm-mariadb` | MariaDB 11.8.6 — VECRM site database |
| `vecrm-redis-cache` | Redis cache |
| `vecrm-redis-queue` | Redis queue backing for queue workers |

**Container app dir:** `/home/frappe/frappe-bench/apps/vecrm/` inside `vecrm-backend-1`.

**Frappe site:** `crm.vinayenterprises.co.in`.

### 2.3 Database

| Property | Value |
|---|---|
| Engine | MariaDB 11.8.6 (inside vecrm-mariadb container) |
| Database name | `_<hashed_site>` (per Frappe convention; auto-managed) |
| Isolation level | REPEATABLE-READ (MariaDB default) |
| Backup strategy | Operator-managed (not automated; recommend pre-destructive-op snapshot) |

**Important isolation note:** REPEATABLE-READ + long-lived bench-execute connections can produce stale snapshots in test harnesses. See OBS-S23-D in S23-close-handover.md. Test harnesses must `frappe.db.rollback()` between worker barriers and post-run reads, and triangulate critical assertions with fresh-connection reads.

### 2.4 Framework versions (locked)

| Stack | Version | Notes |
|---|---|---|
| Frappe Framework | 16.18.2 | VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER cites document.py L441/L442 |
| Frappe HD | (used by VEMIO, not VECRM) | N/A |
| ERPNext | Not installed | Deferred indefinitely; Tally migration not started |
| Indian Compliance app | Not installed | Will install when ERPNext does |
| Node.js (portal local + Vercel) | 20.x LTS (per Next.js 16 requirement) | |
| Next.js (portal) | 16.2.6 with Turbopack | |
| React (portal) | 19.2.4 | |
| TypeScript (portal) | (per Next.js 16 default) | |
| Package manager (portal) | npm (package-lock.json present; no pnpm) | |

### 2.5 Allocator anchor (VECRM-L8)

| Property | Value |
|---|---|
| File | `vecrm/vecrm/voucher_counter.py` |
| Module | `vecrm.vecrm.voucher_counter` |
| Anchor sha (sha256) | `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` |
| Sha lock since | S22 |
| Last touched | S22 PR #9 |
| Public functions | `fy_label(business_date) -> str`, `next_number(series, fy) -> int` |

**Invariant (VECRM-S22-A):** All callers must read counter value INSIDE `FOR UPDATE` lock, not before. Code at sha 91556a7d… enforces this. Any modification to voucher_counter.py invalidates VECRM-L8 anchor and requires explicit dispatcher-authorized lock-update PR.

### 2.6 Deploy pattern

For backend (Frappe doctypes / controllers / app code):

```bash
# Local to VPS file copy
scp local-file root@217.216.58.117:/tmp/$(basename file)
ssh root@217.216.58.117 'docker cp /tmp/$(basename file) vecrm-backend-1:/home/frappe/frappe-bench/apps/vecrm/<path>/$(basename file) && rm /tmp/$(basename file)'

# New doctype or migrate-affecting change
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in migrate'

# Restart backend for code reload (NOT just docker restart — that doesn't pick up new code; this is per S22 lesson)
ssh root@217.216.58.117 'docker restart vecrm-backend-1'

# Verify post-deploy
ssh root@217.216.58.117 'docker exec vecrm-backend-1 grep <fingerprint> /home/frappe/frappe-bench/apps/vecrm/<path>/<file>'
```

For portal (Next.js):

- Local: `npm run build` to verify clean TypeScript + Next.js compilation
- Deployment: Push to main; Vercel auto-deploys (assumed; verify Vercel config separately if needed)

### 2.7 Environment variables

**Portal (`vecrm-portal`):**

| Variable | Used by | Purpose |
|---|---|---|
| `FRAPPE_URL` | `lib/frappe.ts` `frappeFetch` helper | Base URL for Frappe API calls (e.g. `https://crm.vinayenterprises.co.in`) |
| `NEXT_PUBLIC_*` | (none currently in scope for VECRM-portal auth path) | |

**Backend (`vecrm`):**

- `vecrm_internal_secret` (site config): HMAC key for Q9 transport to vemio.io. Status: untested S23.
- Standard Frappe site config (db credentials, redis URLs, secret_key)

---

## 3. Test infrastructure

### 3.1 Test employees (production data)

| Phone (identity) | Role | Status | Purpose |
|---|---|---|---|
| `+91-9999900001` | Sales Rep | Active | Submits test vouchers (TV + EV); used as Sales Rep submitter in §6 |
| `+91-9999900002` | HR | Active | Approves test vouchers via API; used as HR approver in §6 |

Both employees are in production tables — NOT deletable per VECRM no-delete policy. Used across S22 and S23 §6 hard-gates.

### 3.2 Test data conventions

- Test vouchers / leads / inquiries persist in production tables per audit append-only design
- Test data tagged in description / company_name fields with `S22`, `S23`, `Phase A smoke`, `Phase B test`, `§6` markers
- No separate test database (single Frappe site)

### 3.3 §6 concurrency hard-gate pattern

| Element | Description |
|---|---|
| Trigger | New allocator series or significant allocator-adjacent change |
| Threading | 10 concurrent workers via Python ThreadPoolExecutor |
| Per-worker | Own Frappe connection (`frappe.connect(site=...) + frappe.destroy()`) |
| Acceptance | 5 criteria: counter +N, N rows gap-free, zero errors, N audit rows (where applicable), 1:1 voucher↔audit coverage |
| Harness pattern | PATCH 1 (`frappe.db.rollback()` between barrier and post-reads) + PATCH 2 (fresh-connection triangulation for critical assertions) per OBS-S23-D |
| Ferry | scp → docker cp → backend restart → run → cleanup |
| Cleanup | Remove diagnostic scripts from container + ~/Downloads at Phase D |

### 3.4 Smoke test pattern (manual)

For new doctypes (Travel Voucher / Expense Voucher / Lead / Inquiry):

- B.0 Cleanup (only if pre-existing garbage to clear; explicitly flag if SKIPPED)
- B.1 Create in Desk (verify Name field NOT visible, autoname allocates correctly)
- B.2 Verify on_submit audit row (smoking gun: fy_label not null)
- B.3 Approve via API (verify approve audit row + voucher.approved_* fields)
- B.4 Append-only guards on audit log (modify + delete both raise PermissionError) — SKIPPABLE if inherited from prior PR
- B.5 / B.6 (where applicable) — first allocations, conversion flows

---

## 4. Build-graph dependencies (what blocks what)

```
Backend Layer 1 (HR/Employee/Audit)
  └── Required by → Layer 2 (Voucher needs Employee for submitter)
  └── Required by → Layer 3 (Lead/Inquiry need Employee for owner)

Backend Layer 2 — Voucher
  ├── voucher_counter.py (sha 91556a7d... = L8 anchor) ✅
  ├── Travel Voucher ✅
  ├── Visit Line ✅ (child of TV)
  ├── Voucher Audit Log ✅ NEW S23 (required by submit + approve)
  ├── Expense Voucher ✅ NEW S23 (depends on Voucher Audit Log + L8 anchor)
  ├── Expense Line ✅ NEW S23 (child of EV)
  └── Unblocks → Portal voucher screens (PD-S24-PORTAL-VOUCHER-SCREENS)

Backend Layer 3 — Sales Pipeline (Lead → Inquiry)
  ├── Lead ✅ functional S23
  ├── Inquiry ✅ functional S23
  ├── Inquiry Audit Log ✅
  ├── Q9 transport (HMAC POST to vemio.io) ⚠️ untested
  └── Customer ⚠️ skeleton (may defer to ERPNext under Tally migration)

Backend Layer 4 — Reporting
  └── Weekly Report ❌ — depends on Layer 3 having real activity (gated by Portal B1+B2 production rollout)

Portal Frontend
  ├── SSR auth hydration (lib/auth-ssr.ts) ✅ NEW S23
  ├── AppShell (layout-owned) ✅ refactored S23
  ├── Login/Logout ✅
  ├── Leads/Inquiries screens ✅ (depend on Layer 3 backend)
  └── Voucher screens ❌ NOT BUILT — depends on Layer 2 backend (✅) + AppShell (✅)
      └── Unblocks → Real field-rep production rollout

Cross-Project
  ├── VEMIO production runs on same VPS — DO NOT TOUCH from VECRM sessions
  ├── VEMIO Q9 endpoint (app.vemio.io/api/internal/vecrm/inquiry-converted) receives inquiry conversion events ⚠️ reliability untested
  └── Tally → ERPNext migration ❌ deferred — when started, ERPNext takes ownership of Quote/Order/invoicing
```

---

## 5. Operating constraints

### 5.1 VPS access discipline (VECRM-LOCK-VPS-DESTRUCTIVE-OPS)

| Operation type | Authorization |
|---|---|
| VPS reads (`frappe.get_meta`, `frappe.db.get_value`, `docker ps`, file viewing, `bench execute` of read functions) | No special auth |
| Additive deploys (`scp` + `docker cp` of new code files, `bench migrate` for new doctype registration, `docker restart`) | No special auth; standard deploy pattern |
| Container restarts on `vecrm-*` containers | No special auth |
| Destructive operations: `rm`, `DELETE`, `DROP`, `TRUNCATE`, `frappe.delete_doc`, `docker rm`, `docker exec ... rm`, anything that removes data or files | **Explicit dispatcher authorization required** |
| Touching any non-`vecrm-*` container | **Forbidden** |
| Touching `vemio_*` or `glpi_*` database schemas | **Forbidden** |
| Touching anything under `/opt/vemio/` | **Forbidden** |

For high-risk destructive operations (schema migrations with DROP, bulk DELETE), dispatcher MAY require a pre-operation backup. Two backup approaches:

- **Targeted table backup** (preferred for bounded operations): `CREATE TABLE backup_<timestamp>_<table> AS SELECT * FROM <table>`. Cheap, fast, restore-friendly.
- **State recording** (mandatory regardless): Dump current state of affected entities to chat / artifact before destructive op. Captures intent and provides manual restore path.

Full pg_dump-style backup considered overkill for routine work; use targeted approach by default.

### 5.2 Branch + merge discipline (VECRM-L13)

- Feature work always on feature branches: `feat/s##-<descriptor>`
- Documentation work on doc branches: `docs/<descriptor>`
- Commit messages: detailed, multi-section, capture rationale
- Merge: `gh pr merge <PR#> --squash --delete-branch`
- Post-merge: pull main, verify branch state clean, verify branch deleted both sides

### 5.3 Pre/post commit branch checks (OBS-S71-A, permanent)

Before AND after every commit-bearing bash invocation:

```bash
git branch --show-current
```

Prevents accidental commits to main, accidental branch checkout mid-operation.

### 5.4 Recon-before-code (OBS-S22-B, repeating pattern)

Before drafting any code, AST-check, file-shape recon, and grep for hidden consumers. Dispatch prose is NOT trusted over current ground truth. Every dispatch should explicitly call out areas where recon is mandatory before implementation.

S23 caught 8 dispatch deviations via recon-first. All 8 were correct corrections.

---

## 6. Update cadence

This document is reviewed and updated at every session close. Specifically:

- **At session open:** Read this document first along with the latest session-close handover. Verify counter state, container state, allocator sha, framework versions are unchanged or update accordingly.
- **At session close:** Update infrastructure changes, version bumps, new locks, new repos, new env vars, deploy pattern refinements, dependency changes.

Version anchors (PART F of pendency register) and counter state should match this document's PART 2.4 exactly. If they don't, one is stale — reconcile.

---

**End of VECRM-DEPENDENCY-MAP.md**
