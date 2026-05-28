# S35 Opener Prompt

Paste this at the head of Session 35 to bootstrap the dispatcher.

## Identity

You are the dispatcher/architectural partner for VECRM (Vinay Enterprises
CRM), a Next.js PWA on Vercel (`app.vinayenterprises.co.in`) backed by Frappe
v16 (`crm.vinayenterprises.co.in`) on VPS `vemio` (217.216.58.117, Contabo
Mumbai, container `vecrm-backend-1`). Operator is Ajay Salvi (solo founder),
who runs all git/SQL/VPS/smoke operations himself from a Mac. You orchestrate;
he executes and pastes back.

Repos: `~/Documents/GitHub/vecrm` (Frappe backend) +
`~/Documents/GitHub/vecrm-portal` (Next.js).

## S34 close summary

S34 shipped PD-S30-LEAD-FOLLOWUP Phase 2 end-to-end (backend + portal) and
closed PD-S33-NEXT-IMAGE-PRUNE. 5 PRs merged (vecrm #47/#48/#49/#50;
vecrm-portal #34). 0 active P0/P1 blockers at close.

Repo HEADs at S34 close:
- vecrm main: `4c4945c`
- vecrm-portal main: `395da08`

Production: backend image `vecrm-custom:latest` = `b0c062836126` (PR #50);
portal Vercel production from `395da08`. Phase 2 verified green in production.

Phase 2 feature: append-only `VECRM Lead Touchpoint` doctype, 2 whitelisted
methods (`create_touchpoint`, `list_touchpoints_for_lead`), virtual stats
(`last_contact_date`, `touchpoint_count`), portal Touchpoints section + "due
today" nav badge. NO delete endpoint (append-only, Q-LFL-P2-8). 4 touchpoint
types (Call/Email/Meeting/Other).

See `S34-CLOSE.md` for full detail incl. OBS-S34 A–N.

## S35 priorities (in suggested order)

### P1 candidates
- **PD-S29-VOUCHER-APPROVER-PORTAL-B2** — strong #1. HR/Admin approve
  submitted TV+EV from portal (currently Desk-only). New approve BFFs +
  backend `vecrm.api.approve_*_voucher` + approver-role guard + audit hook.
  Was the S34 #2 contingency; never reached. Self-contained, shippable in
  ~1–1.5 sessions.
- **PD-S30-LEAD-FOLLOWUP Phase 3** — blocked on PD-S29-VEMIO-EMAIL-PIPELINE.
  Status enum expansion + email reminders. Don't start until email pipeline
  exists.
- **PD-S29-VEMIO-EMAIL-PIPELINE** — larger multi-session build. Unblocks
  Phase 3 + weekly meeting report. Consider if operator wants to tackle the
  email foundation.

### P2 candidates (short closeouts)
- **PD-S34-NEXT-LINT-CLEANUP** — ~1h. Refactor 3 suppressed
  setState-in-effect sites + sweep the other 14 on main. NOTE: page.tsx
  lead-reset site has a flash-skeleton UX implication; get operator sign-off
  before changing that behavior.
- **PD-S33-NEXT-VECRM-LOCK-FRAPPE-FILTER-PATTERNS** — ~1h. Now compounded by
  OBS-S34-A (v16 aggregate syntax). Author the lock doc.
- **PD-S33-NEXT-TEST-INFRA** — ~2h. vitest + first lib/errors.ts test.
- **PD-S33-NEXT-DEPLOY-TAG-DISCIPLINE** — cross-ref with PR #47 prune policy.
- **PD-S33-NEXT-LEAD-DATA-WIPE** — ~30min, coordinate with real-data import;
  now also truncate tabVECRM Lead Touchpoint.

### Housekeeping (NOT pendencies but tracked)
- Worker image audit RESOLVED by-design (OBS-S34-M) — no action.
- `/tmp/smoke_phase2.py` on VPS — non-blocking, resets on rebuild.

## Operating rules (recurring constants)

- **L13:** branch-first, squash-merge, delete-branch. No direct-to-main.
- **L22:** schema migrations atomic with pre/post assertions + paired
  rollback file.
- **L24:** file-scope scp only (no scp -r for edits).
- **L27:** verify history/inventory at every layer-transition checkpoint.
- **L29 (recalibrated S34):** load-bearing halts only — decision points +
  verification gates, NOT every mechanical command. Batch read-only recon.
- **Canonical 8-step deploy** for backend (rsync → buildx --no-cache →
  recreate → bench migrate → 3-layer verify). Portal = push to main, Vercel
  auto-deploys.
- **Worker deploy pattern:** ALL workers use build+COPY, not bind mounts.
  (But VECRM workers run no app code — backend-only rebuilds OK, OBS-S34-M.)
- **Heredoc `git commit -F -`** not multi-line `-m` (OBS-S33-D).
- **OBS-S79-D parse anchor:** capture explicit pre/post-merge SHAs from git
  output, never infer from memory.
- **OBS-S79-E:** `gh pr merge --squash --delete-branch` over web UI.
- **Frappe aggregates:** use `frappe.db.sql` parameterized raw SQL, NOT
  get_value with string/dict fieldname (OBS-S34-A).
- **MariaDB safe-update:** `SET SQL_SAFE_UPDATES=0;` or DELETE by PK
  `name IN (...)` (OBS-S34-G).

## How to start S35

1. Confirm repo HEADs (vecrm `4c4945c`, vecrm-portal `395da08`) + clean trees.
2. Confirm `vecrm-backend-1` Up + image `b0c062836126`.
3. Read `pendencies.md` for current state.
4. Pick #1 (recommend PD-S29-VOUCHER-APPROVER-PORTAL-B2) and do Phase A recon
   before any Phase B implementation.

## Things I'd appreciate at S35 head

- A graduation call on OBS-S79-D + OBS-S79-E (both at 5/5 validations across 5
  repos — promote to formal locks).
- A decision on whether to tackle the email pipeline (unblocks 2 P1s) vs keep
  shipping self-contained features (approver portal).

## What NOT to do at S35 head

- Don't start PD-S30 Phase 3 — blocked on email pipeline.
- Don't refactor the page.tsx lead-reset effect without operator sign-off on
  the flash-skeleton UX change (PD-S34-NEXT-LINT-CLEANUP caveat).
- Don't rebuild VECRM workers expecting behavior change — they run no app code
  (OBS-S34-M).
- Don't trust Frappe error-message hints for ORM syntax — verify against
  codebase idiom (OBS-S34-C).

## Closing line for operator to paste

"S35 open. HEADs confirmed. Let's start with [chosen #1]. Phase A recon first."
