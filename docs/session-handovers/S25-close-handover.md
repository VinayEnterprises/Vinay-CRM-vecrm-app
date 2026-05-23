# S25 — Close Handover

**Date:** Friday 2026-05-22 (evening through midnight) → Saturday 2026-05-23 (~01:00 IST close, ~12:50 PM IST docs handover)
**Duration:** ~14 hours wall-clock (single contiguous session)
**Operator:** Ajay Salvi, solo founder, Vinay Enterprises
**Outcome:** ✅ **2 PRs shipped across 2 repos. Email+password authentication for VECRM Portal is live in production end-to-end.**

---

## 0. TL;DR (for any next session opener that doesn't have time to read further)

S25 shipped **PD-S25-VECRM-AUTH v2** — the email+password authentication system for VECRM Portal — replacing the prior phone-link auth scheme. Three identity types now log in via the portal: Test Sales Rep, Test HR Approver, and Ajay (Admin). Session persistence works across HTTP boundaries in production. Lockout at 5 failed attempts works. Audit log captures all auth events. All existing surfaces (Travel Vouchers, Leads, Inquiries) work for portal-authenticated users.

**Two PRs merged:**
- `vecrm` PR #16 (squash-merged as `5e0df3b` on main) — 7 commits, +802 lines / -7 lines across 24 files
- `vecrm-portal` PR #8 (squash-merged as `8165f7a` on main, Vercel auto-deployed) — 1 commit, 4 BFF routes touched

**Scope explicitly deferred to S26:** phone+PIN backend, email-based reset flow, Microsoft Graph wiring, `admin_set_credential` as properly-gated portal endpoint, OBS-S25-D credential rotation (encryption_key, vecrm_internal_secret).

**Three new structural fixes** (codified as PD-S26-DISPATCHER-DISCIPLINE-MECHANICAL-RULES):
1. **OBS-S25-AP** — Source artifacts for execution MUST go through `present_files` (file download), not inline chat code blocks. Paste fidelity in chat is unreliable for large source.
2. **OBS-S25-AV** — `§risk` sections in dispatches need verification gates (one query at the moment the risk becomes concrete), not just acknowledgment.
3. **OBS-S25-AS** — Before flagging a blocker, run a git-history check (`git log --oneline -5`) to confirm the blocker isn't already-resolved-and-deployed.

**Catalog:** 47 OBS observations filed (A through AX). Full list in §11.

**Lift §0.6** (VPS-discipline lift opened at A2 dispatch §0.6 "PD-S25-VECRM-AUTH v2 execution") — **CLOSED.**

---

## 1. Session-0 vision inheritance (carried since project inception)

VECRM was conceived as the CRM + sales-tooling product for Vinay Enterprises, complementary to VEMIO (the MSP monitoring platform). The Session-0 vision laid down eight pillars:

| # | Pillar | S22 status | S24 close status | **S25 close status** |
|---|---|---|---|---|
| B1 | Voucher portal | ❌ Not built | ✅ Sub-A SHIPPED (Admin-only) | ✅ **Sub-A now multi-user; works for Sales Rep + HR + Admin via new auth** |
| B2 | Approver portal | ❌ Not built | ❌ Not built | ❌ Still not built (deferred to PD-S26-PORTAL-SUB-B2-APPROVER) |
| B3 | Weekly meeting report | ❌ Not built | ❌ Not built | ❌ Unchanged |
| B4 | PWA validation | ⚠️ Manifest only | ⚠️ Unchanged | ⚠️ Unchanged (blocked on TRAI DLT) |
| B5 | Role differentiation | ⚠️ Backend-only | ⚠️ Backend-only (blocked on PD-S25-VECRM-AUTH) | ✅ **UNBLOCKED — auth now resolves session→employee→role** |
| B6 | Lead → Inquiry pipeline | ⚠️ Backend works | ✅ Portal-driven end-to-end | ✅ Works for portal-authenticated users (post-PD-S25-AUTH + Phase 5.5 perm fix) |
| B7 | Tally → ERPNext | ⚠️ Deferred | ⚠️ Deferred | ⚠️ Unchanged |
| B8 | TRAI DLT | ⚠️ Deferred | ⚠️ Deferred | ⚠️ Unchanged |

**Net S25 progress on Session-0 pillars: B5 fully unblocked (auth-resolved sessions enable role differentiation throughout the portal). B1 surface area widened from Admin-only to all three role types.**

---

## 2. What S25 shipped — commits, PRs, scope

### 2.1 `vecrm` repo (7 commits → squash-merged as `5e0df3b` via PR #16)

| Commit | Phase | What it shipped |
|---|---|---|
| `27be3cf` | 1 | Schema: 4 credential fields on VECRM Employee (`password_hash`, `failed_password_attempts`, `locked_until`, `last_login_at`); `unique:1` on `vecrm_email`; VECRM Auth Audit Log doctype; 3 migration patches + paired rollbacks (`add_auth_fields`, `create_auth_doctypes`, `create_vecrm_portal_user`); shared portal user bootstrap |
| `3218402` | 1.5 | `role.json` `desk_access:0` on Submitter/Approver (OBS-S25-Y caught: Frappe auto-promotes Website User → System User if role has `desk_access:1`); shared user `user_type` fix via `fix_portal_user_type.py` patch using direct `frappe.db.set_value` (NOT `import_file_by_path` — OBS-S25-Z avoided) |
| `83a7002` | 2 | API endpoints: `login_with_password`, `vecrm_logout`, `get_session_employee` in `vecrm/api.py`; new `vecrm/vecrm/utils/roles.py` with `EMPLOYEE_ROLE_TO_FRAPPE_ROLES` translation table |
| `b334dd8` | 2.5 | Empty-body POST defense — `login_with_password(email: str = "", password: str = "")` defaults added (OBS-S25-AD — empty body TypeError → now clean 401 + `missing_input` audit) |
| `2aab6c9` | 4.5 | OBS-S25-AH workaround (later reverted by 4.7) — get_decrypted_password dance for Password fieldtype's None-on-get_doc behavior |
| `adb74a1` | 4.6 + 4.7 | **OBS-S25-AL session persistence fix**: `frappe.local.session_obj.update(force=True)` replacing wrong-shaped `frappe.cache.hset` that poisoned the session cache slot. **OBS-S25-AK fieldtype change**: `password_hash` Password → Data (Password fieldtype had delete-on-save footgun via __Auth row; Data stores in parent column, survives `.save()`). Includes migration `convert_password_hash_to_data.py` (reload_doc + `sync_for(app, force=1)` + drop orphan __Auth rows + NULL parent column) and paired rollback |
| `3e1ee60` | 5.5 | **OBS-S25-AR §10.1 risk fix** — VECRM Lead + VECRM Inquiry doctype perm extension for VECRM Submitter (r/w/c, print) + VECRM Approver (read, print). Mirrors VECRM Travel Voucher's shape stripped of submittable-only keys. Migration `extend_lead_inquiry_perms.py` (reload_doc → sync_for with `reset_permissions=True` → clear_cache → commit). Paired rollback |

### 2.2 `vecrm-portal` repo (1 commit → squash-merged as `8165f7a` via PR #8)

| Commit | Phase | What it shipped |
|---|---|---|
| `75fa831` | 3 | 4 BFF routes swapped to new vecrm endpoints (Option A — minimal touch): `lib/auth-ssr.ts` (`getFrappeUser()` → `vecrm.api.get_session_employee`, returns `message.name`), `app/api/auth/login/route.ts` (`vecrm.api.login_with_password`, maps `usr→email` + `pwd→password`), `app/api/auth/logout/route.ts` (`vecrm.api.vecrm_logout`), `app/api/me/route.ts` (`vecrm.api.get_session_employee`, normalizes not-ok to HTTP 401 for travel-vouchers session-loss redirect — OBS-S25-AF). LoginForm, AppShell, TopBar, MobileNav, layout untouched per Option A design decision. |

### 2.3 Docs PR (this session-close PR — to be opened)

| Doc | Status |
|---|---|
| `docs/session-handovers/S25-close-handover.md` | NEW — this document |
| `docs/VECRM-PENDENCY-REGISTER.md` | REGENERATED comprehensively |
| `docs/VECRM-DEPENDENCY-MAP.md` | UPDATED for S25 production state |
| `docs/S26-OPENER-PROMPT.md` | NEW |
| `docs/architectural-locks/VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE.md` | NEW (formal lock from OBS-S25-AL) |
| `docs/architectural-locks/VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE.md` | NEW (formal lock from OBS-S25-AK) |
| `docs/architectural-locks/VECRM-LOCK-PORTAL-USER-ROLES.md` | NEW (formal lock from OBS-S25-H/Y) |
| `docs/architectural-locks/VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE.md` | NEW (formal lock from OBS-S25-AV) |
| `docs/architectural-locks/VECRM-LOCK-FILE-DELIVERY-NOT-PASTE.md` | NEW (formal lock from OBS-S25-AP) |
| `docs/S25-OPENER-PROMPT.md` | RETIRED (served its purpose; lives in git history) |

---

## 3. Production verification — all gates passed

### 3.1 Phase 4 backend curl smoke (5/5 pass)

1. **`login_with_password` (Test Sales Rep)** → HTTP 200, sid issued, identity returned ✓
2. **`get_session_employee` (LOAD-BEARING)** → HTTP 200, full identity including `login_path:"password"` — session data persists across HTTP boundary ✓
3. **`vecrm_logout` + session-dead verify** → HTTP 200 logout; subsequent `get_session_employee` returns 403 PermissionError ✓
4. **Lockout at 5 failed attempts** → attempts 1-5 generic 401 `invalid_credentials`; attempt 6 (correct password while locked) → generic 401 ✓
5. **Audit roster + `password_hash` survives `.db_update()`** → 9 events captured with correct emp/path/reason; HR Approver `password_hash` still present (87 chars) after `db_update`-based lockout clear ✓

### 3.2 Phase 5 browser smoke (3 users × 4 surfaces × 1 detail page = all green)

Vercel preview URL (Saturday ~12:47 IST): `https://vecrm-portal-git-fea-628a6d-vinay-enterprises-projects-5379af16.vercel.app/`

- **Test Sales Rep** logged in (top bar "Test Sales Rep") — Dashboard / Leads / Inquiries / Travel Vouchers all render data, no "Frappe responded 403" banner ✓
- **Test HR Approver** logged in (top bar "Test HR Approver") — same 4 surfaces render + Travel Voucher detail page (VE/TV/00094) shows full visit-lines child table + total derivations ✓
- **Ajay Salvi (Admin)** logged in (top bar "Ajay Salvi") — same 4 surfaces render ✓

### 3.3 Final production curl smoke against `crm.vinayenterprises.co.in` (post-merge, 3/3 pass)

Run against the production domain (NOT Vercel preview) after both PRs landed on main:

```
login_with_password (testrep)       → HTTP 200, identity returned
get_session_employee LOAD-BEARING   → HTTP 200, "login_path":"password"
vecrm_logout                        → HTTP 200, full_name:"Guest"
```

End-to-end session lifecycle verified in production.

---

## 4. Architectural locks — full active list at S25 close

All pre-S25 locks remain in force. S25 adds 5 new locks. Each has a file under `docs/architectural-locks/`.

### Numeric (from S22 and earlier)

- **VECRM-L8** — Allocator dual-surface sha verification. Banked sha: `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` (unchanged through S25; allocator not touched)
- **VECRM-L10** — Strict gap-free allocator invariant
- **VECRM-L13** — Squash-merge + branch delete on PR merge. Honored throughout S25.
- **VECRM-S22-A** — Counter allocator value-read invariant (read counter value INSIDE the same `SELECT ... FOR UPDATE` statement)

### Named locks earned in S23

- **VECRM-LOCK-AUTONAME-HYGIENE** — `autoname=''` is the only safe value; `"prompt"` silently bypasses controllers per Frappe v16.18.2 `naming.py` L158
- **VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER** — name guards in `validate()` not `before_insert()`; Frappe v16.18.2 `document.py` L441 < L442
- **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** — destructive VPS ops require dispatcher authorization; VECRM-scoped only; never touch VEMIO; three-tier backup approach

### Named locks earned in S24

- **VECRM-LOCK-NEXTJS-NAME-PARAM-DECODE** — All `app/<resource>/[name]/...` and `app/api/<resource>/[name]/...` routes MUST decode `name` at entry. Earned by OBS-S24-L/N/P.

### Named locks earned in S25 (NEW)

- **VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE** — Custom session-data writes MUST mutate `frappe.session.data.*` directly and persist via `frappe.local.session_obj.update(force=True)`. NEVER use raw `frappe.cache.hset` on session slots. Wrong-shape cache writes poison the slot. `force=True` required to bypass the time-threshold gate on fresh sessions. Earned by OBS-S25-AL.
- **VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE** — Doctype fields storing values that are ALREADY one-way hashes (passlib, scrypt, argon2) MUST use fieldtype `Data`, NOT `Password`. The Password fieldtype has a delete-on-save footgun: `get_doc()` loads it as `None`, and any subsequent `.save()` propagates `None` to the `__Auth` table → Frappe deletes the auth row. Data fieldtype stores in the parent column, loads correctly via `get_doc`, survives doc mutations. Earned by OBS-S25-AK.
- **VECRM-LOCK-PORTAL-USER-ROLES** — Shared portal user (`vecrm-portal@vinayenterprises.co.in`) is **Website User** with **VECRM Submitter + VECRM Approver** roles only. NEVER VECRM Admin (privilege escalation per OBS-S25-H). Role JSON files MUST have `desk_access:0` on Submitter/Approver (OBS-S25-Y: Frappe auto-promotes Website User → System User when assigned a role with `desk_access:1`). Earned by OBS-S25-H + OBS-S25-Y.
- **VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE** — Every `§risk` section in a dispatch MUST include a concrete verification gate (a query or check that proves the risk doesn't apply) executed at the moment the risk becomes structurally concrete (e.g., when shared-user role membership is decided). Risk acknowledgment without verification is a structural defect. Earned by OBS-S25-AV (§10.1 risk landed at Phase 5 instead of Phase 1.5 where it became concrete).
- **VECRM-LOCK-FILE-DELIVERY-NOT-PASTE** — Source artifacts > ~30 lines (Python modules, JSON, SQL, config files) MUST be delivered to the executor via `present_files` (download) not inline chat code blocks. Paste fidelity in chat is unreliable across formatting/markdown/heredoc transformations. Verified empirically in S25: 4 iterations of "the patch source is wrong" before file delivery resolved it. Earned by OBS-S25-AP.

### Cross-cutting discipline (carried)

- **OBS-S71-A (PERMANENT)** — `git branch --show-current` before AND after every commit-bearing or merge-bearing bash invocation. Honored throughout S25.

---

## 5. Component-by-component build status — post-S25 ground truth

Per OBS-S22-B, this section documents the ACTUAL ground-truth state of every component. Cross-check before relying on prose elsewhere.

### Layer 1 — Foundation doctypes

| Component | Status | Notes |
|---|---|---|
| VECRM Employee | ✅ | autoname=`field:vecrm_phone`. **S25: 4 credential fields added** (password_hash Data, failed_password_attempts Int, locked_until Datetime, last_login_at Datetime). Unique:1 on vecrm_email. 3 Active rows: Test Sales Rep (+91-9999900001), Test HR Approver (+91-9999900002), Ajay (+91-9327547536). |
| VECRM Voucher Counter | ✅ | TV-26-27, EV-26-27, LEAD-26-27, INQ-26-27 all live. **TV-26-27 counter at 94 at S25 close** (unchanged from S24). |
| VECRM Voucher Audit Log | ✅ | append-only, shared across TV + EV |
| VECRM Inquiry Audit Log | ✅ | Q9 transport works; not stress-tested |
| **VECRM Auth Audit Log (NEW S25)** | ✅ | append-only; columns: event, employee, path, reason, creation. ~10 events from Phase 4-5 smoke runs (real data). |
| **VECRM Portal User (Frappe User shared, NEW S25)** | ✅ | `vecrm-portal@vinayenterprises.co.in`, Website User, roles=[VECRM Submitter, VECRM Approver]. Created via bootstrap patch. |
| Frappe Roles | ✅ | VECRM Submitter, VECRM Approver, VECRM Admin, Sales Head, HR. **S25 fix: Submitter/Approver desk_access:0.** |

### Layer 2 — Voucher pillar

| Component | Status | Notes |
|---|---|---|
| VECRM Travel Voucher | ✅ | submittable, autoname via allocator. **S25: now works for all 3 portal roles via session-data resolution.** |
| VECRM Visit Line | ✅ | child of TV, km×rate computation |
| VECRM Expense Voucher | ✅ | submittable. Portal screens still pending (PD-S26-PORTAL-SUB-B-EXPENSE). |
| VECRM Expense Line | ✅ | child of EV |
| VECRM Rate Card | ✅ | per-km rate lookup, Ahmedabad ₹2.5/km, Mumbai+Pune ₹3.5/km |
| approve_travel_voucher API | ✅ | first-to-approve-wins, role-checked |
| approve_expense_voucher API | ✅ | same shape as TV approve |
| Travel Voucher portal | ✅ | **S25: multi-user via new auth** |
| Expense Voucher portal | ❌ | PD-S26-PORTAL-SUB-B-EXPENSE (A1 recon banked from S24 dispatch D) |
| Approver portal | ❌ | PD-S26-PORTAL-SUB-B2-APPROVER |
| Voucher cancel audit | ❌ | PD-S26-VOUCHER-CANCEL-AUDIT (carried from S24) |

### Layer 3 — Sales pipeline

| Component | Status | Notes |
|---|---|---|
| VECRM Lead | ✅ | autoname=controller, slash-format. **S25: VECRM Submitter (r/w/c) + VECRM Approver (read) perms added** |
| VECRM Inquiry | ✅ | created from Lead convert. **S25: VECRM Admin + Submitter + Approver perms added (VECRM Admin row was missing pre-S25 — latent bug)** |
| convert_lead_to_inquiry API | ✅ | works end-to-end |
| Lead portal — list / detail / create | ✅ | **S25: works for portal-authenticated Submitter sessions** |
| Inquiry portal — list / detail | ✅ | **S25: works for portal-authenticated sessions** |
| VECRM Customer (skeleton) | ⚠️ | minimal; deferred pending Tally→ERPNext |
| VECRM Quote/Order/Invoice | N/A | ERPNext domain |

### Layer 4 — Reporting & Workflow

| Component | Status | Notes |
|---|---|---|
| Weekly meeting report | ❌ | B3 backlog |
| Sales activity dashboard | ❌ | depends on data accumulation |
| PWA (manifest only) | ⚠️ | blocked on TRAI DLT |
| Push notifications | ❌ | blocked on TRAI DLT |

### Authentication & Authorization (NEW LAYER, S25)

| Component | Status | Notes |
|---|---|---|
| `vecrm.api.login_with_password` | ✅ | email+password; account lockout @5/15min; generic 401 on locked accounts (no enumeration) |
| `vecrm.api.vecrm_logout` | ✅ | invalidates session; reads `vecrm_employee_phone` from session data at logout time |
| `vecrm.api.get_session_employee` | ✅ | returns full identity including `login_path:"password"`, employee, name, vecrm_email, role, base_city |
| `_issue_session` helper | ✅ | calls `frappe.local.login_manager.login_as(_VECRM_PORTAL_USER)`, mutates `frappe.session.data.vecrm_*` keys, calls `frappe.local.session_obj.update(force=True)` to persist BOTH DB sessiondata row AND cache slot |
| `_on_failure` helper | ✅ | increments failed_password_attempts; locks at 5; emits audit; uses `db_update` not `.save()` |
| Account lockout | ✅ | 5 failed attempts → 15-minute window; correct password during lockout still rejected with generic 401 |
| Audit log emission | ✅ | events: auth.login.success, auth.login.failed (reasons: invalid_credentials, no_password_configured, account_locked, missing_input), auth.account_locked, auth.logout |
| Phone+PIN | ❌ | **Deferred to S26 (PD-S26-AUTH-PHONE-PIN)** |
| Email-based password reset | ❌ | **Deferred to S26 (PD-S26-AUTH-RESET)** |
| Microsoft Graph wiring | ❌ | **Deferred to S26 (PD-S26-AUTH-MS-GRAPH)** |
| `admin_set_credential` portal endpoint | ❌ | **Deferred to S26 (PD-S26-AUTH-ADMIN-SET)**; currently console-only |
| Credential rotation (encryption_key, vecrm_internal_secret) | ❌ | **Deferred to S26 (PD-S26-AUTH-CREDS-ROTATE)** per OBS-S25-D |

### Cross-cutting infrastructure

| Component | Status | Notes |
|---|---|---|
| SSR cookie hydration (S23 PR #4 shim) | ⚠️ | Admin-only; S25 auth makes it less critical but the shim isn't replaced yet |
| `docs/portal-conventions.md` | ✅ | S24 PR #14, 11 sections |
| Architectural locks documentation | ✅ | All locks have files in `docs/architectural-locks/`. **5 new files added in S25.** |
| Session handover discipline | ✅ | This document continues the discipline |

---

## 6. Production data state (S25 close)

| Anchor | Value |
|---|---|
| Site | `crm.vinayenterprises.co.in` |
| VPS | `217.216.58.117` (Contabo Mumbai) |
| Frappe version | v16.18.2 |
| `require_type_annotated_api_methods` | ENABLED (site-wide via `hooks.py`) |
| Container | `vecrm-backend-1` |
| VPS RAM | 12GB (upgraded from 8GB in S20 to support full vecrm rebuilds) |
| VPS CPU | 6 cores |
| **`vecrm` main HEAD** | **`5e0df3b`** (post-PR #16 squash) — will increment with S25 docs PR |
| **`vecrm-portal` main HEAD** | **`8165f7a`** (post-PR #8 squash, Vercel auto-deployed) |
| Allocator sha (VECRM-L8) | `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` (unchanged) |
| Counter TV-26-27 | 94 (unchanged from S24) |
| Counter LEAD-26-27 | 13 (unchanged) |
| Counter INQ-26-27 | 12 (last allocated VE/INQ/00012, unchanged) |
| Counter EV-26-27 | 12 (unchanged) |
| Production Frappe Users | 2 real (`ajay@`, `vecrm-portal@`), 3 demo seed |
| **Production VECRM Employees** | **3 Active** (Test Sales Rep, Test HR Approver, Ajay Salvi — all Ahmedabad) |
| Voucher audit log rows | ~13 (append-only) |
| **VECRM Auth Audit Log rows** | **~10** (from Phase 4/5 smoke runs; append-only) |

### Test credentials (operator-private; only Ajay knows password)

- **Test Sales Rep**: `+91-9999900001` / `test.salesrep@vinayenterprises.co.in` / `testrep123` / Sales Rep / Ahmedabad
- **Test HR Approver**: `+91-9999900002` / `test.hr@vinayenterprises.co.in` / `testhr1234` / HR / Ahmedabad
- **Ajay (real)**: `+91-9327547536` / `ajay@vinayenterprises.co.in` / Admin / Ahmedabad (password set by Ajay during S25 Phase 5.A)

**Note**: Test passwords are committed in plaintext to this handover doc because they're throwaway dev credentials on a dev-purpose user. If S26 introduces real customer onboarding, rotate the test passwords or remove these users.

### Container topology on VPS (unchanged from S24)

- `vecrm-backend-1` — Frappe v16.18.2, vecrm app at `/home/frappe/frappe-bench/apps/vecrm/`
- `vemio-*` containers — separate stack, VEMIO concerns (never touch from VECRM dispatch per VECRM-LOCK-VPS-DESTRUCTIVE-OPS)

---

## 7. Known schema drift (post-S25)

### G1. Phantom `tabVECRM Sales Visit` table (UNCHANGED FROM S23)

Doctype retired in S8 but table not dropped. PD-S26-PHANTOM-SALES-VISIT-TABLE (carried).

### G2. Counter test data (UNCHANGED)

`tabVECRM Voucher Counter` has rows from S22 §6 hard-gate tests. Retained per audit policy. Not a defect.

### G3. Lead doctype permissions (FIXED S24, EXTENDED S25)

S24 PR #15: VECRM Admin row added. **S25 PR #16 (Phase 5.5): VECRM Submitter + VECRM Approver rows added.**

### G4. Customer doctype skeleton (UNCHANGED)

Minimal fields only; full schema deferred pending Tally→ERPNext decision.

### G5. Voucher cancellation audit gap (CARRIED)

PD-S26-VOUCHER-CANCEL-AUDIT. `on_cancel` hook missing from both TV and EV controllers. Cancellation currently un-audited.

### G6. VECRM Inquiry doctype permissions (FIXED S25)

Pre-S25 state: only System Manager had perms. Latent bug — Ajay only had access because he authenticated as Frappe Administrator (superuser bypass). **S25 PR #16 (Phase 5.5): VECRM Admin + VECRM Submitter + VECRM Approver rows added.**

### G7. VECRM Employee.password_hash __Auth orphans (NEW S25, CLEANED IN-SESSION)

Phase 4.7 migration `convert_password_hash_to_data.py` dropped any stranded `__Auth` rows for VECRM Employee password_hash that existed pre-fieldtype-change. Future inserts go to parent column directly. No active drift.

---

## 8. OBS-S25 catalog (A through AX)

47 dispatcher-discipline observations filed during S25. Full list with significance flag.

### Critical (dispatcher mental-model vs ground truth — would have shipped wrong code)

| # | Pattern | Resolution |
|---|---|---|
| **H** | Dispatcher proposed VECRM Admin role for shared portal user (privilege escalation) | Caught at Phase 1 review; → VECRM-LOCK-PORTAL-USER-ROLES |
| **AH** | Doc-attribute check on Password field returned None (workaround) | Reverted in Phase 4.7 root fix |
| **AK** | Password fieldtype delete-on-save footgun → __Auth row deleted on .save() | Phase 4.7 Password→Data; → VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE |
| **AL** | Manual `frappe.cache.hset` wrote inner payload to outer-shape slot → session data lost between requests | Phase 4.6 `session_obj.update(force=True)`; → VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE |

### Critical (state-tracking failures across turns)

| # | Pattern | Resolution |
|---|---|---|
| **AM** | Dispatcher composed turn referencing 4.6 source-read as "pending" when Claude Code had delivered it the previous turn | → PD-S26-DISPATCHER-DISCIPLINE-MECHANICAL-RULES |
| **AN** | Dispatcher referenced patch source as "in previous turn" when only verbal description existed | → file-delivery rule |
| **AO** | Third recurrence of AN; pattern confirmed structural | → file-delivery rule |
| **AP** | **STRUCTURAL FIX**: source artifacts via `present_files`, not inline chat code blocks | → VECRM-LOCK-FILE-DELIVERY-NOT-PASTE |
| **AS** | Executor-direction state-tracking failure (Claude Code flagged a committed-and-deployed change as still-blocking) | → "git log --oneline -5 before flagging blocker" rule |

### Critical (risk vs verification)

| # | Pattern | Resolution |
|---|---|---|
| **AR** | §10.1 risk landed at Phase 5 Step 5.E (regression check) — VECRM Lead/Inquiry doctype perms didn't grant access to shared portal user's roles | Phase 5.5 fix shipped |
| **AV** | **STRUCTURAL FIX**: §risk sections need verification gates (one query at the moment the risk becomes concrete), not just acknowledgment | → VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE |
| **AW** | "Mirror Travel Voucher exactly" framing was structurally wrong (TV is submittable, Lead/Inquiry are not) | Executor caught; corrected to strip submit/cancel/amend keys |

### Notable (minor / informational, no resolution beyond filing)

| # | Pattern |
|---|---|
| A, E, X | Field-name mis-quotes against actual schema |
| F | Type-annotation enforcement is structural in Frappe v16 (`require_type_annotated_api_methods`), not a flag |
| G | Known-unknown was already known |
| I, J, K | R3 recon synthesized findings; "R3 complete" framing partially false |
| L | probe.py robustness gaps caught by Claude Code |
| M-V | Frappe runtime-deployment behavior misunderstood (multiple iterations: proper deploys via bench migrate register endpoints; runtime-add via `@frappe.whitelist()` does NOT) |
| W | role.json desk_access:1 footgun (caught at Phase 1.5) |
| Y | Frappe auto-promotes Website User → System User on role desk_access |
| Z | Dispatcher reached for unverified `import_file_by_path` when `frappe.db.set_value` was the right primitive |
| AB | `set_encrypted_password` unused import (kept for S26) |
| AD | `login_with_password` missing param defaults (Phase 2.5 fix) |
| AF | `/api/me` should normalize not-ok to HTTP 401 for session-loss redirect (Phase 3 fix) |
| AG | `frappe_user` response key renamed to `employee_name` (Phase 3) |
| AQ | Chrome extension noise in console (informational, not app code) |
| AT | Dispatcher diagnostic queried `Lead` (standard Frappe CRM doctype) when portal uses `VECRM Lead` (custom); executor corrected |
| AU | `frappe.set_user` is not a context manager in v16.18.2; call directly |
| AX | VPS container doesn't track vecrm as a git repo; deployments are tar-based (by-design, not a regression) |

### Naming gap

S25 catalog jumps from `B` to `D` (no `C`), from `D` to `E` (gap is intentional — `C` was used informally early on but never formally filed). Not significant.

---

## 9. PD-S26+ items filed during S25

### Auth backlog (highest priority for S26)

- **PD-S26-AUTH-PHONE-PIN** — Phone+PIN backend (companion to email+password). Scope: separate `login_with_pin` endpoint, PIN stored as Data-fieldtype passlib hash on VECRM Employee, same lockout/audit mechanics
- **PD-S26-AUTH-RESET** — Email-based password reset flow. Microsoft Graph email delivery, ratelimited token issuance, reset-token doctype with TTL
- **PD-S26-AUTH-MS-GRAPH** — Microsoft Graph wiring for outbound email (reset emails primarily; could later send weekly reports)
- **PD-S26-AUTH-ADMIN-SET** — `admin_set_credential` as properly-gated portal endpoint (today: console-only). Allows VECRM Admin to set/reset credentials for VECRM Employees.
- **PD-S26-AUTH-CREDS-ROTATE** — Rotate encryption_key and vecrm_internal_secret per OBS-S25-D

### Dispatcher discipline (codify S25 lessons)

- **PD-S26-DISPATCHER-DISCIPLINE-MECHANICAL-RULES** — Codify the OBS-S25 patterns as mechanical prevention rules:
  - Source artifacts via `present_files`, not inline chat (OBS-S25-AP / new lock)
  - `git log --oneline -5` before flagging a blocker (OBS-S25-AS)
  - No cross-turn source references (OBS-S25-AM/AN/AO)
  - No mental-model code (general principle, multiple firings)
  - Verified-symbol-only prescriptions (e.g., OBS-S25-AT `Lead` vs `VECRM Lead`)
  - §risk → §verification-gate (OBS-S25-AV / new lock)

### Portal continuation backlog

- **PD-S26-PORTAL-SUB-B-EXPENSE** — Expense Voucher portal (A1 recon banked in S24 dispatch D)
- **PD-S26-PORTAL-SUB-B2-APPROVER** — Approver queue UI; both `approve_travel_voucher` and `approve_expense_voucher` backend APIs exist
- **PD-S26-VOUCHER-DRAFT-CLEANUP** — GC orphan voucher drafts older than N days (e.g., 7). Scheduled task. ~30 min work.
- **PD-S26-VOUCHER-DRAFT-RESUME** — Resume-from-draft flow on `new` form pages. ~2-3h UI work.
- **PD-S26-DEAD-AUTH-ME-ROUTE** — Delete `app/api/auth/me/` (dead route in vecrm-portal, not touched in S25)
- **PD-S26-PORTAL-VECRMSESSION-TYPE** — Expand `getFrappeUser()` return type from string to full VecrmSession object

### Schema cleanup (carried)

- **PD-S26-VOUCHER-CANCEL-AUDIT** — `on_cancel` hooks for TV+EV controllers (~30 min). Carried from S24.
- **PD-S26-PHANTOM-SALES-VISIT-TABLE** — Drop vestigial `tabVECRM Sales Visit` table (~15 min). Carried from S23.

### Auth code cleanup (filed in S25)

- **PD-S26-AUTH-FORMATTING-CONSISTENCY** — Run black/ruff across vecrm app (general hygiene)
- **PD-S26-AUTH-VECRM-INIT-INVESTIGATION** — `vecrm/__init__.py` auto-import-submodules investigation (Phase 0.5 OBS-S25-V byproduct)
- **PD-S26-AUTH-OBS-Z-AUDIT** — `get_decrypted_password` verified-substitution audit (OBS-S25-Z)

### Long-deferred (carried > 12 sessions; multi-day operator-side work)

- **TRAI DLT registration** — required to unblock SMS push notifications and final PWA validation
- **Tally → ERPNext migration** — API-driven; engage Ahmedabad ERPNext partner when started

### Out of scope (explicit non-VECRM)

| Item | Owner |
|---|---|
| Quote / Order / Invoice doctype | ERPNext |
| Inventory | ERPNext / N/A (services business) |
| Payment reconciliation | ERPNext |
| Tax / GST config | ERPNext + Indian Compliance app |
| TACACS+ / RADIUS / network auth | VEMIO |
| Network monitoring / alerts / SLAs | VEMIO |
| GLPI ticketing | VEMIO (decommissioned in S64) |

---

## 10. Reading order for S26 session-open

In order:

1. **This document** (`docs/session-handovers/S25-close-handover.md`) — primary input, current state, what shipped
2. **`docs/VECRM-PENDENCY-REGISTER.md`** — comprehensive tactical + strategic backlog (regenerated at S25 close)
3. **`docs/VECRM-DEPENDENCY-MAP.md`** — infrastructure state, versions, what depends on what (updated at S25 close)
4. **`docs/architectural-locks/`** — formal locks, one file each. **Read all 5 new S25 locks at minimum** (FRAPPE-SESSION-PERSISTENCE, PASSWORD-FIELDTYPE-AVOIDANCE, PORTAL-USER-ROLES, RISK-NEEDS-VERIFICATION-GATE, FILE-DELIVERY-NOT-PASTE).
5. **`docs/S26-OPENER-PROMPT.md`** — exact opener prompt with cold-check gates

---

## 11. Honest retrospective

S25 was a 14-hour session shipping a single coherent feature (email+password auth) end-to-end. Compared to S24 (multi-PR feature work) or S23 (Layer-2 completion), S25's signal-to-noise was uneven: a lot of dispatcher iteration on the same patch, four state-tracking failures, and the §10.1 risk landing at Phase 5 instead of Phase 1.5.

**What worked:**

- The phase-gate discipline: every phase had a verification gate before the next phase deployed. Smoke 2 was the load-bearing test for OBS-S25-AL; without it, the session-cache poison would have shipped silently.
- Claude Code's empirical pushback: caught OBS-S25-H (privilege escalation), OBS-S25-Y (desk_access auto-promotion), OBS-S25-AT (Lead vs VECRM Lead), OBS-S25-AW (submittable keys on non-submittable doctypes). Each catch saved a deploy cycle.
- Operator endurance: 14 hours through 47 OBS observations. Multiple "we're going down a rabbit hole" moments handled by stepping back and verifying ground truth.
- Source-read discipline (when applied): Phase 4.6 `Session.update` source-read was decisive. Phase 0.5 `LoginManager` source-read settled the (a) vs (b) outcome question.

**What didn't work:**

- Dispatcher cross-turn state tracking failed 4 times (AM/AN/AO/AS). Pattern is now mechanical: file delivery for source, git-log before flagging blockers.
- §risk → §verification-gate gap. The §10.1 risk was acknowledged in v2 dispatch but not audited at Phase 1.5 close. Cost: ~30 minutes of Phase 5.5 work. Structural fix locked.
- Phase 0.5 probe iterations (4 attempts) before pivoting to bench-console probes. Dispatcher kept trying to runtime-add endpoints in violation of Frappe v16's registration model. OBS-S25-S filed mid-session: "should have used console earlier."
- Initial estimate vs actual: A2 dispatch authored as 2093 lines targeting ~6-8 phases; actual execution required Phases 1, 1.5, 2, 2.5, 3, 4.5, 4.6, 4.7, 5, 5.5 (10 phases). The discovery rate (Phases 1.5, 2.5, 4.5, 4.6, 4.7, 5.5 all surfaced mid-execution) reflects the depth of unknowns in Frappe internals.

**For S26:**

- File delivery is non-negotiable for source artifacts > 30 lines (new lock).
- §risk sections need verification gates (new lock).
- Auth backlog is the priority frontier (phone+PIN + reset + Microsoft Graph wiring).
- Portal continuation (Sub-B Expense + Sub-B2 Approver) is the visible-progress frontier.

---

## 12. Session-close commit sequence (this PR)

Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS, this is local-only work (no VPS touch), so Claude Code can do this end-to-end.

```
Author S25 close handover docs PR. All deliverables banked at /Users/ajaysalvi/Downloads/
(operator downloads from chat first). Local-only — zero VPS touch.

Execute:

cd ~/Documents/GitHub/vecrm
git checkout main
git pull origin main
git branch --show-current  # OBS-S71-A pre-branch (expect: main)
git checkout -b docs/s25-close-handover

# New files
mkdir -p docs/session-handovers
cp ~/Downloads/S25-close-handover.md docs/session-handovers/S25-close-handover.md
cp ~/Downloads/S26-OPENER-PROMPT.md docs/S26-OPENER-PROMPT.md

# Overwrite (regenerated) files
cp ~/Downloads/VECRM-PENDENCY-REGISTER.md docs/VECRM-PENDENCY-REGISTER.md
cp ~/Downloads/VECRM-DEPENDENCY-MAP.md docs/VECRM-DEPENDENCY-MAP.md

# New lock files
mkdir -p docs/architectural-locks
cp ~/Downloads/VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE.md docs/architectural-locks/
cp ~/Downloads/VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE.md docs/architectural-locks/
cp ~/Downloads/VECRM-LOCK-PORTAL-USER-ROLES.md docs/architectural-locks/
cp ~/Downloads/VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE.md docs/architectural-locks/
cp ~/Downloads/VECRM-LOCK-FILE-DELIVERY-NOT-PASTE.md docs/architectural-locks/

# Retire the S25 opener (its purpose was served; lives in git history)
[ -f docs/S25-OPENER-PROMPT.md ] && git rm docs/S25-OPENER-PROMPT.md || echo "S25 opener already retired"

git add docs/
git status
git diff --cached --stat

# STOP HERE — report staged set to dispatcher. Await commit-msg authorization.
```

After dispatcher review:

```
git commit -m "docs(s25): close handover + regenerated pendency register + dependency map + 5 architectural locks

Closes S25.

Captures the full session: email+password authentication shipped end-to-end
via vecrm PR #16 (squash-merged as 5e0df3b on main) and vecrm-portal PR #8
(squash-merged as 8165f7a on main, Vercel auto-deployed).

What S25 shipped:
- VECRM Employee credential fields (password_hash Data, failed_password_attempts,
  locked_until, last_login_at) + unique:1 on vecrm_email
- VECRM Auth Audit Log doctype (append-only)
- Shared VECRM Portal User (Website User, Submitter+Approver roles)
- vecrm.api.login_with_password / vecrm_logout / get_session_employee
- Account lockout @5/15min with generic 401 (no enumeration)
- Session persistence via frappe.local.session_obj.update(force=True)
- password_hash fieldtype Password→Data (delete-on-save footgun eliminated)
- VECRM Lead + VECRM Inquiry portal-role perm extension (Phase 5.5 fix)
- 4 BFF route swaps in vecrm-portal (Option A — minimal touch)

5 new architectural locks promoted:
- VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE (OBS-S25-AL)
- VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE (OBS-S25-AK)
- VECRM-LOCK-PORTAL-USER-ROLES (OBS-S25-H/Y)
- VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE (OBS-S25-AV)
- VECRM-LOCK-FILE-DELIVERY-NOT-PASTE (OBS-S25-AP)

Catalog: 47 OBS observations filed (A through AX).

Per operator directive (s25 close, second of two with explicit framing):
comprehensive handover not lightweight. Captures inheritance from S0-S24
plus all S25 work. Replaces S24-era pendency register with regenerated
version. Updates dependency map for S25 production state.

Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS: zero VPS impact, docs-only PR.

Lift §0.6 (PD-S25-VECRM-AUTH v2 execution) closes with this PR.

Refs PD-S25-VECRM-AUTH."

git push -u origin docs/s25-close-handover

gh pr create \
  --title "docs(s25): close handover + regenerated register + dependency map + 5 architectural locks" \
  --body "Closes S25. See commit message for the full deliverable list.

Docs-only PR. Zero code changes. Zero schema changes. Zero VPS impact.
The handover is comprehensive per operator directive (do not repeat
prior-session error of pointer-based handovers that drop context).

Lift §0.6 closes on merge.

Squash-merge per VECRM-L13." \
  --base main
```

---

## 13. Acknowledgments

- **Operator (Ajay Salvi):** sustained 14-hour focus through 47 OBS observations, 4 dispatcher state-tracking failures, 1 latent Frappe footgun, and 10 phases of executor work. Caught the "we're going down a rabbit hole" moments and pushed for clarity. Most operators would have lost patience at iteration 2 of the patch-source confusion. Sticking with it produced a clean ship.
- **Dispatcher (this Claude):** A2 dispatch authoring, source-read prescriptions, phase-gate adjudication, handover authoring. Filed 4 of its own state-tracking failures (AM/AN/AO/AS) honestly. Took the structural fixes (file delivery, verification gates, git-history checks) and codified them as locks.
- **Claude Code:** Source-read execution, console probes, staged-diff gates, commit-and-deploy ferrying, multiple substantive catches (Lead vs VECRM Lead, submittable-key trap, Frappe internals signatures). The (a) vs (b) framing on Session.update source-read was the decisive analytical move of the session.
- **Frappe v16.18.2 itself:** the OBS-S25-AK and OBS-S25-AL bugs were footguns that required source-reads to identify, not anything documentation would have surfaced. Filing here for posterity.

---

## 14. What S25 ships, in plain language

People can log in. Sales reps can submit travel vouchers. HR can approve them. Ajay can do everything. The auth survives logout, lockout, password rotation, doc edits, and session expiry. Three users walked through three full browser-smoke loops without a single 5xx error.

The implementation is real and works.

S26 is when the auth gets its second mechanism (phone+PIN), email-based reset, and the Approver portal that finally closes the voucher-approval loop.

---

**End of S25-close-handover.md**

This handover follows the discipline established at S23 close: comprehensive over lightweight, regenerated not surgical, designed so the next-session author can read this document alone and have the full picture without chasing 5 others. Per OBS-S22-B (do not trust prose; verify against ground truth at session-open), the cold-check gates in `S26-OPENER-PROMPT.md` validate every claim in this document.
