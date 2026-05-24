# PD-S28-CLOSE-HANDOVER

**Session:** S28 (VECRM)
**Status:** CLOSED — 2026-05-24
**Operator:** Ajay Salvi
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (IDE)

**Predecessor:** S27 close (`PD-S27-CLOSE-HANDOVER.md`, commit `083cd37`)
**Successor:** S29 opener (`PD-S29-OPENER.md`, authored as part of this close commit)

---

## §1 — One-line summary

S28 shipped the end-to-end password/PIN reset flow (Option α, full 6-sub-PD plan) across 8 PRs in two repos. All ship-gate audit items PASS. Two surgical hotfixes (PR #23, PR #24) caught mid-flow defects without disrupting the dispatch sequence. No production incidents, no rollbacks. The auth-reset feature is live and security-cleared.

---

## §2 — Narrative

### §2.1 — Session opening

S28 opened from S27's clean baseline (vecrm `6d46b0d` / vecrm-portal `8540794` / image `a05637cd2be5`). The S28 opener prompt + 6 sub-PD dispatches were already authored in the S27 close commit, so S28 had zero recon overhead and went directly to Phase B execution. Cold-check at S28 open cleared all 8 gates cleanly; production state matched the S27-close baseline exactly. Operator chose Option α (full 6-sub-PD reset flow, ~9-11 hrs planned).

Operator pre-work completed before S28's first dispatch fired:

- Vercel env vars set on vecrm-portal Production (`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_NOREPLY_VECRM`) — sourced from vemio-dashboard, reuses `vemio-email-sender` Azure AD app reg per VECRM-LOCK-VEMIO-EMAIL-PATTERN
- OBS-S27-AA closed as benign at Gate 7 (`ip_address length:45` is a Frappe v16 metadata floor, not a defect)
- PD-S20-KRUNAL-UAT surfaced as an explicit deferred pendency (still external-trigger, awaiting first production Lead→Inquiry)

### §2.2 — Primary work (8 PRs across both repos)

**PR #22 — `vecrm` — PD-S28-AUTH-RESET-BACKEND-API**
- 4 whitelist methods: `request_password_reset`, `request_pin_reset`, `complete_password_reset`, `complete_pin_reset`
- New module `vecrm/vecrm/utils/auth_reset.py` (pure crypto, zero Frappe imports): `generate_token` (256-bit CSPRNG via `secrets.token_urlsafe(32)`), `hash_token` (sha256), `constant_time_equals` helper (banked for future raw-string comparisons)
- Audit-log vocabulary extended with 5 new events: `auth.reset.{requested, consumed, expired, invalid_token, rate_limited}`
- Rate limit: 3 reset requests per employee per `reset_for` per 15-min window
- Path deviation flagged in commit: dispatch said `vecrm/utils/auth_reset.py`, actual S25 convention is `vecrm/vecrm/utils/` (where `roles.py` lives). Filed per VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE.
- Schema discovery: dispatch §3.3 implied `password_locked_until`; actual column is `locked_until` (no `password_` prefix). PIN side uses `pin_locked_until` (asymmetric). Documented in commit.
- Squash-merge: `0bb7817`

**PR #11 — `vecrm-portal` — PD-S28-AUTH-RESET-EMAIL-MECHANISM**
- `lib/email.js` ships `sendMailNoreply({toAddresses, subject, html, replyTo?})` — Microsoft Graph client-credentials flow, token cached in module scope with 60-sec safety margin
- Mirrors `vemio-dashboard/lib/email.js` exactly per VECRM-LOCK-VEMIO-EMAIL-PATTERN (the lock held its first cross-project test)
- Smoke confirmed real email delivery from `DoNotReply@vinayenterprises.co.in` to ajay@vinayenterprises.co.in
- Smoke pattern surfaced OBS-S28-F: `npx tsx --env-file=.env.local` does NOT inject env vars; shell-export required for Graph calls
- Squash-merge: `a1e03a1`

**PR #12 — `vecrm-portal` — PD-S28-AUTH-RESET-EMAIL-TEMPLATE**
- 3 new modules under `lib/email-templates/`: `shared.ts` (layout helpers + escape utils), `password-reset.ts`, `pin-reset.ts`
- HTML email constraints honoured: all-inline styles (no `<style>` blocks), table-based layout for Outlook Desktop, exact hex codes (`#FF8C00` / `#5D4037` / `#F5F1EB`)
- `escapeHtml` wired at every user-supplied interpolation; XSS-defense smoke check baked into `/tmp/template-smoke.mjs`
- Brand-styled wrapper with VINAY ENTERPRISES wordmark, cream footer, "Est. 1993 · Ahmedabad, India"
- Squash-merge: `65acac1`

**PR #13 — `vecrm-portal` — PD-S28-AUTH-RESET-PORTAL-BFF**
- 3 Next.js App Router routes: `forgot-password`, `forgot-pin`, `complete-reset`
- Helper signature divergence: dispatch sample assumed `callFrappeAPI(method, params)`; actual existing helper is `frappeFetch(path, {method, body})` returning `{ok, status, data, error, setCookie}`. Adapted per VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE.
- No-enumeration contract enforced at UI boundary: identical 93-byte responses across all paths (match, no-match, backend error, Graph error)
- `complete-reset` returns generic 400 message on any failure — does NOT propagate `result.error` (frappe.throw text can disclose token state like "expired 4 minutes ago")
- HALT-AND-REPORT fired mid-dispatch: backend `_internal` didn't return `delivery_email` for PIN path. Caught early; resolved via PR #23 sibling.
- Squash-merge: `e326e46`

**PR #23 — `vecrm` — PD-S28-AUTH-RESET-BACKEND-PIN-EMAIL (addendum)**
- Surgical fix: backend `_internal` populated with `delivery_email` (PIN path looks up via `employee_doc.vecrm_email`; password path echoes the user-submitted email)
- 3 behavioural lines; +18/-2 total diff including doc-keeping (per OBS-S28-N, earned this PR — "don't lie in the docstring")
- Squash-merge: `5672809`

**PR #14 — `vecrm-portal` — PD-S28-AUTH-RESET-PORTAL-UI**
- 4 new components under `app/components/auth/`: `ForgotPasswordForm`, `ForgotPinForm`, `SetPasswordForm`, `SetPinForm`
- 2 new pages: `app/set-password/page.tsx`, `app/set-pin/page.tsx`
- `app/LoginForm.tsx` mode toggle replaces S27 "Coming soon" placeholder
- **Structural scope extension** — modified `app/components/AppShell.tsx` outside §1 ALLOWED FILES. Reason: Next.js root-layout inheritance + AppShell `user`-null short-circuit prevents reset accept pages from rendering for logged-out users. Fix: hardcoded `PUBLIC_AUTH_PATHS = ["/set-password", "/set-pin"]` + `.includes()` check. Audited as PASS in PR #25 §1.13.
- Path divergence: dispatch said `components/auth/`; portal has no root `components/` dir. Placed at `app/components/auth/` per existing convention.
- Squash-merge: `8f7c1b7`

**PR #24 — `vecrm` — PD-S28-AUTH-RESET-BACKEND-DISPLAY-NAME (surgical fix)**
- Caught during PR #14 E2E smoke: reset emails greeted users with their phone (`Hi +91-9327547536,`) instead of display name (`Hi Ajay Salvi,`)
- Root cause: schema naming clash — VECRM Employee has `name` (autoname = phone) AND `employee_name` (display name field). The `_internal["employee_name"]` write was reading the wrong field.
- Fix: `response["_internal"]["employee_name"] = (employee_doc.employee_name or employee_doc.name)` in both `request_*_reset` methods
- 2 behavioural lines; +22/-4 with naming-clash inline comments + docstring updates
- Squash-merge: `a81a856`

**PR #25 — `vecrm` — PD-S28-AUTH-RESET-SECURITY-REVIEW (audit gate)**
- Pre-ship security review across all 6 layers: schema, crypto helpers, backend API, portal email, portal BFF, portal UI
- 13/13 audit items PASS, 6/6 production smoke paths PASS
- 3 new observations captured (OBS-S28-T, U, V — see §4 here)
- The single pre-confirmation §1.7 WARN (timing side-channel) was downgraded to PASS after operator multi-sample probe (sample-1 cold-start outlier explained the gap; ratio with sample-1 excluded was 0.96, real-match *faster* than no-match)
- Sign-off APPROVE-confirmed by both auditor + operator
- Squash-merge: `955f7ae`

All 8 PRs deployed cleanly. Backend deploys via PD-S27-DEPLOY-RUNBOOK; portal deploys via Vercel auto-deploy on push to main. No rebuilds, no rollbacks.

### §2.3 — In-flight discoveries that became surgical hotfixes

S28's dispatch sequence was designed strictly linear (BACKEND-API → EMAIL-MECHANISM → EMAIL-TEMPLATE → PORTAL-BFF → PORTAL-UI → SECURITY-REVIEW). Two defects surfaced mid-flow and were patched without breaking the sequence:

1. **`delivery_email` gap** caught during PORTAL-BFF authoring. The dispatch §3 said "the email STILL goes to the user's email address" but BACKEND-API didn't actually return the email. HALT-AND-REPORT fired; resolved via PR #23 (1-line backend behavioural fix). PORTAL-BFF shipped its already-written `forgot-pin` code unchanged once #23 deployed.

2. **Display-name in email greeting** caught during PORTAL-UI E2E smoke. Greeting read `Hi +91-...,` instead of `Hi Ajay,`. Schema naming clash (`employee_doc.name` is autoname = phone; `employee_doc.employee_name` is the display name field). Fixed via PR #24 (2-line backend behavioural fix). PORTAL-UI no rework needed.

Both hotfixes used the same shape as a typical dispatch: surgical commit, accurate docstring per OBS-S28-N, paired rollback not needed (additive changes only). This is the canonical pattern for caught-mid-flow defects in a multi-dispatch session — fix at the right layer, don't disrupt downstream dispatches that are already authored.

### §2.4 — Session close

PR #25 audit findings doc remains the canonical security baseline at `docs/dispatches/PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md` — referenceable for any future auth work. Five P2/P3 follow-up PDs banked for S29 (see §4).

S29 opener authored as part of this close commit (`docs/handovers/PD-S29-OPENER.md`).

---

## §3 — Final production state

| Property | Value |
|---|---|
| vecrm `main` HEAD | `955f7ae` (PR #25 audit merge); will advance to S28 docs commit after this close |
| vecrm-portal `main` HEAD | `8f7c1b7` (PR #14 PORTAL-UI merge) |
| Production image | `vecrm-custom:latest` = post-PR #24 deploy (sha post-`4eca723e3803`) |
| Vercel production deploy | `6Tm6fNvfa` Ready (post-PR #14) |
| Frappe v16 site | `crm.vinayenterprises.co.in` — HTTP 200, fully migrated |
| Next.js portal | `app.vinayenterprises.co.in` — Vercel deployed |
| Container image audit trail (rollback tags) | s19-mac-build → s20-pre-fix-rollback → s21-pre-s22-rollback → s22-pre-build → s26-pre-s27-rollback → s27-pre-pr21-rollback → **s28-pre-pr22-rollback (current rollback anchor)** → latest |
| Counter state | TV-27-28=14, LEAD-26-27=15 (+1 from §2.5 audit smoke), INQ-26-27=12, EV-26-27=12 |
| Fleet | 36 containers (vemio + vecrm + frappe-helpdesk); zero alarm counters |
| Production data | 15 leads (Ajay), 0 inquiries from real flow, **N reset tokens produced during §2 smokes (mostly consumed, audit-tracked)**, Ajay's password rotated post-§2.5 |

---

## §4 — Pendency closures (this session)

- ✅ **PD-S28-AUTH-RESET-FLOW (parent)** — all 6 sub-PDs shipped + audit passed
- ✅ **PD-S28-AUTH-RESET-BACKEND-API** — PR #22 (`0bb7817`)
- ✅ **PD-S28-AUTH-RESET-EMAIL-MECHANISM** — PR #11 (`a1e03a1`)
- ✅ **PD-S28-AUTH-RESET-EMAIL-TEMPLATE** — PR #12 (`65acac1`)
- ✅ **PD-S28-AUTH-RESET-PORTAL-BFF** — PR #13 (`e326e46`)
- ✅ **PD-S28-AUTH-RESET-PORTAL-UI** — PR #14 (`8f7c1b7`)
- ✅ **PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE** — PR #25 (`955f7ae`)
- ✅ **PD-S28-AUTH-RESET-BACKEND-PIN-EMAIL** (addendum, in-flight) — PR #23 (`5672809`)
- ✅ **PD-S28-AUTH-RESET-BACKEND-DISPLAY-NAME** (addendum, in-flight) — PR #24 (`a81a856`)
- ⚠ **PD-S27-TEST-PIN-ROTATION** — **STILL OPEN** (15 min). The §2.5 audit smoke inadvertently rotated the operator's password (see OBS-S28-U), but the *test rep* PIN values remain at S26 defaults. Latest safe trigger: before the first non-Ajay employee gets a VECRM Employee row.

PR #25 sign-off conditions (§4 of audit findings doc):
- ✅ §2.1 + §2.2 happy-path E2E smokes confirmed clean
- ✅ §2.4 + §2.5 + §2.6 error-path smokes show generic message + correct audit row
- ⏳ The 6 banked P2/P3 follow-ups + 3 observations to be filed in this close's pendency register (THIS doc set)
- ✅ No new high-priority defects discovered during operator smoke

---

## §5 — Observations banked (S28)

**Caveat:** The OBS-S28 catalog reflects observations Claude has direct evidence for from chat-session memory + audit findings. The user's instructions referenced "OBS-S28-A through OBS-S28-V" as if there were a complete A-through-V series; in practice, only a subset is documented here with concrete provenance. If additional S28 OBSes were captured in operator-side notes (terminal scrollback, side channels), they should be folded into this catalog or the pendency register at S29 open.

| OBS ID | Description | Disposition |
|---|---|---|
| OBS-S28-F | `npx tsx --env-file=.env.local` does NOT inject env vars into the spawned process; shell-export required for Graph send smokes | Banked as operator-runbook lore; PR #11 smoke pattern documents the workaround |
| OBS-S28-I | `vercel env pull` returns empty quoted strings for non-Sensitive env vars (Vercel quirk); operator must shell-export those after pulling | Banked; PR #13 smoke header documents the workaround |
| OBS-S28-N | "Don't lie in the docstring" — earned during PR #23 surgical fix when updating `_make_reset_response` narrative. Applied again in PR #24. Worth promoting to a soft convention for any surgical-fix PR going forward | Banked as a convention to apply at every surgical-fix PR's author time |
| OBS-S28-Q | Safari autofill/save-password dialog interrupts PIN input due to `type="password"` on the LoginForm phone-mode PIN field | Banked → P3 PD-S28-LOGINFORM-PIN-MINLENGTH companion (see §3 of pendency); cosmetic, addressable via `type="text"` + custom masking |
| OBS-S28-R | Vercel env-var dashboard surfaces non-Sensitive vars differently from Sensitive ones; the Production-environment visibility on the dashboard is opaque without dropdown-selecting "Production" explicitly. Operator decision needed at S29 opener: promote to P3 PD or leave as operator-routine lore. | **STATUS DECISION DEFERRED** to S29 opener |
| OBS-S28-T | zsh history expansion breaks `!` inside curl `-d` JSON bodies *even when double-quoted* (unlike bash). Single-quote JSON bodies in zsh. | Banked as operator-side lore; documented in PR #25 audit findings §4 |
| OBS-S28-U | PR #25 §2.5 smoke (consumed-token replay) inadvertently consumed Ajay's production password reset token. Ajay's VECRM password is now whatever the operator subsequently set it to. Operationally fine; banked for any future security smoke that traverses `complete-reset` — use a throwaway credential intended for immediate re-rotation. | Banked as operational-hygiene lore for future security smokes |
| OBS-S28-V | PR #25 §1.7 multi-sample WARN→PASS when sample-1 cold-start outlier excluded. Vercel serverless cold-start mechanism: first invocation post-deploy/idle loads modules + initialises module-scope caches. Lesson: always discard sample-1 on Vercel-deployed endpoint timing probes, or warm with a discarded probe first. | Banked as operator-side audit-pattern lore |

The earlier in-session OBS letters (A through E, G through M, O, P, S) — if used at all during S28 — were not formally banked with concrete observations in chat-session memory and are not enumerated here to avoid fabricating entries.

---

## §6 — Architectural locks promoted at S28 close

**One new permanent lock promoted this session.**

### VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY (new permanent)

Public-auth paths (paths a logged-out user must reach without short-circuiting to LoginForm) MUST be declared as a hardcoded `string[]` at module top-level, with an explicit `Array.includes(pathname)` check in the boundary component. NOT `startsWith`, NOT regex.

**Why permanent:** Public-auth paths sit on the auth-trust boundary — the difference between "renders the login screen" and "renders an unauthenticated page that can mutate credentials." `includes()` makes the membership check auditable in one glance; `startsWith` and regex introduce subtle scoping bugs (`/set-password-evil` would match `startsWith("/set-password")`). PR #25 §1.13 cited the hardcoded-array pattern explicitly as the basis for its PASS verdict.

**Applies to:** `vecrm-portal/app/components/AppShell.tsx:24` (current single application).

**Cross-refs:** PR #14 (introduces), PR #25 §1.13 (audits + cites).

### Reaffirmations (no new lock, but earned more applications)

- **VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE** (S27 lock): held without exception across all 4 build dispatches with code samples this session (BACKEND-API path divergence, PORTAL-BFF helper-signature divergence, PORTAL-UI file-layout divergence, EMAIL-TEMPLATE styling divergence). The lock's "existing code wins" rule is now load-bearing for any multi-dispatch session that includes code samples authored from outside the live repo. No drift suspected; lock remains canonical.
- **VECRM-LOCK-VEMIO-EMAIL-PATTERN** (S27 lock): held cleanly in PR #11. The vemio-dashboard `lib/email.js` pattern transferred 1:1 with no architectural surprises.
- **VECRM-LOCK-PORTAL-SHARED-PRINCIPAL** (S27 lock): the entire reset flow is built on this — `frappe.session.user` is the shared portal user; per-rep identity flows via `frappe.session.data` and the audit log's `employee` field. Lock continues to be load-bearing.
- **VECRM-LOCK-FILE-DELIVERY-NOT-PASTE** (S25 lock): held; all 8 PRs in S28 used file-based delivery for source artifacts and commit messages (`/tmp/commit-msg-*.txt`).
- **VECRM-L13** (squash-merge + branch delete): held across all 8 PRs.
- **VECRM-L22** (paired rollback for migrations): N/A this session — no schema changes after PR #21 (S27). The reset-token doctype's CRUD operations are application-layer, not schema migrations.

**Total permanent locks at S28 close: 28** (27 at S27 close + 1 promoted this session).

---

## §7 — Effort

| Phase | Effort | Notes |
|---|---|---|
| Cold-check at S28 open | ~30 min | All 8 gates green; no surprises |
| PR #22 BACKEND-API author + deploy + smoke | ~3 hrs | Estimate held; type-annotation guard from S25 era helped author cleanly |
| PR #11 EMAIL-MECHANISM author + deploy + smoke | ~1.5 hrs | OBS-S28-F + OBS-S28-I cost ~15 min of detour, banked for future use |
| PR #12 EMAIL-TEMPLATE author + smoke | ~1 hr | Visual smoke + XSS-defense check baked into the script |
| PR #13 PORTAL-BFF author + smoke | ~2 hrs | HALT-AND-REPORT on PIN delivery_email cost 15 min (resolved via PR #23) |
| PR #23 addendum author + deploy + smoke | ~30 min | Tiny PR; the model for surgical mid-flow fixes |
| PR #14 PORTAL-UI author + deploy + smoke | ~3 hrs | Slightly over estimate due to AppShell structural discovery + 8th file (`app/components/AppShell.tsx`) modification |
| PR #24 display-name addendum author + deploy + smoke | ~30 min | Caught by E2E dogfood; same surgical shape as #23 |
| PR #25 SECURITY-REVIEW + smoke | ~4 hrs | Multi-sample timing investigation extended the audit; operator-side smoke runs ~2 hrs of the 4-hr total |
| Close docs (this + pendency + dependency + S29 opener) | ~1.5 hrs | This document set |
| **Total** | **~16 hrs** | Across 1 calendar day for execution + 1 day for audit + close |

S28 is the second-longest session of the project after S27 (~12 hrs). The extra hours are the two surgical hotfixes (PR #23 + PR #24, ~1 hr combined including their own deploys + smokes) plus the audit's multi-sample timing investigation that extended PR #25.

---

## §8 — Risk register (active at S28 close)

| Risk | Severity | Mitigation status |
|---|---|---|
| Test rep PINs not rotated before real customer onboarding | P1 | PD-S27-TEST-PIN-ROTATION still open (15 min). Trigger: first non-Ajay employee row. |
| Containerfile not in tracked repo | P1 | PD-S28-CONTAINERFILE-TRACKED still open (1.5 hrs). No incidents since S27 close; recoverable via S27 reconstruction procedure if needed. |
| Per-rep scoping not yet active on Lead BFFs | P1 | PD-S28-LEAD-SCOPING-CUTOVER still open (~4.5 hrs). Substrate (`creating_employee` column) ready since PR #20. |
| Counter origin investigation (TV-27-28=14) | P3 | PD-S25-COUNTER-ORIGIN-S26F still open. No functional impact. |
| PIN reset rate-limit per `reset_for` not shared | P3 | NEW this session: PD-S29-CANDIDATE-RESET-RATELIMIT-SHARED. Attacker could spam 3 password + 3 PIN per employee per 15-min window (6 total). Above the rate-limit threshold but below practical abuse. |
| ForgotPin display `=91-` glitch in confirmation card | P2 | NEW this session: PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE. Display-only; email delivery unaffected. |
| LoginForm PIN input lacks `minLength` enforcement | P3 | NEW this session: PD-S28-LOGINFORM-PIN-MINLENGTH. Backend rejects 1-3 digit PINs but UX feedback is delayed by round-trip. |

No P0 risks. No data integrity concerns. No security issues outstanding per PR #25 audit.

The §1.7 timing side-channel candidate (PD-S29-CANDIDATE-RESET-TIMING-SIDECHANNEL) was **retired** during PR #25 multi-sample probing — the side channel does not exist once cold-start is factored out. Captured as OBS-S28-V for posterity rather than carried forward.

---

## §9 — Next session opener

S29 opener authored as `docs/handovers/PD-S29-OPENER.md` (in this same close commit). Recommended S29 scope:

**S29 Phase A (recon):** None needed. PD-S29-OPENER §3 lists three candidate workstreams; operator chooses at open.

**S29 candidate workstreams (operator picks):**

1. **PD-S28-LEAD-SCOPING-CUTOVER** (~4.5 hrs) — P1, substrate ready since PR #20. Highest-value security improvement available.
2. **S28 follow-up sweep** (~3-4 hrs) — clean up the 5 P2/P3 pendencies from PR #14 + PR #25 before broader user exposure
3. **PD-S28-CONTAINERFILE-TRACKED** (~1.5 hrs) — P1 infra debt; one-time cost
4. **Session-0 strategic backlog review** — first opportunity since S22 mid-session to decide which strategic item (approval workflow, role split, OTP auth, etc.) to schedule

Operator may also combine 1+2 if a 7-8 hour block is available.

---

**S28 OFFICIALLY CLOSED.**

vecrm `main` HEAD: `955f7ae` (will advance to S28 docs commit after this close).
vecrm-portal `main` HEAD: `8f7c1b7`.
The auth reset flow is live, security-cleared, and end-to-end verified. Operator may sleep, eat, log off; production won't degrade.

**Six-line cold-check preamble for the next session operator:**

```
S28 closed clean. Reset flow live. 13/13 audit PASS.
Backend HEAD 955f7ae, portal HEAD 8f7c1b7, image post-PR#24, Vercel 6Tm6fNvfa.
5 P2/P3 follow-ups from PR #14+#25, 1 retired (timing). PD-S27-TEST-PIN-ROTATION still open.
Rollback anchor: s28-pre-pr22-rollback (image tag) + s28-close (git tag, post this PR merge).
S29 candidate scope: LEAD-SCOPING-CUTOVER (P1) | S28 follow-up sweep | CONTAINERFILE-TRACKED (P1) | Session-0 strategic review.
Audit findings doc: docs/dispatches/PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md — referenceable for any future auth work.
```
