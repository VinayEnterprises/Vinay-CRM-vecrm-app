# S23 — Close Handover

**Date:** Thursday 2026-05-21 (evening) + Friday 2026-05-22 (morning, after 8-hour sleep break)
**Duration:** ~14 hours wall-clock across two contiguous work periods
**Operator:** Ajay Salvi
**Outcome:** ✅ 4 PRs shipped across 2 repos. Layer-2 100% complete. Lead/Inquiry pipeline functional for the first time ever. Portal loading flash eliminated.

---

## 1. TL;DR

S23 closed four major pendencies: PD-S22-VOUCHER-AUDIT (PR #11), PD-S23-AUTONAME-HYGIENE (PR #11 — newly surfaced and same-session fixed), PD-S22-EXPENSE-VOUCHER (PR #12), and PD-S22-LOADING-FLASH (vecrm-portal PR #4). Backend Layer-2 (Voucher) is now 100% complete. The Lead → Inquiry sales-pipeline backend, latent since S18 due to a silent autoname-prompt bug, is functional in production for the first time. The portal's two loading flashes (hard-refresh + between-route) are eliminated via SSR cookie hydration. Three architectural locks were earned (autoname hygiene, Frappe v16 lifecycle order, VPS destructive-ops guardrail). Eight OBS-S22-B firings were caught and corrected by recon-before-code discipline. 21 production vouchers, 11 leads, 11 inquiries, and 27 audit rows were created as test data, all preserved per audit append-only design.

**S24 entry priorities (recommended):**
1. PD-S24-PORTAL-VOUCHER-SCREENS — HIGH — voucher submission UI on vecrm-portal (15-25h, multi-session)
2. PD-S24-VOUCHER-CANCEL-AUDIT — LOW — on_cancel hook for TV + EV (10-line change)
3. PD-S24-PHANTOM-SALES-VISIT-TABLE — LOW — drop vestigial table (5 min)

---

## 2. What shipped (4 PRs, 2 repos)

### PR #10 — vecrm `63100f7` — docs(s23): bank opener prompt + comprehensive pendency register

Banked at S22→S23 transition. Authored: S23-OPENER-PROMPT.md (221 lines) + VECRM-PENDENCY-REGISTER.md (413 lines, 7 parts) + S22-close-handover.md (in docs/session-handovers/). This PR captured the strategic backlog correctly for the first time per OBS-S22-E (strategic dropping pattern). **This handover supersedes that register; see PART E for the updated comprehensive version.**

### PR #11 — vecrm `44a0b6d` — feat(s23): VECRM Voucher Audit Log + controller autoname hygiene (3 doctypes)

**Three sub-deliverables in one PR (scope expanded mid-session per operator directive "path ε, everything in this PR, take the long road"):**

**(a) NEW doctype: VECRM Voucher Audit Log.** Mirrors VECRM Inquiry Audit Log pattern (recon-discovered as canonical VECRM audit shape; dispatcher's initial design rejected per OBS-S22-B). Schema: `event` (Data, reqd, dotted name e.g. `voucher.travel.submitted`), `event_timestamp` (Datetime, reqd, defaulted in before_insert), `payload` (Long Text JSON). `autoname: "hash"` for opaque ids. Controller enforces append-only: `on_update` raises PermissionError if not flags.in_insert AND get_doc_before_save() is not None; `on_trash` raises unconditionally. Permissions: System Manager + VECRM Admin (create + read, no write/delete), VECRM Approver (read-only), VECRM Submitter (no access).

**(b) Travel Voucher rewired to use new audit log.** `_audit()` method body rewritten — was: insert to VECRM User Audit Log with event_type/actor/target/event_timestamp/detail fields. Now: insert to VECRM Voucher Audit Log with event + event_timestamp + payload (JSON-merged auto-fields voucher_name + voucher_doctype + actor_user, then caller's payload merged in). `on_submit` emits `voucher.travel.submitted`. Module-level `approve_travel_voucher` emits `voucher.travel.approved`.

**(c) Controller autoname hygiene fix (3 doctypes).** Pre-existing bug surfaced during Phase B manual Desk smoke. Travel Voucher, Lead, and Inquiry all had `autoname: "prompt"` or `"Prompt"` in JSON paired with a controller `autoname()` method. Per Frappe v16.18.2 model/naming.py L158, `autoname.lower() in ("prompt", "uuid")` causes the entire `run_method("autoname")` block to be SKIPPED. Result: name = user-typed Desk Name field, controller's allocator call never runs, counter never advances, fy_label never set.

**Smoking gun evidence:** Travel Voucher Desk-created with `autoname: "prompt"` got named "Test Sales Rep" (the submitter's display name leaked in via Frappe Desk's prompt-mode Name field). Audit row had `fy_label=null`. Lead and Inquiry counters at 0 since S18 — zero rows in either table — silently broken for all Desk-driven creation. Only programmatic paths (e.g. `Lead.convert_to_inquiry`) bypassed the bug because they leave self.name empty, hitting the autoname branch.

**Fix:** All 3 doctype JSONs: `autoname = ""` (empty). Frappe's case-insensitive comparison no longer matches; controller `autoname()` is called. TV JSON also drops `naming_rule: "Set by user"` (was paired with prompt mode). All 3 controllers: defensive prefix-pattern guard added in `validate()` (NOT `before_insert`).

**(d) Defensive guard placement — empirically verified Frappe v16 lifecycle.** Initial design placed guards in `before_insert`. Phase B Desk smoke empirically falsified that placement: guard fired with self.name=None, blocking all creation. Claude Code parallel-read recon of Frappe v16.18.2 document.py established actual lifecycle:

```
L441: run_method("before_insert")      ← self.name is None HERE
L442: set_new_name(...)                ← triggers autoname, sets name
L447: run_before_save_methods()        ← calls validate; name is set
L458: db_insert(...)
```

Guard relocated to `validate()`. Each guard includes a comment block citing these line numbers so future readers don't have to re-derive the lifecycle rationale. This became **OBS-S23-C, promoted to formal lock VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER**.

**(e) `from frappe import _` import fix in Travel Voucher.** Pre-existing latent NameError surfaced by Claude Code's AST undefined-names recon: `vecrm_travel_voucher.py` used `_(...)` at line 57 inside `autoname()` without importing `_`. Currently unreachable (JSON reqd:1 holds the line) but defensive guard would have raised NameError instead of intended ValidationError. Fix: add `from frappe import _` matching Lead/Inquiry pattern.

**Files:** 9 changed, +237 / -24 (3 new in vecrm_voucher_audit_log/, 3 modified controllers, 3 modified JSONs).

### PR #12 — vecrm `dc52c43` — feat(s23): VECRM Expense Voucher (Layer-2 Phase 3)

NEW doctype: **VECRM Expense Voucher** (submittable, mirrors Travel Voucher precisely but per-line expense items instead of km-based travel computation). NEW child doctype: **VECRM Expense Line** (istable=1, category Select reqd: Hotel/Food/Supplies/Communication/Misc, amount Currency reqd, description Small Text reqd, attachment Attach). NEW API: **`approve_expense_voucher`** (mirrors approve_travel_voucher; same approver set Sales Head/HR/Admin per S22 lock).

**Audit events:** `voucher.expense.submitted` (on_submit) + `voucher.expense.approved` (approve API). **First reuse of VECRM Voucher Audit Log** from PR #11 — validates the disjoint-doctype architectural decision. The audit log now serves both Travel and Expense vouchers via shared on_submit/approve patterns.

**Counter series:** EV. First allocation: `VE/EV/00001/26-27`.

**All S23 lessons applied preventively from day one:**
- autoname='' in JSON, not "prompt" or "Prompt"
- naming_rule='' in JSON, not "Set by user"
- Name guard in validate() not before_insert() (with full lifecycle citation comment block)
- `from frappe import _` imported from day one

**Two dispatch deviations caught in Phase A recon (OBS-S22-B, 4th and 5th of session):**
- Import path: dispatch said `from vecrm.voucher_counter` (wrong); correct is `vecrm.vecrm.voucher_counter` (nested-module convention)
- Canonical fy_label: dispatch defined its own; correct is to import the public `voucher_counter.fy_label` helper that TV/Lead/Inquiry all use

**Files:** 6 new, +473 / -0 (purely additive; allocator vecrm/voucher_counter.py untouched, L8 anchor `91556a7d...` valid).

### PR #4 — vecrm-portal `d880eda` — feat(s23): SSR cookie hydration eliminates LOADING-FLASH

Eliminates two distinct loading flashes visible on every page load:
1. **Hard-refresh flash** — AppShell called client-side `useAuth()` which fetched `/api/auth/me`. Hook returned `loading=true` initially, rendering `<FullPageLoading />` until fetch resolved.
2. **Between-route flash** — Every page file wrapped itself in `<AppShell>`. On navigation, entire shell tree (TopBar, useAuth, FullPageLoading) unmounted and remounted.

**Path δ design — SSR cookie hydration, no library:**
- NEW `lib/auth-ssr.ts` — server-only `getFrappeUser(): Promise<string | null>`. Reads sid cookie via next/headers (async); short-circuits if no sid (saves Frappe round-trip for unauthenticated requests); reuses `lib/frappe.ts`'s `frappeFetch` (no new env var, no inconsistent base-URL config); mirrors `/api/auth/me`'s verification logic.
- `app/layout.tsx` — async server component with `export const dynamic = "force-dynamic"`; resolves user via `getFrappeUser()`; mounts `<AppShell user={user}>{children}</AppShell>` at root. All existing head content preserved (THEME_INIT_SCRIPT, metadata, viewport, suppressHydrationWarning).
- `app/components/AppShell.tsx` — receives `user: string | null` as prop. `FullPageLoading` deleted entirely. `useAuth()` narrowed to `{login, logout}` actions only.
- `app/useAuth.ts` — thinned: dropped AuthState type, useState, useEffect, /api/auth/me fetch, refresh callback, user/loading state. Login + logout call `router.refresh()` after underlying fetch resolves.
- 5 page files (`app/page.tsx`, `app/leads/page.tsx`, `app/leads/[name]/page.tsx`, `app/inquiries/page.tsx`, `app/inquiries/[name]/page.tsx`) — drop `<AppShell>` wrap, return content component directly.

**Three Phase A recon deviations (OBS-S22-B, 6th-8th of session):**
1. `user` is a string (email), not an object — preserves TopBar/MobileNav contracts as "KEEP unchanged" per dispatch (dispatcher's `FrappeUser = {email}` object type would have forced changes to those components)
2. Reuse `lib/frappe.ts`'s `frappeFetch` instead of standalone fetch with new env var (avoids inconsistent 2nd base-URL config)
3. Forward full cookie header (gating on sid), don't reconstruct `sid=...` cookie string (mirrors `/api/auth/me`'s existing behavior)

**Build:** Next.js 16.2.6 / Turbopack, ✓ Compiled in 941ms, TypeScript clean, 16 routes (all `ƒ Dynamic` per force-dynamic).

**Smoke tests (7 of 7 PASS):** hard-refresh / between-route navigation / login flow / logout flow / mobile-nav regression at 393px / invalid session (sid deleted) / TTFB sanity (Network panel shows no `/api/auth/me` round-trip).

**Files:** 9 changed, +101 / -81 (1 new lib/auth-ssr.ts, 8 modified). ZERO production data side effects (purely frontend, no schema, no VPS state).

---

## 3. Production state at S23 close

### vecrm backend (Frappe, crm.vinayenterprises.co.in)

**Doctypes (Layer 1 → Layer 4):**

| Layer | Doctype | Status | Notes |
|---|---|---|---|
| 1 | VECRM Employee | ✅ | autoname=`field:vecrm_phone` per S2 lock |
| 1 | VECRM Rate Card | ✅ | Ahmedabad ₹2.50/km, Mumbai+Pune ₹3.50/km |
| 1 | VECRM User Audit Log | ✅ | Append-only; for general user actions |
| 2 | VECRM Voucher Counter | ✅ | Allocator at sha `91556a7d...` (L8 anchor); FOR UPDATE invariant active |
| 2 | VECRM Travel Voucher | ✅ | Submittable; submit + approve emit voucher.travel.* events |
| 2 | VECRM Visit Line | ✅ | Child of Travel Voucher |
| 2 | VECRM Voucher Audit Log | ✅ NEW S23 | Append-only; serves all voucher doctypes |
| 2 | VECRM Expense Voucher | ✅ NEW S23 | Submittable; submit + approve emit voucher.expense.* events |
| 2 | VECRM Expense Line | ✅ NEW S23 | Child of Expense Voucher; category Select |
| 3 | VECRM Lead | ✅ functional S23 | Was latent since S18 (autoname-prompt bug) |
| 3 | VECRM Inquiry | ✅ functional S23 | Was latent since S18 (autoname-prompt bug) |
| 3 | VECRM Inquiry Audit Log | ✅ | Lead→Inquiry conversion events |
| 3 | VECRM Customer | ⚠️ minimal skeleton | Real schema = Layer 3 follow-up; not blocking |
| 4 | (Weekly Report) | ❌ not started | Layer 4 = reporting; out of S24 scope |

**Counter state (VECRM Voucher Counter doctype):**

| counter_key | last_value | First allocation | Latest in production |
|---|---|---|---|
| TV-26-27 | 89 | VE/TV/00001/26-27 (early S22) | VE/TV/00089/26-27 (S23 §6) |
| LEAD-26-27 | 11 | VE/LEAD/00001/26-27 (S23) | VE/LEAD/00011/26-27 (S23 §6) |
| INQ-26-27 | 11 | VE/INQ/00001/26-27 (S23) | VE/INQ/00011/26-27 (S23 §6) |
| EV-26-27 | 12 | VE/EV/00001/26-27 (S23) | VE/EV/00012/26-27 (S23 §6) |

**Row counts (production tables, all real data preserved per audit append-only design):**

| Table | Rows | S23 delta |
|---|---|---|
| VECRM Travel Voucher | ~91 | +11 (1 Desk smoke + 10 §6 + 1 Test Sales Rep cancelled) |
| VECRM Lead | 11 | +11 (first ever allocations in S23) |
| VECRM Inquiry | 11 | +11 (first ever allocations in S23) |
| VECRM Expense Voucher | 12 | +12 (all new in S23: 1 Phase A smoke + 1 Phase B + 10 §6) |
| VECRM Voucher Audit Log | 27 | +27 (all new in S23: 13 from PR #11 work + 14 EV-prefixed) |
| VECRM Inquiry Audit Log | 1 | +1 (B.6.a Lead→Inquiry conversion) |
| VECRM Customer | minimal | unchanged |

**APIs whitelisted:**
- `vecrm.api.approve_travel_voucher(voucher_name, approver_employee, notes)` — existing S22
- `vecrm.vecrm.doctype.vecrm_expense_voucher.vecrm_expense_voucher.approve_expense_voucher(voucher_name, approver_employee, notes)` — NEW S23
- `vecrm.api.convert_lead_to_inquiry(lead_name, contact_person, contact_phone, requirement, status)` — existing
- Frappe defaults (`frappe.client.*`, `frappe.auth.get_logged_user`, etc.)

### vecrm-portal frontend (Next.js 16.2.6, app.vinayenterprises.co.in)

| Component | Status | Notes |
|---|---|---|
| TopBar | ✅ | mobile-responsive; user prop = email string |
| MobileNav | ✅ | hamburger drawer; createPortal-mounted (S22) |
| AppShell | ✅ | layout-owned post-S23; receives user prop; no FullPageLoading |
| LoginForm | ✅ | unchanged S22→S23 |
| Login page (`/`) | ✅ | redirects via router.refresh after login |
| Dashboard `/` | ✅ | recent inquiries widget |
| Leads list `/leads` | ✅ | filter by status |
| Lead detail `/leads/[name]` | ✅ | view + convert action |
| Inquiry list `/inquiries` | ✅ | filter by status |
| Inquiry detail `/inquiries/[name]` | ✅ | view only |
| **Travel Voucher screens** | ❌ | NOT BUILT — biggest gap blocking field-rep rollout |
| **Expense Voucher screens** | ❌ | NOT BUILT — biggest gap blocking field-rep rollout |
| **Approver queue / dashboard** | ❌ | NOT BUILT |
| PWA install prompt | ❌ | TRAI DLT deferred 2-4 weeks |
| Service worker / offline | ❌ | deferred |

### Infrastructure (Contabo Mumbai VPS, 217.216.58.117)

| Component | Version | Status | Notes |
|---|---|---|---|
| Host OS | Ubuntu 24 | ✅ | shared with VEMIO production |
| Docker | (operator-managed) | ✅ | 9 vecrm-* containers Up |
| MariaDB | 11.8.6 | ✅ | shared host, separate DBs per site |
| Frappe Framework | 16.18.2 | ✅ | locked S23; lifecycle order documented in VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER |
| Frappe HD | (not used by VECRM) | n/a | Used by VEMIO helpdesk (separate concern) |
| ERPNext | (not installed) | n/a | Deferred indefinitely (Tally→ERPNext migration not started) |
| Site | crm.vinayenterprises.co.in | ✅ | separate Frappe site |
| Allocator anchor sha | `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` | ✅ | VECRM-L8 valid post-S23; never touched |

**vecrm-* containers (9):** vecrm-backend-1, vecrm-mariadb, vecrm-redis-cache, vecrm-redis-queue, vecrm-frontend-1, vecrm-websocket, vecrm-queue-short, vecrm-queue-long, vecrm-scheduler.

**Shared infrastructure with VEMIO (CRITICAL):** Same VPS hosts VEMIO production (vemio-* containers, 5 live tenants including AIA Engineering Limited, 913+ tickets, real customer data). Same SSH credentials, same docker exec access. VECRM and VEMIO are isolated at the Docker network + Frappe site level, BUT the dispatcher/operator must never touch VEMIO infrastructure from a VECRM session. This is **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** (new S23, see PART F).

### Repositories

| Repo | Last commit | Purpose | Visibility |
|---|---|---|---|
| `VinayEnterprises/Vinay-CRM-vecrm-app` | `dc52c43` (PR #12) | Frappe app, doctypes, controllers, voucher_counter | Private |
| `VinayEnterprises/Vinay-CRM-config` | (separate) | Handover docs banked here historically per S3 convention | Private |
| `VinayEnterprises/vecrm-portal` | `d880eda` (PR #4) | Next.js 16 PWA, vecrm-portal | Private |

**Note on the config repo:** Historically (S3-era) handovers were banked to `Vinay-CRM-config`. From S22 onward they live in `Vinay-CRM-vecrm-app/docs/session-handovers/`. The config repo may have stale handovers; this close handover supersedes anything banked there for S22+.

---

## 4. What surfaced and was resolved (S23 discovery log)

S23 surfaced and resolved more latent bugs than it shipped planned features. Banking each here for institutional memory.

### 4.1 Autoname-prompt silent bug (3 doctypes affected)

Travel Voucher, Lead, Inquiry all had `autoname: "prompt"` or `"Prompt"` paired with controller `autoname()` method. Frappe v16's case-insensitive check at naming.py L158 caused the controller to be SKIPPED.

**Detection:** Phase B manual Desk smoke. TV created via Desk got named "Test Sales Rep" (operator's display name) instead of `VE/TV/00079/26-27`. Audit row showed `fy_label=null`. Inspecting the JSON revealed `autoname: "prompt"`.

**Impact:** Lead and Inquiry counters at 0 since S18. Zero rows in `tabVECRM Lead` and `tabVECRM Inquiry`. All Desk-driven creation silently broken. Only programmatic paths bypassed because they leave self.name empty.

**Fix:** `autoname: ""` (empty) in all 3 JSONs. **Promoted to formal lock VECRM-LOCK-AUTONAME-HYGIENE** (see PART F).

### 4.2 Frappe v16 insert lifecycle inversion

Initial Phase A.5 design placed defensive name-prefix guards in `before_insert`. Phase B smoke falsified — guards fired with self.name=None, blocking all creation.

**Resolution:** Claude Code parallel-read recon of Frappe v16.18.2 `frappe/model/document.py` established lifecycle order: L441 before_insert → L442 set_new_name → L447 validate. Guards relocated to validate(). **Promoted to formal lock VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER**.

### 4.3 `from frappe import _` import missing in Travel Voucher

Claude Code AST undefined-names recon caught `_(...)` used at TV controller line 57 without importing `_`. Currently unreachable (JSON reqd:1 holds the line) but defensive code path would have raised NameError instead of intended ValidationError.

**Fix:** Added `from frappe import _` to imports, matching Lead/Inquiry pattern. Included in PR #11. Applied preventively to Expense Voucher controller from day one.

### 4.4 Test harness REPEATABLE-READ stale snapshot bug (C.1 §6 false-FAIL)

Phase C.1 Travel Voucher §6 reported FAIL on criteria 1, 4, 5 despite production code working correctly. Diagnosis: harness's `run()` executed in one long-lived bench-execute connection. MariaDB REPEATABLE-READ isolation froze a snapshot at pre-run state. The 10 worker threads committed on their own connections, but post-run reads on the harness's main connection returned stale values.

**Resolution:** PATCH 1 (`frappe.db.rollback()` between worker barrier and post-run reads) + PATCH 2 (fresh-connection triangulation read as authoritative). Applied to C.2 (Lead), C.3 (Inquiry), and Expense Voucher §6 from start. Both verdict and triangulation agreed in C.2, C.3, EV §6. **Banked as OBS-S23-D candidate (not promoted to lock; relevant only for test harness authoring).**

### 4.5 Lead status enum mismatch (caught in C.2 recon, not surfaced as bug)

Dispatch for Lead §6 sample used `status="New"`. Phase C.2 recon revealed actual Lead.status Select options: Open / Converted / Closed-Lost. Caught preemptively in recon; substituted "Open" (the field default). **Banked as OBS-S23-E candidate (worker-scope recon discipline).**

### 4.6 Voucher cancellation audit gap

VE/EV/00002/26-27 was cancelled via Desk after approval (operator misunderstanding of instructions, see § 5.3 below). Cancellation produced NO audit row. Investigation: neither Travel Voucher nor Expense Voucher controllers have `on_cancel` hook emitting `voucher.*.cancelled` events. Same gap exists for both doctypes.

**Status:** Banked as PD-S24-VOUCHER-CANCEL-AUDIT (LOW). ~10-line change per controller. Defer to S24.

### 4.7 Stray dispatch artifacts in vecrm-portal repo root

Cold-check found 3 untracked S21 dispatch markdown files (`DISPATCH-S21-D3a-fix.md.` with trailing-dot malformed name, `DISPATCH-S21-D3a-foundation.md`, `DISPATCH-S21-D3b.md`) in vecrm-portal repo root.

**Resolution:** Removed via `rm` at cold-check (not git rm; they were untracked). Banked as OBS-S23-H (workflow note): dispatch artifacts belong in `~/Downloads/` (operator side) or `/mnt/user-data/outputs/` (dispatcher side), never inside a repo working directory.

### 4.8 Dispatcher OBS-S22-B count for S23

Recon overrode dispatch prose **8 times** in S23. Every override was correct (verified against ground truth before adoption):

1. PR #11: Audit doctype shape (canonical Inquiry Audit Log pattern, not dispatcher's structured target/action design)
2. PR #11: autoname semantics (`""` not `"prompt"`)
3. PR #11: Frappe v16 lifecycle order (validate not before_insert)
4. PR #12: voucher_counter import path (`vecrm.vecrm.voucher_counter` not `vecrm.voucher_counter`)
5. PR #12: canonical fy_label helper (import from voucher_counter, not redefine locally)
6. PR #4: user is string not object (preserves TopBar/MobileNav contracts)
7. PR #4: reuse lib/frappe.ts's frappeFetch (not new env var)
8. PR #4: forward full cookie header (not reconstructed sid string)

**Banking observation:** Eight overrides in one session is high. The pattern suggests dispatcher (Claude in dispatch role) over-designs in dispatch prose without verifying against ground truth first. **Banked as dispatcher-discipline note for S24+: dispatcher must explicitly call out areas where recon is mandatory before implementation in every dispatch.**

---

## 5. Process moments worth banking

### 5.1 Two-period session structure

S23 ran ~10 hours Thursday evening, then took an 8-hour sleep break, then resumed Friday morning for ~4 more hours. **This was the right call.** Pushing through fatigue would have produced lower-quality work on PR #12, PR #4, and the close handover. Future sessions exceeding ~10 hours should consider explicit sleep breaks rather than pushing through.

### 5.2 Scope expansion mid-session (autoname hygiene + lifecycle relocation + import fix)

S23 opened with one priority: PD-S22-VOUCHER-AUDIT. Phase B surfaced the autoname-prompt bug. Operator's "path ε, everything in this PR" call expanded scope to include autoname fix across 3 doctypes + lifecycle relocation + `_` import fix. Total PR #11 grew from ~50 LOC estimate to +237 LOC actual.

The scope expansion was justified — fixing the autoname bug separately would have required another PR and another deploy cycle. But it added ~3 hours to the session. **Banking observation:** scope expansion mid-session is acceptable when the new work shares deploy lifecycle with the originally planned work AND when the surfaced bug is currently blocking production. Both were true in S23.

### 5.3 Communication misunderstanding (VE/EV/00002 cancellation)

After PR #12 Phase B.3 (approve via API), operator cancelled VE/EV/00002 via Desk UI under the impression dispatcher had asked. **Dispatcher had not asked.** Operator was pattern-matching from earlier S23 TV Phase B.0 which DID start with cancellation of "Test Sales Rep" voucher. The Expense Voucher Phase B did not need a B.0 step.

**Outcome:** No data loss (audit log append-only design preserved the submit + approve events; voucher just sits at docstatus=2). Surfaced PD-S24-VOUCHER-CANCEL-AUDIT (cancellation is unaudited — real auditor would call this a gap).

**Banking for S24:** When reusing a phase template, explicitly flag steps that are SKIPPED relative to the template. E.g. "Note: no B.0 step here — VE/EV/00001 from Phase A smoke is fine to keep, no pre-existing voucher to clean up."

### 5.4 VPS guardrail clarification

Operator raised: VECRM is on shared VPS with VEMIO (live production). Claude Code had been running VPS commands directly all session. Operator's concern: prevent unintended destructive operations on shared infrastructure.

**Resolution:** Established **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** (see PART F). Claude Code MAY perform VECRM-scoped VPS operations (reads, additive deploys, container restarts) without special authorization. Claude Code MUST request explicit dispatcher authorization for destructive operations (rm, DELETE, DROP, TRUNCATE, frappe.delete_doc, docker rm, etc.). Claude Code MUST NOT touch any non-vecrm-* container, the vemio_* or glpi_* databases, or anything under /opt/vemio/.

**Dispatcher discipline note:** Dispatcher should have established this guardrail at S23 open given VEMIO's live status. Operator had to raise it mid-session. Banked as dispatcher-discipline observation: when shared infrastructure is in scope, enforce VPS guardrail at session open, not wait for operator reminder.

### 5.5 Handover document philosophy shift

Earlier in S23 we discussed lightweight ~150-line close handover with pointers. Operator overrode at close: "do not make the mistake of the previous sessions of not including everything." This document follows the heavy/comprehensive path: next-session author should have full picture from reading this alone, not have to chase 5 other documents.

**Banking for future close handovers:** When in doubt, err on the side of comprehensive. Pointer-based handovers fragment institutional memory across documents and create OBS-S22-E (silent dropping pattern). Heavy handovers are the safer default for a multi-session project like VECRM.

---

## 6. Architectural locks active (post-S23)

Complete list of locks governing VECRM development. Three new in S23.

### 6.1 Pre-S23 locks (carried forward from S1-S22)

| Lock ID | Earned | Purpose |
|---|---|---|
| VECRM-L1 | S1 | Authoritative single-spec docs in handovers/ (S1+S2+S3 canonical) |
| VECRM-L2 | S1 | Strategic decisions are written, not remembered |
| VECRM-L3 | S2 | Append-only audit invariant for VECRM User Audit Log |
| VECRM-L4 | S2 | Defense-in-depth: controller + permission layers both enforce write/delete restrictions |
| VECRM-L5 | S3 | Per-session opener cold-checks before any code |
| VECRM-L6 | S3 | Layer boundaries are hard: no Layer-N+1 code until Layer-N is verified |
| VECRM-L7 | S3 | Image rebuild lifecycle: scp → docker compose build --no-cache → docker compose up -d |
| **VECRM-L8** | S3 | **Allocator sha verification — `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9`** |
| VECRM-L9 | S4 | (candidate, see S4 handover) |
| VECRM-L10 | S4 | Gap-free allocator invariant |
| VECRM-L11 | S5 | (forthcoming numbering — populated per S5+ handover) |
| VECRM-L13 | S5+ | Squash-merge + branch delete on PR merge |
| VECRM-L17-L27 | S10+ | (various; see prior handovers banked in `Vinay-CRM-config/handovers/`) |
| VECRM-L27 | S64 | **Permanent.** Verify history/inventory at every layer-transition checkpoint |
| **VECRM-S22-A** | S22 | **Counter allocator value-read invariant (read inside FOR UPDATE)** |
| OBS-S71-A | (carried from VEMIO) | **Permanent.** `git branch --show-current` before AND after every commit-bearing bash invocation |

### 6.2 Locks earned in S23 (3 new, all PROMOTED TO FORMAL)

| Lock ID | Purpose |
|---|---|
| **VECRM-LOCK-AUTONAME-HYGIENE** | autoname='' is the only safe value for controller-driven naming in Frappe v16+; "prompt"/"Prompt"/"uuid" silently SKIP the controller |
| **VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER** | Name-related guards belong in validate() not before_insert(); Frappe v16.18.2 runs before_insert at L441 BEFORE set_new_name at L442 |
| **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** | Destructive VPS operations require explicit dispatcher authorization; VECRM-scoped only; never touch VEMIO infrastructure |

Full lock text for each in `docs/architectural-locks/`. Each lock has its own ~50-line file with rationale, canonical examples, enforcement points, and links to surfacing-session evidence.

### 6.3 OBS-S23 candidates (NOT promoted; banked as observations)

| OBS ID | Description |
|---|---|
| OBS-S23-A | Shell-quoting fragility through ssh→docker→bench→eval layers; prefer Frappe ORM helpers (`frappe.db.table_exists`, `frappe.get_all`, `frappe.get_meta`) over raw SQL when identifiers contain spaces |
| OBS-S23-D | Test harnesses on long-lived bench-execute connections see stale REPEATABLE-READ snapshots; must `frappe.db.rollback()` between worker barrier and post-run reads. Triangulate critical assertions with fresh-connection reads. |
| OBS-S23-E | Worker-scope recon discipline: verify reqd fields, enum options, lifecycle order against source before drafting code at every implementation scope, not just dispatcher scope |
| OBS-S23-F | Manual Desk smoke is structurally important and not skippable — caught the autoname-prompt bug AND the lifecycle inversion that all programmatic §6 tests would have missed |
| OBS-S23-G | (became PD-S24-VOUCHER-CANCEL-AUDIT — promoted to pendency) |
| OBS-S23-H | Dispatch artifacts must live in `~/Downloads/` or `/mnt/user-data/outputs/`, never in repo working directories |
| OBS-S23-I | Dispatcher must explicitly enforce VPS-destructive-ops discipline at session open when shared infrastructure is in scope; don't wait for operator to remind |
| OBS-S23-J | Eight OBS-S22-B firings in one session is a dispatcher-discipline signal: dispatcher over-designs in prose without verifying against ground truth. Future dispatches must explicitly call out areas requiring recon-before-implementation. |

---

## 7. What's deferred to S24+

See **VECRM-PENDENCY-REGISTER.md** (separate document, regenerated at S23 close) for the full active backlog. High-level summary:

### 7.1 HIGH priority for S24

- **PD-S24-PORTAL-VOUCHER-SCREENS** (15-25h, multi-session): Build Travel Voucher + Expense Voucher submission UI on vecrm-portal. This is the single biggest gap between "backend works" and "production rollout." Field sales reps currently cannot submit vouchers from their phones — only Frappe Desk works, which is wrong for field-rep UX.

### 7.2 LOW priority (small / cleanup)

- **PD-S24-VOUCHER-CANCEL-AUDIT** (~10 lines per controller, ~30 min total): Add `on_cancel` hook to TV and EV controllers emitting `voucher.travel.cancelled` and `voucher.expense.cancelled` events to VECRM Voucher Audit Log. Audit gap surfaced in S23 PR #12 Phase B (VE/EV/00002 cancellation un-audited).
- **PD-S24-PHANTOM-SALES-VISIT-TABLE** (~5 min): Drop vestigial `tabVECRM Sales Visit` 0-row table from a deferred S22 design decision.

### 7.3 Strategic / multi-session (carried forward from S22)

- **Voucher approver portal** (B2): Approver queue UI for Sales Head / HR / Admin to review and approve incoming vouchers. ~10-15h.
- **PWA install prompt + service worker + offline storage**: Deferred per TRAI DLT 2-4 week deferral.
- **Tally → ERPNext migration**: Deferred indefinitely. When started: API-driven migration (not UI entry); ERPNext UI used as-is for back-office; Ahmedabad ERPNext partner engagement for opening-balance recon and GST account restructuring.
- **TRAI DLT registration**: Deferred 2-4 weeks per S22.

### 7.4 Out of VECRM scope (clarified S23)

These items appeared in the S22 register's PART B B6 ("Lead → Inquiry → Quote → Order → Customer pipeline") but are NOT actually VECRM's responsibility. They belong to the deferred Tally → ERPNext migration:

- VECRM Quote — ❌ not built; ERPNext will own when migrated
- VECRM Order — ❌ not built; ERPNext will own when migrated
- State machine connecting Inquiry → Quote → Order — ❌; ERPNext domain

VECRM owns: HR/Employee (Layer 1), Voucher (Layer 2), Sales Pipeline up through Inquiry (Layer 3 partial). Quote/Order/invoicing is ERPNext's job once migration happens.

### 7.5 Pre-existing infrastructure debt (deferred)

- No CI on either repo. No linting, no build check, no test run. Local pre-commit `npm run build` and `python -m py_compile` and AST checks do all verification today. Layer 1 CI (Dependabot, lint, Semgrep) would catch what slips today. Pattern to copy: VEMIO S56-S58.
- No automated test suite. All testing today is manual smoke + §6 concurrency hard-gates. Promoting §6 hard-gates to a permanent `tests/` directory is a register item carried since S22 (Part C C1, still deferred).

---

## 8. Reading order for S24 session-open

1. **This document** (`docs/session-handovers/S23-close-handover.md`) — primary input
2. **VECRM-PENDENCY-REGISTER.md** (`docs/`) — active backlog, regenerated at S23 close
3. **VECRM-DEPENDENCY-MAP.md** (`docs/`) — infrastructure state, versions, what depends on what (NEW S23, see § 9)
4. **`docs/architectural-locks/`** — formal locks, one file each. Read VECRM-LOCK-AUTONAME-HYGIENE, VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER, VECRM-LOCK-VPS-DESTRUCTIVE-OPS (all new S23) and VECRM-S22-A (governs all allocator work) at minimum.

Per-session opener cold-checks (verify before any code) per VECRM-L5 — see `docs/S24-OPENER-PROMPT.md` for exact commands.

---

## 9. New document banked alongside this handover

**VECRM-DEPENDENCY-MAP.md** (NEW S23): Comprehensive single-source-of-truth for infrastructure versions, repo paths, container names, environment variables, allocator sha, and dependency relationships. Replaces ad-hoc references in prior handovers. Reviewed and updated at every session close going forward.

See `docs/VECRM-DEPENDENCY-MAP.md`.

---

## 10. Session-close commit sequence (this PR)

```bash
cd ~/Documents/GitHub/vecrm
git checkout main
git pull origin main
git checkout -b docs/s23-close-handover

# New files
mkdir -p docs/session-handovers
cp ~/Downloads/S23-close-handover.md docs/session-handovers/S23-close-handover.md
cp ~/Downloads/VECRM-DEPENDENCY-MAP.md docs/VECRM-DEPENDENCY-MAP.md
cp ~/Downloads/S24-OPENER-PROMPT.md docs/S24-OPENER-PROMPT.md

# Regenerated file (overwrite the S22-era register)
cp ~/Downloads/VECRM-PENDENCY-REGISTER.md docs/VECRM-PENDENCY-REGISTER.md

# New lock files
mkdir -p docs/architectural-locks
cp ~/Downloads/VECRM-LOCK-AUTONAME-HYGIENE.md docs/architectural-locks/
cp ~/Downloads/VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER.md docs/architectural-locks/
cp ~/Downloads/VECRM-LOCK-VPS-DESTRUCTIVE-OPS.md docs/architectural-locks/

# Retire the S23 opener (it served its purpose; lives in git history from PR #10)
git rm docs/S23-OPENER-PROMPT.md

git add docs/
git status
git diff --cached --stat

git commit -m "docs(s23): close handover + regenerated pendency register + new dependency map + 3 architectural locks

Closes S23. 4 PRs shipped across 2 repos:
- vecrm PR #10 (docs banking)
- vecrm PR #11 (Voucher Audit Log + autoname hygiene + lifecycle relocation + _ import)
- vecrm PR #12 (Expense Voucher, Layer-2 100% complete)
- vecrm-portal PR #4 (SSR cookie hydration, both loading flashes eliminated)

Per operator directive (s23 close): comprehensive handover, not lightweight.
Captures everything not just S23-scope. Replaces the S22-era pendency register
with a regenerated version. Adds a new VECRM-DEPENDENCY-MAP single-source-of-
truth doc. Promotes 3 OBS candidates to formal architectural locks:
- VECRM-LOCK-AUTONAME-HYGIENE
- VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER
- VECRM-LOCK-VPS-DESTRUCTIVE-OPS

S23-OPENER-PROMPT.md retired (its purpose served; remains in git history
from PR #10)."

git push -u origin docs/s23-close-handover

gh pr create \
  --title "docs(s23): close handover + pendency register + dependency map + 3 locks" \
  --body "Closes S23. See commit message for the full deliverable list.

This is a docs-only PR. Zero code changes. Zero schema changes. Zero VPS
impact. The handover document is comprehensive per operator directive
(do not repeat prior-session error of pointer-based handovers that drop
context)." \
  --base main
```

After dispatcher review of staged set → squash-merge with branch delete.

---

## 11. Acknowledgments

- **Operator (Ajay):** sustained focus across two work periods totaling ~14 hours; made the right call to sleep mid-session rather than push through; caught a critical guardrail gap mid-session and corrected it.
- **Dispatcher (this Claude):** dispatch authoring, diff review, decision adjudication, handover authoring.
- **Claude Code:** local recon, AST checks, file authoring, ferry, git operations, VPS reads + scoped VECRM operations.
- **The §6 saga (S22) and its lock VECRM-S22-A** governed all four allocators tested in S23. That lock saved hours of debugging in S23.

S23 ships **Layer-2 100% complete**, **Lead/Inquiry pipeline functional for the first time ever**, and **portal auth-resolution fixed architecturally**. The next milestone (PD-S24-PORTAL-VOUCHER-SCREENS) is the single biggest gap between "backend works" and "production rollout" — when that ships, VECRM becomes deployable to real field-rep users.

---

**End of S23-close-handover.md**
