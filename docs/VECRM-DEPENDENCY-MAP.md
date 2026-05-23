# VECRM Dependency Map

**Last regenerated:** S25 close, 23 May 2026
**Maintained by:** Session-close handovers
**Purpose:** Single source of truth for infrastructure versions, repo paths, container names, environment variables, allocator anchor sha, deploy patterns, and dependency relationships.

**Verification discipline:** Per OBS-S22-B, NEVER trust handover prose — verify against this document at session-open. Cold-check gates in `docs/S26-OPENER-PROMPT.md` validate every entry.

---

## 1. Infrastructure

### 1.1 Production environment

| Anchor | Value |
|---|---|
| Site domain | `crm.vinayenterprises.co.in` |
| VPS host | Contabo Mumbai, IP `217.216.58.117` |
| OS | Ubuntu (server LTS) |
| RAM | 12 GB (upgraded from 8 GB in S20 to support full vecrm Docker rebuilds) |
| CPU | 6 cores |
| Storage | (per Contabo plan) |
| TZ | Asia/Kolkata |
| SSH | `ssh root@217.216.58.117` (alias `vecrm-vps` not configured; uses direct IP) |
| HTTPS | Let's Encrypt cert via Frappe nginx |

### 1.2 Docker containers (VECRM-relevant only)

| Container | Image | Purpose | Notes |
|---|---|---|---|
| `vecrm-backend-1` | Frappe v16.18.2 | Main Frappe app server | Hosts the vecrm custom app at `/home/frappe/frappe-bench/apps/vecrm/` |
| `vecrm-db-1` | MariaDB 11.8.6 | Database | Default isolation REPEATABLE-READ; `innodb_snapshot_isolation` defaults ON in 11.8.6 |
| `vecrm-redis-cache-1` | Redis | Session cache, doctype cache | Used by Frappe internals |
| `vecrm-redis-queue-1` | Redis | Background job queue | RQ |
| `vecrm-frontend-1` | (Frappe nginx + Vue Desk) | Web server | Serves Desk + handles `/api/method/...` routes |

**Discipline reminder:** VEMIO containers (`vemio-*`) share this VPS. **VECRM dispatch NEVER touches VEMIO containers, files, or DB.** Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS.

### 1.3 Frappe app installed on `crm.vinayenterprises.co.in`

| App | Source | Notes |
|---|---|---|
| `frappe` | Frappe v16.18.2 | Framework |
| `crm` | Frappe CRM app | Standard Lead/Opportunity doctypes (NOT used by VECRM portal — VECRM uses its own VECRM Lead/Inquiry) |
| `vecrm` | `VinayEnterprises/Vinay-CRM-vecrm-app` | Vinay Enterprises custom CRM app |

### 1.4 Hooks.py declarations of note

```python
require_type_annotated_api_methods = True  # Site-wide (Frappe v16 feature)
```

This means EVERY `@frappe.whitelist()` method in `vecrm/api.py` MUST have type annotations on all parameters AND the return type. OBS-S25-F filed this as a structural enforcement, not an opt-in flag.

---

## 2. Repositories

### 2.1 vecrm (backend Frappe app)

| Anchor | Value |
|---|---|
| GitHub | `VinayEnterprises/Vinay-CRM-vecrm-app` |
| Default branch | `main` |
| Local checkout | `~/Documents/GitHub/vecrm` |
| **Main HEAD at S25 close** | **`5e0df3b`** (post-PR #16 squash) — increments with S25 docs PR |
| Deployment target | `vecrm-backend-1:/home/frappe/frappe-bench/apps/vecrm/` |
| Deploy mechanism | tar → scp → docker cp → bench migrate (NOT git pull) — see §5 |

### 2.2 vecrm-portal (Next.js portal)

| Anchor | Value |
|---|---|
| GitHub | `VinayEnterprises/vecrm-portal` |
| Default branch | `main` |
| Local checkout | `~/Documents/GitHub/vecrm-portal` |
| **Main HEAD at S25 close** | **`8165f7a`** (post-PR #8 squash) |
| Production URL | `vecrm-portal.vercel.app` (or custom domain — verify) |
| Vercel project | (Vinay Enterprises org) |
| Deploy mechanism | Vercel auto-deploys on push to main; PR previews on feature branches |
| Stack | Next.js 16, React 19, TypeScript 5, Tailwind v4 (installed but unused — uses CSS vars per S24 conventions) |

### 2.3 Vinay-CRM-config (legacy — no longer touched)

| Anchor | Value |
|---|---|
| GitHub | `VinayEnterprises/Vinay-CRM-config` |
| Status | **Legacy/retired.** All recent work happens in `vecrm` + `vecrm-portal`. |

---

## 3. Environment variables and secrets

### 3.1 Frappe site config (`/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json`)

Critical entries (do not commit values to repo):

| Key | Purpose |
|---|---|
| `db_name`, `db_password` | Site database credentials |
| `encryption_key` | Used by Frappe to encrypt Password fieldtype values in `__Auth` and other tables. **Rotation pending — PD-S26-AUTH-CREDS-ROTATE** |
| `vecrm_internal_secret` | Used for any future internal API signing (banked, not yet consumed). **Rotation pending.** |

### 3.2 Vercel env vars (vecrm-portal)

| Key | Purpose | Notes |
|---|---|---|
| `FRAPPE_URL` | Base URL of Frappe backend | Production: `https://crm.vinayenterprises.co.in` |

(Other env vars may exist; verify at session-open if relevant.)

### 3.3 Shared portal user credentials

| Field | Value |
|---|---|
| Frappe User | `vecrm-portal@vinayenterprises.co.in` |
| Password | (configured during S25 Phase 1 bootstrap; rotate periodically per security hygiene) |
| User type | Website User |
| Roles | VECRM Submitter + VECRM Approver (NOT Admin per VECRM-LOCK-PORTAL-USER-ROLES) |

---

## 4. Versions matrix (S25 close)

| Component | Version | Pinning source |
|---|---|---|
| Frappe | v16.18.2 | bench-installed version on VPS |
| Python | 3.11+ (Frappe v16 requirement) | container default |
| Node | 18.x or 20.x LTS | container default |
| MariaDB | 11.8.6 | container default |
| Redis | (latest stable per Frappe deps) | container default |
| Next.js | 16 | vecrm-portal `package.json` |
| React | 19 | vecrm-portal `package.json` |
| TypeScript | 5.x | vecrm-portal `package.json` |
| Tailwind | v4 | installed; unused per CSS-var convention |
| passlib | (whichever ships with Frappe v16.18.2) | `frappe.utils.password.passlibctx` |

---

## 5. Deploy patterns

### 5.1 vecrm app deploy (NOT git pull on VPS)

**Pattern (established S20+, verified throughout S25):**

```bash
# Local: build tar of changed files
cd ~/Documents/GitHub/vecrm
tar -czf /tmp/vecrm-deploy.tar.gz \
  vecrm/api.py \
  vecrm/patches.txt \
  vecrm/vecrm/doctype/.../*.json \
  vecrm/patches/v1_1/*.py

# Ferry to VPS
scp /tmp/vecrm-deploy.tar.gz root@217.216.58.117:/tmp/

# Land in container
ssh root@217.216.58.117 'docker cp /tmp/vecrm-deploy.tar.gz vecrm-backend-1:/tmp/'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 tar -xzf /tmp/vecrm-deploy.tar.gz -C /home/frappe/frappe-bench/apps/vecrm/'

# Apply migrations + clear cache + restart
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in migrate'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in clear-cache'
ssh root@217.216.58.117 'docker restart vecrm-backend-1'
sleep 12

# Cleanup
rm /tmp/vecrm-deploy.tar.gz
```

**Why not git pull on VPS:** Per OBS-S25-AX, the container at `/home/frappe/frappe-bench/apps/vecrm/` is NOT a git checkout. This is by-design.

### 5.2 vecrm-portal deploy

Vercel auto-deploys on push to main. PR branches get preview URLs.

No VPS interaction required for portal changes.

### 5.3 Three-tier rollback ladder (for schema migrations)

Per VEMIO L22 (observed in VECRM patches):

1. **Patch-level rollback** — every forward patch has a paired `rollback_*.py` file in `vecrm/patches/v1_1/`. Idempotent. Designed to recover from a patch that landed but caused issues.
2. **Doctype JSON revert** — `git revert` the offending PR; re-run `bench migrate` to apply the JSON revert via reload_doc + sync_for.
3. **Last-resort DB restore** — restore from nightly backup (verify backup procedure exists; S25 didn't test it).

### 5.4 Migration patch conventions (S25-established)

Every forward migration in `vecrm/patches/v1_1/`:
- Has a `def execute() -> None:` function
- Imports verified Frappe symbols (verified via `bench console` source-read before authoring — per S25 OBS-S25-V)
- Is idempotent (safe to re-run)
- Prints progress lines (operator can see what happened during `bench migrate`)
- Has a paired `rollback_*.py` file

Forward patches landed in S25:
- `add_auth_fields.py` (Phase 1)
- `create_auth_doctypes.py` (Phase 1)
- `create_vecrm_portal_user.py` (Phase 1)
- `fix_portal_user_type.py` (Phase 1.5)
- `convert_password_hash_to_data.py` (Phase 4.7)
- `extend_lead_inquiry_perms.py` (Phase 5.5)

---

## 6. Allocator anchor

### 6.1 Banked sha (VECRM-L8)

```
91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9
```

This is the sha256 of the canonical voucher_counter allocator (post-S22 §6 hard-gate, post-VECRM-S22-A correction). **Unchanged through S25** — the allocator was not touched.

### 6.2 What the allocator does

`vecrm.vecrm.utils.voucher_counter.next_for(prefix, fiscal_year)`:
- Opens a transaction with `frappe.db.commit()` if any prior work pending
- Issues `SELECT last_value FROM tabVECRM Voucher Counter WHERE prefix=... AND fiscal_year=... FOR UPDATE` (locks the row)
- Reads `last_value` from the SAME locking SELECT (VECRM-S22-A invariant — never split into a separate non-locking SELECT)
- Returns `last_value + 1`, increments the row, commits
- Caller uses the returned integer in the doctype's `autoname` controller

### 6.3 Counters live at S25 close

| Counter | Prefix | Fiscal Year | last_value |
|---|---|---|---|
| TV-26-27 | `VE/TV/` | 26-27 | 94 |
| EV-26-27 | `VE/EV/` | 26-27 | 12 |
| LEAD-26-27 | `LEAD/` | 26-27 | 13 |
| INQ-26-27 | `VE/INQ/` | 26-27 | 12 |

---

## 7. Authentication architecture (S25 — NEW)

### 7.1 Shared portal user

All portal sessions run as the shared Frappe User `vecrm-portal@vinayenterprises.co.in`. This user is **Website User** (not System User) and has roles **VECRM Submitter + VECRM Approver only**.

### 7.2 Session-data convention

After `login_with_password` authenticates a VECRM Employee, the `_issue_session` helper:
1. Calls `frappe.local.login_manager.login_as("vecrm-portal@vinayenterprises.co.in")` — this opens a Frappe session as the shared user
2. Mutates `frappe.session.data.vecrm_employee_phone`, `vecrm_employee_name`, `vecrm_employee_role`, `vecrm_login_path` directly on the inner payload dict
3. Calls `frappe.local.session_obj.update(force=True)` to persist BOTH the DB sessiondata row AND the cache slot with the correct outer-shape data
4. Returns the sid in the response Set-Cookie

Subsequent requests reach the portal's BFF routes, which forward the sid as a cookie to Frappe. Frappe's `Session.resume()` loads the payload from cache or DB; `frappe.session.data.vecrm_employee_phone` is now populated. `get_session_employee` reads from this and returns the full identity.

### 7.3 Lockout mechanics

- 5 failed `login_with_password` attempts (any combination of invalid_credentials / no_password_configured / wrong path) → row's `failed_password_attempts` = 5 → `locked_until` set to `now + 15 minutes`
- On the 5th failure, an `auth.account_locked` event is emitted
- Subsequent requests with correct password during lockout window → generic `Invalid credentials` 401 + `auth.login.failed` with `reason=account_locked` (no enumeration)
- After lockout expires: counter resets on next successful login

### 7.4 Why password_hash is Data fieldtype, not Password

Per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE and OBS-S25-AK: Frappe's Password fieldtype stores the value in `__Auth` table and loads it as `None` on `get_doc()`. A subsequent `.save()` propagates that `None` to `__Auth` → Frappe deletes the auth row. Since `password_hash` already stores a one-way passlib hash, encrypting it at rest via Password fieldtype adds zero security but introduces the delete-on-save footgun.

**S25 fix:** fieldtype Data. Stores in parent column. Loads correctly. Survives `.save()` and `.db_update()`. Migration `convert_password_hash_to_data.py` performed the conversion in-session.

---

## 8. Production data inventory (S25 close)

### 8.1 Real users

| User | Type | Notes |
|---|---|---|
| `Administrator` | System User | Frappe superuser |
| `ajay@vinayenterprises.co.in` | System Manager + VECRM Admin | Operator |
| `vecrm-portal@vinayenterprises.co.in` | Website User + VECRM Submitter + Approver | **NEW S25** — shared portal user |

Plus 3 demo seed Frappe Users (from S0/S1 era; not relied upon).

### 8.2 VECRM Employees (Active)

| Phone | Name | Email | Role | Base City |
|---|---|---|---|---|
| +91-9999900001 | Test Sales Rep | test.salesrep@vinayenterprises.co.in | Sales Rep | Ahmedabad |
| +91-9999900002 | Test HR Approver | test.hr@vinayenterprises.co.in | HR | Ahmedabad |
| +91-9327547536 | Ajay Salvi | ajay@vinayenterprises.co.in | Admin | Ahmedabad |

All 3 have valid `password_hash` (87-char passlib hash). All 3 successfully logged in via Phase 5 browser smoke.

### 8.3 Voucher data

- ~94 Travel Vouchers (TV-26-27 series, mix of Submitted and Draft per S25 Phase 5 browser observation)
- ~12 Expense Vouchers (EV-26-27)
- ~13 Leads (LEAD-26-27)
- ~12 Inquiries (INQ-26-27)
- ~13 Voucher Audit Log rows (append-only)
- ~10 VECRM Auth Audit Log rows from S25 Phase 4/5 smoke (append-only)

### 8.4 Test data policy

Per Session-0 no-delete rule: test data is NOT purged from production DB. Identifiable by:
- VECRM Employee phone `+91-99999*`
- Voucher submitter matching test phones
- Leads/Inquiries with company names like "Smoke Co" or "S23 §6 Lead N"

Acceptable to keep for regression testing.

---

## 9. Build graph dependencies

```
vecrm-portal (Next.js, Vercel)
  ↓ HTTPS Bff routes
  ↓ /api/method/vecrm.api.*
  ↓
vecrm-backend-1 (Frappe v16.18.2, Contabo Mumbai)
  ↓
vecrm Python app (custom doctypes + api.py + utils)
  ↓ allocator
voucher_counter.next_for() → SHA-pinned at 91556a7d... (VECRM-L8)
  ↓
MariaDB 11.8.6 (REPEATABLE-READ, innodb_snapshot_isolation default ON)
```

**Dependency notes:**

- vecrm-portal depends on vecrm-backend at runtime (every BFF route makes an HTTP call)
- vecrm depends on Frappe v16.18.2 (`require_type_annotated_api_methods=True` is Frappe v16+)
- All vecrm migration patches depend on Frappe's `frappe.model.sync.sync_for(app, force=, reset_permissions=)` (signature verified in S25 Phase 4.7)
- Session persistence depends on `frappe.local.session_obj.update(force=True)` — `session_obj` exists during HTTP request contexts only, NOT in `bench console` (OBS-S25-AS-companion finding: probes that depend on session_obj must run via HTTP, not console)
- Authentication depends on passlib (`frappe.utils.password.passlibctx`) — verified available in S25 Phase 0.5 console probe

---

## 10. Glossary of common terms

| Term | Meaning |
|---|---|
| Frappe Desk | The admin web UI built into Frappe (used by Ajay for direct doctype management) |
| Portal | The Next.js app at `vecrm-portal` (used by Sales Reps, HR, Admin for daily workflows) |
| BFF | Backend-for-frontend; Next.js API routes that proxy to Frappe |
| Doctype | Frappe's term for a database table + UI form definition |
| Submittable | A Frappe doctype with submit/cancel/amend workflow (TV, EV; NOT Lead, Inquiry) |
| Allocator | The voucher_counter utility that assigns gap-free sequence numbers |
| Audit log | append-only log of business events; never deleted |
| Lift | A multi-session work block with a §0.6 lift-and-close discipline |
| §risk | A risk section in a dispatch document |
| Phase | A unit of dispatch execution with a verification gate at the end |

---

**End of VECRM-DEPENDENCY-MAP.md**

This document is the single source of truth for VECRM infrastructure. Cold-check gates in the next-session opener validate every numeric/structural claim against ground truth before any work begins.
