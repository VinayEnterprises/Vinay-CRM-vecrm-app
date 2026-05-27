# S34 Opener Prompt

**Pasted at the start of S34 to give the dispatcher full continuity from S33 close.**

---

## Identity

I am Ajay Salvi, solo operator of VECRM (Vinay Enterprises CRM/field-ops PWA).
Working from `~/Documents/GitHub/vecrm` (Frappe backend) and
`~/Documents/GitHub/vecrm-portal` (Next.js portal).

VPS: `vemio` (alias for `217.216.58.117`, Contabo Mumbai). Frappe v15 +
MariaDB 11.8 + Python 3.14. Backend site:
`crm.vinayenterprises.co.in`. Portal: `app.vinayenterprises.co.in`.

I work in numbered AI-pair sessions with strict halt-on-drift cadence,
branch-first commits, atomic PRs, 3-layer code verification post-deploy.

---

## S33 close summary

**Outcome:** Clean close. 0 active P0/P1 blockers. PD-S30-LEAD-FOLLOWUP
Phase 1 shipped end-to-end across 4 PRs.

**PRs merged in S33:**
- vecrm #46 (`d35d173`) — PD-S30 Phase 1 backend: `update_lead_followup`
  whitelisted method, `next_followup_date` Date column, audit row, terminal-
  state guard, date-format validation. Schema migration v1_6 executed.
- vecrm-portal #31 (`1f0db96`) — PD-S32 voucher submit 403 differentiation.
- vecrm-portal #32 (`59af290`) — PD-S30 Phase 1 portal: BFF route + Lead
  detail inline modal + 4 filter chips + list BFF extension.
- vecrm-portal #33 (`f718b5c`) — same-session hotfix: Overdue filter must
  exclude NULL `next_followup_date` (Frappe v15 NULL semantics quirk —
  OBS-S33-U).

**Production state at S33 close:**
- vecrm-backend-1: Up, image `vecrm-custom:latest` = `929d6e3b92d8` built
  2026-05-27 09:59 IST.
- vecrm-portal: production deployed to Vercel at `f718b5c`.
- Schema: `tabVECRM Lead.next_followup_date` Date NULL exists, migration
  v1_6 in Patch Log (`dp2q64lfus`).
- Rollback tag on VPS: `vecrm-custom:s33-pre-pr-followup-phase-1-rollback`
  (image `687212415b67`).
- VPS disk: 47% used / 78GB free (post S33 disk-pressure recovery, ~58GB
  freed across 3 tranches).

**Smoke verified:** Backend SM-1 through SM-6 (6/6), backend regression
R1–R6 (6/6), portal SAM-33-3 a–j (10/10), PR #33 hotfix verified in
browser.

---

## S34 priorities (in suggested order)

### P1 candidates

**1. PD-S30-LEAD-FOLLOWUP Phase 2** (largest piece)
- New `VECRM Lead Touchpoint` standalone doctype with type enum + notes +
  lead link
- 3 whitelisted methods (`log_touchpoint`, `list_touchpoints`,
  `delete_touchpoint`)
- Lead controller derives `last_contact_date` + `touchpoint_count`
- Portal: touchpoint UI on Lead detail page + nav badge "X due today"
- Estimated: 1–1.5 sessions

**2. PD-S29-VOUCHER-APPROVER-PORTAL-B2**
- HR/Admin approve TV+EV from portal (currently Desk-only)
- Mirror detail pages, add Approve/Reject + notes
- New backend approve endpoints with approver-role guard

**3. PD-S29-VEMIO-EMAIL-PIPELINE**
- Blocks PD-S30 Phase 3 + PD-S29-WEEKLY-MEETING-REPORT
- Multi-session build

### P2 candidates (any of these are short closeouts)

- PD-S33-NEXT-IMAGE-PRUNE (P1 actually — disk policy script + cron, ~1h)
- PD-S33-NEXT-VECRM-LOCK-FRAPPE-FILTER-PATTERNS (~1h, doc-only)
- PD-S33-NEXT-TEST-INFRA (~2h, infrastructure)
- PD-S33-NEXT-DEPLOY-TAG-DISCIPLINE (~30min, convention update)
- PD-S30-NEXT-LEAD-LIST-CLOSED-WON-FILTER (~15min, one-line addition)

### Housekeeping (NOT pendencies but tracked)

- **Worker image audit (OBS-S33-J).** vecrm-frontend-1 + 5 workers still
  pinned to `vecrm-custom:s22-pre-build` (`21bb1afd017e`). Determine
  by-design vs drift. Rebuild if drift.

---

## Operating rules (recurring constants)

These do not need to be re-explained mid-session:

1. **Halt cadence is structural.** Dispatcher writes "Halt" with specific
   paste-back request. Operator runs the step, pastes output, waits for
   dispatcher confirmation before next step. Chaining multiple halts into
   one paste is the failure mode flagged 6× in S33 (lock candidate L29).

2. **Recon-before-write.** Every new file or non-trivial edit preceded by
   `view` or `grep` to confirm actual current state, not assumed state.

3. **3-layer deploy verification.** Per VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE:
   Mac source → vendor copy → live container all 3 must be consistent
   post-deploy. Grep assertions + AST parse + schema check.

4. **Branch-first, squash-merge, delete-branch.** No direct-to-main when a
   feature branch + PR is available. `gh pr merge <N> --squash
   --delete-branch`. Tag rollback before deploy.

5. **Atomic PRs.** One pendency per PR. PD-prefixed commit titles.

6. **Heredoc for multi-line commits.** `git commit -F - <<'EOF' ... EOF` —
   not multi-line `-m` (zsh folds newlines into spaces per OBS-S32-W).

7. **Rollback tags use `vecrm-custom:<tag>` form** — not
   `<descriptive-tag>:latest` (S32 produced 4 wrong-convention tags per
   OBS-S33-O).

8. **Frappe nullable-date filters must pair with `is set` predicate** —
   `<`, `>`, `=`, `between` don't enforce SQL NULL semantics in Frappe v15
   per OBS-S33-U.

---

## How to start S34

1. Open this prompt. Acknowledge identity + S33 context.
2. **Read `docs/handovers/S33-CLOSE.md` end-to-end** — full state including
   OBS bankings A–U and lock promotion recommendations.
3. **Read `docs/handovers/pendencies.md`** — full active list including new
   P1/P2/P3 pendencies opened in S33.
4. **Operator names the S34 #1 work item** — typically the highest-priority
   active P1 (PD-S30 Phase 2 is the natural follow-on).
5. **Dispatcher proposes a recon plan** — what to `view`, what to `grep`,
   what spec questions to lock before any code touches the repo.
6. **Lock spec questions FIRST** (if any) via Q-document pattern. Then
   build.

---

## Things I'd appreciate at S34 head

- Acknowledge the L29 (halt-chain-skip) lock promotion candidate
  explicitly. If operator opts in, codify in
  `docs/architectural-locks/VECRM-LOCK-HALT-CADENCE.md` early in S34 before
  any sprint work begins.
- Decide on PD-S33-NEXT-IMAGE-PRUNE priority. Operator preference: P1 or
  P2?
- Confirm "Phase 2 of PD-S30" is the S34 #1 selection, or pivot to
  PD-S29-VOUCHER-APPROVER-PORTAL-B2 if business priorities have shifted
  overnight.

---

## What NOT to do at S34 head

- Don't re-prove S33 state. The close doc is authoritative.
- Don't rebuild workers without operator decision (OBS-S33-J is pending).
- Don't run schema migrations without 3-layer verification afterward
  (VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE applies to all deploys, not just
  S33's).
- Don't pre-author multiple artifact dispatches in advance. Per-PR atomic
  dispatch with halts is the model.

---

## Closing line for operator to paste

> S33 closed clean. Phase 1 shipped end-to-end (vecrm #46 + vecrm-portal
> #31, #32, #33). 0 active P0/P1. Read S33-CLOSE.md and pendencies.md, then
> let me know what's the S34 priority and I'll propose the recon plan.
