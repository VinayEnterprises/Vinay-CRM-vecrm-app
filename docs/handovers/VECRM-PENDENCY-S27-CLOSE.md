# VECRM-PENDENCY-S27-CLOSE

**Supersedes:** `VECRM-PENDENCY-S26-CLOSE.md`
**Generated:** 2026-05-24 (S27 close)

---

## §1 — Format

Each PD entry has: ID, priority (P0/P1/P2/P3), session of origin, effort estimate, depends-on list, brief description, status.

Statuses: `OPEN` (active), `BLOCKED` (waiting on something), `PROGRESS` (partially shipped), `CLOSED` (done), `DEFERRED` (acknowledged but not scheduled).

---

## §2 — Closed during S27

| PD ID | Status | Closed via |
|---|---|---|
| PD-S26-AUTH-LOGOUT-PATH-RECORD | CLOSED | PR #19 (`4f1d4a3`) |
| PD-S26-DOCS-DRIFT | CLOSED | PD-S27-DEPLOY-RUNBOOK now exists as canonical procedure with §12 worked example |
| PD-S27-LEAD-SCOPING (schema half) | PROGRESS → schema CLOSED | PR #20 (`5cd656e`) ships substrate; per-rep scoping logic deferred |
| PD-S28-AUTH-RESET-INFRA | CLOSED | Recon findings + addendum committed (`56d520e` + `22bf471`) |
| PD-S28-AUTH-RESET-SCHEMA | CLOSED | PR #21 (`6d46b0d`) ships substrate |

---

## §3 — Active P1 items (must address in S28 or before real customer onboarding)

### PD-S28-AUTH-RESET-FLOW (parent)

- **Status:** OPEN, schema substrate shipped in S27
- **Effort:** 9-11 hrs remaining across 6 sub-PDs
- **Origin:** S27 recon
- **Sub-PDs (all dispatches authored, held in S27 close commit):**
  - PD-S28-AUTH-RESET-BACKEND-API (2.5-3 hrs)
  - PD-S28-AUTH-RESET-EMAIL-MECHANISM (1.5 hrs)
  - PD-S28-AUTH-RESET-PORTAL-BFF (2 hrs)
  - PD-S28-AUTH-RESET-PORTAL-UI (2-2.5 hrs)
  - PD-S28-AUTH-RESET-EMAIL-TEMPLATE (45 min - 1 hr)
  - PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE (3.5-4 hrs)
- **Description:** End-to-end password and PIN reset flow — Forgot form → emailed link → set new credential → log in. Portal-side Graph email (Vemio pattern mirror), Frappe-side token storage + credential write.
- **User-visible impact:** Required before any real customer onboarding; otherwise locked-out users have no recovery path.

### PD-S28-LEAD-SCOPING-CUTOVER

- **Status:** OPEN, substrate from PR #20 in place
- **Effort:** ~4.5 hrs
- **Origin:** S27 (substrate shipped, scoping logic deferred per scope discipline)
- **Description:** Wire per-rep scoping into Lead list/detail BFF routes. Reps see only `creating_employee = self.phone` rows; HR Approvers and System Managers see all. Lead detail check at BFF and at backend API layer (defense in depth).
- **Latent privacy concern:** Currently any portal-authenticated user can read any Lead via the `/api/resource/VECRM Lead` proxy. Scope discipline kept this out of S27, but P1 because it's a real privacy gap.

### PD-S28-CONTAINERFILE-TRACKED

- **Status:** OPEN
- **Effort:** 1.5 hrs
- **Origin:** S27 (OBS-S27-K, T)
- **Description:** Commit `/opt/vecrm/images/custom/Containerfile` into a tracked repo (vecrm-infra or similar) with a paired `sha-pins.json` (or similar) tracking the canonical voucher_counter.py sha. Update PD-S27-DEPLOY-RUNBOOK to reflect the new flow.
- **Why P1:** Containerfile is currently a critical production artifact living only on the VPS. Loss of VPS = loss of build definition. Also: sha-gate stale-text fix (OBS-S27-X) belongs in this PD.

### PD-S27-TEST-PIN-ROTATION

- **Status:** OPEN
- **Effort:** 15 min
- **Origin:** S26
- **Description:** Test rep PINs (Test Sales Rep `1234`, Test HR Approver `5678`) MUST be rotated to operator-chosen non-trivial values BEFORE any real customer onboarding. Currently using documented test values from S26 setup — fine for development, unsafe for production.
- **Trigger:** Before the first non-Ajay employee gets a VECRM Employee row.

---

## §4 — Active P2 items

### PD-S27-L8-REBANK

- **Status:** OPEN
- **Effort:** 45 min
- **Origin:** S27 cold-check Gate 4
- **Description:** VECRM-L8.md references an outdated path / lacks the current canonical sha (`91556a7d07...`). Update to current values; ensure the Containerfile sha-gate references the same canonical that VECRM-L8 declares.

### PD-S26-FRAPPE-PERM-MECHANISM-PROBE

- **Status:** OPEN (partially resolved by S27 cold-check Probe 5.1)
- **Effort:** 1-2 hrs
- **Origin:** S26
- **Description:** Investigate Frappe v16's permission mechanism when `frappe.get_doc()` is called from API methods. The shared-principal model (VECRM-LOCK-PORTAL-SHARED-PRINCIPAL) means the portal user has broad doctype access — verify this matches our intent and doesn't unintentionally expose data.

### PD-S26-VECRM-EMPLOYEE-PERM-FLOOR

- **Status:** OPEN
- **Effort:** 1 hr
- **Origin:** S26
- **Description:** Tighten read permissions on `tabVECRM Employee` so the shared portal user can't read all employee phone numbers as a side effect of needing to read its own. Add If Owner condition, or scope via custom permission method.

### PD-S26-PORTAL-VECRMSESSION-TYPE

- **Status:** OPEN
- **Effort:** 2-3 hrs
- **Origin:** S26
- **Description:** Richer TypeScript return type from `getFrappeUser()` so consumers see `vecrm_employee_phone`, `vecrm_login_path`, etc., as first-class fields rather than ad-hoc casts from `session.data`.

### PD-S27-PORTAL-SCOPING-PATTERN

- **Status:** OPEN
- **Effort:** 30 min
- **Origin:** S27 (documentation, depends on PD-S28-LEAD-SCOPING-CUTOVER)
- **Description:** Write up the scoping helper pattern once D2 establishes it. Becomes the canonical pattern for any future "per-rep scoped" endpoint on the portal.

---

## §5 — Active P3 items

### PD-S25-CONTAINER-LOGS-DIRS

- **Status:** OPEN
- **Effort:** 1 hr
- **Origin:** S25
- **Description:** Add explicit `RUN mkdir -p /home/frappe/frappe-bench/logs` to Containerfile to avoid runtime log-dir creation race.

### PD-S26-LOCAL-BRANCH-HOUSEKEEPING

- **Status:** OPEN
- **Effort:** 10-15 min
- **Origin:** S26 (refreshed S27 — added `feat/s27-login-ua-polish` and `feat/s28-auth-reset-schema` to the cleanup list)
- **Description:** Delete dormant local feature branches across vecrm and vecrm-portal. `git remote prune origin` to clean up tracking branches for deleted upstreams.

### PD-S25-COUNTER-ORIGIN-S26F

- **Status:** OPEN
- **Effort:** 30 min
- **Origin:** S26
- **Description:** TV-27-28 counter was at 14 at S26 close with no observed user-initiated travel vouchers. Investigate whether seed/migration created these. No functional impact.

---

## §6 — Deferred (acknowledged, not scheduled)

### PD-S27-A1-LEAD-DETAIL-BFF (deferred to S28 LEAD-SCOPING-CUTOVER)

The Lead detail BFF route is one of the unscoped surfaces PD-S28-LEAD-SCOPING-CUTOVER addresses.

### PD-S27-PORTAL-LIST-PAGES (deferred to S28+)

Lead list, Inquiry list, Travel Voucher list pages on vecrm-portal are not yet built. Currently the only flow is "create new lead" via `/leads/new`. List pages would benefit reps but aren't blocking.

### OBS-S28+-VEMIO-EMAIL-DUPLICATION (banked as W in OBS catalog)

Vemio's Graph email mechanism is now duplicated across 4 locations after S28's PD-S28-AUTH-RESET-EMAIL-MECHANISM ships. Long-term, refactor into a shared library or service. Deferred indefinitely until duplication actually hurts.

---

## §7 — Counter state

| Counter | S26 close | S27 close | Notes |
|---|---|---|---|
| EV-26-27 | 12 | 12 | Unchanged |
| INQ-26-27 | 12 | 12 | Unchanged |
| LEAD-26-27 | 13 | 14 | +1 (Checkpoint C new lead) |
| TV-26-27 | 94 | 94 | Unchanged |
| TV-27-28 | 14 | 14 | Unchanged (PD-S25-COUNTER-ORIGIN-S26F P3) |

Reset token rows: 0 (new doctype, no production tokens emitted yet).

---

## §8 — Full S27 observation catalog (referenced in close handover §5)

| OBS ID | Description | Disposition |
|---|---|---|
| OBS-S27-A | Opener HEAD lag on Mac vs origin | Closed (one-time, operator routine) |
| OBS-S27-B | login_path response shape inconsistency | Banked → covered by S28 reset flow re-touch |
| OBS-S27-C | macOS resource-fork artifacts in rsync | Closed (excludes prevent) |
| OBS-S27-D | Cold-check Gate 5 model gap (audit log perms) | Defer to S28+ opener template improvement |
| OBS-S27-E | Schema column name drift (`creating_employee` vs `created_by_employee`) | Closed (mitigated in PR #20 commit message) |
| OBS-S27-F | Latent privacy bug on Lead list/detail unscoped | Promoted to PD-S28-LEAD-SCOPING-CUTOVER |
| OBS-S27-G | S24 shipped more than docs noted | Closed (S24 docs back-filled in close commit) |
| OBS-S27-H | Container image drift (lost tags) | Closed (rollback-tag discipline restored) |
| OBS-S27-I | `vecrm_*` prefix convention | Closed (documented in dependency map) |
| OBS-S27-J | `reload_doc` pattern in patches | Closed (locked into PR #20/21 pattern) |
| OBS-S27-K | Deploy mechanism undocumented | Closed via PD-S27-DEPLOY-RUNBOOK |
| OBS-S27-L | VPS path naming confusion | Closed via VECRM-LOCK-VPS-PATH-CONVENTIONS |
| OBS-S27-M | `.git` presence violates S13 lock | Closed (excluded in rsync, defense-in-depth Containerfile rm) |
| OBS-S27-N | Vendor was Mac-rsynced (different file ownership) | Closed (documented; no functional impact) |
| OBS-S27-O | Vendor drift — patches/v1_1 missing in vendor vs container | Closed (rsync --delete enforces parity) |
| OBS-S27-P | S20-era `66118d7` HEAD reference | Closed (historical) |
| OBS-S27-Q | Vendor working tree dirty | Closed (rsync cleared) |
| OBS-S27-R | Multi-shell paste error | Closed (operator-side hygiene) |
| OBS-S27-S | Containerfile sha stale | Closed via Containerfile sed-update + VECRM-LOCK-CONTAINERFILE-SHA-MAINTENANCE |
| OBS-S27-T | Containerfile not under version control | Promoted to PD-S28-CONTAINERFILE-TRACKED |
| OBS-S27-U | Rollback-tag-before-recreate discipline | Closed (locked into PD-S27-DEPLOY-RUNBOOK §2.1) |
| OBS-S27-V | Executor lacks `conversation_search` | Closed (workaround documented; dispatcher-fill for past-session lookups) |
| OBS-S27-W | Vemio email pattern duplicated | Banked → P3 indefinite |
| OBS-S27-X | Containerfile gate "6 controllers" stale | Banked → PD-S28-CONTAINERFILE-TRACKED |
| OBS-S27-Y | Patch docstring print verbose output | Closed (documented as informational) |
| OBS-S27-Z | Frappe v16 metadata columns (`_user_tags` etc) | Closed (documented in runbook) |
| OBS-S27-AA | Frappe Data field min-length auto-bump to 64 | Banked → revisit at PD-S28-AUTH-RESET-BACKEND-API author time |

27 observations total. Above-historical-average for a session; reflects the deploy-mechanism reconstruction surface area.

---

## §9 — Cross-references

- Close handover narrative: `docs/handovers/PD-S27-CLOSE-HANDOVER.md`
- Dependency map: `docs/handovers/VECRM-DEPENDENCY-S27-CLOSE.md`
- Deploy runbook: `docs/runbooks/PD-S27-DEPLOY-RUNBOOK.md`
- S28 opener: `docs/handovers/S28-OPENER-PROMPT.md`
- 6 S28 dispatches: `docs/dispatches/PD-S28-AUTH-RESET-*-dispatch.md`
- Recon findings: `docs/dispatches/PD-S28-AUTH-RESET-INFRA-recon-findings.md` + `...-ADDENDUM.md`

**End of pendency register.**

---

## §10 — S28 mid-session updates (appended in-flight)

**Appended:** 2026-05-24, S28 opening.
**Status of this section:** Living notes during S28. Promoted/closed items will be reflected in `VECRM-PENDENCY-S28-CLOSE.md` at S28 close, which supersedes this entire file.

### §10.1 — Pendency additions / status changes

#### PD-S20-KRUNAL-UAT — promoted to explicit deferred entry

- **Status:** OPEN, async, external-trigger
- **Effort:** Krunal's time, not operator's
- **Origin:** S19 carried through S20, S21, S26, S27 implicitly
- **Trigger:** First production Lead-to-Inquiry conversion firing Q9 management email to Krunal
- **Description:** Async colleague review of Q9 email content (subject pipe-separator, 10 body fields). Scripted-caller verified since S19; awaiting human-eyes UAT.
- **Action when feedback arrives:** Small content/template PR if revisions needed. No Claude scheduling until then.
- **Why surfacing now:** Implicit-carry across 6 sessions; deserves explicit register slot per S28 past-conversation sweep.

#### OBS-S27-AA — closed, confirmed benign

- **Was:** Banked, "revisit at PD-S28-AUTH-RESET-BACKEND-API author time"
- **Now:** CLOSED. Confirmed at S28 Gate 7. `ip_address` declared `length: 45` in `vecrm_auth_reset_token.json`; actual table column is `varchar(64)` per Frappe v16's Data field min-length floor. Functionally benign: IPv6 textual representation max is 45 chars; 64 is more than sufficient. No action needed. Pattern documented in PD-S27-DEPLOY-RUNBOOK section 8.1.

### §10.2 — Session-0 strategic backlog, reference pointer

The Session-0 strategic scope items remain unscheduled and tracked outside the active pendency register. Last comprehensively surfaced in S22 mid-session and acknowledged through S26 close. Items:

1. Voucher / approval workflow — the keystone unbuilt piece
2. Approval-chain business decision — engineer to reporting manager vs direct-to-operator; same question for sales reps
3. Two distinct user roles — Sales Rep vs Field Engineer surface differentiation
4. Sales Visit doctype portal UI
5. Weekly meeting report
6. PWA-on-phone validation — never installed on actual phone
7. OTP auth replacing password placeholder — MSG91 SMS+WhatsApp pluggable, Phase 4 originally
8. Priority 1-5 bar-gradient UI — BNI visual language

**Decision:** Defer surfacing for active scheduling until S28 reset-flow ships and S29 scope is being chosen. Items 2 (approval-chain) and 3 (role split) are blocking-decision items that must be answered before item 1 can be designed. Recommend S29 opener includes a "Session-0 strategic backlog review" gate.

### §10.3 — S28 in-flight items: parent plus 6 sub-PDs

Mirrored from PD-S27-CLOSE-HANDOVER section 9 plus close-commit dispatch files. Status will advance as each sub-PD merges and deploys.

#### PD-S28-AUTH-RESET-FLOW parent

- **Status:** IN PROGRESS — S28 active scope, Option α
- **Schema substrate:** Shipped S27 PR #21 (`6d46b0d`). `tabVECRM Auth Reset Token` doctype live, 0 rows.
- **Backend + portal:** In-flight via 6 sub-PDs below.

| Sub-PD | Effort | Status | Notes |
|---|---|---|---|
| PD-S28-AUTH-RESET-BACKEND-API | 2.5-3 hrs | IN PROGRESS | 4 whitelist methods + `vecrm/utils/auth_reset.py` |
| PD-S28-AUTH-RESET-EMAIL-MECHANISM | 1.5 hrs | IN PROGRESS | vecrm-portal `lib/email.js` mirroring Vemio's pattern |
| PD-S28-AUTH-RESET-EMAIL-TEMPLATE | 45 min - 1 hr | NOT STARTED | HTML template modules; depends on EMAIL-MECHANISM |
| PD-S28-AUTH-RESET-PORTAL-BFF | 2 hrs | NOT STARTED | 3 routes; depends on BACKEND-API + EMAIL-MECHANISM |
| PD-S28-AUTH-RESET-PORTAL-UI | 2-2.5 hrs | NOT STARTED | Forgot forms + set-password/set-pin pages; depends on PORTAL-BFF |
| PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE | 3.5-4 hrs | NOT STARTED | Final gate; depends on ALL prior sub-PDs |

**Operator prep status, S28-opening, 2026-05-24:**

- ✅ Vercel env vars set on vecrm-portal Production: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_NOREPLY_VECRM`. Sourced from vemio-dashboard env, reuses vemio-email-sender Azure AD app reg.
- ✅ Branch housekeeping clean on both repos: Mac vecrm and vecrm-portal each have only `main` plus standard remote refs.
- ⏳ **PD-S27-TEST-PIN-ROTATION** — outstanding. Latest safe moment: before SECURITY-REVIEW-SMOKE section 2.1, which exercises the test rep account E2E. 15 min operator work.

### §10.4 — Cold-check gates at S28 open: all PASS

All 8 gates from `docs/operating-patterns/cold-check-template.md` cleared at S28 open. Production state matches S27-CLOSE baseline exactly:

- Mac vecrm HEAD `083cd37`, vecrm-portal HEAD `8540794`, both clean
- VPS `vecrm-backend-1` Up, image `a05637cd2be5`, HTTP/2 200
- `vecrm-custom:s27-pre-pr21-rollback` tag present — rollback anchor
- voucher_counter.py sha matches VECRM-L8 canonical `91556a7d07...`
- Vendor parity confirmed — `vecrm_auth_reset_token` doctype dir plus patch registered
- `tabVECRM Auth Reset Token` schema verified — 5 functional plus 4 Frappe v16 metadata cols, 0 rows, `token_hash` UNI
- Frappe v16 `require_type_annotated_api_methods` site-wide setting confirmed active — `[True]`

---
