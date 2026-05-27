# Q-LEAD-FOLLOWUP — Phase 2 Addendum

**Ratified:** 2026-05-27 (S34)
**Operator:** Ajay Salvi
**Parent spec:** `docs/dispatches/PD-S30-LEAD-FOLLOWUP-LOCK.md` (S33)
**Parent ratification commit:** vecrm `c9b8bec` + Q-11 revision at `339fe92`
**Status:** Phase 2 spec locked, build dispatch pending

---

## Purpose

The S33 parent lock ratified Phase 2 conceptually (Q-LEAD-FOLLOWUP-4, Q-LEAD-FOLLOWUP-6, deliverable scope block) but left implementation-level questions underspecified that surfaced during S34 head recon. This addendum captures the 5 Phase 2-specific Qs and reconciles one spec-vs-pendency discrepancy.

This is an addendum, not a replacement. The parent lock remains authoritative for all questions not addressed here.

---

## Phase 2 spec lock (Q-LFL-P2-* items)

| Q | Decision | Rationale |
|---|---|---|
| Q-LFL-P2-2 | (a) Delete-touchpoint auth = `canReadLead` on parent lead (creator + Admin) | Matches Q-11 codebase precedent. Touchpoint `actor_employee` is informational, not an auth axis. Note: Q-LFL-P2-8/9 below removes the delete method entirely, making this Q moot in practice — locked here for future reference if the decision is ever revisited. |
| Q-LFL-P2-3 | (b) `last_contact_date` + `followup_count` = **virtual fields** (read-time computed in controller) | Frappe-idiomatic. Avoids hook complexity. Avoids denormalization-sync bugs. Performance acceptable at current and projected data volume. |
| Q-LFL-P2-6 | (c) Touchpoint and `next_followup_date` are **independent** | Logging a touchpoint does NOT auto-clear or auto-set `next_followup_date`. Cleanest mental model. Coupling them at this stage bakes in workflow assumptions. If sales reps later request combined UX, add as a Phase 2.1 enhancement. |
| Q-LFL-P2-8 | (d) **No delete endpoint** — touchpoints are append-only | Matches voucher / inquiry append-only audit pattern. If a touchpoint is logged in error, the rep adds a corrective touchpoint with explanatory `summary`. Simpler, more honest audit trail. |
| Q-LFL-P2-9 | Spec lock wins over pendency tracker | `pendencies.md` listed 3 methods including `delete_touchpoint`; parent spec body lists only `create_touchpoint`, `list_touchpoints_for_lead`, derived-fields read. Spec is authoritative. Pendency to be updated at S34 close. |
| Q-LFL-P2-10 | (a) VECRM Employee link `on_delete = Restrict` | Frappe default. Safest. Production has never deleted a VECRM Employee anyway. |

---

## Convention-default items (not Q-locked, recorded for clarity)

These items did not require operator ratification but are recorded so the Phase 2 dispatch has explicit defaults:

- **Touchpoint UI sort order:** Descending by `touchpoint_date` (newest first), standard activity-feed convention.
- **`summary` field:** Frappe Small Text, optional (no `reqd` flag). Per parent spec.
- **Nav badge count:** `next_followup_date <= today AND status NOT IN terminal` for current rep. Uses Phase 1 column, NOT touchpoint data. Per parent spec.

---

## Revised Phase 2 deliverable scope

Replaces the "Phase 2 deliverable scope" block in the parent lock with the following clarifications:

### Backend (vecrm)

- New doctype: `VECRM Lead Touchpoint` (standalone)
  - Fields per parent spec: `lead` (Link → VECRM Lead, reqd, **on_delete=Restrict on lead side**), `touchpoint_type` (Select: Call/Email/Meeting/Other), `touchpoint_date` (Date, reqd, default today), `summary` (Small Text, optional), `actor_employee` (Link → VECRM Employee, read_only, set server-side, **on_delete=Restrict**)
- **2 new whitelisted methods** (revised from 3 per Q-LFL-P2-9):
  - `vecrm.api.create_touchpoint(lead_name, touchpoint_type, touchpoint_date, summary_optional)`
  - `vecrm.api.list_touchpoints_for_lead(lead_name)`
- Permission gate on both methods: `canReadLead` precedent — caller must be lead creator OR Admin
- Terminal-state behavior on `create_touchpoint`: TBD in Phase 2 dispatch recon — proposal: allow touchpoints on terminal leads (post-conversion follow-up is real; reps may log a post-close call), but defer final answer to dispatch
- Lead controller: derive `last_contact_date` + `followup_count` as **virtual fields** (read-time, computed from touchpoint query)
- No new doc_events in hooks.py
- No new scheduler_events in hooks.py
- Schema migration: v1_7 patch — create `tabVECRM Lead Touchpoint` table

### Portal (vecrm-portal)

- Touchpoint log section on `/leads/[name]`:
  - Chronological list of past touchpoints (descending date)
  - "Log touchpoint" button → modal with type select + date picker + summary textarea
  - Calls new BFF route `app/api/leads/[name]/touchpoints/route.ts` (GET + POST)
  - **No delete UI** per Q-LFL-P2-8
- Nav badge: "X due today" — count from new BFF endpoint or extension of existing `/api/leads` list endpoint with `followup_filter=due_today` (reuse Phase 1 plumbing)
- Touchpoint UI visible on all leads regardless of status (consistent with Q-LFL-P2-6 independence — touchpoint logging may be permitted on terminal leads pending dispatch recon)

---

## Out of scope additions (all phases)

Append to parent lock's out-of-scope list:

- Touchpoint deletion (append-only by design per Q-LFL-P2-8)
- Touchpoint edit (out by extension — append-only)
- Bulk touchpoint operations
- Touchpoint type-specific custom fields (e.g. "call duration" for Call type) — all touchpoint types share the same field set in Phase 2; type-specific extensions are Phase 3+ if requested

---

## Open items for Phase 2 dispatch recon (NOT spec-locked, dispatch-time decisions)

These are implementation details, not spec questions. Dispatch recon will resolve them:

- Terminal-state behavior on `create_touchpoint` (allow vs reject) — see Backend deliverable above
- Whether `actor_employee` is set from session user (Frappe `frappe.session.user` → VECRM Employee lookup) or from an explicit param — Frappe convention is session-derived
- Pagination on `list_touchpoints_for_lead` if a lead accumulates >50 touchpoints — defer until needed
- Exact JSON shape of the touchpoint list response — match `reassignment_history` pattern from Phase 1

---

## Production gating

Unchanged from parent: **(β) Phase 1+2 deploy as a unit**. Phase 2 ships to main, goes live in portal UI. No long-lived feature branches. Standard L13 branch-first / squash-merge per PR. After Phase 2 merge, lead follow-up workflow is operationally complete enough for daily sales-rep use.

---

## Revisions to this addendum

(None yet — newly ratified at S34 head.)
