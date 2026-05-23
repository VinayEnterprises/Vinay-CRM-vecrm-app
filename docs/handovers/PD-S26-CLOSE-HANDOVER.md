# S26 Close Handover — PD-S26-AUTH-PHONE-PIN Phase 1.B

**Session:** S26 (VECRM only)
**Date:** 2026-05-23
**Operator:** Ajay Salvi
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (IDE)
**Outcome:** ✅ SHIPPED — phone+PIN authentication live in production across both repos

---

## §1 — Executive summary

S26 added a parallel authentication path (phone + numeric PIN) to the VECRM portal, alongside the existing email + password path shipped in S25. Both paths are now live in production and functionally verified end-to-end.

### What's live at S26 close

- **Backend** (vecrm repo `main` @ `fd69017`): `vecrm.api.login_with_pin(phone, pin)` API endpoint, 4 new VECRM Employee schema columns (`pin_hash`, `failed_pin_attempts`, `pin_locked_until`, `pin_rotated_at`), independent lockout state from password
- **Portal** (vecrm-portal `main` @ `ebd3e69`): Top-of-form segmented control "Email + Password" / "Phone + PIN" tabs, new BFF route `/api/auth/login-pin`, mode-aware login form
- **Both deployed to production** at `crm.vinayenterprises.co.in` (backend) and `app.vinayenterprises.co.in` (portal)

### Both PRs merged

| Repo | PR | Squash-merge SHA | Branch deleted |
|---|---|---|---|
| vecrm-portal | [#9](https://github.com/VinayEnterprises/vecrm-portal/pull/9) | `ebd3e69` | ✓ local + remote |
| vecrm | [#18](https://github.com/VinayEnterprises/Vinay-CRM-vecrm-app/pull/18) | `fd69017` | ✓ local + remote |

---

## §2 — Full session narrative

### Phase 0 — Cold check (8 gates, all PASS)

Verified before any work:

1. Repos + HEADs (vecrm@6c39113 → portal@8165f7a)
2. Production reachable (crm.vinayenterprises.co.in HTTP 200)
3. Auth lifecycle (email+pwd login with `login_path="password"`)
4. VECRM-L8 allocator sha `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` intact at session start (Note: file path subject to S27 re-discovery per OBS-S26-Z)
5. Portal-user invariant (Website User, Submitter+Approver, both desk_access=0)
6. Counter state baseline (TV-26-27=94, EV-26-27=12, INQ-26-27=12, LEAD-26-27=13, undocumented TV-27-28=14)
7. VECRM Employee schema (`password_hash=Data` per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE)
8. Doctype perms (Lead/Inquiry/TravelVoucher across 4 portal roles)

### Phase 1 — Backend recon (R1-R6, all cleared)

8 design decisions banked from source-reads:

1. **R1-A**: `_issue_session` refactor — add `login_path: str` parameter (4-line diff, 1 existing caller)
2. **R2**: passlibctx default `pbkdf2_sha256`, scheme identical to password
3. **R3**: No perm extension needed (`frappe.get_doc` works for shared portal user despite missing tabDocPerm — mechanism remains unexplained, deferred as PD-S26-FRAPPE-PERM-MECHANISM-PROBE)
4. **R4**: 4 new VECRM Employee columns collision-free
5. **R5**: Phone format `+91-<10 digits>` canonical; normalization helper at API boundary
6. **R6**: Independent lockout state — separate `failed_pin_attempts`/`pin_locked_until` from password equivalents
7. Endpoint structure mirrors `login_with_password` for review minimization
8. `db_update()` not `.save()` — bypasses naming-series + hooks, appropriate for high-frequency lockout-counter writes

### Phase 2 — Backend A2 implementation

Single feature commit `ec7edf2` (+250/-4 across 5 files):
- `vecrm/api.py` — new `login_with_pin` endpoint + `_normalize_phone` helper + `_issue_session(login_path: str)` refactor
- `vecrm/hooks.py` — `require_type_annotated_api_methods` enforcement
- `vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json` — 4 new field definitions
- `vecrm/patches/v1_1/add_pin_auth_fields.py` — atomic migration
- `vecrm/patches/v1_1/rollback_add_pin_auth_fields.py` — paired rollback per VECRM-L22

Plus 2 docs commits totaling ~1,628 lines.

### Phase 3 — Backend deploy + Phase 4 production smoke

Backend deployed directly to production VPS (container `vecrm-backend-1`, image `31383918a699`). Smoke against `crm.vinayenterprises.co.in`:

- Smoke 1: empty body → HTTP 401 `missing_input` ✓
- Smoke 2: wrong PIN → HTTP 401 `invalid_credentials` ✓
- Smoke 3: success PIN login → HTTP 200, `"login_path":"pin"` ✓
- Smoke 4: phone normalization variants (`9999900001`, `+91 99999 00001`) both succeed ✓
- Smoke 5: 5-attempt PIN lockout fires; attempt 6 with correct PIN locked; **password login for SAME locked user still succeeds** (R6 independence verified) ✓
- §12.2 regression: email+password returns `"login_path":"password"` (S25 NOT broken) ✓
- Audit roster: 1 account_locked, 1 account_locked_failed, 6 invalid_credentials, 1 missing_input, 3 success — matched predictions exactly

### Phase 5 — Portal recon (PR1-PR5, all cleared)

6 banked design decisions:
1. **U1**: toggle inside existing `LoginForm.tsx` (plain useState, no React Hook Form)
2. PIN BFF mirrors password BFF structurally except endpoint + field names; no field renaming at boundary (backend takes phone/pin directly)
3. `useAuth.login(usr, pwd, mode)` signature widens to dispatch endpoint based on mode
4. `LoginForm.onLogin(usr, pwd, mode)` plumbs mode through
5. `getFrappeUser` unchanged — `login_path` NOT surfaced in UI this iteration (deferred to PD-S26-PORTAL-VECRMSESSION-TYPE)
6. Delete dead `app/api/auth/me/` (closes PD-S26-DEAD-AUTH-ME-ROUTE)

**Key recon finding:** No `app/login/page.tsx` exists. Login UI rendered inline by `AppShell.tsx:26` when user is null. Structurally simpler than dispatch assumed.

### Phase 6 — Portal A2 implementation

Commit `e6d7b9e` (+250/-32 across 4 files):
- `app/api/auth/login-pin/route.ts` — NEW BFF (52 LOC)
- `app/LoginForm.tsx` — mode state, conditional fields, original bottom-link toggle
- `app/useAuth.ts` — mode-aware endpoint dispatch
- `app/api/auth/me/` — DELETED (dead route)

Critical safety provision: `app/api/me/` (live route, used by travel-vouchers) NOT touched; only `app/api/auth/me/` (dead) deleted. §11.1 verification gate ran BEFORE and AFTER.

### Phase 7 — Portal Vercel preview smoke #1 (caught UX defect)

Initial smoke attempts FAILED because operator (Ajay) never clicked "Use PIN instead" toggle — typed phone format into EMAIL field, submissions hit `/api/auth/login` (password endpoint) and got 401. Dispatcher initially false-positive declared a wiring bug (OBS-S26-T), then re-read source and recognized the actual issue: the toggle was a bottom-of-form text link, easily missed.

Real bug = **UX defect: toggle discoverability** (OBS-S26-S promoted from "defer" to "fix this session").

### Phase 8 — U-A addendum (toggle prominence)

Authored addendum (`PD-S26-AUTH-PHONE-PIN-portal-A2-addendum.md`, 400 lines). Replaced bottom text link with top-of-form segmented control. Single file touched (`LoginForm.tsx`); no other changes.

Commit `25bdbb4` (+54/-19 LoginForm.tsx + addendum doc).

### Phase 9 — Portal Vercel preview smoke #2 (full validation)

14/14 checks pass:
- Tabs visible from first paint ✓
- Default = Email + Password ✓
- Tab click swaps active state + fields ✓
- PIN POST → `/api/auth/login-pin` (verified via X-Matched-Path) ✓
- Email POST → `/api/auth/login` (verified via X-Matched-Path) ✓
- Dashboard renders post-login on both paths ✓
- Mobile tap targets ≥44px on 400px viewport ✓
- Light + dark mode both render correctly ✓
- No layout breakage on mobile responsive view ✓

### Phase 10 — Production-main sanity

Operator verified at `app.vinayenterprises.co.in` (production custom domain): tabs visible, both auth paths functional. **S26 portal-side fully validated on production-main.**

### Phase 11 — PRs merged

Both squash-merged with branch deletion per VECRM-L13:
- vecrm-portal#9 → `ebd3e69`
- vecrm#18 → `fd69017`

---

## §3 — Production state at S26 close (canonical baseline for S27 open)

### vecrm-portal repo

```
main: ebd3e69 — S26 Phase 1.B: PD-S26-AUTH-PHONE-PIN — portal UI for PIN login (#9)
prev: 8165f7a — feat(s25): VECRM email-login portal surface (PD-S25-VECRM-AUTH v2 Phase 3) (#8)
prev: b6a5b8d — feat(s24): portal Lead creation form (PD-S24-PORTAL-LEAD-CREATE) (#7)
```

Deployed at `app.vinayenterprises.co.in` via Vercel auto-deploy from main.

### vecrm repo

```
main: fd69017 — S26 Phase 1: PD-S26-AUTH-PHONE-PIN — phone+PIN authentication backend (#18)
prev: 6c39113 — docs(s25): close handover + regenerated pendency register + dependency map + 5 architectural locks (#17)
prev: 5e0df3b — S25 PD-S25-VECRM-AUTH v2 — email+password authentication for VECRM Portal (#16)
```

Deployed to production VPS container `vecrm-backend-1`, image `31383918a699`.

### Production environment

- **VPS**: Contabo Mumbai, `217.216.58.117`, alias `vemio`
- **VPS resources**: 12GB RAM (upgraded from 8GB during S20), 6 CPU cores
- **Container**: `vecrm-backend-1` (vecrm app on Frappe v16.18.2)
- **Site**: `crm.vinayenterprises.co.in`
- **Apps in namespace**: `frappe`, `crm`, `vecrm`
- **Container path convention**: `/opt/vecrm/` on host; `/home/frappe/frappe-bench/` inside container

### Counter state (probed at S26 close)

| Counter | last_value |
|---|---|
| EV-26-27 | 12 |
| INQ-26-27 | 12 |
| LEAD-26-27 | 13 |
| TV-26-27 | 94 |
| TV-27-28 | 14 |

These counters grow continuously with operational use. S27 cold-check should re-probe.

### VECRM Employee schema additions (this session)

4 new columns added via patch `vecrm/patches/v1_1/add_pin_auth_fields.py`:
- `pin_hash` — Data (NOT Password fieldtype per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE). Stores passlibctx pbkdf2_sha256 hash.
- `failed_pin_attempts` — Int, default 0
- `pin_locked_until` — Datetime, nullable
- `pin_rotated_at` — Datetime, nullable

Rollback patch present at `vecrm/patches/v1_1/rollback_add_pin_auth_fields.py` per VECRM-L22.

### Test credentials (DEV ONLY — rotate before real users)

⚠️ **Per VECRM-LOCK-API-KEY-ROTATION: These PINs MUST be rotated before any real customer onboarding.**

| User | Email | Phone | PIN |
|---|---|---|---|
| Test Sales Rep | test.salesrep@vinayenterprises.co.in | +91-9999900001 | 1234 |
| Test HR Approver | test.hr@vinayenterprises.co.in | +91-9999900002 | 5678 |
| Ajay Salvi | ajay@vinayenterprises.co.in | +91-9327547536 | not bootstrapped |

S27 should address PIN rotation as part of any "seed real users" workflow.

---

## §4 — OBS catalog (A through Z, complete S26 inventory)

| ID | Severity | Status | Topic |
|---|---|---|---|
| OBS-S26-A | low | OPEN | Opener prompt docs defects (Gate 4 path, Gate 6 column names) |
| OBS-S26-B | lock candidate | CLOSED (promoted) | Bench-console heredoc + for-loop unreliable; single statements work |
| OBS-S26-C | trans | CLOSED | Transient docker-cp file lock |
| OBS-S26-D | low | OPEN | Container missing `/home/frappe/logs/` and `<site>/logs/` dirs |
| OBS-S26-E | meta | CLOSED | Dispatcher symptom-chasing across 4 rounds before pivoting |
| OBS-S26-F | low | PARTIAL | TV-27-28=14 counter row not in S25 handover (value now captured; origin still unclear) |
| OBS-S26-G | meta | CLOSED | Dispatcher wrote query with unverified column name |
| OBS-S26-H | med | OPEN | VECRM Employee perm floor is [System Manager] only; latent fragility |
| OBS-S26-I | med | OPEN | `frappe.get_doc` succeeds for shared portal user despite missing tabDocPerm; mechanism unexplained |
| OBS-S26-J | meta | CLOSED | Multi-line commit msg via chat paste unreliable; file delivery required |
| OBS-S26-K | meta | CLOSED | Dispatcher JSON snippet shape diverged from on-disk reality |
| OBS-S26-L | meta | CLOSED | Paranoid pre-check command mixed local/remote contexts |
| OBS-S26-M | meta | CLOSED (promoted) | Dispatcher helper-function snippets should mirror existing helpers |
| OBS-S26-N | meta | CLOSED | Bench restart syntax confusion (no `--site` flag) |
| OBS-S26-O | low | CLOSED | Dispatcher should anticipate prior-session branch artifacts |
| OBS-S26-P | meta | CLOSED | Portal recon assumed `app/login/page.tsx` exists; reality was AppShell conditional |
| OBS-S26-Q | meta | CLOSED (promoted) | Dispatcher verification grep patterns structurally wrong in 3/6 cases |
| OBS-S26-R | infra | CLOSED | Next.js `.next/` cache stale validator after route deletion; mitigation `rm -rf .next` |
| OBS-S26-S | UX | CLOSED | Toggle discoverability — fixed via U-A addendum |
| OBS-S26-T | meta | CLOSED | Dispatcher false-positive bug call; failed to read screenshot evidence |
| OBS-S26-U | low | OPEN | Dormant local feature branches accumulate post-PR-merge (housekeeping) |
| OBS-S26-V | meta | CLOSED | Dispatcher PR-body file inventories should be sourced from `git diff --name-status` |
| OBS-S26-W | meta | CLOSED | Single-statement bench-console queries with backticks need `<< 'EOF'` quoted heredoc |
| OBS-S26-X | infra | CLOSED | `docker exec -it ... bash -c` with heredoc stdin throws "input device is not a TTY" |
| OBS-S26-Y | infra | CLOSED | `bench console` (IPython) consumes heredoc but never executes; needs interactive TTY or `bench execute` |
| OBS-S26-Z | low | OPEN | VECRM-L8 allocator sha verification path from session memory references file that doesn't exist; S27 must re-locate |

**Closed this session:** B, C, E, G, J, K, L, M, N, O, P, Q, R, S, T, V, W, X, Y
**Still open:** A, D, F (partial), H, I, U, Z (8 items, none blocking)

---

## §5 — Lock register update

### Locks honored throughout S26 (no changes)

- VECRM-L8 (allocator sha verification — file path needs S27 re-discovery per OBS-S26-Z)
- VECRM-L13 (squash-merge + branch deletion)
- VECRM-L22 (atomic schema migration + paired rollback file)
- VECRM-L24 (file-scope scp; no `scp -r` for file edits)
- VECRM-L26 (`\d <table>` before any SQL probe)
- VECRM-L27 (verify history/inventory at every layer-transition checkpoint)
- VECRM-LOCK-FILE-DELIVERY-NOT-PASTE
- VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE
- VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE
- VECRM-LOCK-PORTAL-USER-ROLES
- VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE
- VECRM-LOCK-VPS-DESTRUCTIVE-OPS
- OBS-S71-A (git branch --show-current before/after commit-bearing ops)
- VECRM-LOCK-API-KEY-ROTATION (test PINs must rotate before real users)

### New locks promoted at S26 close

**VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE (PROMOTED from draft)**

After 5x recurrence (OBS-S26-K, M, Q, plus 2 portal-A2 banking instances): Dispatcher code snippets in all phases — implementation code, CSS, helper functions, verification grep patterns — are illustrative only. Executor MUST read existing equivalent files and mirror their shape (idioms, token names, structural patterns, defensive checks). Deviations from dispatch snippets in favor of existing-code-mirror are pre-approved and expected. Risk register must include verification gates that anticipate at least one banked deviation per A2 commit.

**VECRM-LOCK-BENCH-CONSOLE-SCRIPTED-EXECUTION (PROMOTED, replacing -SINGLE-STATEMENT draft)**

After OBS-S26-B, W, X, Y: `bench console` (IPython REPL) cannot reliably execute heredoc-supplied Python. For scripted probes, use one of:

1. **Direct mysql client** inside the container (preferred for SELECT queries):
   ```bash
   docker exec vecrm-backend-1 bash -c 'mysql -h <host> -u <db_name> -p<pass> <db_name> -e "SELECT ..."'
   ```
2. **`bench execute` with a registered function** (for Frappe ORM logic — requires the function to live in the vecrm app)
3. **Save script to `/tmp/probe.py` inside container, then execute via bench's Python**:
   ```bash
   docker exec vecrm-backend-1 bash -c 'cd /home/frappe/frappe-bench && bench --site crm.vinayenterprises.co.in execute /tmp/probe.py'
   ```

NEVER use `<<<` here-string with backticks (shell-escape conflicts). NEVER use `docker exec -it` with heredoc stdin (TTY mismatch).

---

## §6 — Architectural decisions banked this session (cross-reference for S27)

### Backend

- API endpoint names match `login_with_password` convention; PIN endpoint is `login_with_pin`
- Session shape extended with `login_path: "password" | "pin"` field; queryable via `get_session_employee`
- Audit log gets new `path` discriminator column (`"password"` | `"pin"` | `NULL` for pre-S26 rows)
- Password and PIN lockout state are INDEPENDENT (separate fields, separate enforcement)
- Phone normalization at API boundary; canonical format `+91-<10 digits>`; helper accepts variants
- Type annotations required on all API methods (Frappe v16 `require_type_annotated_api_methods`)
- Patch files in `vecrm/patches/v1_1/` registered via `vecrm/patches.txt` (NOT custom migration framework)

### Portal

- AppShell renders LoginForm inline when user is null (no dedicated `/login` route)
- Mode state (`"email" | "pin"`) drives conditional field rendering + endpoint dispatch
- BFF routes proxy to Frappe with Set-Cookie relay
- `useAuth.login(id, secret, mode)` is the single auth dispatch function
- Top-of-form segmented control is the canonical mode-switch UX (U-A pattern from S26)
- CSS palette mirrors `TopBar.tsx`'s `.topbar-nav-link--active` for active states
- aria-pressed semantics on tabs (NOT full ARIA tablist pattern)

---

## §7 — Phase 1.B work that did NOT ship in S26 (deferred)

Carefully scoped out during S26 to keep the session focused:

- **`login_path` UI surfacing**: `getFrappeUser` still returns just `name`; richer `VecrmSession` return type deferred to PD-S26-PORTAL-VECRMSESSION-TYPE
- **Auto-detect input format** (Option U-C): single field that detects email-vs-phone and swaps second field — deferred to PD-S27-AUTH-LOGIN-AUTODETECT pending real-user feedback on U-A toggle
- **Logout audit path discrimination**: `auth.logout` audit rows still record `path=None`; PD-S26-AUTH-LOGOUT-PATH-RECORD
- **Frappe perm mechanism investigation**: why `frappe.get_doc` works for shared portal user — PD-S26-FRAPPE-PERM-MECHANISM-PROBE
- **VECRM Employee perm floor hardening**: currently `[System Manager]` only — PD-S26-VECRM-EMPLOYEE-PERM-FLOOR
- **Test PIN rotation**: dev creds `1234`/`5678` still active; rotate at S27 open when real users seeded

---

## §8 — Vercel deployment notes

Portal main `ebd3e69` auto-deployed via Vercel. Production custom domain: `app.vinayenterprises.co.in` (verified during Phase 10 sanity check). Vercel preview URLs follow pattern `vecrm-portal-git-<branch-slug>-vinay-enterprises-projects-5379af16.vercel.app`.

Build pipeline: `rm -rf .next && npm run build` (per OBS-S26-R, .next cache can hold stale validators after route deletions). Vercel builds from scratch so this is only a local-build concern.

---

## §9 — Files added/modified across S26 (canonical inventory)

### vecrm repo

```
New:
  vecrm/patches/v1_1/add_pin_auth_fields.py                          (+48)
  vecrm/patches/v1_1/rollback_add_pin_auth_fields.py                 (+30)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-A2-dispatch.md               (+893)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-recon-dispatch.md            (+413)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-recon-findings.md            (+322)

Modified:
  vecrm/api.py                                                       (+140 -4)
  vecrm/patches.txt                                                  (+1)
  vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json             (+35)
```

### vecrm-portal repo

```
New:
  app/api/auth/login-pin/route.ts                                                 (+52)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-portal-recon-dispatch.md                  (+276)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-portal-recon-findings.md                  (+146)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-portal-A2-dispatch.md                     (+693)
  docs/dispatches/PD-S26-AUTH-PHONE-PIN-portal-A2-addendum.md                     (+400)

Modified:
  app/LoginForm.tsx                                                  (+219 -55)
  app/useAuth.ts                                                     (+8 -2)

Deleted:
  app/api/auth/me/route.ts                                           (-20)
```

Total documentation: ~3,143 lines preserved for audit trail in docs/dispatches/.

---

## §10 — Acknowledgments and notes

- The Phase 5 portal smoke #1 → false-positive bug call → re-read → real UX defect surfacing → U-A addendum cycle was an instance of the dispatch/executor/operator pattern catching its own errors via discipline rather than missing them. The recon-first methodology paid off: the wiring code was correct on first try; the only iteration was UX, caught fast via smoke discipline.
- 5 separate OBS this session relate to dispatcher-vs-reality precision (K, M, Q, V, W). The promotion of VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE captures the pattern formally for future sessions.
- 4 separate OBS relate to bench-console execution gotchas (B, W, X, Y). The promotion of VECRM-LOCK-BENCH-CONSOLE-SCRIPTED-EXECUTION captures the resolution.

---

**End of S26 close handover.**

Refs: PD-S26-AUTH-PHONE-PIN, vecrm-portal#9, vecrm#18.
