# VECRM-PENDENCY-FULL-S30-OPEN

**Supersedes:** `VECRM-PENDENCY-S29-CLOSE.md`
**Generated:** 2026-05-25, S30 open (before any S30 work begins)
**Purpose:** Capture **all** known pendency — including Session 0 scope-contract gaps surfaced in S30-open conversation — before memory decay. This is the live ledger; `VECRM-PENDENCY-S30-CLOSE.md` will be derived from this at S30 close.

---

## §1 — How to read this document

Three categories of pendency:

1. **A. Active workstream pendency** — items that already had PD-IDs assigned in prior sessions and were carried into S29 close. Inherited from `VECRM-PENDENCY-S29-CLOSE.md` and re-prioritized against today's surfaced gaps.
2. **B. Scope-contract gaps surfaced 2026-05-25** — items from Session 0 / S22 strategic adjudication / role-matrix discussion that were never tracked in the pendency register but are real product commitments. New PD-IDs assigned.
3. **C. Unverified items** — gaps that may or may not exist depending on production state. Probes specified; no design work proceeds until probe results land.

Each entry has: **PD-ID, Priority, Status, Effort, Depends-on, Origin, Description.**

Statuses:
- `OPEN` — active, not yet started
- `IN-PROGRESS (S30)` — within S30 scope per opener; do not re-open
- `BLOCKED` — waiting on a dependency (named)
- `UNVERIFIED — PROBE PENDING` — existence/scope depends on probe result
- `DEFERRED` — acknowledged, not scheduled
- `CLOSED` — done (kept here for one cycle for visibility)

Priority semantics for VECRM:
- **P0** — production-broken or actively blocking real user work
- **P1** — Session-0 scope-contract gap (i.e., promised at v1 framing, not yet delivered)
- **P2** — quality-of-life or operator-workflow polish on already-shipped surfaces
- **P3** — backlog, accepted-as-deferred items, observability/audit cleanups

---

## §2 — Probes to run before any S30-extension scope work

Three production-state probes are pending. None of these block S30 scope as planned (Workstream B + D), but they reshape priority on items in §3.C.

```bash
# PROBE-9 — Does VECRM Expense Voucher doctype + table exist in production?
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SHOW TABLES LIKE \"tabVECRM%Voucher%\""'

# PROBE-10 — Is SMTP configured on the VECRM site?
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT name, email_id, smtp_server, enable_outgoing, default_outgoing FROM \`tabEmail Account\` WHERE default_outgoing = 1"'

# PROBE-11 — Have any Q9 conversion emails (from S12 logic) actually sent since deployment?
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT COUNT(*) AS sent, MAX(creation) AS last_sent FROM \`tabCommunication\` WHERE subject LIKE \"%[VECRM Inquiry]%\""'

# PROBE-12 — Does vecrm-portal/lib/email.js exist? (operator-runs locally)
cd ~/Documents/GitHub/vecrm-portal && ls -la lib/email.js 2>&1; grep -rn "graph.microsoft.com" lib/ app/ 2>&1 | head -10
```

### Probe results (2026-05-25 S30 open)

| Probe | Result | Implication |
|---|---|---|
| PROBE-1 vecrm at db4bf94 | ✅ confirmed | clean |
| PROBE-2 vecrm-portal at e0111b8 | ✅ confirmed (2 untracked dispatch files) | clean |
| PROBE-3/4 HTTP 200 both surfaces | ✅ | production responsive |
| PROBE-5 auth columns | ✅ pwd_len=87, pin_len=87, all counters baseline | S29 fix held |
| PROBE-6 audit events | ✅ recent activity traces S29 diagnostic spiral | expected |
| PROBE-7 rollback ladder | ✅ all 8 tags present | recoverable |
| PROBE-8 data counts | ⚠️ **15 leads / 13 inquiries / 3 employees** (expected 14/12/1) | **needs operator confirmation — organic production activity since S29 close?** |
| PROBE-9 voucher tables | ✅ All 4 exist: `tabVECRM Expense Voucher`, `tabVECRM Travel Voucher`, `tabVECRM Voucher Audit Log`, `tabVECRM Voucher Counter` | **Expense Voucher backend shipped — portal-only work remaining** |
| PROBE-10 SMTP config | ✅ **Empty result (no default Email Account)** | **EXPECTED per VECRM-LOCK-VEMIO-EMAIL-PATTERN — VECRM does not use Frappe SMTP. Email is portal-side via Microsoft Graph.** |
| PROBE-11 Q9 emails sent | ❌ **0 sends ever, last_sent NULL** | S12's `frappe.sendmail`-based Q9 has been a silent no-op since deployment. Needs migration to portal-side Graph pattern. |
| PROBE-12 portal email lib | TBD — operator to run | Determines whether `lib/email.js` already exists or needs scaffolding |

---

## §3 — Active pendency

### §3.A — In-progress within S30 (per opener)

#### PD-S29-PIN-INPUT-SEGMENTED-6BOX (Workstream B)

- **Status:** `IN-PROGRESS (S30)`
- **Priority:** P2
- **Effort:** ~2-3 hrs
- **Origin:** S29 Phase A recon (PR #15)
- **Depends on:** None
- **Description:** 6-segmented PIN input component for LoginForm + /set-pin (new + confirm) + /account ChangePinForm. Also tightens `complete_pin_reset` backend (currently 4-6 → exactly-6) and adds length check to `login_with_pin` (currently no length validation). Brings full policy A consistency across PIN entry surfaces.

#### PD-S29-LEAD-FORM-FIELDS (Workstream D)

- **Status:** `IN-PROGRESS (S30)`
- **Priority:** P2
- **Effort:** ~2 hrs
- **Origin:** S29 σ-4 dispatch
- **Depends on:** None
- **Description:** Add 3 mandatory fields to New Lead form: `contact_number`, `contact_email`, `meeting_brief`. Migration LOCKED: schema-permissive (nullable cols) + code-mandatory + forward-only. Existing 14 Leads stay NULL; form-level mandatory enforced in `vecrm.api.create_lead` + portal create form. Lead detail page renders "—" for null.

#### PD-S28-LOGINFORM-PIN-MINLENGTH

- **Status:** `IN-PROGRESS (S30)` — absorbs into Workstream B
- **Priority:** P3
- **Effort:** ~15 min (folded into B)
- **Origin:** S28 close
- **Depends on:** PD-S29-PIN-INPUT-SEGMENTED-6BOX
- **Description:** `minLength={6}` on PIN input in LoginForm. Becomes a no-op once the 6-segment input ships.

---

### §3.B — Small items eligible to ticket into S30 if energy permits

These are sized small enough that they can fold into S30 alongside Workstream B + D without scope creep. **Do not** start them at the cost of finishing B + D.

#### PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE

- **Status:** `OPEN`
- **Priority:** P2
- **Effort:** ~30 min
- **Origin:** S28 close
- **Depends on:** None
- **Description:** Intermittent `+` → ` ` (space) mangling in PIN reset confirmation card display.

#### PD-S28-AUTH-PHONE-PREFIX-LOCK

- **Status:** `OPEN`
- **Priority:** P2
- **Effort:** ~1 hr
- **Origin:** S28 close
- **Depends on:** None
- **Description:** Lock phone input to fixed `+91-` prefix in LoginForm + ForgotPasswordForm phone tab. Eliminates URL-encoding edge cases that have caused intermittent failures.

#### PD-S28-LOGIN-ERROR-UX

- **Status:** `OPEN`
- **Priority:** P2
- **Effort:** ~1 hr
- **Origin:** S28 close, re-surfaced S29 smokes
- **Depends on:** None
- **Description:** Replace `"Frappe responded 401"` raw inline error with human-readable copy. Tonight's smokes again surfaced how confusing this is for users.

#### PD-S29-AUTH-AUDIT-VOCABULARY-NO-PIN

- **Status:** `OPEN`
- **Priority:** P3
- **Effort:** ~15 min
- **Origin:** OBS-S29-TT
- **Depends on:** None
- **Description:** `change_pin` emits reason `current_mismatch` when `pin_hash` is null/empty (genuinely no-PIN-configured case). Should be `no_pin_configured` to match `login_with_pin`'s vocabulary. Symmetric fix for `change_password`. Pure audit-log clarity.

#### PD-S29-DOCS-DRIFT (deferred runbook update)

- **Status:** `OPEN`
- **Priority:** P3
- **Effort:** ~30 min
- **Origin:** S29 banked observations
- **Depends on:** None
- **Description:** Update `PD-S27-DEPLOY-RUNBOOK` with: (a) OBS-S29-KK on benign "orphan containers" warning during `docker compose up --force-recreate <service>`; (b) OBS-S29-JJJ pattern for `bench console < file.py` script execution; (c) OBS-S29-CCC reference to S25 canonical write pattern.

---

### §3.C — P1 scope-contract gaps surfaced 2026-05-25 (NEW)

**These are the items missing from prior pendency registers but present in Session 0 / S22 strategic adjudication / S30-open role-matrix discussion. They are not S30-scope but are the largest gaps in the actual product.**

#### PD-S30-LEAD-CLOSURE-UI ⭐ candidate for S30 if small enough

- **Status:** `OPEN`
- **Priority:** P1 — Session-0 scope-contract gap
- **Effort:** ~2-3 hrs
- **Origin:** Surfaced 2026-05-25, S30-open audit
- **Depends on:** None
- **Description:** Lead has `Closed-Lost` status value (S1-locked) and filter button (S21-shipped), but no transition UI. Need: (a) "Mark as Closed-Lost" action on Lead detail when status=Open; (b) close-reason capture (Data field on VECRM Lead); (c) audit event `lead.closed_lost` written to VECRM Lead Audit Log; (d) re-open path (Closed-Lost → Open) restricted to Sales Head + Admin per role matrix. Sales Rep can close own Leads; cannot re-open. **Sizing note:** if recon shows this can ship in ≤3 hrs total, ticket into S30; otherwise S31.

#### PD-S30-INQUIRY-CLOSURE-UI

- **Status:** `OPEN`
- **Priority:** P1 — Session-0 scope-contract gap
- **Effort:** ~3-4 hrs
- **Origin:** Surfaced 2026-05-25, S30-open audit
- **Depends on:** None
- **Description:** Inquiry has `Closed-by-Ops` filter button (S21-shipped) but no defined semantics or transition UI. Need to decide and ship:
  - **Three terminal states:** `Won` (converted to Order/PO from customer), `Lost` (customer chose competitor / shelved), `Cancelled` (internal: duplicate, fraudulent, withdrawn)
  - Transition UI on Inquiry detail (Sales Rep can mark own; Sales Head + Admin can mark any)
  - Mandatory `close_reason` (Select) + optional `close_notes` (Small Text) at transition
  - Audit events: `inquiry.won`, `inquiry.lost`, `inquiry.cancelled`
  - `Closed-by-Ops` filter renames to three separate filters or one "Closed" filter with sub-filter
  - **Pricing-link decision deferred:** "Won" does NOT yet create an ERPNext Sales Order (Tally→ERPNext deferred per Session-0-B); for now, "Won" just records the terminal state with optional `order_reference_external` (free-text PO number).

#### PD-S30-ADMIN-USER-MANAGEMENT-PAGE

- **Status:** `OPEN`
- **Priority:** P1 — required for any field-staff hiring
- **Effort:** ~6-10 hrs (recon + backend + portal)
- **Origin:** Surfaced 2026-05-25, S30-open conversation
- **Depends on:** Locked role matrix (proposed in S30-open chat; awaits operator sign-off)
- **Description:** Portal pages `/admin/users` (list) + `/admin/users/[name]` (detail) for Admin and HR roles. Capabilities per role-matrix:
  - **Admin:** create / deactivate / reactivate / **delete (soft, irreversible)** / reset password / reset PIN / change role / assign reporting-line
  - **HR:** create / deactivate / reactivate / reset password / reset PIN (no role-change, no delete)
  - Backend methods: `create_employee`, `deactivate_employee`, `reactivate_employee`, `delete_employee` (soft, with `is_deleted` + `deleted_at` + `deleted_by` fields), `admin_reset_password`, `admin_reset_pin`, `change_employee_role`
  - All methods require Admin or HR role per matrix; audit each via `admin.user.{action}` events
  - **Hard locks:** self-deactivate forbidden (cannot delete own account); deleting sole-Admin forbidden; role change to non-existent role rejected; HR cannot grant Admin role
- **Sub-decisions still open** (need operator sign-off before recon):
  - Confirm role matrix as proposed in S30-open conversation
  - Confirm soft-delete vs hard-delete semantics (proposal: soft-delete only, with `is_deleted` flag separate from `is_active`)
  - Confirm sole-Admin protection (cannot delete; cannot self-deactivate)

#### PD-S30-EXPENSE-VOUCHER-PORTAL

- **Status:** `OPEN` — backend confirmed shipped via PROBE-9
- **Priority:** P1 — Session-0 scope-contract gap
- **Effort:** ~6-10 hrs portal-only
- **Origin:** S23 backend shipped (doctype + controller + audit), S24 began portal recon, never completed
- **Depends on:** PD-S30-VOUCHER-SUBMITTER-PORTAL substrate (or ships as part of it)
- **Description:** Backend confirmed live in production (`tabVECRM Expense Voucher` exists per PROBE-9). Remaining work is portal-only:
  - Expense Voucher create form (per-line category Hotel/Food/Supplies/Communication/Misc + amount + receipt photo)
  - Form-level validation (mirror Travel Voucher patterns)
  - Approval queue integration via approver-portal work
- **Note:** Verify backend test-coverage before portal work — probe at S31 recon time: are there any existing Expense Voucher rows in `tabVECRM Expense Voucher`? If zero, this hasn't been smoke-tested end-to-end. If non-zero, who created them and when?

#### PD-S30-VOUCHER-APPROVAL-NOTIFICATION

- **Status:** `OPEN` — design path clarified post-PROBE
- **Priority:** P1 — Session-0 scope-contract gap; operator-stated as "required setup"
- **Effort:** ~3-5 hrs (assumes PD-S30-PORTAL-EMAIL-LIB foundation is in place)
- **Origin:** Surfaced 2026-05-25, S30-open conversation; S22 locked notification-on-submit as part of approval-chain
- **Depends on:** PD-S30-PORTAL-EMAIL-LIB (foundation), PROBE-12 result, VECRM-LOCK-VEMIO-EMAIL-PATTERN
- **Description:** Email notification sent to all members of `approver_set` when Travel or Expense Voucher is submitted, via portal-side Microsoft Graph (NOT Frappe SMTP — per VECRM-LOCK-VEMIO-EMAIL-PATTERN). Approver receives: voucher number, submitter, date(s), total amount, deep link to approval queue.
  - Subject template: `[VECRM Approval] {voucher_number} — {submitter_name} — ₹{total_amount}`
  - One email per approver OR BCC-grouped (operator preference, default: one per approver for clarity)
  - On approve/reject: notify submitter + other approvers (queue item gone)
  - Audit events: `voucher.{type}.submitted` (with `notified_to[]`), `voucher.{type}.approved`, `voucher.{type}.rejected`
  - **Architecture:** vecrm-portal BFF route receives submit → calls Frappe backend `submit_voucher` API → on success, portal calls `lib/email.js::sendApprovalNotification` → Graph send. Email-send failure must NOT roll back submission, but MUST audit.
- **Open sub-questions:**
  - Notification fatigue policy: per-event vs daily digest at 6pm vs both (configurable per-approver)
  - SMS via MSG91 in scope? — DEFERRED per existing TRAI-DLT block
  - Operator decision: include voucher line-items in email body, or link-only?

#### PD-S30-VOUCHER-SUBMITTER-PORTAL

- **Status:** `OPEN`
- **Priority:** P1 — Session-0 scope-contract gap
- **Effort:** ~15-25 hrs (multi-session)
- **Origin:** S22 pendency (B1), restated 2026-05-25
- **Depends on:** PD-S30-EXPENSE-VOUCHER probe-9 resolution
- **Description:** Portal screens for Sales Reps + Field Engineers to submit vouchers from phone:
  - Voucher list (mobile-optimized, filter by status: Draft / Submitted / Approved / Rejected)
  - Travel Voucher create form (visit-line builder, GPS-assisted km, photo upload)
  - Expense Voucher create form (per-line category + amount + receipt photo)
  - Voucher detail / status screen
- **Sub-decision:** PWA install + offline draft storage are NOT in this PD — see PD-S30-PWA-VALIDATION

#### PD-S30-VOUCHER-APPROVER-PORTAL

- **Status:** `OPEN`
- **Priority:** P1 — Session-0 scope-contract gap
- **Effort:** ~10-15 hrs
- **Origin:** S22 pendency (B2), restated 2026-05-25
- **Depends on:** PD-S30-VOUCHER-SUBMITTER-PORTAL (need real vouchers in production to test approval queue)
- **Description:** Pending-approvals queue UI for HR / Admin / Sales Head / Head of Engineers:
  - Queue filterable by submitter, date, voucher type, amount
  - Voucher review screen with full visit/expense detail + receipts
  - One-tap approve / reject-with-reason
  - History view of past approvals (uses Voucher Audit Log)
  - First-to-approve-wins enforced at API level (already locked S22)

#### PD-S30-ROLE-MATRIX-LOCK

- **Status:** `OPEN` — awaiting operator sign-off
- **Priority:** P1 — gates all PD-S30-ADMIN-* and approval-portal work
- **Effort:** ~30 min to write up + operator review
- **Origin:** Surfaced 2026-05-25
- **Depends on:** None
- **Description:** Author `docs/architectural-locks/VECRM-LOCK-ROLE-MATRIX.md` capturing:
  - Full submitter → approver-set map (incl. Sales Head / Head of Engineers / HR / Admin as submitters — currently UNSPECIFIED in S22 lock)
  - Self-approval forbidden invariant
  - Empty-approver-set → reject-submission invariant
  - Role-capability matrix (the table in S30-open conversation): who can create/deactivate/delete users, modify rate card, force-reassign leads, etc.
  - Sole-Admin protection invariants
- **Note:** This is the foundation document. Every PD-S30-ADMIN-* and PD-S30-VOUCHER-APPROVER-* depends on this being locked. Should be authored before or during S31.

#### PD-S30-PORTAL-EMAIL-LIB ⭐ foundation for all VECRM email

- **Status:** `OPEN` — partially verified, PROBE-12 will confirm
- **Priority:** P1 — foundation; blocks PD-S30-VOUCHER-APPROVAL-NOTIFICATION and PD-S30-Q9-EMAIL-MIGRATION
- **Effort:** ~2-3 hrs if `lib/email.js` doesn't exist yet; ~30 min code-read + extension if it does
- **Origin:** VECRM-LOCK-VEMIO-EMAIL-PATTERN (S27 close); referenced as PD-S28-AUTH-RESET-EMAIL-MECHANISM in S27 close pendency
- **Depends on:** Microsoft Graph app reg access (existing Vemio app reg per S27 R4-α decision)
- **Description:** Build `vecrm-portal/lib/email.js` mirroring `vemio-dashboard/lib/email.js`. Provides:
  - `sendEmail({ to, subject, html, plainText? })` — generic Graph-send wrapper
  - Configured via env vars (`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_ADDRESS`)
  - Error handling: throws on send-failure with structured error; caller decides whether to retry / audit / fail-soft
  - Once shipped, becomes the foundation for: Q9 conversion email migration, voucher approval notifications, password-reset emails (if S28 reset flow used it — verify), invite emails (future)
- **Status uncertainty:** S27 scoped this as `PD-S28-AUTH-RESET-EMAIL-MECHANISM` for the password-reset flow. S28 actually shipped password reset per S29 close handover. **Open question:** did S28's password-reset implementation actually use Graph (in which case `lib/email.js` exists), or did it use some other mechanism (in which case the foundation lib still needs to be built)? PROBE-12 resolves this.

#### PD-S30-Q9-EMAIL-MIGRATION

- **Status:** `OPEN` — silent no-op in production since S12
- **Priority:** P2 (was P1, downgraded because no real Inquiries are flowing yet — Krunal's UAT is the only consumer and it's already blocked elsewhere)
- **Effort:** ~1-2 hrs (assumes PD-S30-PORTAL-EMAIL-LIB is in place)
- **Origin:** PROBE-11 (0 emails sent ever) + S12 design (`frappe.sendmail` fail-soft); reconciled against S27 VECRM-LOCK-VEMIO-EMAIL-PATTERN
- **Depends on:** PD-S30-PORTAL-EMAIL-LIB
- **Description:** S12 implemented Q9 management email on Lead→Inquiry conversion using `frappe.sendmail` with fail-soft semantics. PROBE-10 confirms VECRM has no Frappe Email Account configured (expected per VECRM-LOCK-VEMIO-EMAIL-PATTERN). PROBE-11 confirms 0 Q9 emails have been sent since deployment. Migrate Q9 email send from backend `frappe.sendmail` → portal-side Graph via `lib/email.js`.
  - Move send-trigger from `vecrm.api.convert_lead_to_inquiry` Frappe controller → vecrm-portal `app/api/leads/[name]/convert/route.ts` (after backend convert returns success)
  - Keep recipient list (`ajay@, krunal@, info@vinayenterprises.co.in`), subject template, body template unchanged
  - Keep fail-soft semantics: send failure does NOT roll back conversion
  - Keep fail-loud audit: write `inquiry.conversion.email_failed` to audit log on send-failure (or `inquiry.conversion.email_sent` on success — keeps audit symmetric)
  - Delete dead `frappe.sendmail` call from backend controller
- **Why this matters:** Krunal's async UAT review of Q9 email content (referenced in top-of-mind context across many sessions) has been blocked since S12 because no email has ever sent. The blocker isn't UAT bandwidth — it's that the pipeline is broken. Fixing this unblocks UAT closure.

---

### §3.D — Active P2 carryovers (no priority change)

#### PD-S29-INQUIRY-SCOPING

- **Status:** `OPEN`
- **Priority:** P2
- **Effort:** ~2-3 hrs
- **Origin:** OBS-S29-X, OBS-S29-AA
- **Depends on:** None
- **Description:** Per-rep Inquiry scoping (parallel to Lead scoping shipped S29 PR #16). OBS-S29-X also noted `inquiry_owner=Administrator` write-path issue. Reuses `getScopedLeadFilter` / `canReadLead` pattern from `lib/scoping.ts`.

---

### §3.E — Active P3 carryovers

#### PD-S28-ADMIN-PIN-SET-UI

- **Status:** `OPEN` — partially obsoleted by S29
- **Priority:** P3
- **Effort:** ~2-3 hrs
- **Origin:** S28 close
- **Depends on:** None — but absorbs into PD-S30-ADMIN-USER-MANAGEMENT-PAGE
- **Description:** Originally: Frappe Desk button to set/reset employee PIN via admin UI. Now absorbed into the larger Admin User Management portal page (PD-S30-ADMIN-USER-MANAGEMENT-PAGE includes admin-reset-PIN as a capability). Mark CLOSED when PD-S30-ADMIN-USER-MANAGEMENT-PAGE ships.

#### PD-S29-CANDIDATE-RESET-RATELIMIT-SHARED

- **Status:** `OPEN`
- **Priority:** P3
- **Effort:** ~1 hr
- **Origin:** S28 close, restated S29
- **Depends on:** None
- **Description:** Reset rate limit is per-`reset_for` (password vs PIN), allowing 6 total reset requests per employee per 15-min window. Consider shared rate limit (3 total) since both surface to the same user.

#### PD-S29-PORTAL-VECRMSESSION-EXTENSION-FUTURE

- **Status:** `OPEN`
- **Priority:** P3
- **Effort:** TBD
- **Origin:** S29 PR #18 banked
- **Depends on:** Future user request for an Account field that doesn't fit in session
- **Description:** Trigger for introducing the (β) endpoint approach from S29 Workstream C recon: when first Account field is requested that doesn't belong in `VecrmSession` (e.g., notification prefs, theme, language).

---

### §3.F — Additional P1+ scope-contract gaps surfaced today (NEW, lower urgency than §3.C P1s)

#### PD-S30-WEEKLY-MEETING-REPORT

- **Status:** `OPEN`
- **Priority:** P1 — Session-0 scope-contract gap
- **Effort:** ~8-12 hrs
- **Origin:** Session 0 scope, S22 pendency (B3), restated 2026-05-25
- **Depends on:** PD-S30-LEAD-CLOSURE-UI + PD-S30-INQUIRY-CLOSURE-UI (need terminal states to report on)
- **Description:** Per Session 0, Vinay Enterprises holds weekly meetings reviewing sales pipeline + activities. Output is a structured report:
  - `VECRM Weekly Report` doctype (week_start, week_end, generated_by, sections JSON)
  - Server-side generator (scheduled Sunday night for Mon meeting)
  - Sections: pipeline movements (open/converted/lost by rep), visits summary, calls summary, voucher spend by rep, won/lost ratio
  - Manual annotation fields (managers can add notes)
  - PDF export for meeting print
  - Email to {Admin, Sales Head, HR}

#### PD-S30-SALES-VISIT-RECONCILIATION

- **Status:** `OPEN` — needs decision before any voucher portal design
- **Priority:** P1 — gates PD-S30-VOUCHER-SUBMITTER-PORTAL
- **Effort:** ~30 min decision + design implication
- **Origin:** Surfaced 2026-05-25; S8/S9 shipped Sales Visit, S22 onwards used Travel Voucher without reconciling
- **Depends on:** None
- **Description:** Decide the relationship between `VECRM Sales Visit` (S8/S9 — rate-card-driven reimbursement compute, has portal screen) and `VECRM Travel Voucher` (S22 — FY-numbered, approval-chain, no portal). Three options:
  - **(a) Sales Visit deprecated** — Travel Voucher is the canonical surface; archive Sales Visit code/UI
  - **(b) Sales Visit remains "log per visit"** + Travel Voucher batches visits weekly — Sales Visit child-lines roll into Travel Voucher.visit_lines
  - **(c) Sales Visit and Travel Voucher are separate flows** for different reimbursement types (visit-based per-km vs trip-based reimbursement) — both surface in voucher portal
- **Operator decision required** before PD-S30-VOUCHER-SUBMITTER-PORTAL begins.

#### PD-S30-ROLE-DIFFERENTIATION-UI

- **Status:** `OPEN`
- **Priority:** P2 (was P1 in S22; downgraded because Lead scoping S29 PR #16 handled the highest-impact axis)
- **Effort:** ~4-6 hrs
- **Origin:** S22 pendency (B5)
- **Depends on:** PD-S30-ROLE-MATRIX-LOCK
- **Description:** Portal home screen differentiation by role:
  - Sales Rep: Leads + Inquiries + Vouchers
  - Field Engineer: Vouchers only (no Leads/Inquiries)
  - Sales Head: team's Leads + Inquiries + Approval queue + own Vouchers
  - Head of Engineers: team's Vouchers + Approval queue + own Vouchers
  - HR: Admin/User page + Approval queue (all)
  - Admin: everything

#### PD-S30-PWA-VALIDATION

- **Status:** `OPEN`
- **Priority:** P2 — Session-0 scope but field-staff are not yet hired so impact lag
- **Effort:** ~6-10 hrs
- **Origin:** Session 0, S22 pendency (B4)
- **Depends on:** PD-S30-VOUCHER-SUBMITTER-PORTAL (need vouchers to test offline draft)
- **Description:** Manifest exists; everything else is missing:
  - Service worker (cache strategy for portal shell)
  - Offline voucher draft storage (IndexedDB or similar)
  - Background sync on reconnection
  - Install prompts (Android Add-to-Home-Screen)
  - Validate on actual Android phone with a real Sales Rep workflow ("30-second voucher log")

---

## §4 — Strategic backlog (Session-0 items, multi-session efforts)

Unchanged from S29 close pendency. Retained here for completeness.

| ID | Description |
|---|---|
| Session-0-A | VECRM portal usability cohort testing — manual testing with real Sales Reps once 2-3 are hired |
| Session-0-B | Tally → ERPNext migration — API-driven, defer customs UI rejected post-audit, engage Ahmedabad ERPNext partner for opening-balance recon + GST account restructuring |
| Session-0-C | VEMIO ↔ VECRM CRM Lead-to-Project handoff — Lead converted to Inquiry to Quote to PO needs handoff into VEMIO tenant provisioning |
| Session-0-D | VECRM dashboard widgets — role-aware (Sales Rep sees own; Admin sees aggregate) |
| Session-0-E | OTP auth via MSG91 — blocked on TRAI DLT registration (parked 12+ sessions) |

---

## §5 — Closed in S29 (kept for one cycle visibility)

| PD ID | Closed via |
|---|---|
| PD-S28-LEAD-SCOPING-CUTOVER | PR #16 (vecrm-portal, `f269563`) |
| PD-S27-PORTAL-SCOPING-PATTERN | Pattern doc shipped in PR #16 |
| PD-S29-ACCOUNT-SELF-SERVICE | PR #27 (vecrm) + PR #18 (vecrm-portal) |
| PD-S29-AUTH-WRITE-PATTERN-FIX | PR #29 (vecrm) — surfaced + fixed same session |
| PD-S29-PIN-LOGIN-BROKEN | Absorbed by PD-S29-AUTH-WRITE-PATTERN-FIX |
| PD-S26-PORTAL-VECRMSESSION-TYPE | Absorbed by PR #18 |
| PD-S27-TEST-PIN-ROTATION | PIN now rotatable via /account |

---

## §6 — Ledger summary

| Category | Count |
|---|---|
| In-progress within S30 (§3.A) | 3 |
| Small ticketable in S30 if energy (§3.B) | 5 |
| **P1 scope-contract gaps surfaced today (§3.C)** | **10** |
| Active P2 carryovers (§3.D) | 1 |
| Active P3 carryovers (§3.E) | 3 |
| Additional P1+ surfaced today (§3.F) | 4 |
| **Total active PDs** | **26** |
| Strategic backlog | 5 |
| Closed in S29 (visibility cycle) | 7 |

**Trend:** S29 close reported 10 active PDs. Today's audit surfaces 14 additional pendency items (10 P1 scope-contract + 4 mixed). Total active jumps from 10 → 26, but this is a one-time correction (catching memory decay + integrating Graph-email reality), not new work materializing. Expected trajectory: 26 → ~24 at S30 close (B + D + 1-2 small).

---

## §7 — Decisions awaiting operator sign-off (block-list)

These need operator decisions before respective PDs can advance to recon:

1. **PD-S30-ROLE-MATRIX-LOCK** — confirm proposed role/capability matrix (S30-open conversation)
2. **PD-S30-SALES-VISIT-RECONCILIATION** — pick (a), (b), or (c)
3. **PD-S30-VOUCHER-APPROVAL-NOTIFICATION** — notification fatigue policy (per-event vs digest vs both)
4. **PD-S30-INQUIRY-CLOSURE-UI** — confirm three terminal states (Won / Lost / Cancelled) and `order_reference_external` as Tally-bridge placeholder
5. **PD-S30-ADMIN-USER-MANAGEMENT-PAGE** — confirm soft-delete semantics + sole-Admin protections
6. **PROBE-8 data-count drift** — confirm/explain +1 Lead, +1 Inquiry, +2 Employees vs S29-close baseline (organic activity? test data? unexpected writes?)
7. **PROBE-12** — operator runs locally to confirm whether `vecrm-portal/lib/email.js` already exists; determines effort estimate for PD-S30-PORTAL-EMAIL-LIB

---

## §8 — Update protocol

This document is the live ledger from S30-open until S30-close. At S30 close:

1. Move all `IN-PROGRESS (S30)` items that shipped to §5 (Closed)
2. Append PROBE-9/10/11 results
3. Update PD-S30-EXPENSE-VOUCHER + PD-S30-VOUCHER-APPROVAL-NOTIFICATION status based on probe results
4. Rename file to `VECRM-PENDENCY-S30-CLOSE.md`
5. Generate `VECRM-PENDENCY-FULL-S31-OPEN.md` (copy of S30-close)

---

**End of full pendency register, S30-open.**
