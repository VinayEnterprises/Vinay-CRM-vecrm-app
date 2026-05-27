# PD-S30-LEAD-FOLLOWUP — Operator-Locked Spec

**Ratified:** 2026-05-27 (S33)
**Operator:** Ajay Salvi
**Pendency:** PD-S30-LEAD-FOLLOWUP-WORKFLOW (P1)
**Status:** Spec locked, Phase 1 dispatch pending

---

## Production gating

**(β) — Deploy after Phase 1+2 to production.** Phase 1 ships to main and goes live in portal UI. Phase 2 ships to main and goes live. Phase 3 (email reminders + status enum expansion) is post-production enhancement, NOT blocking production cutover. Phase 3 itself depends on PD-S29-VEMIO-EMAIL-PIPELINE delivery.

Implications:
- No long-lived feature branches; standard L13 branch-first/squash-merge per phase.
- After Phase 2 merge, the lead follow-up workflow is operationally complete enough for sales reps to use daily. Reminders via email are nice-to-have, not load-bearing.

---

## Operator decision lock

| Q | Decision | Rationale / scope |
|---|---|---|
| Q-LEAD-FOLLOWUP-1 | (d) Unified workflow: reminders + touchpoints + intermediate states | Three sub-problems share data model, phase them rather than separate them |
| Q-LEAD-FOLLOWUP-2 | (c) Sales reps drive data, admin sees aggregate | Reps update; admin reads pipeline view |
| Q-LEAD-FOLLOWUP-3 | (b) Expand enum: add Contacted / Quoted / Negotiating | **Phase 2 work, not Phase 1** |
| Q-LEAD-FOLLOWUP-4 | Phase 1: `next_followup_date` only. Phase 2: derive `last_contact_date` + `followup_count` from touchpoint doctype | New fields phased with their feeders |
| Q-LEAD-FOLLOWUP-5 | (a) Follow-up assignee = `lead_owner` | Single ownership field; no delegation split |
| Q-LEAD-FOLLOWUP-6 | (a) Touchpoint doctype, standalone (not child table) | **Phase 2 work.** Matches `vecrm_inquiry_audit_log` / `vecrm_voucher_audit_log` standalone-doctype pattern |
| Q-LEAD-FOLLOWUP-7 | (b) Email + portal in-app — split across phases | Phase 1 (filter chips), Phase 2 (nav badge), Phase 3 (email) |
| Q-LEAD-FOLLOWUP-8 | (a) Activate `scheduler_events` — **Phase 3 only** | No cron in Phase 1/2 |
| Q-LEAD-FOLLOWUP-9 | (b) Dedicated "log a follow-up" modal on Lead detail | Verb-matched UX |
| Q-LEAD-FOLLOWUP-10 | (a) Filter chips on existing `/leads` list page | Due today / Due this week / Overdue / No follow-up scheduled |
| Q-LEAD-FOLLOWUP-11 | **(a) Lead creator (creating_employee) + Admin can write. REVISED S33 mid-session.** | Original Q-11=c (lead_owner + Sales Head + Admin) revised after `canReadLead` audit revealed: (i) every existing lead-write BFF (close, convert, attach, single-read) uses `canReadLead` which only allows creating_employee + Admin; (ii) Sales Head is not yet a distinct write-permission category in `lib/scoping.ts`; (iii) backend lead methods (close_lead, convert_lead_to_inquiry) have NO permission gates beyond doctype perms — portal BFF is the sole enforcement. Q-11=c was a rapid-fire analogy to the voucher on-behalf pattern; vouchers and leads are not symmetric. If Sales Head cross-rep write access becomes a real operational need, see PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT (P3). |
| Q-LEAD-FOLLOWUP-12 | (a) No follow-up actions on terminal leads | Converted / Closed-Won / Closed-Lost are read-only for follow-up purposes |
| Q-LEAD-FOLLOWUP-13 | (a) Existing leads NULL — moot, demo data wipes pre-production | See PD-S33-NEXT-LEAD-DATA-WIPE |
| Q-LEAD-FOLLOWUP-14 | (a) Phase 1 (field+filter+modal) → Phase 2 (touchpoints+badge) → Phase 3 (reminders+enum+email) | Smallest operational win first |

## Tension resolutions (S33 follow-up rounds)

| Tension | Resolution |
|---|---|
| T-1 (Q-3 phasing) | Enum expansion locked at (b) but deferred to Phase 2 |
| T-2 (Phase 1 field set) | Phase 1 adds exactly ONE new field: `next_followup_date` (Date, optional) |
| T-3a (Phase 1 reminder shape) | (ii) In-app nav badge only — but badge moves to Phase 2 since it depends on touchpoint-derived "due today" rendering; Phase 1 reminders = filter chips only |
| T-3b (Phase 3 email co-build) | (i) Block on PD-S29-VEMIO-EMAIL-PIPELINE separate delivery |
| T-3c (Email-pipeline priority) | (i) Don't bump VEMIO-EMAIL-PIPELINE priority now |
| T-4a (Phase 1 scheduler) | (i) No scheduler in Phase 1. On-demand queries only |
| T-4b (Q-8 scope) | Q-8=(a) applies to Phase 3 not Phase 1 |
| T-5 (existing leads) | Confirmed demo data; truncate before production |

---

## Phase 1 deliverable scope

**Backend (vecrm):**
- Doctype: 1 new field on VECRM Lead — `next_followup_date` (Date, optional, no default)
- Migration: `vecrm/patches/` entry for the field add + `patches.txt` registration
- API: 1 new whitelisted method — `vecrm.api.update_lead_followup(lead_name, next_followup_date, notes_optional)`
  - Permission gate: caller must be lead_owner OR Sales Head OR Admin (Q-11=c)
  - Terminal-state guard: reject if `status in (Converted, Closed-Won, Closed-Lost)` (Q-12=a)
  - Logs transition via existing `reassignment_history` pattern + Assignment Ledger Entry
  - Returns updated lead summary
- Controller: extend `before_save` to log `next_followup_date` changes the same way it logs status/owner changes
- No new doctypes
- No scheduler activation
- No enum changes

**Portal (vecrm-portal):**
- New modal component on `/leads/[name]`: "Log follow-up" — captures next_followup_date + optional notes textarea, calls update_lead_followup BFF
- New BFF route: `app/api/leads/[name]/followup/route.ts` (POST)
- New filter chips on `/leads` list page: "Due today" / "Due this week" / "Overdue" / "No follow-up scheduled"
- Filter logic implemented at BFF query layer (passed to backend list params), not client-side
- No nav badge (deferred to Phase 2 per T-3a clarification)

**Smoke matrix:** SAM-33-2-{a..h} — to be authored in Phase 1 dispatch.

---

## Phase 2 deliverable scope

**Backend (vecrm):**
- New doctype: `VECRM Lead Touchpoint` (standalone, not child table)
  - Fields: lead (Link → VECRM Lead, reqd), touchpoint_type (Select: Call/Email/Meeting/Other), touchpoint_date (Date, reqd, default today), summary (Small Text), actor_employee (Link → VECRM Employee, read_only, set server-side)
- 3 new API methods: `create_touchpoint`, `list_touchpoints_for_lead`, derived-fields read (last_contact_date, followup_count)
- Lead controller: derive `last_contact_date` + `followup_count` from touchpoints on save / via virtual field

**Portal (vecrm-portal):**
- Touchpoint log section on `/leads/[name]` — table of past touchpoints + "Log touchpoint" button
- Nav badge: "X due today" — count from `next_followup_date <= today AND status NOT IN terminal` for current rep

---

## Phase 3 deliverable scope (POST-PRODUCTION)

**Backend (vecrm):**
- Status enum expansion via migration: add Contacted / Quoted / Negotiating values to `tabVECRM Lead.status` select options (backward-compatible — only adding values)
- Activate `scheduler_events` in `hooks.py` — daily job at configurable hour
- Email reminder job: query leads where `next_followup_date == today AND status NOT IN terminal`, send templated email to lead_owner via VEMIO-EMAIL-PIPELINE

**Portal (vecrm-portal):**
- Pipeline view by status (kanban or grouped list)
- Email-template preview / send-test UI for admin

**Blocks on:** PD-S29-VEMIO-EMAIL-PIPELINE delivery.

---

## Out of scope (all phases)

- Calendar integration (Outlook/Google) for follow-up appointments
- AI/ML-driven priority scoring or next-best-action recommendations
- Mobile push notifications
- SMS reminders
- Aggregate analytics dashboards beyond simple "due today" filter (a separate reporting initiative if needed)

---

## Mid-session revisions

### S33 (2026-05-27) — Q-11 relaxed from (c) to (a)

After Phase 1 pre-author recon audited all lead-write BFFs (`/api/leads/[name]/{close,convert,attachments,/}/route.ts`) and confirmed all use `canReadLead(creating_employee)` — i.e. (a) creator + Admin — with no Sales Head precedent in `lib/scoping.ts`, Q-11 revised from (c) to (a) to match codebase precedent. Sales Head write access is not removed conceptually; it is parked as a future cross-cutting refactor (PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT) to be applied consistently across ALL lead-write surfaces, not as a Phase 1 carve-out.

Phase 1 reuses `canReadLead` for followup authorization. No new helper introduced. No new code paths for Sales Head detection.