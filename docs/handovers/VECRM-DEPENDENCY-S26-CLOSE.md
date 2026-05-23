# VECRM Dependency Document — S26 Close

**Scope:** VECRM project only (vecrm + vecrm-portal repos)
**Updated:** 2026-05-23 (S26 close)
**Format:** Layered dependency graph

---

## §1 — High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  USER LAYER                                                      │
│  Field reps (Sales, HR Approvers) · Operator (Ajay)             │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  PORTAL FRONTEND (vecrm-portal)                                  │
│  Next.js 16 / React 19 / TypeScript                              │
│  Domain: app.vinayenterprises.co.in (custom)                     │
│         vecrm-portal.vercel.app (Vercel default)                 │
│  Host: Vercel (auto-deploy from main)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS (BFF routes proxy)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  BACKEND API (vecrm app on Frappe v16.18.2)                      │
│  Domain: crm.vinayenterprises.co.in                              │
│  Site: crm.vinayenterprises.co.in                                │
│  Container: vecrm-backend-1                                      │
│  Image: 31383918a699                                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  DATABASE (MariaDB)                                              │
│  Per-site DB: _02c50791cf17d9de                                  │
│  Apps in namespace: frappe, crm, vecrm                           │
└─────────────────────────────────────────────────────────────────┘

INFRASTRUCTURE: Contabo VPS @ 217.216.58.117 (alias `vemio`)
                12GB RAM, 6 CPU cores
                Path: /opt/vecrm/ (host) → /home/frappe/frappe-bench/ (container)
```

---

## §2 — vecrm-portal repo structure (post-S26)

```
vecrm-portal/
├── app/
│   ├── layout.tsx              → Root layout; calls getFrappeUser; renders AppShell
│   ├── components/
│   │   ├── AppShell.tsx        → Conditional render: LoginForm (if !user) | normal app
│   │   ├── TopBar.tsx          → Top navigation; .topbar-nav-link--active palette
│   │   └── MobileNav.tsx       → Mobile drawer menu
│   ├── LoginForm.tsx           → Auth UI; mode-aware (email | pin); segmented tabs
│   ├── useAuth.ts              → Auth hook; login(id, secret, mode) + logout()
│   ├── api/
│   │   ├── auth/
│   │   │   ├── login/route.ts          → Email+pwd BFF (S25)
│   │   │   ├── login-pin/route.ts      → Phone+PIN BFF (S26 NEW)
│   │   │   └── logout/route.ts         → Logout BFF
│   │   └── me/route.ts                  → Session probe (LIVE; used by travel-vouchers)
│   ├── leads/
│   │   ├── page.tsx            → Leads list
│   │   └── [name]/page.tsx     → Lead detail (S24 URL-decode fix applied)
│   ├── inquiries/
│   │   ├── page.tsx            → Inquiries list
│   │   └── [name]/page.tsx     → Inquiry detail
│   ├── travel-vouchers/
│   │   └── page.tsx            → Travel vouchers list; calls /api/me for session check
│   └── api/me/route.ts         → Session probe (LIVE)
├── lib/
│   ├── frappe.ts               → frappeFetch helper (env-aware base URL)
│   ├── auth-ssr.ts             → getFrappeUser, get_session_employee bindings
│   └── useTheme.ts             → Theme toggle (light/dark)
└── docs/dispatches/            → Session dispatch documentation (audit trail)
```

### Internal dependency flow

```
app/layout.tsx
  └─ lib/auth-ssr.ts::getFrappeUser()
       └─ HTTP GET → crm.vinayenterprises.co.in/api/method/vecrm.api.get_session_employee

app/LoginForm.tsx
  └─ app/useAuth.ts::login(id, secret, mode)
       └─ if mode === "email": POST /api/auth/login        → BFF → vecrm.api.login_with_password
       └─ if mode === "pin":   POST /api/auth/login-pin    → BFF → vecrm.api.login_with_pin

app/api/auth/login/route.ts
  └─ lib/frappe.ts::frappeFetch("/api/method/vecrm.api.login_with_password")

app/api/auth/login-pin/route.ts                                                 (NEW S26)
  └─ lib/frappe.ts::frappeFetch("/api/method/vecrm.api.login_with_pin")

app/travel-vouchers/page.tsx
  └─ fetch("/api/me")                                       ← LIVE route (do not delete)
       └─ lib/frappe.ts::frappeFetch(...) (or direct session check)
```

### External dependencies

| Package | Version | Purpose |
|---|---|---|
| next | 16.x | Framework |
| react | 19.x | UI library |
| typescript | 5.x | Type checking |
| lucide-react | 0.383.0 | Icons |
| tailwindcss | 3.x | Styling (utility classes) |

### Vercel build pipeline

```
git push origin <branch>
  → Vercel webhook triggers build
  → npm install
  → npm run build (Next.js production build)
  → Deploy to preview URL (or main URL if branch=main)
  → Auto-comment on PR with preview URL
```

**Known caching issue:** `.next/` directory locally caches type validators referencing every route. After route deletion (e.g., `app/api/auth/me/` removal in S26), `tsc --noEmit` reports phantom errors until `rm -rf .next`. Vercel builds from scratch so this is local-only. (Per OBS-S26-R.)

---

## §3 — vecrm repo structure (post-S26)

```
vecrm/
├── vecrm/
│   ├── __init__.py
│   ├── api.py                                      → All public API endpoints
│   ├── hooks.py                                    → Frappe app hooks; require_type_annotated_api_methods
│   ├── patches.txt                                 → Migration registration
│   ├── patches/
│   │   ├── v1_0/                                   → S20-S25 migrations
│   │   └── v1_1/
│   │       ├── add_pin_auth_fields.py              → S26 PIN columns migration
│   │       └── rollback_add_pin_auth_fields.py     → Paired rollback per VECRM-L22
│   ├── vecrm/
│   │   └── doctype/
│   │       ├── vecrm_lead/
│   │       ├── vecrm_inquiry/
│   │       ├── vecrm_travel_voucher/
│   │       ├── vecrm_sales_visit/
│   │       ├── vecrm_voucher_counter/
│   │       ├── vecrm_employee/                     → Schema extended in S26 (4 PIN columns)
│   │       └── vecrm_authentication_audit_log/    → Schema extended in S26 (path column)
│   └── utils/                                       → Helper modules (allocator location pending PD-S26-Z)
└── docs/dispatches/                                 → Session dispatch documentation
```

### Public API surface (`vecrm/api.py`)

| Endpoint | Origin | Purpose |
|---|---|---|
| `vecrm.api.login_with_password(email, password)` | S25 | Email + password auth; returns session + employee data |
| `vecrm.api.login_with_pin(phone, pin)` | S26 NEW | Phone + PIN auth; returns same shape with login_path="pin" |
| `vecrm.api.get_session_employee()` | S25 | Returns current session's employee data including login_path |
| `vecrm.api.convert_lead_to_inquiry(lead_name)` | S20 | Creates VECRM Inquiry from VECRM Lead |
| (others) | various | Lead/Inquiry/TravelVoucher CRUD wrappers |

### Internal dependency flow

```
vecrm.api.login_with_password(email, password)
  └─ _normalize_email(email)
  └─ frappe.get_doc("VECRM Employee", {email: ...})
  └─ passlibctx.verify(password, employee.password_hash)
  └─ _check_lockout(employee, path="password")
  └─ _issue_session(employee, login_path="password")     ← refactored S26 to take login_path

vecrm.api.login_with_pin(phone, pin)                       (NEW S26)
  └─ _normalize_phone(phone)                                (NEW S26)
  └─ frappe.get_doc("VECRM Employee", {phone: ...})
  └─ passlibctx.verify(pin, employee.pin_hash)
  └─ _check_lockout(employee, path="pin")                   (extended S26 for path)
  └─ _issue_session(employee, login_path="pin")             (uses refactored helper)

vecrm.api.get_session_employee()
  └─ frappe.session.user → employee lookup
  └─ frappe.session.data["login_path"] → surfaced in response
```

### Schema dependencies

**VECRM Employee** (extended in S26):
```
name (Link → User)
email (Data, unique)
phone (Data; +91-XXXXXXXXXX canonical format)
role (Select: Sales Rep | Approver | Admin | ...)
password_hash (Data, NOT Password fieldtype)
failed_password_attempts (Int, default 0)
password_locked_until (Datetime, nullable)
pin_hash (Data)                                  ← NEW S26
failed_pin_attempts (Int, default 0)             ← NEW S26
pin_locked_until (Datetime, nullable)            ← NEW S26
pin_rotated_at (Datetime, nullable)              ← NEW S26
vecrm_account_status (Select: Active | Suspended | Locked)
desk_access (Check, default 0)
```

**VECRM Authentication Audit Log** (extended in S26):
```
event (Select: success | invalid_credentials | account_locked | account_locked_failed | missing_input | logout)
path (Select: password | pin | NULL)             ← NEW S26
employee (Link → VECRM Employee, nullable)
ip_address (Data)
user_agent (Data)
creation, modified (standard Frappe meta)
```

**VECRM Voucher Counter:**
```
name (Data; format: <TYPE>-<FY>, e.g. TV-26-27)
last_value (Int, default 0)
```

### Patches v1_1 (registered in patches.txt)

```
vecrm.patches.v1_1.add_pin_auth_fields                       (NEW S26)
vecrm.patches.v1_1.rollback_add_pin_auth_fields              (NEW S26 — paired per L22)
```

### External dependencies

| Component | Version | Purpose |
|---|---|---|
| Frappe Framework | v16.18.2 | Application framework + ORM + auth + perms |
| MariaDB | (Frappe-bundled) | Database |
| Python | 3.14 | Runtime |
| passlib | (Frappe-bundled) | pbkdf2_sha256 password/PIN hashing |
| `crm` app | (Frappe first-party) | Coexists in namespace; potential doctype clash (PD-DEFERRED-VECRM-CRM-DOCTYPE-CLASH) |

---

## §4 — Cross-repo API contracts

### Login endpoints

```
Portal → BFF → Backend

POST /api/auth/login (BFF)
  body: { usr: string, pwd: string }
  → POST /api/method/vecrm.api.login_with_password (Backend)
       body (form-encoded): email=<usr>, password=<pwd>
       returns: { message: { success, employee, name, role, login_path: "password" } }
       Set-Cookie: sid=...
  Returns to portal:
    Status: 200 | 401
    Body: { ok: true, full_name } | { error }
    Set-Cookie: sid=... (relayed)

POST /api/auth/login-pin (BFF)                                                 (NEW S26)
  body: { phone: string, pin: string }
  → POST /api/method/vecrm.api.login_with_pin (Backend)
       body (form-encoded): phone=<phone>, pin=<pin>
       returns: { message: { success, employee, name, role, login_path: "pin" } }
       Set-Cookie: sid=...
  Returns to portal:
    Status: 200 | 401
    Body: { ok: true, full_name } | { error }
    Set-Cookie: sid=... (relayed)

POST /api/auth/logout (BFF)
  → POST /api/method/logout (Frappe standard)
  Clears sid cookie.
```

### Session probe endpoints

```
GET /api/me (Portal — LIVE)
  → Calls frappeFetch with current session cookie
  → Returns employee data or 401

[REMOVED in S26: GET /api/auth/me (Portal — DEAD ROUTE, deleted)]
```

### Business doctype endpoints

(Pattern same across Lead, Inquiry, Travel Voucher — handled by Frappe's built-in REST surface)

```
GET /api/resource/VECRM Lead?fields=...&filters=...
GET /api/resource/VECRM Lead/<name>
POST /api/method/frappe.client.insert  (with doctype="VECRM Lead", payload=...)
```

---

## §5 — Deployment dependencies

### vecrm-portal (Vercel)

```
git push origin main
  → Vercel webhook
  → npm install + npm run build
  → Deploy to:
       https://app.vinayenterprises.co.in (custom domain)
       https://vecrm-portal.vercel.app (Vercel default)
       https://vecrm-portal-git-<branch>.vercel.app (preview URLs)
```

### vecrm backend (manual VPS deploy)

```
Operator on VPS:
  cd /opt/vecrm/
  git pull origin main
  bench --site crm.vinayenterprises.co.in migrate  # if patches added
  bench restart  # restarts gunicorn workers
```

**Backend deploy pattern**: dispatch (operator-driven) BEFORE portal PR, so portal smoke can verify against live backend. PR opened AFTER production confirmed working. See S26 narrative §2 for the canonical flow.

### Docker container build (when backend image changes)

```
Operator on VPS:
  cd /opt/vecrm/
  docker compose build --no-cache vecrm-backend
  docker compose up -d vecrm-backend
```

**Critical pattern** (inherited from VEMIO L23/L24, applies to VECRM): Workers/services use `build:` with COPY in Dockerfile, NOT bind mounts. `scp` + `docker restart` is INSUFFICIENT. Verify post-deploy by inspecting container filesystem, not host.

---

## §6 — Authentication lockout state machine

```
                    ┌──────────────────────────────┐
                    │  Login attempt arrives        │
                    │  with (id, secret, path)      │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  _check_lockout(emp, path)    │
                    │                               │
                    │  if path == "password":       │
                    │    field = password_locked_until│
                    │  if path == "pin":            │
                    │    field = pin_locked_until   │
                    │                               │
                    │  if field is in future:       │
                    │    → 401 account_locked       │
                    │    → audit event              │
                    └──────────────┬───────────────┘
                                   │ (not locked)
                                   ▼
                    ┌──────────────────────────────┐
                    │  passlibctx.verify(...)       │
                    └──────────────┬───────────────┘
                          │                  │
                       success              fail
                          │                  │
                          ▼                  ▼
                  ┌───────────────┐  ┌─────────────────────┐
                  │ reset attempts│  │ increment failed_X  │
                  │ → issue       │  │ if attempts >= 5:   │
                  │   session     │  │   set X_locked_until│
                  │ → audit       │  │     = now + 15min   │
                  │   success     │  │ audit invalid_creds │
                  └───────────────┘  └─────────────────────┘

KEY INVARIANT: password_X fields and pin_X fields are FULLY INDEPENDENT.
A locked password does NOT lock PIN, and vice versa. (Verified S26 Smoke 5.)
```

---

## §7 — Critical files for new sessions to read first

When starting a new VECRM session, read these BEFORE any work:

### Backend
1. `vecrm/vecrm/api.py` — All public API endpoints, current state of auth helpers
2. `vecrm/vecrm/hooks.py` — App configuration, including `require_type_annotated_api_methods`
3. `vecrm/patches.txt` — Migration registration list
4. `vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json` — Schema source of truth

### Portal
1. `app/LoginForm.tsx` — Auth UI, mode-toggle pattern
2. `app/useAuth.ts` — Auth dispatch hook
3. `app/api/auth/login/route.ts` and `app/api/auth/login-pin/route.ts` — BFF route shape
4. `app/components/AppShell.tsx` — Top-level conditional rendering for auth gate
5. `app/components/TopBar.tsx` — Active-state palette source (.topbar-nav-link--active)
6. `lib/frappe.ts` — frappeFetch interface

### Documentation
- `docs/dispatches/` in BOTH repos — Session dispatch history (audit trail)
- Most recent `PD-S<n>-CLOSE-HANDOVER.md` — Operative baseline document

---

## §8 — Known fragilities (latent risk inventory)

These are NOT bugs (system works correctly) but represent areas where future changes could surface issues:

1. **VECRM Employee perm floor** (OBS-S26-H) — `[System Manager]` only documented; portal roles work via undocumented bypass mechanism
2. **Frappe perm mechanism for shared portal users** (OBS-S26-I) — `frappe.get_doc` works despite missing tabDocPerm; could break in Frappe patch updates
3. **VECRM-L8 allocator location** (OBS-S26-Z) — Documented path doesn't exist; need to re-discover and re-document
4. **`crm` + `vecrm` app coexistence** — Same namespace; doctype name distinction is the only guard
5. **Custom domain `app.vinayenterprises.co.in`** — Maps to Vercel; DNS + SSL managed elsewhere; rotation/expiry not tracked in repo
6. **Test PINs in production** — `1234`/`5678` still active; rotation pending

---

## §9 — External system integrations (current state)

| System | Used for | State |
|---|---|---|
| Vercel | Portal hosting + preview deploys | ✅ active; auto-deploys main |
| Contabo VPS | Backend hosting | ✅ active; 12GB RAM, 6 CPU |
| MariaDB (Frappe-bundled) | Database | ✅ active; single instance |
| Microsoft Graph | Email delivery (inherited from VEMIO) | ✅ active; pipeline confirmed S63 |
| Frappe HD (Helpdesk) | Helpdesk integration (inherited from VEMIO) | ✅ active; not used by VECRM directly |

VECRM does NOT currently depend on: Auvik (VEMIO-only), Sophos/Fortinet (infrastructure-only), Tally (deferred migration), Slack (VEMIO-only).

---

**End of dependency document.**

This document supersedes the dependency mapping from prior sessions. Next regeneration at S27 close.
