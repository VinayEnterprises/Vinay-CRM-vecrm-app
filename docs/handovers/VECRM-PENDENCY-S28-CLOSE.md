# VECRM-PENDENCY-S28-CLOSE

**Supersedes:** `VECRM-PENDENCY-S27-CLOSE.md`
**Generated:** 2026-05-24 (S28 close)

---

## §1 — Format

Each PD entry has: ID, priority (P0/P1/P2/P3), session of origin, effort estimate, depends-on list, brief description, status.

Statuses: `OPEN` (active), `BLOCKED` (waiting on something), `PROGRESS` (partially shipped), `CLOSED` (done), `DEFERRED` (acknowledged but not scheduled).

---

## §2 — Closed during S28

| PD ID | Status | Closed via |
|---|---|---|
| PD-S28-AUTH-RESET-FLOW (parent) | CLOSED | All 6 sub-PDs shipped + audit passed (PR #25, `955f7ae`) |
| PD-S28-AUTH-RESET-BACKEND-API | CLOSED | PR #22 (`0bb7817`) — 4 whitelist methods + auth_reset.py crypto module |
| PD-S28-AUTH-RESET-EMAIL-MECHANISM | CLOSED | PR #11 (`a1e03a1`) — `lib/email.js` sendMailNoreply via Graph |
| PD-S28-AUTH-RESET-EMAIL-TEMPLATE | CLOSED | PR #12 (`65acac1`) — 3 HTML template modules |
| PD-S28-AUTH-RESET-PORTAL-BFF | CLOSED | PR #13 (`e326e46`) — 3 BFF routes |
| PD-S28-AUTH-RESET-PORTAL-UI | CLOSED | PR #14 (`8f7c1b7`) — 4 forms + 2 pages + AppShell whitelist |
| PD-S28-AUTH-RESET-BACKEND-PIN-EMAIL (addendum, in-flight) | CLOSED | PR #23 (`5672809`) — _internal.delivery_email populated for PIN path |
| PD-S28-AUTH-RESET-BACKEND-DISPLAY-NAME (addendum, in-flight) | CLOSED | PR #24 (`a81a856`) — email greeting uses employee_name not autoname |
| PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE | CLOSED | PR #25 (`955f7ae`) — findings APPROVE-confirmed |
| PD-S29-CANDIDATE-RESET-TIMING-SIDECHANNEL | RETIRED | PR #25 §1.7 multi-sample evidence showed side-channel doesn't exist; captured as OBS-S28-V |
| OBS-S27-AA (Frappe Data min-length 64) | CLOSED | S28 Gate 7 confirmed benign — IPv6 max textual rep is 45 chars; varchar(64) is more than sufficient |

---

## §3 — Active P1 items

### PD-S28-LEAD-SCOPING-CUTOVER

- **Status:** OPEN, substrate from PR #20 in place
- **Effort:** ~4.5 hrs
- **Origin:** S27 (substrate shipped, scoping logic deferred per scope discipline)
- **Depends-on:** none — substrate ready
- **Description:** Wire per-rep scoping into Lead list/detail BFF routes. Reps see only `creating_employee = self.phone` rows; HR Approvers and System Managers see all. Lead detail check at BFF and at backend API layer (defense in depth).
- **Latent privacy concern:** Currently any portal-authenticated user can read any Lead via the `/api/resource/VECRM Lead` proxy. Scope discipline kept this out of S27, but P1 because it's a real privacy gap.
- **Why still highest-priority:** the auth flow is now live (S28), so the next user-visible feature wave will hit Lead/Inquiry surfaces — they need scoping before broader rep onboarding.

### PD-S28-CONTAINERFILE-TRACKED

- **Status:** OPEN
- **Effort:** 1.5 hrs
- **Origin:** S27 (OBS-S27-K, T)
- **Depends-on:** none
- **Description:** Commit `/opt/vecrm/images/custom/Containerfile` into a tracked repo (vecrm-infra or similar) with a paired `sha-pins.json` tracking the canonical voucher_counter.py sha. Update PD-S27-DEPLOY-RUNBOOK to reflect the new flow.
- **Why P1:** Containerfile is a critical production artifact living only on the VPS. Loss of VPS = loss of build definition. Sha-gate stale-text fix (OBS-S27-X) belongs in this PD.
- **S28 status:** zero incidents this session; the PD-S27-DEPLOY-RUNBOOK procedures held cleanly across 4 backend deploys.

### PD-S27-TEST-PIN-ROTATION

- **Status:** OPEN
- **Effort:** 15 min
- **Origin:** S26
- **Depends-on:** none
- **Description:** Test rep PINs (Test Sales Rep `1234`, Test HR Approver `5678`) MUST be rotated to operator-chosen non-trivial values BEFORE any real customer onboarding. Currently using documented test values from S26 setup — fine for development, unsafe for production.
- **Trigger:** Before the first non-Ajay employee gets a VECRM Employee row.
- **S28 update:** OBS-S28-U side-effect — Ajay's own password was rotated during PR #25 §2.5 smoke. Test rep credentials themselves are unchanged.

---

## §4 — Active P2 items

### PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE (NEW S28)

- **Status:** OPEN
- **Effort:** 30-60 min (depending on root-cause path)
- **Origin:** S28 PR #14 + PR #25 audit
- **Depends-on:** none
- **Description:** `ForgotPinForm.tsx` "Check your email" confirmation card sometimes renders `=91-...` instead of `+91-...` when echoing the user-submitted phone. Display-only; email delivery and backend lookup unaffected. Suspected root cause: URL-encoding of `+` as space at some hop in the render path. Reproduction needed before fix.
- **Scope file refs:** `vecrm-portal/app/components/auth/ForgotPinForm.tsx` (the "Check your email" branch starting ~line 50)

### PD-S28-AUTH-PHONE-PREFIX-LOCK (NEW S28)

- **Status:** OPEN (improvement, not defect)
- **Effort:** 1-1.5 hrs
- **Origin:** S28 PR #14 (operator decision)
- **Depends-on:** none
- **Description:** Lock phone input to fixed `+91-` prefix for all India-based users (the only current user pool). Reduces input errors + simplifies validation. Applies to LoginForm (phone tab) and ForgotPinForm. Backend already normalizes via `_normalize_phone`.
- **Scope file refs:** `vecrm-portal/app/LoginForm.tsx` (phone input ~line 215), `vecrm-portal/app/components/auth/ForgotPinForm.tsx`

### PD-S28-ADMIN-PIN-SET-UI (NEW S28)

- **Status:** OPEN
- **Effort:** 2-3 hrs
- **Origin:** S28 (operator observation during reset flow exercise)
- **Depends-on:** none
- **Description:** Frappe Desk UI lacks a "Set PIN" affordance for admin convenience. Current workflow to set a new employee's initial PIN requires `bench console` + `update_password(employee.name, pin, doctype="VECRM Employee", fieldname="pin_hash")`. The user-facing reset flow self-serves end users; admin convenience is the gap. Candidate: a custom action on the VECRM Employee form OR a Frappe-Desk-side button that mirrors `complete_pin_reset` semantics (skip-token-validate, write hash, clear lockout).
- **Scope file refs:** `vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json` (add custom action), `vecrm/api.py` (admin-only whitelist method with role gate)

### PD-S26-PORTAL-VECRMSESSION-TYPE

- **Status:** OPEN (carried from S26)
- **Effort:** 2-3 hrs
- **Origin:** S26
- **Depends-on:** none
- **Description:** Richer TypeScript return type from `getFrappeUser()` so consumers see `vecrm_employee_phone`, `vecrm_login_path`, etc., as first-class fields rather than ad-hoc casts from `session.data`. Becomes load-bearing when PD-S28-LEAD-SCOPING-CUTOVER ships — that PR will read session data heavily.

### PD-S26-FRAPPE-PERM-MECHANISM-PROBE

- **Status:** OPEN (partially resolved by S27 cold-check Probe 5.1)
- **Effort:** 1-2 hrs
- **Origin:** S26
- **Depends-on:** none
- **Description:** Investigate Frappe v16's permission mechanism when `frappe.get_doc()` is called from API methods. The shared-principal model (VECRM-LOCK-PORTAL-SHARED-PRINCIPAL) means the portal user has broad doctype access — verify this matches our intent and doesn't unintentionally expose data.
- **S28 update:** The reset flow's `frappe.get_doc("VECRM Employee", ...)` calls all happen inside `allow_guest=True` whitelist methods with `ignore_permissions=True` semantics implicit in `frappe.db.get_value` / `frappe.get_doc` — no permission-leak observed in audit. Still worth a formal probe.

### PD-S26-VECRM-EMPLOYEE-PERM-FLOOR

- **Status:** OPEN
- **Effort:** 1 hr
- **Origin:** S26
- **Depends-on:** PD-S26-FRAPPE-PERM-MECHANISM-PROBE (would inform what to tighten)
- **Description:** Tighten read permissions on `tabVECRM Employee` so the shared portal user can't read all employee phone numbers as a side effect of needing to read its own. Add If Owner condition, or scope via custom permission method.

### PD-S27-L8-REBANK

- **Status:** OPEN
- **Effort:** 45 min
- **Origin:** S27 cold-check Gate 4
- **Depends-on:** PD-S28-CONTAINERFILE-TRACKED (cleaner if Containerfile is in tracked repo first)
- **Description:** VECRM-L8.md references an outdated path / lacks the current canonical sha (`91556a7d07...`). Update to current values; ensure the Containerfile sha-gate references the same canonical that VECRM-L8 declares.

---

## §5 — Active P3 items

### PD-S29-CANDIDATE-RESET-RATELIMIT-SHARED (NEW S28)

- **Status:** OPEN
- **Effort:** 1-1.5 hrs
- **Origin:** S28 PR #25 audit (§1.11)
- **Depends-on:** none
- **Description:** Rate limit is per-employee per-`reset_for`. Theoretically an attacker can spam 3 password + 3 PIN per window for a known employee (6 total / 15 min). Above the threshold's intent but below practical abuse. Mitigation: shared budget across `reset_for` values, or per-employee floor of 3 total per window. Easy SQL widen in `_count_recent_reset_tokens` to count across both reset_for values.
- **Scope file refs:** `vecrm/api.py:_count_recent_reset_tokens` (~line 718), `vecrm/api.py:797-804` + `872-879` (the two call sites)

### PD-S28-LOGINFORM-PIN-MINLENGTH (NEW S28)

- **Status:** OPEN
- **Effort:** 30 min
- **Origin:** S28 PR #14 (companion to OBS-S28-Q)
- **Depends-on:** none
- **Description:** `app/LoginForm.tsx` PIN input has `maxLength={6}` but no `minLength` enforcement. Backend rejects 1-3 digit PINs (api.py:1075 `not (4 <= len(new_pin) <= 6)`) but UX feedback is delayed by a round-trip. Add client-side `minLength={4}` + matching `pattern="\d{4,6}"` + disabled-state on submit until valid. Mirror the validation pattern already in `SetPinForm.tsx`.
- **Scope file refs:** `vecrm-portal/app/LoginForm.tsx` (PIN input ~line 240)

### PD-S28-LOGIN-ERROR-UX (NEW S28)

- **Status:** OPEN
- **Effort:** 1-1.5 hrs
- **Origin:** S28 PR #14 (operator UX observation during forms work)
- **Depends-on:** none
- **Description:** Login error messages from `useAuth.login()` surface as raw `error.message` strings (e.g. "Login failed" — the BFF route's generic 401 text). Could benefit from contextual UX guidance ("Wrong email or password" + "Forgot your password?" link prominence; "Account locked" + suggested wait time; etc.). Currently the generic message is no-enumeration-correct but information-poor.
- **Scope file refs:** `vecrm-portal/app/LoginForm.tsx` (error display block ~line 152), `vecrm-portal/app/api/auth/login/route.ts` (consider message vocabulary), `vecrm-portal/app/useAuth.ts`

### OBS-S28-Q (P3 candidate)

- **Status:** OPEN observation; consider promoting if recurring
- **Effort:** 1 hr if pursued
- **Origin:** S28
- **Description:** Safari autofill/save-password dialog interrupts PIN input due to `type="password"`. Cosmetic; could be addressed via `type="text"` + custom masking via CSS `-webkit-text-security: disc` or similar. Trade-off: `type="text"` defeats password-manager autofill defense.

### PD-S25-COUNTER-ORIGIN-S26F

- **Status:** OPEN
- **Effort:** 30 min
- **Origin:** S26 (carried through S27, S28)
- **Depends-on:** none
- **Description:** TV-27-28 counter was at 14 at S26 close with no observed user-initiated travel vouchers. Still at 14 at S28 close (no further investigation). Investigate whether seed/migration created these. No functional impact.

### PD-S25-CONTAINER-LOGS-DIRS

- **Status:** OPEN
- **Effort:** 1 hr
- **Origin:** S25
- **Depends-on:** PD-S28-CONTAINERFILE-TRACKED (combine if both ship together)
- **Description:** Add explicit `RUN mkdir -p /home/frappe/frappe-bench/logs` to Containerfile to avoid runtime log-dir creation race.

### PD-S26-LOCAL-BRANCH-HOUSEKEEPING

- **Status:** OPEN
- **Effort:** 10-15 min
- **Origin:** S26 (refreshed at every close)
- **Depends-on:** none
- **Description:** Delete dormant local feature branches across vecrm and vecrm-portal. `git remote prune origin` to clean up tracking branches for deleted upstreams. **S28-specific cleanup list:** vecrm has `feat/s28-auth-reset-backend-api`, `feat/s28-auth-reset-pin-email-addendum`, `feat/s28-auth-reset-display-name`, `audit/s28-auth-reset-security-review` (this branch — delete after merge of S28 close PR). vecrm-portal has `feat/s28-auth-reset-email-mechanism`, `feat/s28-auth-reset-email-template`, `feat/s28-auth-reset-portal-bff`, `feat/s28-auth-reset-portal-ui`.

### PD-S27-PORTAL-SCOPING-PATTERN

- **Status:** OPEN
- **Effort:** 30 min
- **Origin:** S27 (depends on PD-S28-LEAD-SCOPING-CUTOVER)
- **Depends-on:** PD-S28-LEAD-SCOPING-CUTOVER
- **Description:** Write up the scoping helper pattern once LEAD-SCOPING-CUTOVER establishes it. Becomes the canonical pattern for any future "per-rep scoped" endpoint on the portal.

---

## §6 — Deferred (acknowledged, not scheduled)

### PD-S20-KRUNAL-UAT

- **Status:** OPEN, async, external-trigger (surfaced explicitly in S27 close §10.1)
- **Effort:** Krunal's time, not operator's
- **Origin:** S19 carried through S20, S21, S26, S27 implicitly
- **Trigger:** First production Lead-to-Inquiry conversion firing Q9 management email to Krunal
- **Description:** Async colleague review of Q9 email content (subject pipe-separator, 10 body fields). Scripted-caller verified since S19; awaiting human-eyes UAT.
- **Action when feedback arrives:** Small content/template PR if revisions needed. No Claude scheduling until then.
- **S28 status:** unchanged — no production Lead→Inquiry conversions occurred this session.

### PD-S27-A1-LEAD-DETAIL-BFF

- **Status:** DEFERRED to PD-S28-LEAD-SCOPING-CUTOVER

### PD-S27-PORTAL-LIST-PAGES

- **Status:** DEFERRED to S29+ (will likely fold into LEAD-SCOPING-CUTOVER author time)

### OBS-S28+-VEMIO-EMAIL-DUPLICATION (banked as OBS-S27-W)

- **Status:** DEFERRED indefinitely
- **Description:** Vemio's Graph email mechanism is now duplicated across 4 locations after S28 PR #11 shipped. Long-term, refactor into a shared library or service. Defer until duplication actually hurts.

### Session-0 strategic backlog (reference)

The Session-0 strategic scope items remain unscheduled and tracked outside the active pendency register. Last comprehensively surfaced in S22 mid-session and re-acknowledged at S27 close §10.2 and again at S28 close. Items:

1. Voucher / approval workflow — the keystone unbuilt piece
2. Approval-chain business decision — engineer to reporting manager vs direct-to-operator; same question for sales reps
3. Two distinct user roles — Sales Rep vs Field Engineer surface differentiation
4. Sales Visit doctype portal UI
5. Weekly meeting report
6. PWA-on-phone validation — never installed on actual phone
7. OTP auth replacing password placeholder — MSG91 SMS+WhatsApp pluggable, Phase 4 originally
8. Priority 1-5 bar-gradient UI — BNI visual language

**Decision at S28 close:** S29 opener should include a Session-0 strategic backlog review gate. Items 2 (approval-chain) and 3 (role split) are blocking-decision items that must be answered before item 1 can be designed. The reset-flow shipment in S28 *unblocks broader rep onboarding*, which makes the role-split decision more pressing.

---

## §7 — Counter state

| Counter | S27 close | S28 close | Notes |
|---|---|---|---|
| EV-26-27 | 12 | 12 | Unchanged |
| INQ-26-27 | 12 | 12 | Unchanged |
| LEAD-26-27 | 14 | 15 | +1 from PR #25 §2 audit smoke (operator-acknowledged) |
| TV-26-27 | 94 | 94 | Unchanged |
| TV-27-28 | 14 | 14 | Unchanged (PD-S25-COUNTER-ORIGIN-S26F P3 still open) |
| Auth Reset Token rows | 0 | N (consumed in audit smokes; runtime row count varies; expired tokens stay for forensics until manual cleanup) | New doctype, first production use this session |

---

## §8 — Full S28 observation catalog

Documented S28 observations with concrete provenance. The user's S28-close instructions referenced "OBS-S28-A through OBS-S28-V" as if the series were complete; in practice the chat-session-tracked entries are a subset. If additional S28 OBSes were captured in operator-side notes (terminal scrollback, side channels), they should be folded in at S29 open.

| OBS ID | Description | Disposition |
|---|---|---|
| OBS-S28-F | `npx tsx --env-file=.env.local` does NOT inject env vars; shell-export required | Banked (runbook lore; PR #11 smoke docs) |
| OBS-S28-I | `vercel env pull` returns empty quoted strings for non-Sensitive env vars | Banked (PR #13 smoke header docs) |
| OBS-S28-N | "Don't lie in the docstring" — surgical-fix PRs must update docstrings affected by the change | Banked as convention; applied PR #23, PR #24 |
| OBS-S28-Q | Safari autofill interrupts `type="password"` PIN input | Banked → companion to PD-S28-LOGINFORM-PIN-MINLENGTH |
| OBS-S28-R | Vercel env-var dashboard surfaces non-Sensitive vars differently; Production-environment visibility opaque without explicit dropdown | **STATUS DECISION:** keep as operator-routine lore (P-none); promote to PD only if recurrence pattern emerges. Decision deferred to S29 open if operator wants to re-discuss. |
| OBS-S28-T | zsh history expansion breaks `!` in curl `-d` JSON bodies even when double-quoted | Banked (PR #25 audit findings §4 docs) |
| OBS-S28-U | PR #25 §2.5 smoke inadvertently consumed Ajay's production password token | Banked (operator-hygiene lore for future security smokes) |
| OBS-S28-V | PR #25 §1.7 multi-sample WARN→PASS when sample-1 cold-start outlier excluded | Banked (audit-pattern lore: always discard sample-1 on Vercel timing probes, or warm with discarded probe first) |

**Total documented S28 observations: 8.**

Earlier-letter OBSes (A through E, G through M, O, P, S) are not enumerated to avoid fabrication. If operator notes elsewhere include them, fold in at S29 open.

---

## §9 — Cross-references

- Close handover narrative: `docs/handovers/PD-S28-CLOSE-HANDOVER.md`
- Dependency map: `docs/handovers/VECRM-DEPENDENCY-S28-CLOSE.md`
- Deploy runbook: `docs/runbooks/PD-S27-DEPLOY-RUNBOOK.md` (unchanged from S27)
- S29 opener: `docs/handovers/PD-S29-OPENER.md`
- Security audit findings: `docs/dispatches/PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md`
- S28 dispatch files (6): `docs/dispatches/PD-S28-AUTH-RESET-*-dispatch.md` (all six completed this session)
- New permanent lock: `docs/architectural-locks/VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY.md`

**End of pendency register.**
