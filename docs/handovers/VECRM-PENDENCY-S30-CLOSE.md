# VECRM-PENDENCY-S30-CLOSE

**State as of:** 2026-05-25 ~17:30 IST (S30 close)
**Active items:** 26 P1/P2 + 4 P3/P4
**Items closed this session:** 8 (see §1)
**Items added this session:** 6 (see §2)

This document supersedes `VECRM-PENDENCY-FULL-S30-OPEN.md` (PR #31). Format kept consistent so diff is readable.

---

## §1 — Items CLOSED in S30

| ID | Subject | Closed via |
|---|---|---|
| PD-S29-LEAD-FORM-FIELDS | Lead form mandatory fields (backend + portal) | PR #32 + #33 + #19 |
| PD-S29-PIN-INPUT-SEGMENTED-6BOX | PIN segmented 6-box input (backend + portal) | PR #34 + #20 |
| PD-S28-LOGINFORM-PIN-MINLENGTH | LoginForm PIN minLength enforcement | Closes by construction via PR #20 |
| PD-S28-AUTH-PHONE-PREFIX-LOCK | +91- prefix lock on auth phone input | Absorbed into PR #19 |
| PD-S28-LOGIN-ERROR-UX | Login error humanization | Absorbed into PR #19 (humanizeError) |
| PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE | Forgot-PIN URL +-mangle | Closes by construction via PR #19's PhoneInput |
| PD-S30-PORTAL-EMAIL-LIB | Portal email library foundation | Verified existing via PROBE-12 |
| PD-S30-PININPUT-VISUAL-POLISH | Segment border contrast + wrapper border + dark mode | PR #21 |

---

## §2 — Items ADDED to pendency in S30

| ID | Subject | Priority | Target |
|---|---|---|---|
| PD-S30-LEAD-OWNER-ATTRIBUTION | lead_owner = BFF service account instead of human; 5-site fix + migration | P1 | S31 (B-phase) |
| PD-S30-LEAD-CONTACT-FIELDS | Lead contact person name + designation | P1 | S32 |
| PD-S30-LEAD-ATTACHMENTS | Up to 3 attachments per Lead | P2 | S32 |
| PD-S30-LEAD-FOLLOWUP-WORKFLOW | Follow-up date + email reminders (T-1, T-0, T+) + ack workflow + re-follow-up loop | P1 | S33+ |
| PD-S30-PININPUT-HORIZONTAL-CENTER | 6 PIN boxes not horizontally centered in wrapper card | P3 | S31+ (cosmetic) |
| PD-S30-DOCS-DRIFT-PR4-RUNBOOK | PR #4 runbooks describe Mac-buildx workflow; actual builds on VPS | P2 | S31+ |

---

## §3 — Active P1 items (Day-1 priority for S31)

### PD-S30-LEAD-OWNER-ATTRIBUTION (P1, S31 Day-1)

Multi-session latent attribution bug. Recon complete, 552-line findings doc on local branch `recon/s30-lead-owner-attribution`. Confirmed at protocol level.

**Surface:** 5 surgical edits in 4 files + 1 migration patch.

**Files to touch (per recon):**
1. `vecrm/api.py:334` — `lead_owner` source change
2. `vecrm/api.py` (`_issue_session`) — stash `vecrm_email` in session (2 lines)
3. `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.py:84` — reassignment ledger actor source
4. `vecrm/vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py:206` — audit log actor_user
5. `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:162` — audit log actor_user

**Migration:** v1_4 patch + rollback (conditional on F-1.4 probe result for User row existence).

**Inquiry:** fixes itself via cascade once Lead fix lands.

**Blockers:**
- F-1.4 probe: does `ajay@vinayenterprises.co.in` exist as Frappe User row? (P0 for migration shape)
- 14 ATT questions in findings §J (mostly defaulted; ATT-13/ATT-8/ATT-14 need conscious decisions)

**Decisions needed:**
- ATT-1..3: Architecture (acting_user_email param vs request-scoped helper)
- ATT-4..5: Validation strictness (reject if missing? fall back to session.user?)
- ATT-8..10: Migrate or amnesty (and how)
- ATT-13: User row existence (P0 blocker)
- ATT-14: Audit log migration policy (don't migrate is recommended)

### PD-S29-VEMIO-EMAIL-PIPELINE (P1, S31+)

Migrate Q9 email audit trail from `frappe.sendmail` (silent no-op) to portal-side Graph email via `lib/email.js`. Verified zero emails sent since S12 deployment.

Depends on LEAD-OWNER-ATTRIBUTION fix (so recipient is correct).

### PD-S30-LEAD-CONTACT-FIELDS (P1, S32 target)

Add to Lead doctype: `contact_person_name` (Data) + `contact_person_designation` (Data). Same forward-only-nullable migration pattern as PR #32.

Estimated ~2 hours.

Depends on LEAD-OWNER-ATTRIBUTION fix.

### PD-S30-LEAD-FOLLOWUP-WORKFLOW (P1, S33+ target)

Three sub-PRs:

**Sub-PR A: Scheduling + reminder emails (~6-8 hrs)**
- New field `follow_up_date` (Date) on Lead
- Frappe scheduled job (daily ~8:30am IST, configurable)
- Scan logic: `WHERE follow_up_date IS NOT NULL AND status = 'Open' AND (follow_up_date = today + 1 day OR follow_up_date <= today) AND (followup_reminder_sent_today != today OR followup_reminder_sent_today IS NULL)`
- For each match: send email via Graph (`lib/email.js::sendMailNoreply`)
  - To: `<lead_owner.vecrm_email>` (depends on LEAD-OWNER-ATTRIBUTION fix)
  - CC: `ajay@`, `mohit@`, `krunal@`, `info@vinayenterprises.co.in`
  - T-1 subject: `[VECRM Follow-up Tomorrow] {company_name}`
  - T-0 subject: `[VECRM Follow-up TODAY] {company_name}`
  - T+ subject: `[VECRM Follow-up OVERDUE] {company_name} ({n} days)`
- New field `followup_reminder_sent_today` (Date) for idempotency
- Audit events: `lead.followup.scheduled`, `lead.followup.reminded.t-minus-1`, `lead.followup.reminded.t-0`, `lead.followup.reminded.overdue`

**Sub-PR B: Acknowledgement workflow + log (~4-6 hrs)**
- New doctype: `VECRM Lead Followup Log` (append-only)
  - Fields: `lead`, `follow_up_date`, `acknowledged_at`, `acknowledged_by`, `outcome_notes`, `re_follow_up_date`
- Portal UI: "Acknowledge Follow-up" button on Lead detail
- Modal captures outcome + optional re-follow-up date
- If re-follow-up set: update `follow_up_date`, clear `followup_reminder_sent_today`, scheduler picks up automatically
- If no re-follow-up: clear `follow_up_date` (no further reminders), Lead stays Open
- Permission per operator decision: anyone with Lead read access
- Audit: `lead.followup.acknowledged`, `lead.followup.rescheduled`

**Sub-PR C: Closed-state cancellation (~1-2 hrs, ships with PD-S30-LEAD-CLOSURE-UI)**
- On status transition to Closed-Lost/Won: clear `follow_up_date`, clear `followup_reminder_sent_today`, append final log entry
- Hard stop on terminal state per operator decision

**Hard blocker:** LEAD-OWNER-ATTRIBUTION must be fixed first.

### PD-S29-LEAD-INQUIRY-CLOSURE-UI (P1, S32+)

Operator decision for closed states: Closed-Won (sale made), Closed-Lost (no sale). Required by follow-up workflow Sub-PR C and by Session-0 sales-pipeline contract.

### PD-S29-ADMIN-USER-MGMT-PAGE (P1, S32+)

Admin/HR user management page with role-capability matrix. Required before Sales Reps are hired. Couples with Role Matrix Lock (PD-S29-ROLE-MATRIX-LOCK).

### PD-S29-EXPENSE-VOUCHER-PORTAL (P1, S33+)

Expense Voucher portal page for sales rep submission. Backend already shipped (verified via PROBE-9: all 4 voucher tables exist).

### PD-S29-VOUCHER-APPROVAL-NOTIFICATIONS (P1, S33+)

Email notifications to approvers on voucher submission. Depends on email pipeline migration + LEAD-OWNER-ATTRIBUTION fix.

### PD-S29-VOUCHER-SUBMITTER-PORTAL (P1, S33+)

Travel Voucher submitter portal page. Depends on LEAD-OWNER-ATTRIBUTION fix (submitter is currently mis-attributed).

### PD-S29-VOUCHER-APPROVER-PORTAL (P1, S33+)

Voucher approver portal page. Pairs with submitter portal.

### PD-S29-WEEKLY-MEETING-REPORT (P1, S34+)

Weekly meeting report — Sales pipeline status email digest. Couples with follow-up workflow + LEAD-OWNER-ATTRIBUTION.

### PD-S29-ROLE-MATRIX-LOCK (P1, S32+)

Document the role-capability matrix as a permanent lock. Required for Sales Rep hiring. Depends on role design completion.

### PD-S29-PWA-VALIDATION (P1, S33+)

PWA installability validation. Sales reps need installable app on field phones. Depends on portal stability post-LEAD-OWNER fix.

---

## §4 — Active P2 items

### PD-S30-LEAD-ATTACHMENTS (P2, S32 target)

Up to 3 attachments per Lead. Frappe `Attach` fieldtype × 3 OR child-table approach. Storage: built-in File doctype. Size limit: ~10MB. Types: pdf, png, jpg, jpeg (+ maybe docx/xlsx for RFPs — decide at recon).

Depends on LEAD-CONTACT-FIELDS (ship together for cleaner UX).

### PD-S30-DOCS-DRIFT-PR4-RUNBOOK (P2)

PR #4 runbooks describe a fictional Mac-buildx workflow; actual production builds run on the VPS via `docker buildx build`. Documentation should match reality.

### PD-S29-SALES-VISIT-RECON (P2, S32+)

Sales Visit doctype reconciliation. Designed as Option B (standalone with optional Lead link), per-km rate via single-doctype + child table. Backend shipped earlier; needs operator-facing UI.

### PD-S29-TALLY-MIGRATION (P2, deferred)

Tally → ERPNext migration. API-driven only. Engage Ahmedabad ERPNext partner at migration time.

---

## §5 — Active P3/P4 items

### PD-S30-PININPUT-HORIZONTAL-CENTER (P3)

6 PIN segment boxes not horizontally centered within the wrapper card. Single CSS line fix (likely missing `justify-content: center` on `.pin-input-6box-wrapper`). Batch with any portal PR.

### PD-S29-AUDIT-DOCTYPE-ENUM (P3)

Audit-reason taxonomy at 11 values (OBS-S30-I). Move to doctype-level closed-enum at 12+ values.

### PD-S30-SHARED-VALIDATE-PIN-HELPER (P4)

No shared `_validate_pin` helper (OBS-S30-G). Three inline checks remain post-tightening. Consolidate at 4+ entry points.

### PD-S30-SHARED-FORM-PRIMITIVES (P4)

Currently 2 shared primitives (PhoneInput + PinInput6Box). Consolidate naming convention + storage location at 3+ primitives (OBS-S30-H).

---

## §6 — Architectural locks active

(Carried from S29 + earlier.)

| Lock | Purpose |
|---|---|
| VECRM-LOCK-VPS-DESTRUCTIVE-OPS | Operator-only VPS calls |
| VECRM-LOCK-VEMIO-EMAIL-PATTERN | Portal-side Graph email, NOT Frappe SMTP |
| VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE | Dispatch examples are guides; actual code wins |
| VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE | Three-layer code-landed verification mandatory (NEW from S30) |

**Lock candidates promoted from S30 OBS:**
- VECRM-LOCK-DEPLOY-COMMANDS-FROM-EVIDENCE (OBS-S30-K)
- VECRM-LOCK-S29-PORTAL-COMPONENT-PATHS (OBS-S30-J)
- VECRM-LOCK-VERIFY-BASELINE-BEFORE-BRANCH (OBS-S30-CC)

(To be formally promoted at S31 open.)

---

## §7 — Dependency graph (text)

```
PD-S30-LEAD-OWNER-ATTRIBUTION
   ├─→ unblocks PD-S29-VEMIO-EMAIL-PIPELINE (recipient correctness)
   ├─→ unblocks PD-S30-LEAD-FOLLOWUP-WORKFLOW (recipient correctness)
   ├─→ unblocks PD-S29-VOUCHER-APPROVAL-NOTIFICATIONS
   ├─→ unblocks PD-S29-VOUCHER-SUBMITTER-PORTAL (correct submitter)
   ├─→ unblocks PD-S29-VOUCHER-APPROVER-PORTAL
   └─→ unblocks PD-S29-WEEKLY-MEETING-REPORT

PD-S30-LEAD-CONTACT-FIELDS
   └─→ batches with PD-S30-LEAD-ATTACHMENTS

PD-S30-LEAD-FOLLOWUP-WORKFLOW
   ├─ blocks on PD-S30-LEAD-OWNER-ATTRIBUTION
   ├─ Sub-PR C blocks on PD-S29-LEAD-INQUIRY-CLOSURE-UI
   └─ blocks on PD-S29-VEMIO-EMAIL-PIPELINE

PD-S29-ADMIN-USER-MGMT-PAGE
   ├─ blocks PD-S29-ROLE-MATRIX-LOCK formal authoring
   └─ enables Sales Rep hiring

PD-S29-PWA-VALIDATION
   └─ depends on post-LEAD-OWNER-ATTRIBUTION portal stability
```

---

**End of pendency document.**
