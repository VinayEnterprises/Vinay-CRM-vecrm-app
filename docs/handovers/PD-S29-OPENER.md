# PD-S29-OPENER

**For:** S29 dispatcher (Claude chat, future session)
**Authored:** 2026-05-24 (S28 close)

---

## S29 starts here

S28 closed with the end-to-end password/PIN reset flow live in production, security-cleared via PR #25 audit (13/13 PASS, 6/6 smoke PASS). The next user-visible feature wave will hit Lead/Inquiry surfaces, which need per-rep scoping before broader rep onboarding. S29 should:

1. Do a brief cold-check (8 gates from `docs/operating-patterns/cold-check-template.md`)
2. Decide S29 scope (see §3 below)
3. Execute the chosen workstream(s)
4. Close S29 at a sensible breakpoint

---

## §1 — Production state at S28 close

| Property | Value |
|---|---|
| vecrm `main` HEAD | `955f7ae` (PR #25 audit merge) — may have advanced past S28 close docs commit; verify |
| vecrm-portal `main` HEAD | `8f7c1b7` (PR #14 PORTAL-UI) |
| Production image | `vecrm-custom:latest` = post-PR #24 deploy (sha post-`4eca723e3803`) |
| Site | `crm.vinayenterprises.co.in` HTTP 200 |
| Portal | `app.vinayenterprises.co.in` Vercel deploy `6Tm6fNvfa` Ready |
| Doctype `VECRM Auth Reset Token` | First production use this session; consumed-token rows remain for audit forensics |
| Rollback anchor (image) | `vecrm-custom:s28-pre-pr22-rollback` |
| Rollback anchor (git tag, post-merge of S28 close PR) | `s28-close` |

---

## §2 — What's done and what's pending

**Done in S28:**

- ✅ Full reset flow: 6 sub-PDs across PR #11, #12, #13, #14 (vecrm-portal) + PR #22, #23, #24, #25 (vecrm)
- ✅ Security audit (PR #25) with 13/13 audit items + 6/6 smoke paths PASS, APPROVE-confirmed
- ✅ 1 new architectural lock promoted: VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY
- ✅ 5 banked observations (OBS-S28-F/I/N/Q/T/U/V documented + OBS-S28-R deferred)

**Pending into S29 (in priority order):**

- ⏳ **PD-S28-LEAD-SCOPING-CUTOVER** — P1, ~4.5 hrs. Per-rep scoping on Lead BFFs. Substrate (`creating_employee` column) shipped PR #20 (S27).
- ⏳ **S28 follow-up sweep** — 5 P2/P3 items from PR #14 + PR #25:
  - PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE (P2, 30-60 min)
  - PD-S28-AUTH-PHONE-PREFIX-LOCK (P2, 1-1.5 hrs)
  - PD-S28-ADMIN-PIN-SET-UI (P2, 2-3 hrs)
  - PD-S28-LOGINFORM-PIN-MINLENGTH (P3, 30 min)
  - PD-S28-LOGIN-ERROR-UX (P3, 1-1.5 hrs)
  - PD-S29-CANDIDATE-RESET-RATELIMIT-SHARED (P3, 1-1.5 hrs)
  - Combined estimate: ~6-8 hrs across 6 small PRs
- ⏳ **PD-S28-CONTAINERFILE-TRACKED** — P1 infra debt, ~1.5 hrs. One-time cost; no incidents since S27 close.
- ⏳ **PD-S27-TEST-PIN-ROTATION** — P1, 15 min. Trigger: before first non-Ajay employee row.
- ⏳ **PD-S20-KRUNAL-UAT** — async external trigger; first production Lead→Inquiry conversion fires Q9 email to Krunal for human-eyes review.

See `VECRM-PENDENCY-S28-CLOSE.md` for full backlog with effort estimates, dependencies, scope file refs.

---

## §3 — Recommended S29 scope (choose at opener)

### Option α — Single big P1 ship: LEAD-SCOPING-CUTOVER (~4.5 hrs + deploy)

Execute PD-S28-LEAD-SCOPING-CUTOVER as a focused single-PD session. Closes the latent privacy gap (any portal-authenticated user can currently read any Lead). Sets up the canonical "per-rep scoping" helper pattern (PD-S27-PORTAL-SCOPING-PATTERN documentation lands free as a side effect).

**Why this first:** Auth reset is shipped (S28); the next user-visible feature wave is rep-attributed Lead views. Scoping has to be live before broader rep onboarding, OR every new rep gets read access to every other rep's Leads.

### Option β — S28 follow-up sweep (~6-8 hrs across 6 small PRs)

Clean up the 5 P2/P3 pendencies banked from PR #14 + PR #25 before broader user exposure:

1. PD-S28-LOGINFORM-PIN-MINLENGTH (30 min, P3) — quickest cleanup; nice "warmup PR"
2. PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE (30-60 min, P2) — display defect; trace the URL-encoding hop
3. PD-S28-AUTH-PHONE-PREFIX-LOCK (1-1.5 hrs, P2) — UX improvement; touch both LoginForm + ForgotPinForm
4. PD-S28-LOGIN-ERROR-UX (1-1.5 hrs, P3) — contextual error vocabulary
5. PD-S28-ADMIN-PIN-SET-UI (2-3 hrs, P2) — admin convenience; the largest in the sweep
6. PD-S29-CANDIDATE-RESET-RATELIMIT-SHARED (1-1.5 hrs, P3) — easy SQL widen

These are all small, well-scoped, low-risk. A good sweep keeps the auth-UX surface clean before broader use.

### Option γ — Combined α + start of β (~7-8 hrs)

LEAD-SCOPING-CUTOVER as the main ship, plus 1-2 quick P3 sweeps as warmup (PD-S28-LOGINFORM-PIN-MINLENGTH first, then PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE while waiting on deploy of α). Fits in an 8-hr block with one big PR and two micro-PRs.

### Option δ — Infra debt: CONTAINERFILE-TRACKED (~1.5 hrs + decisions)

If S29 is a short session (3-4 hrs available), this is the right scope. Closes a P1 infra debt with one focused PR. Combine with PD-S25-CONTAINER-LOGS-DIRS (1 hr) and PD-S27-L8-REBANK (45 min) for a clean infra-hygiene afternoon.

### Option ε — Session-0 strategic backlog review (no code, ~1 hr decision-only)

Now that reset flow is live, the next strategic feature decision becomes pressing. The Session-0 backlog has been carried implicitly since S22:

- Items 2 (approval-chain decision) and 3 (role split: Sales Rep vs Field Engineer) are *blocking decisions* that must be answered before item 1 (voucher approval workflow) can be designed
- Item 4 (Sales Visit doctype portal UI) is the next likely large workstream after Lead scoping
- Item 7 (OTP auth) replaces the password placeholder — now that reset flow exists, OTP becomes an additive enhancement rather than a security fix

This is a chat-only session: operator + Claude review the backlog, decide which item to schedule for S30, author one or two recon dispatches if needed.

**Recommend:** Option γ if operator has 8 hrs. Option α if not. Option ε in parallel with any of the others if operator wants strategic alignment before scheduling S30+.

---

## §4 — Cold-check checklist for S29 open

Run these 8 gates before any work (from `docs/operating-patterns/cold-check-template.md`):

1. Mac `main` clean for both repos, up to date with origin (vecrm at `955f7ae` post-S28-docs-commit; vecrm-portal at `8f7c1b7`)
2. vecrm `main` HEAD includes S28 close docs commit (this PR's merge SHA)
3. VPS `vecrm-backend-1` Up + HTTP 200
4. voucher_counter.py sha matches VECRM-L8 canonical (`91556a7d07...`)
5. Vendor copy on VPS matches Mac (sample probe — check `vecrm_auth_reset_token` doctype dir presence)
6. `tabVECRM Auth Reset Token` exists in production (carried over from S27; should now have consumed rows from S28 audit smokes)
7. Counter state matches S28 close pendency (`LEAD-26-27=15` notably +1 from audit smoke)
8. Frappe v16 `require_type_annotated_api_methods` site-wide setting still active (test-import one method)

All 8 should pass cleanly. If any fail, investigate before proceeding.

Additional S29-specific gates (recommended):

9. **Reset flow live-check:** `curl -X POST https://app.vinayenterprises.co.in/api/auth/forgot-password -H 'Content-Type: application/json' -d '{"email":"audit-cold-check-nope@example.com"}'` — expect HTTP 200, 93 bytes, `{"success":true,"message":"If an account exists for this email, a reset link has been sent."}`. This confirms the S28 shipment is still functioning end-to-end with no regressions.
10. **AppShell whitelist still intact:** verify `grep PUBLIC_AUTH_PATHS vecrm-portal/app/components/AppShell.tsx` returns the hardcoded `["/set-password", "/set-pin"]` array. The new lock (VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY) forbids drift to startsWith/regex.

---

## §5 — Operator-side prep before S29 opens

- **No mandatory prep.** S29 inherits a clean, audited baseline.
- **Optional:** if going with Option β or γ, glance at `docs/handovers/VECRM-PENDENCY-S28-CLOSE.md` §4 for the 5 P2 items' scope file refs to pre-orient on the surface.
- **Operational note (OBS-S28-U context):** Ajay's VECRM password was rotated during PR #25 §2.5 audit smoke. If passwords were noted anywhere, refresh from current state.
- **Optional cleanup:** PD-S26-LOCAL-BRANCH-HOUSEKEEPING refreshed at S28 close — S28 left ~8 dormant feature branches across both repos that can be cleaned in 10-15 min. Not blocking.

---

## §6 — References to read at S29 open

In order:

1. This opener
2. `docs/handovers/PD-S28-CLOSE-HANDOVER.md` — narrative of S28
3. `docs/handovers/VECRM-PENDENCY-S28-CLOSE.md` — what's open
4. `docs/handovers/VECRM-DEPENDENCY-S28-CLOSE.md` — locks + dependency graph (note: 1 new lock + 3 new modules)
5. `docs/dispatches/PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md` — **referenceable for any future auth work**; baseline security posture documented here
6. `docs/runbooks/PD-S27-DEPLOY-RUNBOOK.md` — unchanged from S27, used for every backend deploy
7. `docs/architectural-locks/VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY.md` — new this session

For Option α (LEAD-SCOPING-CUTOVER): no dispatch authored yet; recon during S29 will draft.
For Option β (sweep): each PD's scope file refs are in `VECRM-PENDENCY-S28-CLOSE.md` §4.

---

## §7 — Reminder: PR #14 + #24 follow-up urgency

The 5 P2/P3 pendencies from PR #14 + PR #25 (FORGOT-PIN-DISPLAY-PLUS-MANGLE, AUTH-PHONE-PREFIX-LOCK, ADMIN-PIN-SET-UI, LOGINFORM-PIN-MINLENGTH, LOGIN-ERROR-UX, plus the audit's RESET-RATELIMIT-SHARED) all touch the auth UX surface. They should be addressed within the first 2-3 sessions (S29-S31) to keep auth UX clean before broader rep onboarding — once real users see the surface daily, defect tolerance drops sharply and small UX gaps become support tickets.

None are blocking, but the longer they sit, the more operator-side workarounds (e.g., "tell the rep to type the `+` carefully because of the `=91-` display glitch") accumulate as institutional debt.

---

**End of opener.**
