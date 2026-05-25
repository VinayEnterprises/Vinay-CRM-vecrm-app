# PD-S30-CLOSE-HANDOVER

**Session:** S30
**Closed at:** 2026-05-25 ~17:30 IST
**Duration:** ~14 hours (S30 opened ~03:30 IST per `.s30_pr32_build_*.log` timestamps)
**Outcome:** ✅ All planned scope shipped + 1 major recon delivered + 1 critical bug surfaced
**Tag:** `s30-close` to be applied to vecrm main HEAD after F-1.4 probe + S31 opener authored

---

## §1 — TL;DR

S30 was the highest-throughput VECRM session to date. Shipped 7 PRs across 2 repos. Surfaced and protocol-confirmed a multi-session latent attribution bug (LEAD-OWNER). Closed the long-running PD-S29-PIN-INPUT-SEGMENTED-6BOX with a 2-PR backend+portal split. Closed PD-S29-LEAD-FORM-FIELDS with backend+portal+follow-up. Restructured pendency from 10 → 26 active items, exposing realistic Session-0 scope gap. 28 OBS-S30 observations banked, 3 promoted to LOCK-CANDIDATE, 1 promoted to LOCK.

**Production state at close:**
- `vecrm-custom:latest` running the final S30 image (B-phase + visual polish complete)
- 15 Leads, 13 Inquiries (after smoke cleanup) — baseline restored
- 5 VECRM Employees, 1 active (Ajay)
- All 4 voucher tables present
- 18/18 workers healthy in VEMIO (unchanged from S29)

---

## §2 — PRs shipped in S30

| # | Repo | Title | Status |
|---|---|---|---|
| #31 | vecrm | docs(s30): full pendency restructure | ✅ MERGED |
| #32 | vecrm | feat(s30): Lead form mandatory fields backend (PD-S29-LEAD-FORM-FIELDS) | ✅ MERGED |
| #33 | vecrm | fix(s30): create_lead missing-field cases route via ValidationError not TypeError | ✅ MERGED |
| #34 | vecrm | fix(s30): PIN policy tightening — login_with_pin length check + complete_pin_reset exactly-6 | ✅ MERGED |
| #19 | vecrm-portal | feat(s30): Lead form mandatory fields + PhoneInput + humanizeError (PD-S29-LEAD-FORM-FIELDS + 2 absorptions) | ✅ MERGED |
| #20 | vecrm-portal | feat(s30): PIN segmented 6-box input (PD-S29-PIN-INPUT-SEGMENTED-6BOX) | ✅ MERGED |
| #21 | vecrm-portal | fix(s30): PinInput6Box visual polish — segment border contrast + wrapper border default state | ✅ MERGED |

**7 PRs in 14 hours.**

---

## §3 — Pendency state at close (vs S30-open)

**S30 opened with:** 10 active P1/P2 items.
**S30 closes with:** 26 active P1/P2 items.

The growth is NOT pendency-drift; it's Session-0 scope finally being honestly tracked. PR #31's restructure surfaced 16 items that had been implicit in Session-0 but not on the active pendency tracker. Real scope is now visible.

**Closed in S30:**
- ✅ PD-S29-LEAD-FORM-FIELDS (backend + portal) — PR #32 + #33 + #19
- ✅ PD-S28-AUTH-PHONE-PREFIX-LOCK — absorbed into PR #19
- ✅ PD-S28-LOGIN-ERROR-UX — absorbed into PR #19
- ✅ PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE — closes by construction via PR #19's PhoneInput
- ✅ PD-S30-PORTAL-EMAIL-LIB — verified via PROBE-12 (foundation already exists)
- ✅ PD-S29-PIN-INPUT-SEGMENTED-6BOX (backend + portal) — PR #34 + #20
- ✅ PD-S28-LOGINFORM-PIN-MINLENGTH — closes by construction via PR #20
- ✅ S30 PR-21 visual polish — PR #21 (S30 scope, addressed visual issues from PR #20 smokes)

**Newly added to pendency during S30:**
- PD-S30-LEAD-OWNER-ATTRIBUTION (P1, recon done, B-phase S31)
- PD-S30-LEAD-CONTACT-FIELDS (P1, S32 target — name + designation)
- PD-S30-LEAD-ATTACHMENTS (P2, S32 target — up to 3 attachments)
- PD-S30-LEAD-FOLLOWUP-WORKFLOW (P1, S33+ target — 3-sub-PR shape)
- PD-S30-PININPUT-HORIZONTAL-CENTER (P3, cosmetic — 6 boxes not horizontally centered in wrapper card)
- PD-S30-DOCS-DRIFT-PR4-RUNBOOK (P2 — PR #4 runbooks describe Mac-buildx workflow but actual builds run on VPS)

Full updated pendency: `VECRM-PENDENCY-S30-CLOSE.md`.

---

## §4 — The big surface: PD-S30-LEAD-OWNER-ATTRIBUTION

Surfaced during D PR-2 visual review on the Vercel preview. Confirmed at protocol level via Set-Cookie + body identity mismatch in `login_with_pin` response. Recon authored, 552 lines.

**Root cause:** Single line at `vecrm/api.py:334` — `doc.lead_owner = frappe.session.user`. The very next line correctly reads the human's phone PK from session, but line 334 captures the BFF service account.

**Surface scope:** 6 sites total — 4 wrong (attribution), 2 correct (Frappe row metadata). All 4 wrong sites identified by file + line in recon §A.

**Impact:**
- UI display: every Lead/Inquiry shows "vecrm-portal@..." as owner (cosmetic but user-visible)
- Audit log forensics: Voucher Audit Log records wrong actor
- Follow-up workflow blocker: emails would go to service account inbox
- Future Inquiry scoping when it ships (currently uses creating_employee — works today, but ownership-based scoping won't work)

**NOT impacted (recon §H.2 correction):**
- Per-rep scoping for Leads — uses `creating_employee`, NOT `lead_owner`. Works today.

**Fix scope:** 5 surgical edits in 4 files + 1 migration patch. No portal changes (backend session already has the identity needed).

**P0 blocker for migration:** ATT-13 — does `ajay@vinayenterprises.co.in` exist as a Frappe User row? Operator runs F-1.4 probe at S30 close. Answer determines whether migration is Case A (straight UPDATE) or Case B (create-user-first).

**B-phase scheduled for S31 open.**

---

## §5 — OBS-S30 observations banked

29 observations total. 3 promoted to LOCK-CANDIDATE. 1 promoted to LOCK.

### Promoted to LOCK

**VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE (was OBS-S30-P/Q):**
Every deploy must conclude with `docker exec <container> grep <expected-changed-string> <file-path>` against a known-changed line. If absent, the deploy is unverified, not GREEN. Caught real silent-deploy bug on first use (PR #33 didn't merge; build ran against PR #32 vendor).

### Promoted to LOCK-CANDIDATE

**VECRM-LOCK-DEPLOY-COMMANDS-FROM-EVIDENCE (was OBS-S30-K):**
Dispatcher deploy commands must cite runbook/build-log evidence, NOT memory. 3+ misses this session: `docker compose build` (wrong), `gh pr merge 33` assumed (no verify), PR #21 dispatch assumed PR #20 was merged when it wasn't.

**VECRM-LOCK-S29-PORTAL-COMPONENT-PATHS (was OBS-S30-J):**
Auth/Account/PIN-related portal components live in `app/components/auth/` and `app/components/account/`, NOT `app/`. 2-occurrence pattern this session.

**VECRM-LOCK-VERIFY-BASELINE-BEFORE-BRANCH (was OBS-S30-CC, derived from OBS-S30-R):**
Code must verify dispatch baseline assumptions against actual `git log` before branching. Caught real misalignment on PR #21 attempt (dispatch said main was post-#20, actual main was at #19).

### Banked observations (A–II)

| OBS | Subject |
|---|---|
| OBS-S30-F | Shared helpers in auth-adjacent code may have load-bearing security semantics |
| OBS-S30-G | No shared `_validate_pin` helper introduced (3 inline checks post-tightening; revisit at 4+ entry points) |
| OBS-S30-H | Shared form-primitive consolidation candidate at 3+ primitives (currently 2: PhoneInput + PinInput6Box) |
| OBS-S30-I | Audit-reason taxonomy at 11 values post-PR-B1; worth doctype-level closed-enum at 12+ |
| OBS-S30-J | → LOCK-CANDIDATE VECRM-LOCK-S29-PORTAL-COMPONENT-PATHS |
| OBS-S30-K | → LOCK-CANDIDATE VECRM-LOCK-DEPLOY-COMMANDS-FROM-EVIDENCE |
| OBS-S30-L | Migration patches should adopt self-verifying NULL-count assertion pattern |
| OBS-S30-M | mariadb `sql_safe_updates=ON` requires DELETE by primary key (name) |
| OBS-S30-N | Frappe v16 API param convention: `field: str = None` defaults + body-level validation |
| OBS-S30-O | Explicit fail-path smokes alongside happy-path smokes (caught PR #32 TypeError issue) |
| OBS-S30-P/Q | → LOCK VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE |
| OBS-S30-R | `gh pr view N --json state,mergedAt` between merge and pull; image SHA changing is NOT sufficient evidence of code change |
| OBS-S30-S | Builds against unchanged source produce new image SHAs even with `--no-cache` |
| OBS-S30-T | Status-aware error humanization requires status to propagate end-to-end (useAuth withStatus pattern) |
| OBS-S30-U | Convert flow lives as inline modal on Lead detail, not as separate page |
| OBS-S30-V | Pre-existing lint baseline (15 problems) informally frozen — lint-baseline-document at S30 close |
| OBS-S30-W | Single-line policy tightenings inside well-tested functions don't need full reset-flow smoke |
| OBS-S30-X | PD-S30-LEAD-OWNER-ATTRIBUTION root cause confirmed at protocol level |
| OBS-S30-Y | zsh interactive paste mode can interpret `# === text ===` comments as commands |
| OBS-S30-Z | When credential-touching endpoints give unexpected HTTP, check audit log FIRST |
| OBS-S30-AA | UI copy asserting policy values must source from constants matching backend policy |
| OBS-S30-BB | Visual smokes catch what functional smokes miss; future PRs should include explicit visual smokes |
| OBS-S30-CC | → LOCK-CANDIDATE VECRM-LOCK-VERIFY-BASELINE-BEFORE-BRANCH |
| OBS-S30-DD | AppShell `.app-shell-main` height calc may be actual centering layer for authenticated users on auth-flow pages |
| OBS-S30-EE | Visual perception of "uncentered" can mislead when small card sits in tall empty viewport |
| OBS-S30-FF | Code's pattern of investigating-instead-of-complying with dispatch checklists is excellent discipline |
| OBS-S30-GG | Dispatcher claims about scoping/coupling require Code to verify against actual code |
| OBS-S30-HH | Same as GG but generalized to all non-trivial-to-verify code paths |
| OBS-S30-II | Visual smokes should check three centerings, not one: card-vertical, card-horizontal, content-inside-card |

---

## §6 — Production state mutations during S30

**Created during smokes (cleaned up):**
- VE/LEAD/00016/26-27 (S30 PR #32 smoke) — DELETED
- VE/LEAD/00017/26-27 (S30 PR #33 regression smoke) — DELETED
- VE/LEAD/00018/26-27 (S30 PR-B1 smoke) — DELETED via deduplication
- VE/LEAD/00019/26-27 (S30 PR #19 portal smoke "Smoke Test S31") — DELETED at close
- VE/INQ/00014/26-27 (S30 PR #19 portal smoke conversion "Smoke Test S31") — DELETED at close

**Final counts:** 15 Leads, 13 Inquiries (matches pre-S30 baseline).

**Append-only audit log entries:** 6 rows from S30 smokes stay forever. Per OBS-S29-II, audit logs are append-only.
- 3 rows at 2026-05-25 15:39 IST, event=auth.login.failed, reason=invalid_pin_format — PR-B1 smokes B1.1/B1.2/B1.3
- 3 rows at 2026-05-25 15:45-15:47 IST, event=auth.change.pin.failed, reason=current_mismatch — PR-B1 smoke B1.8 attempts

**Schema changes:**
- v1_3 patch: 3 new nullable columns on VECRM Lead (contact_number, contact_email, meeting_brief)
- No other schema changes (B-phase was validation-only)

---

## §7 — Production state at close

| Item | State |
|---|---|
| vecrm main HEAD | (post-PR #33 + PR #34, last commit hash to be captured at tag time) |
| vecrm-portal main HEAD | b922863 (post-PR #21) |
| vecrm-custom:latest image SHA | (post-PR #34 build, to be captured) |
| Rollback tags | s30-pre-pr32-rollback, s30-pre-pr33-rollback, s30-pre-pr-b1-rollback (all preserved) |
| Vercel production deploy | post-PR #21 (auto-deployed) |
| Workers | 18/18 healthy (VEMIO; unchanged) |
| Real customer data | none (Ajay-only) |

---

## §8 — What carries to S31

**Item 1 (Day-1):** LEAD-OWNER-ATTRIBUTION B-phase. Findings doc on local branch `recon/s30-lead-owner-attribution`. Operator must:
- Push recon branch (if desired for backup) OR keep local
- Run F-1.4 probe before B-phase authoring
- Answer 14 ATT-1..ATT-14 questions
- Dispatcher then authors B-phase (2 PRs: backend code fix + migration patch)

**Item 2 (Day-1):** Cleanup smoke artifacts (`VE/LEAD/00019/26-27`, `VE/INQ/00014/26-27`) if not done at S30 close.

**Item 3:** Production smokes on `app.vinayenterprises.co.in` post PR #21 deploy. Quick visual check on LoginForm + Account.

**Item 4 (Day-3+):** PD-S30-LEAD-CONTACT-FIELDS + PD-S30-LEAD-ATTACHMENTS (batch with #1).

**Item 5 (Day-7+):** PD-S30-LEAD-FOLLOWUP-WORKFLOW (3-sub-PR shape, blocked on item 1).

**Item 6:** PD-S30-PININPUT-HORIZONTAL-CENTER (cosmetic, single CSS line, batchable with any portal PR).

**Item 7:** Long-tail Session-0 items: closure UI, role matrix, admin user management, PWA validation, Q9 email migration.

---

## §9 — Discipline notes for S31

Tonight's third-iteration lessons codified:

1. **OBS-S30-K + R**: Never author deploy commands from memory. Cite verified runbook lines. Verify merge state explicitly.

2. **OBS-S30-P**: Three-layer deploy verification (Mac grep + vendor grep + container grep) is mandatory, not optional.

3. **OBS-S30-Z**: Audit log is impartial witness; for confusing HTTP shapes on credential endpoints, check audit log FIRST.

4. **OBS-S30-CC**: Code verifies dispatch's baseline assumptions before branching.

5. **OBS-S30-GG / HH**: Dispatcher claims about non-trivial-to-verify code paths require Code to verify.

6. **OBS-S30-FF**: Code's instinct to investigate-instead-of-comply is excellent discipline. Encourage it.

7. **OBS-S30-BB / II**: Visual smokes need their own discipline (3-axis centering, light + dark, multiple surfaces).

---

## §10 — Session in one paragraph

S30 took the longest-running active pendency item (PD-S29-LEAD-FORM-FIELDS, opened S29) and closed it with a 3-PR vertical (backend, follow-up, portal) that absorbed 2 small auth-side fixes along the way. PR #19's smokes surfaced a latent multi-session bug — Leads attribute to a BFF service account instead of the human — which became S30's most substantial discovery; recon was completed and is the cleanest S31 starting line we've had. Workstream B (PIN segmented input + backend tightenings) shipped in 2 PRs with a follow-up visual-polish PR catching screenshot-only-detectable issues. The night's deploy mechanism was stress-tested 4 times; the layered-verification discipline (OBS-S30-P → LOCK) earned its keep on the third deploy by catching a silent unmerged-PR bug. Pendency restructure (PR #31) finally aligns the active tracker with Session-0 scope honestly. 29 OBS-S30 observations, 3 lock-candidates, 1 promoted-to-lock. Operator: Ajay Salvi, focused, evidence-driven, caught the LEAD-OWNER bug from a screenshot. Dispatcher: improved on the deploy discipline 4 times. Code: shipped cleanly across 7 PRs with strong investigation discipline.

---

**End of close handover.**
