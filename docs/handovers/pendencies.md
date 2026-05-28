# VECRM Active Pendencies

Last updated: 2026-05-27 (S34 closed)
0 active P0 blockers. 0 active P1 blockers.

S34 deliverables: 5 PRs merged (vecrm #47, #48, #49, #50; vecrm-portal #34).
PD-S30-LEAD-FOLLOWUP Phase 2 shipped end-to-end. PD-S33-NEXT-IMAGE-PRUNE
closed. See `S34-CLOSE.md`.

---

## Closed this session (S34)

| Pendency | Priority | Closing PR | Closing date |
|---|---|---|---|
| **PD-S30-LEAD-FOLLOWUP Phase 2 (backend)** | **P1** | **vecrm #48/#49/#50** | **2026-05-27** |
| **PD-S30-LEAD-FOLLOWUP Phase 2 (portal)** | **P1** | **vecrm-portal #34** | **2026-05-27** |
| **PD-S33-NEXT-IMAGE-PRUNE** | **P1** | **vecrm #47** | **2026-05-27** |

---

## Active (P1)

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
**Recommended order:** Strong S35 #1 candidate. Was the S34 #2 contingency;
never reached (Phase 2 + portal consumed the session).

### PD-S29-WEEKLY-MEETING-REPORT (P1)
**Banked:** S29.
**Scope:** Friday EOW Outlook digest of leads, vouchers, inquiries piped to
Vinay + Ajay. Probably a scheduled Frappe job + email pipeline.
**Dependency:** PD-S29-VEMIO-EMAIL-PIPELINE.

### PD-S29-VEMIO-EMAIL-PIPELINE (P1)
**Banked:** S29. **Larger build, multi-session.**
**Scope:** Outlook integration via Graph API or SMTP relay through vemio.
Blocks PD-S29-WEEKLY-MEETING-REPORT and PD-S30 Phase 3 email reminders.

---

## Active (P2)

### PD-S34-NEXT-LINT-CLEANUP (P2)
**Banked:** S34.
**Scope:** vecrm-portal main has 17 pre-existing
`react-hooks/set-state-in-effect` lint errors. PR #34 suppressed 3 (in
touched files: MobileNav SSR mount flag, MobileNav route-change dismiss,
Lead detail lead-reset on route change) with documented block-scoped
`eslint-disable` blocks. Proper refactor: convert effect bodies to
subscription pattern or derive-from-render.
**Caveat:** the page.tsx lead-reset site has a visible-UX implication — the
synchronous `setLead(null)` flashes the skeleton on route change between
lead detail pages. A proper subscription-pattern refactor would remove that
flash (lead stays visible until new fetch settles). Needs operator sign-off
on that behavior change before refactoring that specific site.
**Estimated:** ~1h sweep.

### PD-S33-NEXT-TEST-INFRA (P2)
**Banked:** S33.
**Scope:** Install vitest in vecrm-portal. Author first test for
`lib/errors.ts` — specifically the `voucher_submit` ErrorContext branch added
in PR #31. Establishes pattern for unit testing pure-function lib modules.
**Note:** the throwaway `scripts/smoke_phase2.py` (S34, now gitignored) is
NOT this — it's a one-off HTTP smoke harness with hardcoded test data, not a
reusable unit test. This pendency is the real test infra.
**Estimated:** ~2h.

### PD-S33-NEXT-DEPLOY-TAG-DISCIPLINE (P2)
**Banked:** S33.
**Scope:** Add verifiable rollback-tag step to canonical 8-step deploy
procedure. Close-doc convention must require `docker images grep` output
showing the tag exists, not prose claiming it does. Per OBS-S33-B (S32 close
claimed tags existed; verification at S33 entry found only one).
**S34 note:** PR #47's `vps-prune.sh` ("keep latest 3 session-tagged rollback
images") is adjacent to this — the prune policy and the tag-verification
discipline should be cross-referenced when this is authored.

### PD-S33-NEXT-LEAD-DATA-WIPE (P2)
**Banked:** S33.
**Scope:** Truncate `tabVECRM Lead` + audit child rows before production
cutover. Existing leads are demo data per Q-13 / Tension 5 of
Q-LEAD-FOLLOWUP-LOCK.
**S34 note:** now also truncate `tabVECRM Lead Touchpoint` (Phase 2 doctype)
in the same wipe — touchpoints FK to leads.
**Estimated:** ~30min. Coordinate with first real-data import.

### PD-S33-NEXT-VECRM-LOCK-FRAPPE-FILTER-PATTERNS (P2)
**Banked:** S33. **Compounded by OBS-S34-A.**
**Scope:** Author
`docs/architectural-locks/VECRM-LOCK-FRAPPE-FILTER-PATTERNS.md` documenting:
- OBS-S33-U: Frappe v15 nullable-date comparison operators (`<`, `>`, `=`,
  `between`) do NOT enforce SQL-standard NULL semantics. Always pair with
  `["field", "is", "set"]` predicate.
- `is set` / `is not set` Frappe filter operators vs SQL `IS NULL`.
- `between` filter array shape: `["field", "between", [low, high]]`.
- `like` filter wildcard `%` is literal, not regex.
- `in` / `not in` operators take array as third element.
- **OBS-S34-A (NEW): Frappe v16 ORM aggregate syntax.** `frappe.db.get_value`
  rejects BOTH raw-string (`"MAX(col)"`) AND dict (`{"MAX": "col"}`) fieldname
  for SQL functions. Canonical idiom = `frappe.db.sql` with parameterized raw
  SQL. (9 existing call sites in patches confirm this is the house pattern.)
**Estimated:** ~1h. Convert from OBS notes into ratified lock document.

---

## Active (P3)

### PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT (P3)
**Banked:** S33.
**Scope:** Cross-cutting Sales Head write-auth refactor across all lead-write
BFFs if operationally required. Q-LEAD-FOLLOWUP-11 was revised mid-S33 from
(c) lead_owner+Sales Head+Admin to (a) creator+Admin because the original
model didn't match other lead-write BFF auth (close, convert, attachments,
followup, touchpoints all use `canReadLead`). If business requires Sales Head
to write across the team's leads, this would be the refactor entry point.
**Touches:** `lib/scoping.ts` `canReadLead` + all `/api/leads/[name]/*` POST
routes (now including `/touchpoints`).
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

- **Worker image audit — RESOLVED (OBS-S34-M).** OBS-S33-J closed as
  by-design. VECRM app has zero hooks.py registrations (all
  doc_events/scheduler_events commented out); workers run no VECRM Python in
  background loops. Backend-only γ-path rebuilds remain operationally correct.
  No worker rebuild needed.
- `vemio-freeradius` healthcheck misconfigured (`radclient: Nothing to
  send`). Benign, known issue. Tracked in vemio side, not VECRM.
- **`/tmp/smoke_phase2.py` on VPS (root-owned)** — S34 left a copy in
  container `/home/frappe/frappe-bench/apps/vecrm/vecrm/smoke_phase2.py` and
  possibly `/tmp`. Non-blocking cleanup; resets on container rebuild anyway.
