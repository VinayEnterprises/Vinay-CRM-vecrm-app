# S28-OPENER-PROMPT

**For:** S28 dispatcher (Claude chat, future session)
**Authored:** 2026-05-24 (S27 close)

---

## S28 starts here

S27 closed with the schema substrate for the auth reset flow live in production AND six S28 sub-PD dispatches authored and ready to execute. S28 should:

1. Do a brief cold-check (8 gates from `docs/operating-patterns/cold-check-template.md`) — should pass cleanly; production state at S27 close is documented
2. Decide S28 scope (see §3 below)
3. Execute the chosen sub-PDs in dependency order
4. Close S28 at a sensible breakpoint

---

## §1 — Production state at S27 close

| Property | Value |
|---|---|
| vecrm `main` HEAD | `6d46b0d` (PR #21 squash) — may have advanced past S27 close docs commit; verify |
| vecrm-portal `main` HEAD | `8540794` (PR #10 squash, S27 PR #10 last night) |
| Production image | `vecrm-custom:latest` = `a05637cd2be5` (post-PR #21 deploy) |
| Site | `crm.vinayenterprises.co.in` HTTP 200 |
| Portal | `app.vinayenterprises.co.in` Vercel live |
| Doctype `VECRM Auth Reset Token` | Created S27 PR #21, 0 rows in production |

---

## §2 — What's done and what's pending

**Done in S27 (for the reset flow):**
- ✅ Recon (`docs/dispatches/PD-S28-AUTH-RESET-INFRA-recon-findings.md` + ADDENDUM)
- ✅ Schema (`docs/dispatches/PD-S28-AUTH-RESET-SCHEMA-dispatch.md`, PR #21 shipped)
- ✅ Architectural decision: Option 3d-(i) — mirror Vemio's portal-side Graph pattern
- ✅ 6 S28 sub-PD dispatches authored and committed to `docs/dispatches/`

**Pending in S28:**
- ⏳ PD-S28-AUTH-RESET-BACKEND-API (2.5-3 hrs)
- ⏳ PD-S28-AUTH-RESET-EMAIL-MECHANISM (1.5 hrs)
- ⏳ PD-S28-AUTH-RESET-PORTAL-BFF (2 hrs)
- ⏳ PD-S28-AUTH-RESET-PORTAL-UI (2-2.5 hrs)
- ⏳ PD-S28-AUTH-RESET-EMAIL-TEMPLATE (45 min - 1 hr)
- ⏳ PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE (3.5-4 hrs)

Total: ~12-14 hrs sequential, ~9-11 hrs with parallelism. May split across S28 + S29.

---

## §3 — Recommended S28 scope (choose at opener)

### Option α — Full reset flow ships (9-11 hrs)

Execute all 6 sub-PDs in dependency order. Close S28 when SECURITY-REVIEW-SMOKE signs off. Full feature live.

Order:
1. BACKEND-API + EMAIL-MECHANISM (parallel ~3 hrs)
2. EMAIL-TEMPLATE (~45 min, can start as soon as EMAIL-MECHANISM landed)
3. PORTAL-BFF (~2 hrs)
4. PORTAL-UI (~2-2.5 hrs)
5. SECURITY-REVIEW-SMOKE (~3.5-4 hrs)

This is a long session but well-scoped. All dispatches are ready; no recon overhead.

### Option β — S28 ships through PORTAL-BFF (~7 hrs); S29 ships PORTAL-UI + SECURITY-REVIEW-SMOKE

S28 closes when backend + email + BFF routes are all live. User-visible feature ships in S29 with the UI + final audit.

Cleaner break point if S28 needs to fit in a 7-hr block.

### Option γ — Split by repo

S28 = vecrm-side (BACKEND-API only). S29 = vecrm-portal side (EMAIL-MECHANISM + EMAIL-TEMPLATE + BFF + UI). S30 = SECURITY-REVIEW-SMOKE.

This is over-cautious — the dispatches are self-contained, mixing repos in a session is fine.

**Recommend:** Option α if operator has 10+ hrs. Option β if not.

---

## §4 — Cold-check checklist for S28 open

Run these 8 gates before any work (from `docs/operating-patterns/cold-check-template.md`):

1. Mac `main` clean for both repos, up to date with origin
2. vecrm `main` HEAD includes S27 close docs commit
3. VPS `vecrm-backend-1` Up + HTTP 200
4. voucher_counter.py sha matches VECRM-L8 canonical
5. Vendor copy on VPS matches Mac (sample probe)
6. `tabVECRM Auth Reset Token` exists in production
7. Counter state matches S27 close pendency
8. Frappe v16 type-annotation requirement still active (test-import one method)

All 8 should pass cleanly. If any fail, investigate before proceeding.

---

## §5 — Operator-side prep before S28 opens

Two things to handle BEFORE S28's first dispatch fires:

1. **Vercel env vars** — Add to vecrm-portal Vercel project (per PD-S28-AUTH-RESET-EMAIL-MECHANISM dispatch §1):
   - `GRAPH_TENANT_ID` (copy from vemio-dashboard env vars)
   - `GRAPH_CLIENT_ID` (copy from vemio-dashboard)
   - `GRAPH_CLIENT_SECRET` (copy from vemio-dashboard — secret hygiene)
   - `GRAPH_SENDER_NOREPLY_VECRM = DoNotReply@vinayenterprises.co.in`

2. **PD-S27-TEST-PIN-ROTATION** — If S28 is going to produce a real reset flow, the test PINs (Test Sales Rep `1234`, Test HR Approver `5678`) MUST be rotated before any non-development use. This is 15 minutes of operator work; do it before S28 close.

---

## §6 — References to read at S28 open

In order:
1. This opener
2. `docs/handovers/PD-S27-CLOSE-HANDOVER.md` — narrative of S27
3. `docs/handovers/VECRM-PENDENCY-S27-CLOSE.md` — what's open
4. `docs/handovers/VECRM-DEPENDENCY-S27-CLOSE.md` — locks + dependency graph
5. `docs/runbooks/PD-S27-DEPLOY-RUNBOOK.md` — used for every deploy in S28
6. `docs/dispatches/PD-S28-AUTH-RESET-INFRA-recon-findings.md` + ADDENDUM — design rationale
7. The 6 S28 dispatches in `docs/dispatches/` — execute one at a time

**End of opener.**
