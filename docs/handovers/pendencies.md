# VECRM Active Pendencies

Last updated: 2026-05-27 (S33 closed)
0 active P0 blockers. 0 active P1 blockers.

S33 deliverables: 4 PRs merged (vecrm #46; vecrm-portal #31, #32, #33).
PD-S30-LEAD-FOLLOWUP Phase 1 shipped end-to-end. See `S33-CLOSE.md`.

---

## Closed this session (S33)

| Pendency | Priority | Closing PR | Closing date |
|---|---|---|---|
| PD-S32-NEXT-VOUCHER-PERMISSION-ERROR-UX | P2 | vecrm-portal #31 | 2026-05-27 |
| **PD-S30-LEAD-FOLLOWUP Phase 1 (backend)** | **P1** | **vecrm #46** | **2026-05-27** |
| **PD-S30-LEAD-FOLLOWUP Phase 1 (portal)** | **P1** | **vecrm-portal #32** | **2026-05-27** |
| PD-S33-NEXT-OVERDUE-FILTER-BUG | P2 | vecrm-portal #33 | 2026-05-27 |
| PD-S33-NEXT-VEMIO-DASHBOARD-PHANTOM-BRANCH-CLEANUP | — | confirmed absent | 2026-05-27 |

---

## Active (P1)

### PD-S30-LEAD-FOLLOWUP-WORKFLOW — Phase 2 (P1)
**Banked:** S30. **Spec ratified:** S33. **Phase 1 closed:** S33.
**Scope:** Touchpoint doctype + nav badge + status enum prep.
**Phase 2 specifics:**
- New standalone `VECRM Lead Touchpoint` doctype with `touchpoint_date`,
  `touchpoint_type` (Call / Meeting / Email / WhatsApp / Site Visit / Other),
  `notes`, `lead` link.
- 3 whitelisted methods: `log_touchpoint`, `list_touchpoints`,
  `delete_touchpoint` (last one admin-only or creator-only).
- Lead controller derives `last_contact_date` + `touchpoint_count` from
  child table or query — TBD per spec recon.
- Portal: touchpoint UI on Lead detail page (chronological list, add button).
- Portal nav badge: "X due today" indicator on Leads tab.
**Estimated:** ~1–1.5 sessions.
**Production gating:** (β) Phase 1+2 deploy as a unit. Phase 2 should ship
before next month's sales review per operator priority.

### PD-S30-LEAD-FOLLOWUP-WORKFLOW — Phase 3 (P1)
**Banked:** S30. **Blocked on:** PD-S29-VEMIO-EMAIL-PIPELINE.
**Scope:** Status enum expansion (Contacted / Quoted / Negotiating /
Closed-Won / Closed-Lost) + scheduler_events email reminders.
**Production gating:** (β) Phase 3 ships post-production-cutover. Email
reminders blocked on the email pipeline.

### PD-S29-VOUCHER-APPROVER-PORTAL-B2 (P1)
**Banked:** S29.
**Scope:** HR/Admin can approve submitted TV+EV from portal (currently
Desk-only). Mirror TV detail and EV detail pages, add Approve / Reject
buttons and approval-notes textarea for HR/Admin. Calls backend approve
endpoint (to be authored: `vecrm.api.approve_*_voucher`).
**Touches:** new `/expense-vouchers/[name]/approve` flow; same for TV; new
backend endpoints with approver-role guard; audit hook for
`voucher.*.approved`.
**Recommended order:** Consider for S34 #2 if PD-S30 Phase 2 fits in S34
without overflow.

### PD-S29-WEEKLY-MEETING-REPORT (P1)
**Banked:** S29.
**Scope:** Friday EOW Outlook digest of leads, vouchers, inquiries piped to
Vinay + Ajay. Probably a scheduled Frappe job + email pipeline.
**Dependency:** PD-S29-VEMIO-EMAIL-PIPELINE.

### PD-S29-VEMIO-EMAIL-PIPELINE (P1)
**Banked:** S29. **Larger build, multi-session.**
**Scope:** Outlook integration via Graph API or SMTP relay through vemio.
Blocks PD-S29-WEEKLY-MEETING-REPORT and PD-S30 Phase 3 email reminders.

### PD-S33-NEXT-IMAGE-PRUNE (P1)
**Banked:** S33.
**Scope:** Systematic prune policy for old `vecrm-custom` rollback tags on
VPS. Keep ~3 sessions back (e.g. S31, S32, S33 rollbacks).
**Trigger:** S33 disk-pressure recovery freed ~58GB across 3 tranches:
- Tranche 1: `docker builder prune -a -f` (27.4GB)
- Tranche 2: 7 old `vecrm-custom:v0.*` tags
- Tranche 3: 5 S18–S21 rollback tags + 4 misformatted
  `s32-pre-*-rollback:latest` tags (~33GB combined)
Pre-recovery disk: 96% used. Post-recovery: 47% used / 78GB free.
**Action:** Document a `vps-prune.sh` or equivalent. Run before each
deploy that involves `--no-cache` builds.

---

## Active (P2)

### PD-S33-NEXT-TEST-INFRA (P2)
**Banked:** S33.
**Scope:** Install vitest in vecrm-portal. Author first test for
`lib/errors.ts` — specifically the `voucher_submit` ErrorContext branch added
in PR #31. Establishes pattern for unit testing pure-function lib modules.
**Estimated:** ~2h.

### PD-S33-NEXT-DEPLOY-TAG-DISCIPLINE (P2)
**Banked:** S33.
**Scope:** Add verifiable rollback-tag step to canonical 8-step deploy
procedure. Close-doc convention must require `docker images grep` output
showing the tag exists, not prose claiming it does. Per OBS-S33-B (S32 close
claimed tags existed; verification at S33 entry found only one).

### PD-S33-NEXT-LEAD-DATA-WIPE (P2)
**Banked:** S33.
**Scope:** Truncate `tabVECRM Lead` + audit child rows before production
cutover. Existing leads are demo data per Q-13 / Tension 5 of
Q-LEAD-FOLLOWUP-LOCK.
**Estimated:** ~30min. Coordinate with first real-data import.

### PD-S33-NEXT-VECRM-LOCK-FRAPPE-FILTER-PATTERNS (P2)
**Banked:** S33.
**Scope:** Author
`docs/architectural-locks/VECRM-LOCK-FRAPPE-FILTER-PATTERNS.md` documenting:
- OBS-S33-U: Frappe v15 nullable-date comparison operators (`<`, `>`, `=`,
  `between`) do NOT enforce SQL-standard NULL semantics. Always pair with
  `["field", "is", "set"]` predicate.
- `is set` / `is not set` Frappe filter operators vs SQL `IS NULL`.
- `between` filter array shape: `["field", "between", [low, high]]` not
  `["between", low, high]`.
- `like` filter wildcard `%` is literal, not regex.
- `in` / `not in` operators take array as third element.
**Estimated:** ~1h. Convert from OBS notes into ratified lock document.

---

## Active (P3)

### PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT (P3)
**Banked:** S33.
**Scope:** Cross-cutting Sales Head write-auth refactor across all lead-write
BFFs if operationally required. Q-LEAD-FOLLOWUP-11 was revised mid-session
from (c) lead_owner+Sales Head+Admin to (a) creator+Admin because the
original model didn't match other lead-write BFF auth (close, convert,
attachments all use `canReadLead`). If business requires Sales Head to write
across the team's leads, this would be the refactor entry point.
**Touches:** `lib/scoping.ts` `canReadLead` + all `/api/leads/[name]/*` POST
routes.
**Estimated:** ~1.5 sessions including spec ratification.

### PD-S30-NEXT-LEAD-LIST-CLOSED-WON-FILTER (P3)
**Banked:** S33 (incidentally — OBS-S33-T).
**Scope:** Leads list page status filter chip row is missing `Closed-Won`.
Current chips: `["all", "Open", "Converted", "Closed-Lost"]`. Lead doctype
enum has 4 status values; only 3 are filterable from the chips. Either
oversight or deliberate; verify intent and either add the chip or document
why it's omitted.

---

## VPS housekeeping (NOT pendencies, but tracked)

- **Worker image audit (OBS-S33-J).** `vecrm-frontend-1` + 5 worker
  containers (queue-short, queue-long, scheduler, websocket, redis-queue,
  redis-cache, db) are pinned to `vecrm-custom:s22-pre-build` =
  `21bb1afd017e`, stale 5+ days from backend. Operator chose (γ) Phase 1
  backend-only rebuild for S33. **S34 action:** verify by-design vs
  operational drift; rebuild workers from current `vecrm-custom:latest` if
  drift.
- `vemio-freeradius` healthcheck misconfigured (`radclient: Nothing to
  send`). Benign, known issue. Tracked in vemio side, not VECRM.
