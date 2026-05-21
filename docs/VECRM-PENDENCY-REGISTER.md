# VECRM-PENDENCY-REGISTER

**Last updated:** 2026-05-21 (post-S22 close)
**Maintained by:** Session-close handovers
**Purpose:** Single source of truth for ALL deferred work. Tactical AND strategic. Per OBS-S22-E, the tactical register has historically dropped strategic items; this document corrects that by tracking BOTH.

---

## How this document is organized

1. **PART A — Tactical pendencies** — what's blocking specific PRs / recent sessions
2. **PART B — Strategic backlog** — what Session 0 said the product needs, status of each pillar
3. **PART C — Infrastructure debt** — what's accumulated across sessions
4. **PART D — Architectural locks active**
5. **PART E — Component-by-component build status** — actual ground-truth state of every doctype/feature
6. **PART F — Production data state**
7. **PART G — Known schema drift / cleanup needed**

**Per OBS-S22-B:** session-open MUST cross-check this document against ground truth before trusting any line item. Don't assume prose is reality.

---

## PART A — Tactical pendencies (post-S22)

### PD-S22-VOUCHER-AUDIT (🔴 HIGH — blocks production rollout)

**Issue:** `VECRM User Audit Log` has both `actor` and `target` as Link fields to `VECRM Employee`. Unfit for document-action audit (e.g. "Sales Rep X submitted Travel Voucher VE/TV/00021/26-27").

**Current state:** `_audit()` calls in `vecrm_travel_voucher.py` are commented out in `on_submit` and `approve_travel_voucher`, marked inline with `PD-S22-VOUCHER-AUDIT` markers. Functionality works without audit, but voucher workflow cannot ship to sales/HR without audit trail.

**S23 task (in priority order):**
1. Design `VECRM Voucher Audit Log` doctype with:
   - `actor` (Link to VECRM Employee, required)
   - `target_doctype` (Data, e.g. "VECRM Travel Voucher")
   - `target_name` (Data, e.g. "VE/TV/00021/26-27")
   - `action` (Select: insert, submit, approve, cancel, amend)
   - `from_state` / `to_state` (Data, optional, for state transitions)
   - `at_timestamp` (Datetime, default now())
   - `metadata_json` (Long Text, optional, for arbitrary action context)
2. Add controller with permission lockdown (read-only for all, no UI create/edit)
3. Re-enable audit calls in `vecrm_travel_voucher.py` (uncomment + adjust field names)
4. Re-run §5 single-thread + §6 concurrency hard-gate
5. Verify audit table itself doesn't introduce contention (test 10 concurrent submits each writing 2 audit rows = 20 audit inserts)
6. Commit as separate PR

**Estimated effort:** 2-3 hours
**Dependency:** none, can start immediately

### PD-S22-LOADING-FLASH (🟡 MEDIUM)

**Issue:** Portal shows unauthenticated UI flash on initial load before client-side auth state hydrates.

**Three library migrations rejected after S22 recon:**
- NextAuth v4 — incompatible session storage with current setup
- Auth.js v5 — early access, breaking changes ongoing
- Better Auth — promising but adds migration surface

**Selected path:** Path δ — SSR cookie hydration, no library. Server reads auth cookie before render, passes auth state in initial HTML hydration data.

**Banked dispatch:** `/mnt/user-data/outputs/DISPATCH-S22-AUTH-SSR-HYDRATION.md` (drafted S22, not executed)

**Estimated effort:** 1-2 hours
**Dependency:** none

### PD-S22-PHANTOM-SALES-VISIT-TABLE (🟢 LOW)

**Issue:** `tabVECRM Sales Visit` exists in DB with 0 rows. Doctype was retired in S8 but table never dropped.

**S23 task:** Verify 0 rows, then `DROP TABLE`. Single SQL.

**Estimated effort:** 5 minutes
**Dependency:** none

### PD-S22-EXPENSE-VOUCHER (🔴 HIGH — Layer-2 Phase 3 completion)

**Status:** Not started. Layer-2 is 75% complete: Voucher Counter ✅ (S20), Travel Voucher ✅ (S22), Visit Line ✅ (S22), **Expense Voucher ❌**.

**Scope:** `VECRM Expense Voucher` doctype + controller. Mirrors Travel Voucher shape but for non-travel expenses (hotel, food, supplies, communication, misc).

**Design constraints (locked in S22):**
- Submittable doctype, autoname `VE/EV/####/FY` at insert
- Separate counter series `EV` (not shared with `TV`)
- Approval chain: same as Travel Voucher (Sales Rep → {Sales Head, HR, Admin}; Field Engineer → {Head of Engineers, HR, Admin})
- Per-line item with category (Select: Hotel, Food, Supplies, Communication, Misc), amount, description, attachment
- **MUST apply VECRM-S22-A from start** (read value inside FOR UPDATE)
- §6 concurrency hard-gate REQUIRED before merge (per OBS-S22-A)

**Estimated effort:** 4-6 hours
**Dependency:** Should ideally land AFTER PD-S22-VOUCHER-AUDIT so audit shape is established

---

## PART B — Strategic backlog (Session 0 pillars)

These are pillars VECRM was scoped to deliver per Session 0. Some are partially built, some entirely missing. Per OBS-S22-E, this register documents them explicitly so they don't silently drop again.

### B1. Voucher portal (FRONTEND for submitters) — ❌ NOT STARTED

**Scope:** Field sales reps and engineers need a mobile-first PWA to submit travel/expense vouchers from the field. Cannot expect them to use Frappe Desk.

**Current state:** Backend doctypes + API exist (Travel Voucher submit + approve endpoints). Portal frontend does not exist. `vecrm-portal` repo has the auth/login flow and basic shell but no voucher screens.

**Required components (estimated):**
- Voucher list screen (mobile-optimized, filterable by status)
- Travel Voucher create form (with visit line builder, GPS-assisted km lookup, photo upload)
- Expense Voucher create form (per-line category + amount + photo)
- Voucher detail / status screen
- Push notifications for approval state changes (defer to TRAI DLT post-deferral)

**Estimated effort:** 15-25 hours across multiple sessions

### B2. Approver portal (FRONTEND for HR/Sales Head/Admin) — ❌ NOT STARTED

**Scope:** Approvers need a queue UI to see pending vouchers, drill into details, approve/reject.

**Current state:** API endpoint `approve_travel_voucher` exists. Queue UI does not.

**Required components:**
- Pending-approvals queue (filterable by submitter, date, amount)
- Voucher review screen with full visit/expense detail
- One-tap approve / reject-with-reason
- History view of past approvals (audit trail dependent on PD-S22-VOUCHER-AUDIT)

**Estimated effort:** 10-15 hours
**Dependency:** PD-S22-VOUCHER-AUDIT (for history view)

### B3. Weekly meeting report — ❌ NOT STARTED

**Scope:** Per Session 0, Vinay Enterprises holds weekly meetings reviewing sales pipeline + activities. Output is a structured report (lead conversions, visits, calls, won/lost, voucher spend).

**Current state:** Lead / Inquiry doctypes partially exist but not in a state that generates the report. No report builder. No scheduled generation.

**Required components:**
- `VECRM Weekly Report` doctype (week_start, week_end, generated_by, sections JSON)
- Server-side report generator (scheduled Sunday night for Mon meeting)
- Sections: pipeline movements, visits summary, calls summary, voucher summary, won/lost
- Manual override fields (managers can annotate)
- PDF export for meeting print

**Estimated effort:** 8-12 hours

### B4. PWA validation (vecrm-portal as installable app) — ⚠️ PARTIAL

**Scope:** vecrm-portal must be installable as PWA on field reps' phones, work offline for voucher draft creation, sync on reconnection.

**Current state:**
- ✅ `manifest.webmanifest` exists (FAVICON close was part of this)
- ✅ Basic responsive layout
- ❌ Service worker not built
- ❌ Offline draft storage not implemented
- ❌ Background sync not implemented
- ❌ Install prompts not surfaced

**Estimated effort:** 6-10 hours
**Dependency:** Voucher portal (B1) must be partially built first

### B5. Role differentiation (Sales Rep vs Field Engineer) — ⚠️ PARTIAL

**Scope:** Sales Reps and Field Engineers have different approver chains, different voucher types they typically submit, and different KPIs in the weekly report.

**Current state:**
- ✅ Approver chains differ in controller (encoded in `APPROVER_SETS`)
- ✅ Role field on VECRM Employee
- ❌ Portal UI doesn't differentiate (same form for both)
- ❌ Weekly report doesn't break out by role
- ❌ KPIs per-role not defined

**Estimated effort:** 4-6 hours (mostly UI + report work)

### B6. Lead / Inquiry / Customer pipeline — ⚠️ PARTIAL

**Scope:** Per Session 0, full sales pipeline: Lead → Inquiry → Quote → Order → Customer.

**Current state:**
- ✅ `VECRM Lead` doctype exists (S8-ish)
- ✅ `VECRM Inquiry` doctype exists (S9-ish)
- ❌ `VECRM Quote` doctype not built
- ❌ `VECRM Order` doctype not built
- ❌ `VECRM Customer` doctype exists but minimal
- ❌ State machine connecting them not built
- ❌ Voucher allocator now also called from Lead and Inquiry (per recon) — these were likely working pre-S22 fix; verify post-fix they still allocate correctly

**Estimated effort:** 20-30 hours across multiple sessions

### B7. Tally → ERPNext migration — ⚠️ DEFERRED

**Status:** Deferred per long-term operator decision. When migration happens, will be API-driven (not UI entry). ERPNext UI used as-is for back-office; custom frontend rejected after audit (UI surface too large: tax templates, GST, e-invoicing).

**Future requirement:** engage Ahmedabad ERPNext partner for opening-balance recon + GST account restructuring when migration starts.

**No active work pending.**

### B8. TRAI DLT registration (SMS sender registration) — ⚠️ DEFERRED

**Status:** Deferred 2-4 weeks per S22 decision.

**Impact when started:** unblocks push notifications + SMS for approval state changes (B2).

---

## PART C — Infrastructure debt

### C1. Diagnostic scripts in container

**Issue:** Multiple `_*.py` diagnostic files were created during S22 §6 investigation and copied into the container at `/home/frappe/frappe-bench/apps/vecrm/vecrm/_*.py`. Local repo copies were cleaned before commit, but container copies persist.

**Files (approximate list, verify before deleting):**
- `_diag_lock.py`, `_lock_diag.py`, `_deep_diag.py`, `_diag_full.py`
- `_get_doc_test.py`, `_conn_inline.py`, `_conn_in_orm.py`
- `_si_lock_test.py`, `_si_when_test.py`, `_si_orm_test.py`, `_test_si_off.py`
- `_set_global_si.py`, `_check_si.py`, `_check_commits.py`
- `_post_6_check.py`, `_check_counter.py`, `_check_audit.py`, `_recon_audit.py`
- `_check_draft.py`, `_conn_diag.py`, `_db_check.py`
- `_seed_test_employees.py`, `_smoke5.py`, `_smoke6.py`, `_smoke_prereq.py`

**Risk if left:** none active (not auto-loaded), but adds visual clutter when inspecting the app dir.

**Cleanup task (~10 min):**
```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bash -c "rm -f /home/frappe/frappe-bench/apps/vecrm/vecrm/_*.py"'
```

**Caveat:** `_smoke5.py` and `_smoke6.py` may want to be RETAINED in container (as regression tests for any future allocator changes). Consider promoting to permanent location at `vecrm/vecrm/tests/test_concurrency.py` instead of deleting.

### C2. `innodb_snapshot_isolation` GLOBAL was toggled during S22

**Issue:** Set to OFF globally during diagnostic, then restored to ON at close. Restoration was a runtime `SET GLOBAL` — does not persist across MariaDB container restart.

**Risk:** if vecrm-db-1 container restarts (manual or via update), `innodb_snapshot_isolation` may default to whatever the image config says. Need to verify the default in image config.

**S23 verification:**
```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute frappe.db.sql --args "[\"SELECT @@innodb_snapshot_isolation, @@global.innodb_snapshot_isolation\"]"'
```

**Optional hardening:** add to MariaDB config (my.cnf in image or volume) explicitly setting `innodb_snapshot_isolation = ON`. Low priority since VECRM-S22-A ensures correctness regardless of SI state.

### C3. Test data in production database

**Issue:** ~80 Travel Voucher rows from `+91-9999900001` accumulated in `crm.vinayenterprises.co.in` during §5 + §6 testing.

**Per Session 0 no-delete rule:** test data is NOT purged from production DB. Acceptable to keep for regression testing.

**S23 consideration:** if planning to onboard real submitters, may want to either:
- Tag test vouchers with a flag for UI filtering
- Reset counter to a clean number (e.g. 1000) so real vouchers start from there
- Just accept the noise — test data is identifiable by submitter `+91-9999900001`

### C4. Workflow violation tracking

**Per S63 history:** PD46 was committed directly to main (skipped feature branch). Path A accepted given minimal structural risk. **L13 says feature-branch-then-squash-merge**; the exception was a one-time judgment call.

**No active follow-up needed.** Just don't repeat.

### C5. Container deploy pattern documentation

**Pattern established across S59-S63:**
- For Python file changes: `scp` → `docker cp` → `docker restart`
- For full image changes: `docker compose build --no-cache <service>` → `docker compose up -d <service>`
- `docker restart` alone is INSUFFICIENT for code that's baked into the image (reuses stale image)
- Post-deploy verification: `docker exec <container> grep ... /app/index.js` or sha-check

**No active task.** Captured for S23 reference.

---

## PART D — Architectural locks active

### Currently active (full list)

- **VECRM-L8** — Allocator dual-surface sha verification. Banked sha: `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` (updated S22)
- **VECRM-L10** — Strict gap-free allocator invariant
- **VECRM-L11** — (per prior history)
- **VECRM-L13** — Squash-merge + branch delete on PR merge (one-time exception in S63)
- **VECRM-L17 through L27** — Active per prior session history
- **VECRM-S22-A** — Counter allocator value-read invariant (NEW in S22)

### Permanent locks

- **L27 (permanent):** Verify history/inventory at every layer-transition checkpoint. Canonical case: S64 PD45.
- **OBS-S71-A (permanent):** Run `git branch --show-current` before AND after every commit-bearing Bash invocation.

### Hard constraints (carry forward)

- **L22:** Schema migrations require atomic transaction + RAISE EXCEPTION assertions + paired rollback file
- **L24:** File-scope `scp` only, no `scp -r` for file edits
- **L26:** Always run `\d <table>` before any SQL probe

---

## PART E — Component-by-component build status

Per OBS-S22-B, this section documents the ACTUAL ground-truth state of every component, not what handover prose claims. Cross-check before relying.

### Backend doctypes (vecrm app)

| Doctype | Status | Notes |
|---|---|---|
| VECRM Employee | ✅ Built | Role field present (Sales Rep / Field Engineer / Sales Head / HR / Admin) |
| VECRM Voucher Counter | ✅ Built | S20, allocator fixed S22 (sha `91556a7d...`) |
| VECRM Travel Voucher | ✅ Built | S22, submittable, audit deferred |
| VECRM Visit Line | ✅ Built | S22, child table |
| VECRM Expense Voucher | ❌ Not started | PD-S22-EXPENSE-VOUCHER |
| VECRM Rate Card | ✅ Built | Ahmedabad 2.5, Mumbai 3.5, Pune 3.5 |
| VECRM Lead | ⚠️ Partial | Calls allocator; verify post-S22 fix |
| VECRM Inquiry | ⚠️ Partial | Calls allocator; verify post-S22 fix |
| VECRM Customer | ⚠️ Minimal | Skeleton only |
| VECRM Quote | ❌ Not built |  |
| VECRM Order | ❌ Not built |  |
| VECRM Weekly Report | ❌ Not built | B3 |
| VECRM Voucher Audit Log | ❌ Not built | PD-S22-VOUCHER-AUDIT — must be designed before Expense Voucher |
| VECRM User Audit Log | ⚠️ Exists but unfit | Designed for HR-style audit, not document audit |
| VECRM Sales Visit | 🗑️ Retired | Doctype gone since S8, table `tabVECRM Sales Visit` lingers (PD-S22-PHANTOM) |

### API endpoints (vecrm/api.py)

| Endpoint | Status |
|---|---|
| `approve_travel_voucher` | ✅ Built S22 |
| `approve_expense_voucher` | ❌ Not built |
| `submit_visit_voucher_draft` | ❌ Not built (portal-facing) |
| `get_pending_approvals` | ❌ Not built |
| `get_my_vouchers` | ❌ Not built |

### Frappe Roles (vecrm/fixtures/role.json)

| Role | Status |
|---|---|
| VECRM Submitter | ✅ |
| VECRM Approver | ✅ |
| VECRM Admin | ✅ |

### vecrm-portal (frontend)

| Component | Status |
|---|---|
| Auth login flow | ✅ Works |
| Top bar with mobile nav | ✅ Built S22 |
| Favicon | ✅ Cleaned S22 |
| Auth loading flash fix | ❌ Banked (PD-S22-LOADING-FLASH) |
| Voucher list screen | ❌ Not built (B1) |
| Travel Voucher create form | ❌ Not built (B1) |
| Expense Voucher create form | ❌ Not built (B1) |
| Voucher detail screen | ❌ Not built (B1) |
| Approver queue | ❌ Not built (B2) |
| PWA service worker | ❌ Not built (B4) |
| Offline draft storage | ❌ Not built (B4) |
| Push notifications | ❌ Deferred (B8) |

---

## PART F — Production data state

### MariaDB (vecrm-db-1)

- **Version:** 11.8.6-MariaDB-ubu2404
- **Default isolation:** REPEATABLE-READ (Frappe default)
- **innodb_snapshot_isolation:** OFF (current ground truth, verified S23 gate 3). Image config default appears to be OFF; runtime `SET GLOBAL ON` from S22 close did not persist across container restart (vecrm-db-1 restarted between S22 close and S23 open). **Allocator correctness is independent of SI state** per VECRM-S22-A (`last_value` is read inside `FOR UPDATE`). No action required.
- **InnoDB:** default engine

### Site: `crm.vinayenterprises.co.in`

(Note: prior handovers incorrectly referenced `_02c50791cf17d9de` as the site name. That was wrong. Per OBS-S22-B.)

### Voucher Counter state

- `TV-26-27`: last_value=78 (from §6 testing)
- `TV-27-28`: last_value=14 (from §6 testing)
- `INQ-26-27`: last_value=0 (unused — see PART G G4)
- `LEAD-26-27`: last_value=0 (unused — see PART G G4)

### Travel Voucher count

- **FY 26-27:** ~78 rows, all test data from `+91-9999900001`
- **FY 27-28:** ~14 rows, all test data from `+91-9999900001`

### Test employees (retain for regression)

- `+91-9999900001` — Test Sales Rep, base_city=Ahmedabad, role=Sales Rep
- `+91-9999900002` — Test HR Approver, base_city=Ahmedabad, role=HR

### Container state

- 9 containers Up healthy
- Backend image: `vecrm-custom:s22-pre-build` tagged `:latest`
- Rollback image available: `vecrm-custom:s21-pre-s22-rollback`

---

## PART G — Known schema drift / cleanup needed

### G1. `tabVECRM Sales Visit` (PD-S22-PHANTOM-SALES-VISIT-TABLE)

Zero rows. Doctype retired S8. `DROP TABLE` pending in S23.

### G2. Counter test data

`TV-26-27` and `TV-27-28` counter rows have last_value reflecting test data submissions. Real production submissions will pick up FROM these values (78, 14). Not a bug, just noted.

### G3. No fixtures version pinning

`vecrm/fixtures/role.json` is fixture data that gets reapplied on `bench migrate`. Currently the only fixture. If we add more fixtures (e.g. for Voucher Audit Log defaults), need to verify the apply-order doesn't cause conflicts.

### G4. Lead/Inquiry counter rows exist but allocations never recorded

`INQ-26-27` and `LEAD-26-27` counter rows exist in `tabVECRM Voucher Counter` at last_value=0. Surfaced at S23 gate 5.

Three possibilities (not yet investigated):
1. Lead/Inquiry use `voucher_counter.next_number` and simply have never been called in production
2. They use a different allocator path that bypasses `voucher_counter`
3. The wiring exists in counter table but the controller hookup was never completed

**S23+ task:** when next touching Lead or Inquiry, verify which path is used. Counters at 0 mean no harm if path 1 is true; possible silent gap if path 2 or 3.

**Risk if left unverified:** low. §6 fix (VECRM-S22-A) protects path 1 regardless. Paths 2-3 are quality issues, not correctness issues.

---

## How to use this document

1. **At session-open:** read PART E (Component-by-component build status), spot-check against ground truth via SQL/sha/git
2. **When planning next session:** start with PART A (tactical), reference PART B (strategic) for prioritization
3. **At session-close:** update this document with any new PD items, mark closed items, capture new strategic decisions
4. **Per OBS-S22-B:** never trust this document blindly; cross-check critical claims against `\d <table>`, `shasum`, `git log`

---

*Document version: post-S22 close (2026-05-21). Next update: at S23 close.*
