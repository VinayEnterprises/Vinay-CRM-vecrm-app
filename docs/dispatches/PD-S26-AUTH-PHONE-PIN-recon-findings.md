# PD-S26-AUTH-PHONE-PIN — Recon Findings (R1–R6)

**Session:** S26 Phase 1 recon close
**Dispatcher:** Claude (chat)
**Executor:** Operator (bench-console queries) + Claude (chat-driven source-reads)
**Operator:** Ajay Salvi
**Date:** 2026-05-23
**Recon dispatch:** `docs/dispatches/PD-S26-AUTH-PHONE-PIN-recon-dispatch.md`
**Outcome:** ✅ All 6 R-questions cleared; A2 implementation dispatch can proceed.

---

## R4 — VECRM Employee column inventory ✅ PASS

**Probe output (verbatim):**
```
['name', 'creation', 'modified', 'modified_by', 'owner', 'docstatus', 'idx',
 'employee_name', 'vecrm_phone', 'vecrm_email', 'role', 'vecrm_base_city',
 'reporting_approver', 'vecrm_account_status', '_user_tags', '_comments',
 '_assign', '_liked_by', 'password_hash', 'failed_password_attempts',
 'locked_until', 'last_login_at']
```

**Adjudication:**

| Target column for PIN | Present? | Verdict |
|---|---|---|
| `pin_hash` | ❌ absent | ✅ collision-free |
| `failed_pin_attempts` | ❌ absent | ✅ collision-free |
| `pin_locked_until` | ❌ absent | ✅ collision-free |
| `last_pin_login_at` | ❌ absent | ✅ collision-free |

| S25-shipped column | Present? | Verdict |
|---|---|---|
| `password_hash` | ✅ | sanity check passes |
| `failed_password_attempts` | ✅ | sanity check passes |
| `locked_until` | ✅ | sanity check passes |
| `last_login_at` | ✅ | sanity check passes |

**Banked findings:**
- The "status" field is named `vecrm_account_status` (NOT `status` — caused OBS-S26-G in recon authoring)
- The lockout fields are `failed_password_attempts` / `locked_until` (NO password prefix on `locked_until`)
- **A2 column naming convention:** mirror the password pattern but with `pin_` prefix throughout: `pin_hash`, `failed_pin_attempts`, `pin_locked_until`, `last_pin_login_at`. The asymmetry between `locked_until` (existing) and `pin_locked_until` (new) is acceptable — we do not rename the existing column.

**Conclusion:** Migration target columns are fresh. A2 migration safe.

---

## R5 — Phone format inventory ✅ PASS

**Probe output (verbatim):**
```
[{'name': '+91-9327547536', 'vecrm_phone': '+91-9327547536',
  'vecrm_email': 'ajay@vinayenterprises.co.in', 'role': 'Admin',
  'vecrm_account_status': 'Active'},
 {'name': '+91-9999900001', 'vecrm_phone': '+91-9999900001',
  'vecrm_email': 'test.salesrep@vinayenterprises.co.in', 'role': 'Sales Rep',
  'vecrm_account_status': 'Active'},
 {'name': '+91-9999900002', 'vecrm_phone': '+91-9999900002',
  'vecrm_email': 'test.hr@vinayenterprises.co.in', 'role': 'HR',
  'vecrm_account_status': 'Active'}]
```

**Adjudication:**
- 3 rows returned ✓ (matches handover claim)
- All `vecrm_account_status='Active'` ✓
- Phone format consistent: `+91-<10 digits>` (country code, single dash, no internal separators) ✓
- `name == vecrm_phone` for all rows ✓ (autoname invariant holds)
- Total length: 14 characters (1 plus sign + 2 country code digits + 1 dash + 10 mobile digits)

**Banked normalization helper for A2:**
```python
def _normalize_phone(phone: str) -> str:
    """Canonicalize portal-submitted phone to match VECRM Employee.name format.

    Target: '+91-' followed by exactly 10 digits.
    Accepts variants: with/without country code, with/without separators
    (spaces, dashes, parens), with/without leading 0.
    """
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        return phone  # let lookup fail naturally; caller emits invalid_credentials
    return f"+91-{digits}"
```

**Banked lookup pattern for A2:**
```python
normalized = _normalize_phone(phone)
emp_name = frappe.db.get_value("VECRM Employee", normalized, "name")
# emp_name == normalized when found (autoname invariant)
```

**Conclusion:** Phone format is canonical. Normalization helper handles realistic input variants. No production-data migration needed.

---

## R6 — Audit-log event inventory ✅ PASS

**Probe output (verbatim):**
```
[{'event': 'auth.account_locked', 'path': 'password', 'reason': None, 'n': 1},
 {'event': 'auth.login.failed', 'path': 'password', 'reason': 'account_locked', 'n': 1},
 {'event': 'auth.login.failed', 'path': 'password', 'reason': 'invalid_credentials', 'n': 5},
 {'event': 'auth.login.failed', 'path': 'password', 'reason': 'missing_input', 'n': 1},
 {'event': 'auth.login.failed', 'path': 'password', 'reason': 'no_password_configured', 'n': 13},
 {'event': 'auth.login.failed', 'path': 'password', 'reason': 'unknown_email', 'n': 1},
 {'event': 'auth.login.success', 'path': 'password', 'reason': None, 'n': 8},
 {'event': 'auth.logout', 'path': None, 'reason': None, 'n': 7}]
```

**Adjudication (§11.2 verification gate):**
- All non-logout rows have `path='password'` ✓
- `auth.logout` rows have `path=None` ✓ (S25 design — logout doesn't re-record path)
- Zero `path='pin'` rows ✓ (PIN path doesn't exist yet)

**Banked design decisions:**

PIN audit events reuse existing event names, discriminated by `path='pin'`:

| Event | Path | Failure reasons (PIN) |
|---|---|---|
| `auth.login.success` | `pin` | (none) |
| `auth.login.failed` | `pin` | `missing_input`, `unknown_phone` (mirror of `unknown_email`), `account_inactive`, `account_locked`, `no_pin_configured`, `invalid_credentials` |
| `auth.account_locked` | `pin` | (none — emitted on lockout trigger) |
| `auth.logout` | (inherits session's `vecrm_login_path`) | (none) |

**Lockout independence decision (REAFFIRMED):** PIN lockout uses separate state (`failed_pin_attempts`, `pin_locked_until`). A user might forget their password and need PIN access via mobile — locking out one path because of the other is bad UX. State is independent; both paths emit their own audit events.

**R6 update from R1 source-read:** The dispatch had 4 reasons; actual S25 source has 6. Banked above (corrects the recon dispatch's R6 banked design).

**Adjacent finding (NOT in A2 scope):**
- `auth.logout` records `path=None`. Should record the session's `vecrm_login_path` at logout time. Filed as PD-S26-AUTH-LOGOUT-PATH-RECORD (30-min fix, future session).

**Conclusion:** Event namespace clean; PIN events fit symmetrically; lockout independence reaffirmed.

---

## R3 — Permission floor verification ⚠️ FINDINGS

**Probe output (verbatim):**
```
{'VECRM Employee': ['System Manager'],
 'VECRM Auth Audit Log': ['System Manager', 'VECRM Admin']}
```

**Initial adjudication:** Original pass criteria FAILED — neither doctype has VECRM Submitter/Approver perms.

**Re-scoped via R1 source-read:** Login endpoints use `frappe.get_doc("VECRM Employee", ...)` and `_audit_auth` writes via (assumed) `insert(ignore_permissions=True)` or equivalent. Despite the perm gap, the S25 ship works in production (Gate 3 confirmed). Therefore the actual operational invariant is: **login endpoints don't depend on the shared portal user's tabDocPerm roster.**

**Banked decisions:**
- No perm extension needed for A2 PIN endpoint — it will mirror the password endpoint's primitive usage
- The mechanism by which `frappe.get_doc` succeeds for the shared portal user despite missing perms is not fully understood — filed as OBS-S26-I for future investigation
- Latent fragility (any future endpoint relying on perm-checked `get_doc` from a portal session would break) filed as OBS-S26-H / PD-S26-VECRM-EMPLOYEE-PERM-FLOOR

**Verification gate for A2 (per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE):**
After A2 Phase 4 backend smoke, before Phase 5 browser smoke, run:
```bash
curl -sS -c /tmp/pin-test.txt -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "+91-9999900001", "pin": "<test-pin>"}'
```
Pass criteria: HTTP 200 + `success:true`. Same shape as password.

**Conclusion:** R3 cleared with re-scope. A2 proceeds without perm extension.

---

## R1 — `_issue_session` shape ✅ PASS — Verdict: Option R1-A (parameterize)

### R1.a — Caller inventory
```
vecrm/api.py:383: def _issue_session(employee_doc: Any) -> None:   # definition
vecrm/api.py:464:     _issue_session(employee_doc)                   # only call site
```

**Exactly 1 caller.** Cleanest possible refactor case.

### R1.b — Current `_issue_session` source (verbatim)
```python
def _issue_session(employee_doc: Any) -> None:
    """Issue a Frappe session as the shared VECRM Portal User; stash employee
    identity in session data per D8.

    [...docstring about OBS-S25-AL session-persistence mechanism...]
    """
    frappe.local.login_manager.login_as(_VECRM_PORTAL_USER)
    frappe.session.data.vecrm_employee_phone = employee_doc.vecrm_phone
    frappe.session.data.vecrm_employee_name = employee_doc.employee_name
    frappe.session.data.vecrm_employee_role = employee_doc.role
    frappe.session.data.vecrm_login_path = "password"
    frappe.local.session_obj.update(force=True)
```

### R1.c — Banked R1-A refactor for A2

**Diff scope: 4 lines across 3 statements (signature + assignment + 1 existing call site updated + 1 new call site added).**

```python
# Signature change (line 383):
- def _issue_session(employee_doc: Any) -> None:
+ def _issue_session(employee_doc: Any, login_path: str) -> None:

# Assignment change (line 402):
- frappe.session.data.vecrm_login_path = "password"
+ frappe.session.data.vecrm_login_path = login_path

# Updated existing call site (line 464):
- _issue_session(employee_doc)
+ _issue_session(employee_doc, "password")

# New call site in login_with_pin (added by A2):
+ _issue_session(employee_doc, "pin")
```

### R1.d / R1.e — Other banked findings from source-read

1. **`login_with_password` uses `frappe.db.get_value` then `frappe.get_doc`.** The `frappe.get_doc` line is the unexplained-yet-working perm path noted in R3/OBS-S26-I. PIN endpoint mirrors exactly.

2. **`_on_failure` uses `db_update()` + explicit `frappe.db.commit()`** — banked guidance from VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE applied correctly. PIN equivalent (`_on_pin_failure`) mirrors.

3. **`_on_success` resets `failed_password_attempts=0, locked_until=None, last_login_at=now`.** PIN equivalent resets `failed_pin_attempts=0, pin_locked_until=None, last_pin_login_at=now`. Independent state per R6.

4. **Order of checks in `login_with_password`:** missing_input → lookup → status → lockout → no_password_configured → verify. PIN endpoint mirrors this exact order with PIN-specific reason names.

5. **Failure reasons used (6 total):** `missing_input`, `unknown_email`, `account_inactive`, `account_locked`, `no_password_configured`, `invalid_credentials`. PIN equivalents: `missing_input`, `unknown_phone`, `account_inactive`, `account_locked`, `no_pin_configured`, `invalid_credentials`.

**Conclusion:** R1-A is unambiguously correct. Single caller, single assignment line, contained scope. A2 refactor is trivial.

---

## R2 — PIN hash algorithm ✅ PASS

### R2.a — Frappe passlibctx config (Frappe source)
```python
passlibctx = CryptContext(
    schemes=[
        "pbkdf2_sha256",
        "argon2",
    ],
)
```

### R2.b — Runtime verification (verbatim)
```
{'schemes': ['pbkdf2_sha256', 'argon2'],
 'default': 'pbkdf2_sha256',
 'sample_hash_prefix': 'pbkdf2-sha256'}
```

### R2.c — Production password_hash format (verbatim)
```
{'prefix': 'pbkdf2-sha256', 'length': 87, 'first_10_chars': '$pbkdf2-sh'}
```

**Adjudication:**
- Default scheme: `pbkdf2_sha256` ✓
- Sample hash produces `pbkdf2-sha256` prefix ✓
- Production password_hash for Test Sales Rep uses same algorithm ✓ (prefix match)
- Hash length 87 chars — matches `pbkdf2_sha256` passlib output

**Banked decision:** Use `passlibctx.hash(pin)` and `passlibctx.verify(submitted_pin, stored_pin_hash)` identical to password. Same algorithm. Same Data fieldtype storage. Same `pin_hash` length expectation (~87 chars).

**Performance:** ~10-50ms per verify at default `pbkdf2_sha256` rounds. With 5/15min rate-limit, max load ~1 verify/minute. Trivial cost.

**Conclusion:** R2 passes; A2 uses passlibctx primitives identical to password.

---

## Overall conclusion

**A2 dispatch can proceed.**

### Blockers: NONE

### Banked design decisions ready for A2 (8 total)

1. **Schema:** 4 new columns on VECRM Employee — `pin_hash` (Data), `failed_pin_attempts` (Int), `pin_locked_until` (Datetime), `last_pin_login_at` (Datetime)
2. **`_issue_session` refactor:** Option R1-A — add `login_path: str` parameter; 4-line diff
3. **Hash algorithm:** `passlibctx.hash` / `passlibctx.verify` (pbkdf2_sha256) — identical to password
4. **Phone normalization:** `_normalize_phone` helper (14 lines) at API boundary; handles country-code/dash/leading-0/space variants
5. **Lockout independence:** Separate `failed_pin_attempts`/`pin_locked_until` state; PIN lockout doesn't lock password and vice versa
6. **Audit events:** Reuse existing event names with `path='pin'` discriminator; 6 failure reasons mirrored
7. **Endpoint structure:** Mirror `login_with_password` order — missing_input → lookup → status → lockout → no_pin_configured → verify
8. **Perm floor:** No extension needed; A2 mirrors S25's perm-bypassing primitive usage

### Verification gates banked for A2 phases

- **Phase 1.5 gate** (per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE): After schema migration, run `DESCRIBE tabVECRM Employee` and confirm all 4 new columns present + types correct
- **Phase 2.5 gate:** After endpoint authoring, `grep -rn "_issue_session" vecrm/` produces exactly 3 lines (definition + 2 callers)
- **Phase 4 gate:** curl smoke produces HTTP 200 `success:true` for `login_with_pin`
- **Phase 4 audit gate:** After 6 failed PIN attempts, audit log contains 5 `auth.login.failed` (path=pin) + 1 `auth.account_locked` (path=pin) + 1 `auth.login.failed` (path=pin, reason=account_locked)

### Adjacent backlog items surfaced during recon (NOT in A2 scope)

| Item | Estimate | Severity |
|---|---|---|
| PD-S26-AUTH-LOGOUT-PATH-RECORD | 30 min | Cosmetic — logout audit rows have path=None instead of session's login_path |
| PD-S26-FRAPPE-PERM-MECHANISM-PROBE (OBS-S26-I) | 1-2 hr | Investigative — understand why `frappe.get_doc` succeeds despite tabDocPerm gap |
| PD-S26-VECRM-EMPLOYEE-PERM-FLOOR (OBS-S26-H) | 1 hr | Cleanup — align tabDocPerm rosters across portal doctypes |

### OBS catalog updates (S26)

- OBS-S26-A — Opener prompt column-name/path defects (3 items, docs-only fix)
- OBS-S26-B — Bench-console heredoc + for-loop unreliable (lock candidate)
- OBS-S26-C — Transient docker-cp file lock (resolved, no action)
- OBS-S26-D — Container missing `/home/frappe/logs/` and `<site>/logs/` directories
- OBS-S26-E — Dispatcher symptom-chasing across 4 rounds (self-filed)
- OBS-S26-F — TV-27-28=14 counter row not in handover (docs-only)
- OBS-S26-G — Dispatcher wrote R5 query with unverified column name (`status` → `vecrm_account_status`)
- OBS-S26-H — VECRM Employee perm floor is `[System Manager]` only; latent fragility
- OBS-S26-I — `frappe.get_doc` succeeds for shared portal user despite missing tabDocPerm; mechanism not understood

---

**Recon close. A2 implementation dispatch authorization pending operator review.**
