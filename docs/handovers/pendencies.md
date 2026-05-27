# VECRM Active Pendencies

Last updated: 2026-05-27 (S33 in progress)
0 active P0 blockers. 0 active P1 blockers.

S33 in-flight:
- vecrm-portal PR #31 (PD-S32-NEXT-VOUCHER-PERMISSION-ERROR-UX) — smoke deferred, merge pending
- PD-S30-LEAD-FOLLOWUP-WORKFLOW — spec locked, see `docs/dispatches/PD-S30-LEAD-FOLLOWUP-LOCK.md`, Phase 1 dispatch pending

---

## Closed this session (S32)

| Pendency | Priority | Closing PR | Closing date |
|---|---|---|---|
| PD-S31-PORTAL-SESSION-EXPIRY-UX | P1 | (prior batch in S32) | 2026-05-26 |
| PD-S29-ROLE-MATRIX-LOCK | P1 | (prior batch in S32) | 2026-05-26 |
| PD-S29-ADMIN-USER-MGMT-BACKEND | P1 | vecrm #43 | 2026-05-26 |
| PD-S29-ADMIN-USER-MGMT-PORTAL | P1 | vecrm-portal #28 | 2026-05-26 |
| PD-S32-EMPLOYEES-403-FIX | P1 | vecrm-portal #28 | 2026-05-26 |
| PD-S32-VOUCHER-SUBMITTER-PERMISSION | P1 | vecrm #43 | 2026-05-26 |
| PD-S32-TV-SELF-SERVICE | P1 | vecrm-portal #29 | 2026-05-26 |
| **PD-S32-TV-SUBMIT-417** | **P0** | **vecrm #44** | **2026-05-26** |
| PD-S25-PORTAL-SUB-B-EXPENSE-VOUCHER | P1 | vecrm #45 + vecrm-portal #30 | 2026-05-26 |

---

## Active (P1)

### PD-S30-LEAD-FOLLOWUP-WORKFLOW (P1)
**Banked:** S30. **Spec ratified:** S33 (2026-05-27) — see `docs/dispatches/PD-S30-LEAD-FOLLOWUP-LOCK.md`.
**Scope:** Unified follow-up workflow on VECRM Lead: reminders + touchpoints + intermediate status states. 3-phase build.
**Phasing (Q-14a):** Phase 1 (field + filter + modal) → Phase 2 (touchpoint doctype + badge) → Phase 3 (reminders + enum expansion + email, blocks on PD-S29-VEMIO-EMAIL-PIPELINE).
**Production gating:** (β) Deploy after Phase 1+2; Phase 3 is post-production enhancement.
**Current state:** Spec locked, Phase 1 dispatch pending.

### PD-S29-VOUCHER-APPROVER-PORTAL-B2 (P1)
**Banked:** S29. **Phase 3 of voucher subsystem.**
**Scope:** HR/Admin can approve submitted TV+EV from portal (currently Desk-only).
Mirror TV detail and EV detail pages, add Approve / Reject buttons and approval-notes textarea for HR/Admin. Calls backend approve endpoint (to be authored: `vecrm.api.approve_*_voucher`).
**Touches:** new `/expense-vouchers/[name]/approve` flow; same for TV; new backend endpoints with approver-role guard; audit hook for `voucher.*.approved`.
**Recommended order:** S33 #3 (largest of the three).

### PD-S29-WEEKLY-MEETING-REPORT (P1)
**Banked:** S29.
**Scope:** Friday EOW Outlook digest of leads, vouchers, inquiries piped to Vinay + Ajay. Probably a scheduled Frappe job + email pipeline.
**Dependency:** PD-S29-VEMIO-EMAIL-PIPELINE.

### PD-S29-VEMIO-EMAIL-PIPELINE (P1)
**Banked:** S29. **Larger build, multi-session.**
**Scope:** Outlook integration via Graph API or SMTP relay through vemio. Blocks PD-S29-WEEKLY-MEETING-REPORT.

---

## Active (P2)

### PD-S32-NEXT-VOUCHER-PERMISSION-ERROR-UX (P2) — IN-FLIGHT
**Banked:** S32. **In-flight:** S33 (2026-05-27).
**PR:** vecrm-portal #31, branch `fix/s33/voucher-permission-error-ux`, build green, merge pending smoke.
**Actual fix shape (refined during S33 recon):** Extend `ErrorContext` union with `voucher_submit`; re-humanize BFF errors through that context in both TV and EV submit routes. Three edits: `lib/errors.ts` + `app/api/travel-vouchers/[name]/submit/route.ts` + `app/api/expense-vouchers/[name]/submit/route.ts`. No unit test (deferred — see PD-S33-NEXT-TEST-INFRA).
**Smoke status:** SAM-33-1-{a..e} deferred to later today.

### PD-S29-PWA-VALIDATION (P2)
**Banked:** S29. **Deferred indefinitely.**
**Scope:** PWA install flow, offline-first sync, push notifications. Not a current operator priority.

### PD-S33-NEXT-TEST-INFRA (P2) — NEW
**Banked:** S33.
**Scope:** No test infrastructure exists in vecrm-portal. Install vitest as dev dependency, add `vitest.config.ts`, wire `npm test` script in `package.json`, author the first test file `lib/__tests__/errors.test.ts` covering `humanizeError` context-routing (including the new `voucher_submit` 403 path from PR #31).
**Rationale:** Deferred from PD-S32-NEXT-VOUCHER-PERMISSION-ERROR-UX (S33 #1). Keeps the fix PR scoped to UX copy; earns test infra as a separate small PR.
**Effort:** ~1h. Single PR.
**Dependency:** None.

### PD-S33-NEXT-DEPLOY-TAG-DISCIPLINE (P2) — NEW
**Banked:** S33.
**Scope:** S32-CLOSE.md prose claimed VPS rollback tags `s32-pre-pr44-rollback` + `s32-pre-pr45-rollback` exist. S33 recon (via `ssh vemio "docker images | grep vecrm-custom"`) showed they do not — most recent rollback image is `s28-pre-pr22-rollback`. The 8-step canonical deploy procedure either skipped the tag step twice in S32, or tagged in a way that didn't persist. Result: PRs #44 and #45 currently lack a clean rollback path.
**Fix:** Add a verifiable rollback-tag step to the 8-step canonical (operator pastes `docker images | grep <tag>` output back into the dispatch before the close doc is authored). Also retroactively decide whether to tag the current main HEAD as a rollback baseline.
**Effort:** ~30 min discussion + dispatch revision. No code change.
**Dependency:** None.

### PD-S33-NEXT-LEAD-DATA-WIPE (P2) — NEW
**Banked:** S33.
**Scope:** Per Q-LEAD-FOLLOWUP-13 (Tension 5), existing pre-S30 leads in `tabVECRM Lead` are demo data and must be truncated before production cutover. Truncate VECRM Lead + dependent rows (VECRM Assignment Ledger Entry where ref_document starts with VE/LEAD/, VECRM Assignment Log Row child rows owned by lead docs).
**Effort:** ~30 min — author SQL script with foreign-key-aware delete order, dry-run on dev, execute.
**Dependency:** Should run AFTER PD-S30-LEAD-FOLLOWUP Phase 1+2 ship and BEFORE production go-live announcement. Banked now so it isn't forgotten.


---

## Active (P3)

### PD-S33-NEXT-VEMIO-DASHBOARD-PHANTOM-BRANCH-CLEANUP (P3) — NEW
**Banked:** S33.
**Scope:** Trivial cleanup. S33 morning fumble created branch `fix/s33/voucher-permission-error-ux` on vemio-dashboard (wrong repo — should have been vecrm-portal). Empty branch, no semantic content. Delete local + remote.
**Commands:** See S33-CLOSE.md when authored.

### PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT (P3) — NEW
**Banked:** S33 (Q-11 revision).
**Scope:** If Sales Head cross-rep write access on leads becomes a real operational need, audit all lead-write surfaces (close, convert, attachments, followup, single-read) and refactor `canReadLead` → `canWriteLead` with explicit role-based extension applied CONSISTENTLY across all routes. Also retrofit backend permission gates on lead-write whitelisted methods (currently rely solely on portal BFF enforcement — see PD-S32+ BACKEND-SCOPING-DEFENSE for the broader defense-in-depth pendency).
**Rationale:** Phase 1 of PD-S30-LEAD-FOLLOWUP-WORKFLOW relaxed Q-11 from (c) lead_owner+Sales Head+Admin to (a) creator+Admin to match existing codebase precedent. Sales Head as a portal-auth category does not yet exist in `lib/scoping.ts`. If/when it's needed, do it once across all lead writes, not as one-off per feature.
**Trigger:** Operational complaint that Sales Heads can't log followups / close / convert on team-rep leads while rep is unavailable.
**Effort:** ~2-3h. Single multi-file PR touching `lib/scoping.ts`, 4 BFF routes, 4 backend whitelisted methods.
**Dependency:** None blocking. Possibly couples with PD-S32+ BACKEND-SCOPING-DEFENSE.
---

## Banked (deferred but not yet scheduled)

- PD-S32+ PASSWORD-CHANGE (portal self-service password change form)
- PD-S32+ INQUIRY-SCOPING (inquiries list filter by self for non-admin)
- PD-S32+ BACKEND-SCOPING-DEFENSE (backend-side enforcement of list scoping, defense-in-depth)
- PD-S32+ AUDIT-RICH-CONTEXT (audit hooks include more context — IP, user-agent, session-id)
- PD-S32+ ADMIN-GET-EMPLOYEE (admin endpoint to fetch a single employee by phone for impersonation flows)

---

## Lock promotion candidates (track for S33 decision)

1. **Heredoc-discipline lock** — 4 violations in S32 (all OBS-S32-X pattern). S33 has had zero heredoc usage so far; promotion clock did not advance. Re-evaluate at S33 close.
2. **Dispatcher-spec-calibration meta-lock** — banked since S30. Mitigated by recon-first discipline through S32 + S33. Still candidate-only.
3. **Multi-repo-tab-discipline meta-lock** — new candidate from S33 (OBS-S33-A). One incident; promote if recurs.
