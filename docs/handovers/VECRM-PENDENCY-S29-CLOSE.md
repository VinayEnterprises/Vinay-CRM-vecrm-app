# VECRM-PENDENCY-S29-CLOSE

**Supersedes:** `VECRM-PENDENCY-S28-CLOSE.md`
**Generated:** 2026-05-25 (S29 close)

---

## §1 — Format

Each PD entry has: ID, priority (P0/P1/P2/P3), session of origin, effort estimate, depends-on list, brief description, status.

Statuses: `OPEN` (active), `BLOCKED` (waiting on something), `PROGRESS` (partially shipped), `CLOSED` (done), `DEFERRED` (acknowledged but not scheduled).

---

## §2 — Closed during S29

| PD ID | Status | Closed via |
|---|---|---|
| PD-S28-LEAD-SCOPING-CUTOVER | CLOSED | PR #16 (vecrm-portal, `f269563`) |
| PD-S27-PORTAL-SCOPING-PATTERN | CLOSED | Pattern doc shipped in PR #16 |
| PD-S29-ACCOUNT-SELF-SERVICE | CLOSED | PR #27 (vecrm) + PR #18 (vecrm-portal) |
| PD-S29-AUTH-WRITE-PATTERN-FIX | CLOSED | PR #29 (vecrm) — surfaced + fixed same session |
| PD-S29-PIN-LOGIN-BROKEN | CLOSED | Absorbed by PD-S29-AUTH-WRITE-PATTERN-FIX (same root cause) |
| PD-S26-PORTAL-VECRMSESSION-TYPE | CLOSED | Absorbed by PR #18 `VecrmSession` type extension |
| PD-S27-TEST-PIN-ROTATION | CLOSED | No longer relevant; PIN can now be rotated via /account |

---

## §3 — Active P1 items (must address in S30 or before real customer onboarding)

### PD-S29-PIN-INPUT-SEGMENTED-6BOX (Workstream B)

- **Status:** OPEN, deferred from S29
- **Priority:** P2 (UX improvement; backend policy already enforced by S29 PR #29 fix)
- **Effort:** ~2-3 hrs
- **Origin:** S29 Phase A recon (PR #15)
- **Description:** Replace single masked PIN inputs with 6-segmented input component across LoginForm + /set-pin (new + confirm) + /account ChangePinForm. Also tighten `complete_pin_reset` (currently 4-6 → exactly-6) and add length check to `login_with_pin` (currently no length check) for full policy A consistency across all PIN entry surfaces.
- **Depends on:** None
- **Recon status:** Findings doc shipped in PR #15

### PD-S29-LEAD-FORM-FIELDS (Workstream D)

- **Status:** OPEN, deferred from S29
- **Priority:** P2 (operator workflow polish)
- **Effort:** ~2 hrs
- **Origin:** S29 σ-4 dispatch
- **Description:** Add 3 mandatory fields to New Lead form: `contact_number`, `contact_email`, `meeting_brief`. Migration approach LOCKED at recon: schema-permissive (nullable cols) + code-mandatory + forward-only. Existing 14 Leads stay NULL; form-level mandatory enforced in `vecrm.api.create_lead` + portal create form. Lead detail page renders "—" for null.
- **Depends on:** None
- **Recon status:** Not yet authored; first S30 recon dispatch

---

## §4 — Active P2 items

### PD-S29-INQUIRY-SCOPING

- **Status:** OPEN
- **Priority:** P2
- **Effort:** ~2-3 hrs (recon + B-phase)
- **Origin:** S29 banked observation (OBS-S29-X, OBS-S29-AA)
- **Description:** Per-rep Inquiry scoping (parallel to Lead scoping shipped in S29 PR #16). Per OBS-S29-X: writing inquiries also has `inquiry_owner=Administrator` write-path issue that needs investigation. Reusing the scoping helpers `getScopedLeadFilter`/`canReadLead` pattern from `lib/scoping.ts` is the canonical path.
- **Depends on:** None

### PD-S28-FORGOT-PIN-DISPLAY-PLUS-MANGLE

- **Status:** OPEN (carried from S28)
- **Priority:** P2
- **Effort:** ~30 min
- **Origin:** S28 close
- **Description:** Intermittent `+` → ` ` (space) mangling in PIN reset confirmation card display.

### PD-S28-AUTH-PHONE-PREFIX-LOCK

- **Status:** OPEN (carried from S28)
- **Priority:** P2
- **Effort:** ~1 hr
- **Origin:** S28 close
- **Description:** Lock phone input to fixed `+91-` prefix in LoginForm and ForgotPasswordForm phone tab; eliminates URL encoding edge cases.

### PD-S28-LOGIN-ERROR-UX

- **Status:** OPEN (carried from S28)
- **Priority:** P2
- **Effort:** ~1 hr
- **Origin:** S28 close
- **Description:** Replace "Frappe responded 401" inline error with human-readable copy. Tonight's smokes again surfaced how confusing this raw error is for users.

---

## §5 — Active P3 items

### PD-S28-ADMIN-PIN-SET-UI

- **Status:** OPEN (carried from S28)
- **Priority:** P3
- **Effort:** ~2-3 hrs
- **Origin:** S28 close
- **Description:** Frappe Desk button to set/reset employee PIN via admin UI. **Partially obsoleted by S29:** the /account flow now allows users to change their own PIN once it's bootstrapped. But admin-side reset for forgotten PIN before user logs in is still needed. Deferred until real users exist.

### PD-S28-LOGINFORM-PIN-MINLENGTH

- **Status:** OPEN (carried from S28)
- **Priority:** P3
- **Effort:** ~15 min
- **Origin:** S28 close
- **Description:** Add `minLength={6}` to PIN input in LoginForm. Absorbs into PD-S29-PIN-INPUT-SEGMENTED-6BOX when that ships.

### PD-S29-CANDIDATE-RESET-RATELIMIT-SHARED

- **Status:** OPEN (carried from S28 / S29)
- **Priority:** P3
- **Effort:** ~1 hr
- **Origin:** S28 close
- **Description:** Reset rate limit is per-`reset_for` (password vs PIN), allowing 6 total reset requests per employee per 15-minute window. Consider shared rate limit (3 total) since both surface to the same user.

### PD-S29-PORTAL-VECRMSESSION-EXTENSION-FUTURE

- **Status:** OPEN
- **Priority:** P3
- **Effort:** TBD
- **Origin:** S29 PR #18 (banked, not blocking)
- **Description:** If future Account fields (notification prefs, theme, language) need to be added, they may not belong in `VecrmSession` and warrant introducing the (β) endpoint approach from Workstream C recon. Bank as a triage point when first such field is requested.

### PD-S29-DOCS-DRIFT (deferred runbook update)

- **Status:** OPEN
- **Priority:** P3
- **Effort:** ~30 min
- **Origin:** S29 banked observation
- **Description:** PD-S27-DEPLOY-RUNBOOK should be updated to reflect tonight's learnings:
  - Add OBS-S29-KK note about benign "orphan containers" warning during `docker compose up --force-recreate <service>`
  - Add OBS-S29-JJJ pattern for `bench console < file.py` script execution
  - Add S25 canonical write pattern reference (per OBS-S29-CCC)

### PD-S29-AUTH-AUDIT-VOCABULARY-NO-PIN

- **Status:** OPEN
- **Priority:** P3
- **Effort:** ~15 min
- **Origin:** S29 banked observation (OBS-S29-TT)
- **Description:** `change_pin` emits reason `current_mismatch` when `pin_hash` is null/empty (genuinely no-PIN-configured case). Should be `no_pin_configured` to match `login_with_pin`'s vocabulary. Symmetric fix for `change_password`. Pure audit-log clarity improvement; no user-visible impact.

---

## §6 — Strategic backlog (Session-0 items, multi-session efforts)

### Session-0-A — VECRM portal usability cohort testing
- Manual operator testing with real Sales Reps once 2-3 are hired
- Identifies workflow gaps invisible to solo-founder testing

### Session-0-B — Tally → ERPNext migration
- Deferred per multiple sessions
- API-driven migration only (custom UI rejected post-audit)
- Plan to engage Ahmedabad ERPNext partner for opening-balance recon + GST account restructuring

### Session-0-C — VEMIO ↔ VECRM CRM Lead-to-Project handoff
- When MSP customer signs up via Lead-converted-to-Inquiry-converted-to-Quote-converted-to-PO, need handoff into VEMIO tenant provisioning
- Multi-week effort; not P-track candidate

### Session-0-D — VECRM dashboard widgets
- Current dashboard is bare; needs role-aware widgets (Sales Rep sees own Leads/Inquiries; Admin sees aggregate)
- Estimated 5-8 hrs over 2 sessions

---

## §7 — Closed-but-noted (S29 specifically)

These were closed in S29 but worth keeping visible for next-1-or-2 sessions:

| PD ID | Closed in | Note |
|---|---|---|
| PD-S29-AUTH-WRITE-PATTERN-FIX | PR #29 | First time PIN auth has ever worked in VECRM production. Bug had been latent since S28 ship. |
| PD-S29-ACCOUNT-SELF-SERVICE | PR #27 + PR #18 | First end-user-facing portal feature with both backend + frontend in same session |
| PD-S28-LEAD-SCOPING-CUTOVER | PR #16 | Substrate helpers (`scoping.ts`, `roles.ts`, `auth-ssr.ts`) consumed by subsequent workstreams |

---

## §8 — Total ledger

| Category | Count |
|---|---|
| **Closed in S29** | 7 |
| **OPEN P1** | 0 |
| **OPEN P2** | 5 |
| **OPEN P3** | 5 |
| **Strategic backlog** | 4 |
| **TOTAL active PDs** | 10 |

Trend: closed 7, opened 0 new high-priority. PD inventory shrinking — good.

---

**End of pendency register.**

Next review: S30 close.
