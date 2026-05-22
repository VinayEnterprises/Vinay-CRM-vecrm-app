# VECRM-PENDENCY-REGISTER

**Last updated:** 2026-05-22 (post-S23 close)
**Maintained by:** Session-close handovers
**Purpose:** Single source of truth for ALL deferred work — tactical AND strategic. Regenerated comprehensively at S23 close per operator directive (do not repeat prior-session pattern of dropping strategic items).

---

## How this document is organized

- **PART A — Active pendencies (PD-S24-*)** — explicit deferred items with priority + estimate
- **PART B — Strategic backlog (Session-0 pillars status)** — high-level features still pending
- **PART C — Infrastructure debt** — CI, tests, deploy patterns, test data in production
- **PART D — Architectural locks active** — full list governing development
- **PART E — Component-by-component build status** — every doctype + portal screen with ground-truth status
- **PART F — Production data state** — counters, row counts, version anchors
- **PART G — Schema drift + cleanup items** — known vestigial / inconsistent items
- **PART H — Out-of-scope items** — clarifications of what VECRM does NOT own

---

## PART A — Active pendencies (PD-S24-*)

### PD-S24-PORTAL-VOUCHER-SCREENS — HIGH

**Scope:** Build Travel Voucher + Expense Voucher submission UI on vecrm-portal. Field sales reps currently cannot submit vouchers from their phones — only Frappe Desk works, which is unusable for field-rep UX.

**Required components:**
- Travel Voucher create form with visit-line dynamic rows, KM calculator, business-date picker, total auto-compute
- Expense Voucher create form with expense-line dynamic rows, category Select, amount entry, receipt upload (Attach)
- Voucher list view (filter by status: Draft / Submitted / Approved / Cancelled)
- Voucher detail view (read-only post-submit; cancel action for Admin role only)
- Optimistic UI for offline scenarios (PWA storage)

**Dependencies:**
- Voucher Audit Log (✅ shipped S23 PR #11)
- Travel Voucher backend (✅ shipped S22 PR #9)
- Expense Voucher backend (✅ shipped S23 PR #12)
- approve_*_voucher APIs (✅ all shipped)
- SSR auth hydration (✅ shipped S23 PR #4)

**Estimated effort:** 15-25h, multi-session. Decompose into:
- Session A: Travel Voucher create form + list (8-10h)
- Session B: Expense Voucher create form + list (5-7h)
- Session C: Detail view + cancel action + polish (4-6h)
- Possibly Session D: PWA install prompt + offline draft storage (deferred until TRAI DLT clears)

**Status:** Not started. **This is the single biggest gap between "backend works" and "production rollout."**

### PD-S24-VOUCHER-CANCEL-AUDIT — LOW

**Scope:** Add `on_cancel(self)` hook to Travel Voucher and Expense Voucher controllers emitting `voucher.travel.cancelled` and `voucher.expense.cancelled` events to VECRM Voucher Audit Log.

**Discovery:** S23 PR #12 Phase B. VE/EV/00002/26-27 was cancelled via Desk after approval; cancellation produced no audit row. Same gap exists for Travel Voucher.

**Implementation:** ~10 lines per controller, ~30 min total work + PR cycle.

```python
def on_cancel(self) -> None:
    self._audit("voucher.expense.cancelled", {
        "actor_employee": frappe.session.user,  # or resolve via lookup
        "from_state": "submitted" if self.docstatus == 2 else "approved",
        "to_state": "cancelled",
        # ... other relevant snapshot fields
    })
```

**Priority:** LOW because production rollout can proceed without it (cancellations are rare). Bank for clean-audit-trail compliance before any real auditor review.

**Effort:** 30 min + smoke + PR + merge.

### PD-S24-PHANTOM-SALES-VISIT-TABLE — LOW

**Scope:** Drop vestigial `tabVECRM Sales Visit` table.

**Discovery:** S22 schema audit. The table exists from a deferred design decision but has 0 rows and no live code paths reference it.

**Implementation:** `DROP TABLE` after confirming no Frappe doctype references. Single migration script.

**Priority:** LOW. Doesn't block anything; just cleanup hygiene.

**Effort:** 5 min execution + 10 min recon-before-drop verification.

---

## PART B — Strategic backlog (Session-0 pillars status)

Tracking the Session-0 vision against current ground truth. Per OBS-S22-E, strategic pillars have historically been silently dropped from the active register; this section corrects that.

### B1 — Voucher portal (field-rep submission UI)

**Session-0 intent:** Field sales reps submit travel + expense vouchers from their phones. Approver (Sales Head / HR / Admin) reviews on Desk or portal.

**Current state:** Backend fully functional. **Frontend not built.** This is PD-S24-PORTAL-VOUCHER-SCREENS (PART A).

**Effort to feature-complete:** 15-25h multi-session.

### B2 — Approver portal (queue + workflow UI)

**Session-0 intent:** Approver-role users see incoming vouchers in a queue, click to approve/reject with notes.

**Current state:** Backend APIs functional (`approve_travel_voucher`, `approve_expense_voucher`). **No queue UI.** Approvers currently use Desk's default list view.

**Effort to feature-complete:** 10-15h. Lower priority than B1 (field reps must submit before approvers can approve).

### B3 — Weekly meeting report (Layer 4)

**Session-0 intent:** Automated weekly digest of sales activity (leads / inquiries / vouchers) emailed/Slack'd to leadership.

**Current state:** Not started. Layer 4 = 0%.

**Effort:** 8-12h. Lower priority — depends on having real sales activity data (gated by B1 + B2 production rollout).

### B4 — PWA validation (install prompt, service worker, offline storage)

**Session-0 intent:** Portal installable as PWA on Android/iOS; offline draft of voucher when no connectivity.

**Current state:** Manifest exists; install prompt not surfaced; no service worker; no offline storage.

**Blocked by:** TRAI DLT registration (deferred 2-4 weeks per S22). Push notifications require DLT compliance; without push, PWA install prompt has limited value.

**Effort:** 8-12h once DLT clears.

### B5 — Role differentiation (Frappe Roles + permission matrices)

**Session-0 intent:** Roles: VECRM Submitter, VECRM Approver, VECRM Admin, Sales Head, HR. Per-role visibility on voucher fields, approver-only fields, admin-only actions.

**Current state:** Roles defined as Frappe Roles. Permission matrices set on Travel Voucher + Expense Voucher + Voucher Audit Log doctypes per S22 + S23. **Functional.**

**Open items:**
- Lead and Inquiry doctypes don't have explicit role permissions yet (they inherit System Manager defaults). Add per-role permissions when Layer-3 sales pipeline gets prioritized.

### B6 — Lead → Inquiry pipeline

**Session-0 intent (corrected S23):** VECRM owns Lead → Inquiry. Beyond Inquiry (Quote, Order, invoicing) is ERPNext's domain.

**Current state:**
- Lead doctype: ✅ functional S23 (was latent since S18)
- Inquiry doctype: ✅ functional S23 (was latent since S18)
- Lead.convert_to_inquiry API: ✅ functional
- Inquiry Audit Log + Q9 transport (notify vemio.io): ✅ exists; Q9 transport not exhaustively tested but doesn't error

**Open items:**
- Customer doctype is a minimal skeleton; real schema needs flesh out if VECRM is the source-of-truth for customer master data (decision pending; might be deferred to ERPNext if Tally migration starts)
- Q9 transport reliability untested (vemio.io endpoint not exhaustively verified)
- Inquiry → Customer conversion API not built

**Effort to feature-complete:** 5-10h for full schema + conversion logic. Lower priority than B1.

### B7 — Tally → ERPNext migration

**Session-0 intent:** Migrate Vinay Enterprises' accounting from Tally to ERPNext when feasible. VECRM integrates via API once ERPNext is live.

**Current state:** Deferred indefinitely. Decision: API-driven migration (not UI entry); ERPNext UI used as-is for back-office; Ahmedabad ERPNext partner engagement for opening-balance recon and GST account restructuring.

**Effort:** Multi-month, multi-party (operator + partner + finance team). Out of S24 scope.

### B8 — TRAI DLT registration

**Session-0 intent:** Register vinayenterprises.co.in for DLT to enable transactional SMS + push notifications.

**Current state:** Deferred 2-4 weeks per S22.

**Effort:** Operator-driven business process, not engineering work.

---

## PART C — Infrastructure debt

### C1 — Concurrency §6 hard-gates as permanent tests

**Issue:** S22 / S23 §6 concurrency hard-gates are bespoke per doctype. Diagnostic scripts ferried to container, run, removed. Pattern works but not durable — no regression protection.

**Resolution path:** Promote §6 hard-gates to a permanent `tests/` directory under `vecrm/`. Run via `bench --site crm.vinayenterprises.co.in run-tests --app vecrm` in CI when CI exists (see C2).

**Deferred since:** S22.

**Effort:** 4-6h authoring + integration. Lower priority — manual §6 still works for new doctype additions.

### C2 — No CI on either repo

**Issue:** No GitHub Actions / Dependabot / lint / type-check / test runs on PRs. All verification today is local pre-commit (`npm run build` for portal, `python -m py_compile` + AST checks for backend) + manual phase-A/B/C smoke + §6 hard-gates.

**Risk:** Layer-1 CI (security advisories, lint, build verification) would catch what slips today. Pattern to copy: VEMIO S56-S58 (Dependabot + lint/build CI + Semgrep report-only).

**Effort:** 4-6h for Layer 1 CI. Deferred since S22.

### C3 — Test data persisted in production

**Issue:** Per audit append-only design, all S22 + S23 §6 test vouchers, leads, inquiries persist in production tables. 21 vouchers, 11 leads, 11 inquiries, 27 audit rows from S23 alone. Mixed with real data when real rollout begins.

**Mitigation considered:** Tag test data with a `is_test_data` flag, exclude from reports. Or use a `_test_` prefix in counter series. Or operator-driven cleanup script (delete by date-range).

**Decision:** **Keep as-is.** Per audit append-only design, removing audit rows is forbidden. The voucher rows themselves could be cancelled (docstatus=2) to exclude from active reports without deletion. Defer this decision until first real customer rollout when test/prod data separation becomes a real concern.

### C4 — Container deploy pattern formalization

**Issue:** Worker deploy pattern is: scp file → `docker compose build --no-cache <service>` → `docker compose up -d <service>`. `docker restart` alone is insufficient (reuses stale image). Empirically verified S22.

**Status:** Pattern is correct and used consistently. Document this in VECRM-DEPENDENCY-MAP.md (new S23 doc) for future maintainers.

### C5 — Diagnostic script cleanup discipline

**Issue:** S23 §6 diagnostic scripts (`_s23_*_concurrency.py`, `_s23_ev_phase_a_smoke.py`) were ferried to container, run, then cleaned up at Phase D. Pattern works but relies on explicit Phase D cleanup steps.

**Resolution path:** Use `/tmp/` for ephemeral scripts where possible. Or add a session-close cleanup checklist.

**Effort:** None today; banked as discipline note.

### C6 — Q9 transport reliability untested

**Issue:** Inquiry's `enqueue_conversion_email()` calls `_q9_transport(payload)` which HTTP POSTs to `https://app.vemio.io/api/internal/vecrm/inquiry-converted` with HMAC signature. Wrapped in try/except, errors are logged and swallowed.

**Risk:** Transport might be silently broken (vemio.io endpoint changed, secret mismatch, etc.). The conversion proceeds even on transport failure (non-fatal design).

**Resolution path:** S24+ task — test Q9 end-to-end. Verify the inquiry-converted event reaches vemio.io. Check `frappe.log_error` for accumulated Q9 failures.

**Effort:** 30 min recon + endpoint verification.

---

## PART D — Architectural locks active

Full list. Three new in S23.

### Pre-S23 locks (S1-S22)

| Lock | Purpose |
|---|---|
| VECRM-L1 | Single-spec docs authoritative |
| VECRM-L2 | Strategic decisions written, not remembered |
| VECRM-L3 | Append-only audit invariant |
| VECRM-L4 | Defense-in-depth: controller + permission both enforce |
| VECRM-L5 | Per-session opener cold-checks |
| VECRM-L6 | Layer boundaries are hard |
| VECRM-L7 | Image rebuild lifecycle (scp → build --no-cache → up -d) |
| **VECRM-L8** | **Allocator sha verification — `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9`** |
| VECRM-L10 | Gap-free allocator invariant |
| VECRM-L13 | Squash-merge + branch delete |
| VECRM-L17-L26 | (various; see prior handovers) |
| **VECRM-L27** | **Permanent.** Verify history/inventory at every layer-transition checkpoint |
| **VECRM-S22-A** | **Counter allocator value-read inside FOR UPDATE** |
| **OBS-S71-A** | **Permanent.** `git branch --show-current` before AND after commit-bearing bash |

### S23 new locks (3 promotions)

| Lock | Purpose |
|---|---|
| **VECRM-LOCK-AUTONAME-HYGIENE** | `autoname=""` is the only safe value for controller-driven naming in Frappe v16+ |
| **VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER** | Name-related guards belong in validate(), not before_insert() |
| **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** | Destructive VPS ops require dispatcher authorization; VECRM-scoped only; never touch VEMIO |

Lock files in `docs/architectural-locks/`. Each ~50 lines: rationale, examples, enforcement points, surfacing session.

---

## PART E — Component-by-component build status

Single comprehensive table. ✅ = production-ready. ⚠️ = exists but partial/needs work. ❌ = not built.

### Layer 1 — Foundation (HR / Employee / Audit)

| Component | Status | Notes |
|---|---|---|
| VECRM Employee doctype | ✅ | autoname=`field:vecrm_phone`; identity = phone (immutable, set_only_once=1) |
| VECRM Rate Card doctype | ✅ | per-city rates (Ahmedabad ₹2.50/km, Mumbai+Pune ₹3.50/km) |
| VECRM User Audit Log doctype | ✅ | append-only; for general user actions (auth, role changes) |
| Employee Active/Suspended status field | ✅ | OTP-layer auth integration locked elsewhere |
| Reporting approver Link field | ✅ | self-reference to VECRM Employee |
| Sales Visit cleanup (PHANTOM-SALES-VISIT-TABLE) | ⚠️ | Vestigial table to drop, PD-S24-PHANTOM-SALES-VISIT-TABLE |

### Layer 2 — Voucher (financial reimbursement)

| Component | Status | Notes |
|---|---|---|
| VECRM Voucher Counter doctype | ✅ | per-series FY-partitioned; allocator at sha `91556a7d...` (L8) |
| VECRM Travel Voucher doctype | ✅ | submittable; autoname='' (S23 fix); guard in validate (S23) |
| VECRM Visit Line child doctype | ✅ | child of Travel Voucher |
| VECRM Voucher Audit Log doctype | ✅ NEW S23 | append-only; serves TV + EV (and future voucher types) |
| VECRM Expense Voucher doctype | ✅ NEW S23 | submittable; mirrors TV with per-line items |
| VECRM Expense Line child doctype | ✅ NEW S23 | category Select: Hotel/Food/Supplies/Communication/Misc |
| approve_travel_voucher API | ✅ | emits voucher.travel.approved |
| approve_expense_voucher API | ✅ NEW S23 | emits voucher.expense.approved |
| Voucher cancellation audit (on_cancel hook) | ⚠️ | PD-S24-VOUCHER-CANCEL-AUDIT; gap surfaced S23 |
| `from frappe import _` import (TV) | ✅ S23 | fixed in PR #11 |

### Layer 3 — Sales pipeline (Lead → Inquiry)

| Component | Status | Notes |
|---|---|---|
| VECRM Lead doctype | ✅ functional S23 | autoname='' (S23 fix); guard in validate (S23) |
| VECRM Inquiry doctype | ✅ functional S23 | autoname='' (S23 fix); guard in validate (S23) |
| VECRM Customer doctype | ⚠️ | minimal skeleton; may be deferred to ERPNext under Tally migration |
| Lead.convert_to_inquiry API | ✅ | functional; sets Lead.status=Converted, populates converted_inquiry |
| VECRM Inquiry Audit Log doctype | ✅ | separate from Voucher Audit Log; conversion-event audit |
| Q9 transport (vemio.io HMAC POST) | ⚠️ | exists; non-fatal try/except wrapper; reliability untested (PART C C6) |
| Lead reassignment ledger | ✅ | child doctype on Lead; populated by before_save owner-change detection |

### Layer 4 — Reporting

| Component | Status | Notes |
|---|---|---|
| Weekly meeting report (B3) | ❌ | not started |
| Real-time dashboards | ❌ | partial via portal `/` dashboard widget |
| Voucher reimbursement export to accounting | ❌ | deferred to Tally → ERPNext migration |

### vecrm-portal frontend (Next.js 16.2.6, PWA-shaped)

| Component | Status | Notes |
|---|---|---|
| `app/layout.tsx` (root, async server, force-dynamic) | ✅ NEW S23 | resolves user via getFrappeUser |
| `app/components/AppShell.tsx` | ✅ refactored S23 | layout-owned; user as prop; no FullPageLoading |
| `app/components/TopBar.tsx` | ✅ | mobile-responsive |
| `app/components/MobileNav.tsx` | ✅ | hamburger drawer; createPortal-mounted (S22) |
| `app/LoginForm.tsx` | ✅ | unchanged S22→S23 |
| `app/useAuth.ts` | ✅ thinned S23 | login/logout actions only; router.refresh after each |
| `lib/auth-ssr.ts` | ✅ NEW S23 | getFrappeUser server-only helper |
| `lib/frappe.ts` | ✅ | frappeFetch helper, FRAPPE_URL env-based |
| `app/page.tsx` (`/`, dashboard) | ✅ | recent inquiries widget |
| `app/leads/page.tsx` | ✅ | list with status filter |
| `app/leads/[name]/page.tsx` | ✅ | detail + convert action |
| `app/inquiries/page.tsx` | ✅ | list with status filter |
| `app/inquiries/[name]/page.tsx` | ✅ | detail (read-only) |
| `/api/auth/login` route | ✅ | proxies to Frappe login, forwards Set-Cookie |
| `/api/auth/logout` route | ✅ | clears sid cookie |
| `/api/auth/me` route | ✅ kept as debugging endpoint S23 | no longer used by AppShell |
| **Travel Voucher create form** | ❌ | PD-S24-PORTAL-VOUCHER-SCREENS |
| **Travel Voucher list view** | ❌ | PD-S24-PORTAL-VOUCHER-SCREENS |
| **Travel Voucher detail view** | ❌ | PD-S24-PORTAL-VOUCHER-SCREENS |
| **Expense Voucher create form** | ❌ | PD-S24-PORTAL-VOUCHER-SCREENS |
| **Expense Voucher list view** | ❌ | PD-S24-PORTAL-VOUCHER-SCREENS |
| **Expense Voucher detail view** | ❌ | PD-S24-PORTAL-VOUCHER-SCREENS |
| **Approver queue view** | ❌ | B2 strategic |
| Theme switcher | ✅ | light / dark / system; persists via THEME_INIT_SCRIPT |
| Manifest (PWA install) | ⚠️ | exists; install prompt not surfaced |
| Service worker | ❌ | deferred per TRAI DLT |
| Offline draft storage | ❌ | deferred |
| Push notifications | ❌ | TRAI DLT 2-4 weeks |

---

## PART F — Production data state (as of S23 close)

### Counter state (VECRM Voucher Counter doctype)

| counter_key | last_value |
|---|---|
| TV-26-27 | 89 |
| LEAD-26-27 | 11 |
| INQ-26-27 | 11 |
| EV-26-27 | 12 |

Counter row for each appears when first allocation triggers `next_number(series, fy)`. Counter rows for FY 25-26 do NOT exist (no allocations attempted).

### Row counts (production tables)

| Table | Rows | All real data? |
|---|---|---|
| tabVECRM Employee | ~5-10 (varies) | mix of real employees + test (+91-9999900001 Sales Rep, +91-9999900002 HR) |
| tabVECRM Rate Card | 1 (default) | Default card with Ahmedabad ₹2.50/km, Mumbai+Pune ₹3.50/km |
| tabVECRM User Audit Log | unknown count | various from session work |
| tabVECRM Voucher Counter | 4 | TV-26-27, LEAD-26-27, INQ-26-27, EV-26-27 |
| tabVECRM Travel Voucher | ~91 | mix; includes 1 cancelled "Test Sales Rep" + 1 proper Desk VE/TV/00079 + 10 §6 VE/TV/00080-89 from S23 |
| tabVECRM Visit Line | ~100+ | child rows of TV |
| tabVECRM Voucher Audit Log | 27 | all from S23 |
| tabVECRM Expense Voucher | 12 | all from S23 |
| tabVECRM Expense Line | ~24 | child rows of EV |
| tabVECRM Lead | 11 | all from S23 (first allocations ever) |
| tabVECRM Inquiry | 11 | all from S23 (first allocations ever) |
| tabVECRM Inquiry Audit Log | 1 | from S23 B.6.a Lead→Inquiry conversion |
| tabVECRM Customer | minimal | placeholder; needs schema fleshing |

### Version anchors

| Component | Version | Sha / lock |
|---|---|---|
| Frappe Framework | 16.18.2 | VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER (document.py L441/L442) |
| MariaDB | 11.8.6 | |
| Next.js (portal) | 16.2.6 | with Turbopack |
| React (portal) | 19.2.4 | |
| Allocator (`voucher_counter.py`) | sha `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` | **VECRM-L8 anchor** |
| Last main commit (vecrm) | `dc52c43` (PR #12) | |
| Last main commit (vecrm-portal) | `d880eda` (PR #4) | |

---

## PART G — Schema drift + cleanup items

### G1 — Phantom Sales Visit table

See PD-S24-PHANTOM-SALES-VISIT-TABLE. 0-row vestigial table from deferred design decision.

### G2 — Test data in production tables

See PART C C3. Not really drift; expected per audit append-only design. Flagged for awareness at first real customer rollout.

### G3 — Counter rows for unused FYs

`tabVECRM Voucher Counter` only contains rows for active FY 26-27. FY 25-26 counter rows do not exist (no allocations attempted). When FY rolls over to 27-28 in April 2027, new counter rows will be created on first allocation. Not drift; expected behavior.

### G4 — CLOSED S23 — Lead/Inquiry counter mystery

(Historical, closing record): Lead and Inquiry counter rows existed since S18 but at last_value=0 with zero rows in their tables. S23 diagnosed: autoname-prompt bug bypassed controllers, all Desk-driven creation silently failed. Fix shipped in PR #11. First real allocations made in S23. **Closed.**

### G5 — Voucher cancellation audit gap

See PD-S24-VOUCHER-CANCEL-AUDIT. on_cancel hook missing from both TV and EV controllers. Cancellation is currently un-audited.

### G6 — Customer doctype skeleton

VECRM Customer is currently a minimal skeleton. Decision pending: flesh out as VECRM source-of-truth, OR defer entirely to ERPNext under Tally migration. Banked decision: defer until Tally migration starts or until first real customer-data need surfaces.

---

## PART H — Out of VECRM scope (clarifications)

These items appeared in prior register iterations but are NOT VECRM's responsibility. Clarified explicitly to prevent OBS-S22-B drift recurring.

| Item | Owner | Why |
|---|---|---|
| Quote doctype | ERPNext | Beyond Inquiry is accounting/sales-quote territory |
| Order doctype | ERPNext | Beyond Inquiry; sales-order management |
| Invoice / Credit Note | ERPNext | Tax / GST / e-invoicing complexity |
| Inventory | ERPNext / out of scope entirely | Vinay Enterprises doesn't sell inventory (services-based) |
| Payment reconciliation | ERPNext | Bank statements, GST returns |
| Tax templates / GST config | ERPNext + Indian Compliance app | Complex; deferred indefinitely |
| TACACS+ / RADIUS / network device auth | VEMIO | Wrong product entirely |
| Network monitoring / alerts / SLAs | VEMIO | Wrong product entirely |
| GLPI ticketing | VEMIO (deprecated) → Frappe HD (VEMIO migration) | Not VECRM |

---

**End of VECRM-PENDENCY-REGISTER.md**

This register is regenerated comprehensively at every session close per VECRM-L2 (decisions written, not remembered). Surgical edits between session closes are acceptable for adding/closing individual PDs but the register is fully reviewed and regenerated at session boundaries.
