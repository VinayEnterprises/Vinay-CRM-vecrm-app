# PD-S26-AUTH-PHONE-PIN — A2 Implementation Dispatch

**Session:** S26 Phase 1 implementation
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (file edits, source-reads, py_compile)
**Operator:** Ajay Salvi (git, VPS deploy, prod SQL, PR merge)
**Authorized:** Operator selected Option 1 (full recon) at S26 open; recon cleared with 8 banked design decisions (commit `36268ae`); operator confirmed Option α (same branch); A2 scope default = backend-only
**Branch:** `dispatch/s26-auth-phone-pin-recon` (continuing from recon)
**Estimated wall-clock:** 4-6 hours

---

## §0 — Cold-check + recon inheritance

All 8 cold-check gates passed at S26 open. All 6 R-questions cleared in recon. Inheritance into A2:

- vecrm@`36268ae`, vecrm-portal@`8165f7a` (vecrm-portal NOT touched in A2)
- Production auth working: email+password lifecycle green
- VECRM-L8 allocator sha intact
- VECRM Employee schema: 22 columns, 4 PIN-target names collision-free
- Phone format `+91-<10 digits>` across 3 Active employees
- Audit event design banked
- Frappe passlibctx default = `pbkdf2_sha256` (same as password)
- `_issue_session` has exactly 1 caller; R1-A refactor is a 4-line diff

A2 does NOT re-verify cold-check gates. Recon verified them less than 2 hours ago; we trust them.

---

## §1 — Scope

**In scope for A2:**
1. Schema migration: 4 new columns on VECRM Employee + paired rollback
2. `_issue_session` refactor: add `login_path: str` parameter
3. New API endpoint: `vecrm.api.login_with_pin(phone: str = "", pin: str = "")`
4. Helper functions: `_normalize_phone`, `_is_pin_locked`, `_on_pin_failure`, `_on_pin_success`
5. Audit-log integration: PIN events use `path='pin'` discriminator
6. Backend curl smoke verification (mirror S25 Phase 4 — 5 tests)
7. Squash-merge PR to main

**Out of scope (deferred):**
- Portal UI ("Use PIN instead" toggle on `/login`) — Phase 1.B candidate or S27
- `admin_set_credential` endpoint (PD-S26-AUTH-ADMIN-SET)
- Email-based reset flow (PD-S26-AUTH-RESET)
- Microsoft Graph wiring (PD-S26-AUTH-MS-GRAPH)
- Credential rotation (PD-S26-AUTH-CREDS-ROTATE)
- Logout path-record fix (PD-S26-AUTH-LOGOUT-PATH-RECORD)
- VECRM Employee perm floor cleanup (PD-S26-VECRM-EMPLOYEE-PERM-FLOOR)
- Frappe perm mechanism investigation (PD-S26-FRAPPE-PERM-MECHANISM-PROBE / OBS-S26-I)

---

## §2 — Phase breakdown

A2 ships across 7 phases. Each phase has clear entry/exit criteria and a verification gate. Phases are atomic — if a phase fails verification, we halt and adjudicate before the next phase.

| Phase | Description | Wall-clock | Risk |
|---|---|---|---|
| 0.5 | Frappe symbol verification | 5 min | Low — symbols already used in S25 |
| 1 | Schema migration + rollback | 30-45 min | Medium — DDL on production |
| 1.5 | Schema verification gate | 5 min | Low — read-only DESCRIBE |
| 2 | API: `_issue_session` refactor + `login_with_pin` endpoint | 60-90 min | Medium — code authoring |
| 2.5 | Empty-body / missing-input defense | 10 min | Low — mirror S25 Phase 2.5 |
| 3 | Bootstrap PINs for test employees | 15 min | Low — single-doc updates |
| 4 | Backend curl smoke (5 tests) | 30 min | Medium — first prod exposure |
| 5 | OBS catalog + close handover | 30 min | Low |
| 6 | PR + squash-merge | 15 min | Low |

**Total: 3.5-4.5 hours optimistic, 5-6 hours with two phase reworks.**

---

## §3 — Phase 0.5 — Frappe symbol verification

Per S26 anti-drift guard 4 (verify symbols before using them).

**Executor runs (local repo):**

```bash
cd ~/Documents/GitHub/vecrm

# Confirm passlibctx import + signature in current Frappe (we did this in R2, but re-banking):
ssh root@217.216.58.117 'docker exec vecrm-backend-1 python3 -c "from frappe.utils.password import passlibctx; print(passlibctx.hash.__doc__ or \"<no docstring>\"); print(passlibctx.verify.__doc__ or \"<no docstring>\")" 2>&1 | head -20'

# Confirm now_datetime + timedelta imports already present in vecrm/api.py:
grep -n "from datetime\|now_datetime\|timedelta" vecrm/api.py

# Confirm _audit_auth signature (PIN endpoint will call it):
awk '/^def _audit_auth/,/^def /' vecrm/api.py | head -30
```

**Pass criteria:**
- `passlibctx.hash` and `passlibctx.verify` are confirmed callable
- `now_datetime` and `timedelta` already imported in `vecrm/api.py`
- `_audit_auth` signature includes `event, employee=None, identifier=None, path=None, reason=None, extra=None` (or equivalent — confirm before reuse)

**Fallback:** If any symbol is missing, halt — adjust A2 phase 2 to import what's needed.

---

## §4 — Phase 1 — Schema migration + rollback

### §4.1 — Doctype JSON edit

**File:** `vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json`

**Action (executor edits):** Add 4 new fields to the `fields` array, immediately after the existing `last_login_at` field. JSON shape per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE:

```json
{
    "fieldname": "pin_hash",
    "fieldtype": "Data",
    "label": "PIN Hash",
    "read_only": 1,
    "no_copy": 1
},
{
    "fieldname": "failed_pin_attempts",
    "fieldtype": "Int",
    "label": "Failed PIN Attempts",
    "default": "0",
    "read_only": 1
},
{
    "fieldname": "pin_locked_until",
    "fieldtype": "Datetime",
    "label": "PIN Locked Until",
    "read_only": 1
},
{
    "fieldname": "last_pin_login_at",
    "fieldtype": "Datetime",
    "label": "Last PIN Login At",
    "read_only": 1
}
```

**Important:** mirror the S25 password fields' attributes (`read_only`, `no_copy` on the hash, `default` on the counter). The dispatch document for these JSON edits will be delivered via `present_files` (the full doctype JSON is large, > 30 lines).

**Verification (executor runs after edit):**
```bash
cd ~/Documents/GitHub/vecrm
python3 -c "import json; data = json.load(open('vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json')); fields = [f['fieldname'] for f in data['fields']]; print('PIN fields present:', all(f in fields for f in ['pin_hash', 'failed_pin_attempts', 'pin_locked_until', 'last_pin_login_at']))"
```

Expected: `PIN fields present: True`

### §4.2 — Forward migration patch

**File:** `vecrm/patches/v1_1/add_pin_auth_fields.py` (new)

**Pattern (per VECRM-L22 atomic migrations + Phase 4.7 banked structure):**

```python
"""Add PIN auth fields to VECRM Employee — companion to email+password (S25).

Adds:
- pin_hash (Data) — passlib hash of PIN
- failed_pin_attempts (Int) — lockout counter
- pin_locked_until (Datetime) — lockout expiry
- last_pin_login_at (Datetime) — last successful PIN login

Per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE: pin_hash uses Data, NOT Password.
Per VECRM-L22: atomic; assert post-conditions; paired rollback exists.

S26 Phase 1.
"""

import frappe


def execute() -> None:
    print("PD-S26-AUTH-PHONE-PIN Phase 1: add_pin_auth_fields")

    frappe.reload_doc("vecrm", "doctype", "vecrm_employee")
    from frappe.model.sync import sync_for
    sync_for("vecrm", force=1)

    # Assert post-conditions
    meta = frappe.get_meta("VECRM Employee")
    field_names = {f.fieldname for f in meta.fields}
    required = {"pin_hash", "failed_pin_attempts", "pin_locked_until", "last_pin_login_at"}
    missing = required - field_names
    if missing:
        raise Exception(f"PIN fields missing after sync: {missing}")

    # Verify fieldtypes
    expected_types = {
        "pin_hash": "Data",
        "failed_pin_attempts": "Int",
        "pin_locked_until": "Datetime",
        "last_pin_login_at": "Datetime",
    }
    for fname, ftype_expected in expected_types.items():
        ftype_actual = next((f.fieldtype for f in meta.fields if f.fieldname == fname), None)
        if ftype_actual != ftype_expected:
            raise Exception(f"PIN field {fname}: expected {ftype_expected}, got {ftype_actual}")

    print("  ✓ All 4 PIN fields added with correct types")
    print("  ✓ pin_hash uses Data (NOT Password) per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE")

    frappe.db.commit()
```

### §4.3 — Paired rollback

**File:** `vecrm/patches/v1_1/rollback_add_pin_auth_fields.py` (new)

**Pattern:**

```python
"""Rollback for add_pin_auth_fields.

Drops the 4 PIN auth columns from tabVECRM Employee. Does NOT touch
the doctype JSON (revert that via git separately).

Per VECRM-L22: paired rollback exists for every forward migration.

S26 Phase 1 rollback.
"""

import frappe


def execute() -> None:
    print("PD-S26-AUTH-PHONE-PIN Phase 1 ROLLBACK: rollback_add_pin_auth_fields")

    columns_to_drop = ["pin_hash", "failed_pin_attempts", "pin_locked_until", "last_pin_login_at"]

    # Verify columns exist before dropping (idempotency)
    existing = frappe.db.sql("DESCRIBE `tabVECRM Employee`", as_dict=True)
    existing_cols = {c["Field"] for c in existing}

    for col in columns_to_drop:
        if col in existing_cols:
            frappe.db.sql(f"ALTER TABLE `tabVECRM Employee` DROP COLUMN `{col}`")
            print(f"  ✓ Dropped column {col}")
        else:
            print(f"  - Column {col} already absent (idempotent)")

    frappe.db.commit()
```

### §4.4 — Hooks registration

**File:** `vecrm/patches.txt` (edit)

**Action:** Add this line to `patches.txt`:
```
vecrm.patches.v1_1.add_pin_auth_fields
```

**Important:** Do NOT add the rollback to `patches.txt` — rollbacks are invoked manually via `bench execute` if needed, not automatically.

### §4.5 — Deploy procedure (operator runs after executor delivery)

Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS: schema migration is destructive; requires dispatcher authorization (this dispatch authorizes it) and operator execution.

```bash
# 1. From local Mac — verify the patch files compile:
cd ~/Documents/GitHub/vecrm
python3 -m py_compile vecrm/patches/v1_1/add_pin_auth_fields.py
python3 -m py_compile vecrm/patches/v1_1/rollback_add_pin_auth_fields.py

# 2. Tar + scp + docker cp (per VECRM dependency map §5.1):
cd ~/Documents/GitHub/vecrm
tar -czf /tmp/vecrm-deploy.tar.gz \
    vecrm/patches/v1_1/add_pin_auth_fields.py \
    vecrm/patches/v1_1/rollback_add_pin_auth_fields.py \
    vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json \
    vecrm/patches.txt

scp /tmp/vecrm-deploy.tar.gz root@217.216.58.117:/tmp/
ssh root@217.216.58.117 'docker cp /tmp/vecrm-deploy.tar.gz vecrm-backend-1:/tmp/'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 tar -xzf /tmp/vecrm-deploy.tar.gz -C /home/frappe/frappe-bench/apps/vecrm/'

# 3. Run migration:
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in migrate'

# 4. Clear cache:
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in clear-cache'

# 5. Cleanup tar:
rm /tmp/vecrm-deploy.tar.gz
ssh root@217.216.58.117 'rm /tmp/vecrm-deploy.tar.gz'
```

**Pass criteria for Phase 1 close:**
- Migration logs show "✓ All 4 PIN fields added with correct types"
- `bench migrate` exits 0
- No traceback in output

**Fallback if migration fails mid-way:**
- Re-run `bench migrate` (patches are idempotent if assertions are well-placed)
- If still failing: execute the rollback via `bench execute vecrm.patches.v1_1.rollback_add_pin_auth_fields.execute`
- Halt and adjudicate

---

## §5 — Phase 1.5 — Schema verification gate

Per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE — verify at the moment the schema risk becomes concrete.

**Operator runs:**

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
meta = frappe.get_meta("VECRM Employee")
pin_fields = {f.fieldname: f.fieldtype for f in meta.fields if f.fieldname.startswith("pin_") or f.fieldname == "failed_pin_attempts" or f.fieldname == "last_pin_login_at"}
print(pin_fields)
EOF
```

**Pass criteria:**
```
{'pin_hash': 'Data', 'failed_pin_attempts': 'Int', 'pin_locked_until': 'Datetime', 'last_pin_login_at': 'Datetime'}
```

(Order may vary; 4 keys, 4 expected types.)

**Verification gate per §risk §11.1 (schema collision):** the migration's assertion block already enforces this. The console probe is a re-verification at the production layer.

**Fallback:** if any field type is wrong, rollback + adjudicate doctype JSON before re-running.

---

## §6 — Phase 2 — API authoring

### §6.1 — `_issue_session` refactor (R1-A)

**File:** `vecrm/api.py`

**Diff target:**

```python
# Line 383 — signature change:
def _issue_session(employee_doc: Any, login_path: str) -> None:

# Line 402 — assignment change:
frappe.session.data.vecrm_login_path = login_path

# Line 464 — existing call site update:
_issue_session(employee_doc, "password")
```

### §6.2 — New helpers

**Add to `vecrm/api.py`** (suggested location: near `_on_failure` / `_on_success`):

```python
def _normalize_phone(phone: str) -> str:
    """Canonicalize portal-submitted phone to match VECRM Employee.name format.

    Target: '+91-' followed by exactly 10 digits.
    Accepts variants: with/without country code, with/without separators
    (spaces, dashes, parens), with/without leading 0.

    Returns the input unchanged if normalization fails — the caller is
    expected to emit invalid_credentials on lookup failure.
    """
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        return phone
    return f"+91-{digits}"


def _is_pin_locked(employee_doc: Any) -> bool:
    """Check if PIN authentication is currently locked for this employee.

    Mirrors _is_locked (which checks locked_until for password path) but
    reads pin_locked_until instead. Independent lockout state per R6.
    """
    if not employee_doc.pin_locked_until:
        return False
    return now_datetime() < employee_doc.pin_locked_until


def _on_pin_failure(employee_doc: Any) -> None:
    """Increment failed PIN attempts; set PIN-specific lockout if threshold reached.

    Mirrors _on_failure but operates on the pin_ prefixed fields. Independent
    state — password lockout is NOT affected.
    """
    current = (employee_doc.failed_pin_attempts or 0) + 1
    employee_doc.failed_pin_attempts = current
    if current >= _MAX_FAILED_ATTEMPTS:
        employee_doc.pin_locked_until = now_datetime() + timedelta(minutes=_LOCKOUT_MINUTES)
        _audit_auth(
            "auth.account_locked",
            employee=employee_doc.name,
            path="pin",
            extra={"pin_locked_until": str(employee_doc.pin_locked_until)},
        )
    employee_doc.db_update()
    frappe.db.commit()


def _on_pin_success(employee_doc: Any) -> None:
    """Reset failed PIN attempts + record last PIN login.

    Mirrors _on_success but operates on the pin_ prefixed fields.
    """
    employee_doc.failed_pin_attempts = 0
    employee_doc.pin_locked_until = None
    employee_doc.last_pin_login_at = now_datetime()
    employee_doc.db_update()
    frappe.db.commit()
```

### §6.3 — New endpoint `login_with_pin`

**Add to `vecrm/api.py`** (suggested location: immediately after `login_with_password`):

```python
@frappe.whitelist(allow_guest=True, methods=["POST"])
def login_with_pin(phone: str = "", pin: str = "") -> dict[str, Any]:
    """Authenticate VECRM Employee via phone + PIN.

    Companion to login_with_password (S25). Independent lockout state.

    Returns:
        {"success": True, "employee": "<phone>", "name": "<full_name>",
         "role": "<role>"}

    Raises:
        frappe.AuthenticationError with generic "Invalid credentials" for
        all failure modes (no enumeration).
    """
    if not phone or not pin:
        _audit_auth("auth.login.failed", identifier=phone, path="pin", reason="missing_input")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    normalized = _normalize_phone(phone)
    employee_name = frappe.db.get_value("VECRM Employee", normalized, "name")
    if not employee_name:
        _audit_auth("auth.login.failed", identifier=phone, path="pin", reason="unknown_phone")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    employee_doc = frappe.get_doc("VECRM Employee", employee_name)

    if employee_doc.vecrm_account_status != "Active":
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="account_inactive",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if _is_pin_locked(employee_doc):
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="account_locked",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if not employee_doc.pin_hash:
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="no_pin_configured",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if not passlibctx.verify(pin, employee_doc.pin_hash):
        _on_pin_failure(employee_doc)
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="invalid_credentials",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    _on_pin_success(employee_doc)
    _issue_session(employee_doc, "pin")
    _audit_auth("auth.login.success", employee=employee_doc.name, path="pin")

    return {
        "success": True,
        "employee": employee_doc.name,
        "name": employee_doc.employee_name,
        "role": employee_doc.role,
    }
```

### §6.4 — Verification gate at Phase 2 close

**Executor runs (local repo):**

```bash
cd ~/Documents/GitHub/vecrm
python3 -m py_compile vecrm/api.py

# _issue_session caller count must be exactly 3 (def + 2 callers):
grep -c "_issue_session" vecrm/api.py

# login_with_pin must be defined exactly once:
grep -c "^def login_with_pin" vecrm/api.py

# All 4 new helpers defined:
for fn in _normalize_phone _is_pin_locked _on_pin_failure _on_pin_success; do
    echo "$fn: $(grep -c "^def $fn" vecrm/api.py)"
done
```

**Pass criteria:**
- `py_compile` exits 0
- `grep -c "_issue_session"` returns ≥3 (1 def + 2 callers; may be more if docstrings mention it)
- `grep -c "^def login_with_pin"` returns exactly 1
- All 4 helpers each return 1

---

## §7 — Phase 2.5 — Empty-body defense

Mirrors S25 Phase 2.5 (OBS-S25-AD fix). The `login_with_pin(phone: str = "", pin: str = "")` signature with default `""` strings handles empty-body POST cleanly — if request body is empty, both defaults to `""`, the first check (`if not phone or not pin`) catches it, emits `missing_input` audit, returns generic 401.

**No additional code needed** if Phase 2 was authored with the default-empty-string signature (it was).

**Verification:** Phase 4 Smoke 1 (below) exercises this path.

---

## §8 — Phase 3 — Bootstrap PINs for test employees

Production currently has 3 employees with `pin_hash IS NULL`. For Phase 4 smoke testing, set test PINs.

**Operator runs:**

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
from frappe.utils.password import passlibctx

# Set PINs:
# - Test Sales Rep: PIN 1234
# - Test HR Approver: PIN 5678
# - Ajay: PIN set separately by operator (not committed in docs)

frappe.db.set_value("VECRM Employee", "+91-9999900001", "pin_hash", passlibctx.hash("1234"))
frappe.db.set_value("VECRM Employee", "+91-9999900002", "pin_hash", passlibctx.hash("5678"))
frappe.db.commit()

# Verify:
for phone in ["+91-9999900001", "+91-9999900002"]:
    hash_val = frappe.db.get_value("VECRM Employee", phone, "pin_hash") or ""
    print(f"{phone}: pin_hash set ({len(hash_val)} chars, prefix={hash_val[:14]})")
EOF
```

**Pass criteria:**
- 2 rows show pin_hash set, length ~87, prefix `$pbkdf2-sha256`

**Ajay's PIN:** Operator sets via a separate console call (not committed to docs):
```python
# Operator runs separately, not in dispatch:
frappe.db.set_value("VECRM Employee", "+91-9327547536", "pin_hash", passlibctx.hash("<ajay's pin>"))
frappe.db.commit()
```

---

## §9 — Phase 4 — Backend curl smoke (5 tests)

Mirrors S25 Phase 4 smoke. Run from local Mac against production.

### §9.1 — Smoke 1: Empty body defense

```bash
curl -sS -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{}' \
  -w "\nHTTP_STATUS=%{http_code}\n"
```

**Pass criteria:** HTTP 401, generic invalid-credentials message. Audit log records `auth.login.failed` / `path=pin` / `reason=missing_input`.

### §9.2 — Smoke 2: Wrong PIN — invalid_credentials

```bash
curl -sS -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "+91-9999900001", "pin": "0000"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"
```

**Pass criteria:** HTTP 401. Audit log records `auth.login.failed` / `path=pin` / `reason=invalid_credentials`. `failed_pin_attempts` increments to 1.

### §9.3 — Smoke 3: Successful PIN login + session persistence

```bash
COOKIE_FILE=/tmp/vecrm-pin-smoke.txt
rm -f "$COOKIE_FILE"

curl -sS -c "$COOKIE_FILE" -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "+91-9999900001", "pin": "1234"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"

curl -sS -b "$COOKIE_FILE" \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.get_session_employee \
  -w "\nHTTP_STATUS=%{http_code}\n"

curl -sS -b "$COOKIE_FILE" -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.vecrm_logout \
  -w "\nHTTP_STATUS=%{http_code}\n"

rm -f "$COOKIE_FILE"
```

**Pass criteria (LOAD-BEARING — session persistence verification):**
- Login: HTTP 200, `success:true`, employee identity returned
- `get_session_employee`: HTTP 200, response includes `"login_path":"pin"` (NOT `"password"`)
- Logout: HTTP 200

The `login_path: "pin"` confirms the `_issue_session` refactor is working — session data was set with the new parameterized value.

### §9.4 — Smoke 4: Phone normalization variants

```bash
# Variant: no country code
curl -sS -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "9999900001", "pin": "1234"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"

# Variant: spaces
curl -sS -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "+91 99999 00001", "pin": "1234"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"
```

**Pass criteria:** Both succeed (HTTP 200, `success:true`) — `_normalize_phone` canonicalizes correctly.

### §9.5 — Smoke 5: Lockout at 5 failed attempts

```bash
# Attempts 1-5: wrong PIN
for i in 1 2 3 4 5; do
  curl -sS -X POST \
    https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
    -H "Content-Type: application/json" \
    -d '{"phone": "+91-9999900002", "pin": "0000"}' \
    -w "\nAttempt $i: HTTP_STATUS=%{http_code}\n"
done

# Attempt 6: correct PIN — should still fail (locked)
curl -sS -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "+91-9999900002", "pin": "5678"}' \
  -w "\nAttempt 6 (correct PIN, expected locked): HTTP_STATUS=%{http_code}\n"
```

**Pass criteria:**
- All 6 attempts return HTTP 401 with generic invalid-credentials
- Audit log shows 5 × `auth.login.failed` (path=pin, reason=invalid_credentials), then 1 × `auth.account_locked` (path=pin) + 1 × `auth.login.failed` (path=pin, reason=account_locked)
- `tabVECRM Employee` row for `+91-9999900002` shows `failed_pin_attempts=5` and `pin_locked_until` set to ~15 min in the future

**Critical:** Password lockout for Test HR Approver is NOT affected. Verify:

```bash
# After Smoke 5, attempt password login for Test HR Approver — should succeed:
curl -sS -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_password \
  -H "Content-Type: application/json" \
  -d '{"email": "test.hr@vinayenterprises.co.in", "password": "testhr1234"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"
```

**Pass criteria:** HTTP 200, login succeeds. This confirms the **independent lockout state** decision from R6.

### §9.6 — Audit roster post-smoke

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
rows = frappe.db.sql("SELECT event, path, reason, COUNT(*) AS n FROM `tabVECRM Auth Audit Log` WHERE path='pin' GROUP BY event, path, reason ORDER BY event, reason", as_dict=True)
print("PIN audit roster:")
for r in rows:
    print(f"  {r}")
EOF
```

**Pass criteria:** Roster reflects all 5 smokes' expected events. Specifically expect:
- `auth.login.failed` / `pin` / `missing_input` × 1 (from Smoke 1)
- `auth.login.failed` / `pin` / `invalid_credentials` × ≥6 (1 from Smoke 2 + 5 from Smoke 5)
- `auth.login.success` / `pin` / NULL × ≥3 (1 from Smoke 3 + 2 from Smoke 4 normalization variants)
- `auth.login.failed` / `pin` / `account_locked` × 1 (from Smoke 5 attempt 6)
- `auth.account_locked` / `pin` / NULL × 1 (from Smoke 5)
- `auth.logout` rows (these may have path=None — see PD-S26-AUTH-LOGOUT-PATH-RECORD)

### §9.7 — Cleanup Test HR Approver lockout

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
frappe.db.set_value("VECRM Employee", "+91-9999900002", "failed_pin_attempts", 0)
frappe.db.set_value("VECRM Employee", "+91-9999900002", "pin_locked_until", None)
frappe.db.commit()
print("Cleared PIN lockout for Test HR Approver")
EOF
```

---

## §10 — Phase 5 — Close handover

Once Phase 4 smoke is green, draft the S26 Phase 1 close handover. This goes alongside the dispatch + findings on the same branch.

**Deliverable (dispatcher authors, delivered via `present_files`):**
`docs/dispatches/PD-S26-AUTH-PHONE-PIN-close-handover.md`

**Contents:**
- What shipped (commits, file list, line counts)
- Production verification (Smoke 1-5 results)
- OBS catalog updates from A2 execution
- Lift status (PD-S26-AUTH-PHONE-PIN closes; this drives part of B5/B6 of Session-0 pillars forward)
- Test PIN values (committed only because they're throwaway dev creds)
- Forward inventory for S27 (Phase 1.B portal UI, or S27 fresh dispatch)

---

## §11 — Phase 6 — PR + squash-merge

Per VECRM-L13. Branch is `dispatch/s26-auth-phone-pin-recon`. PR base is `main`.

**Operator runs:**

```bash
cd ~/Documents/GitHub/vecrm
git branch --show-current  # expect: dispatch/s26-auth-phone-pin-recon

# Verify all changes committed:
git status

# Push final state:
git push origin dispatch/s26-auth-phone-pin-recon

# Create PR (use the PR title and body shape established in S23-S25):
gh pr create \
  --title "S26 Phase 1: PD-S26-AUTH-PHONE-PIN — phone+PIN auth backend (recon + impl)" \
  --body "<dispatcher-authored body, delivered separately via present_files>" \
  --base main

# After CI passes (if any) + visual review of diff:
gh pr merge <PR_NUMBER> --squash --delete-branch
```

PR body authored separately by dispatcher and delivered via `present_files`.

---

## §12 — Risk register (per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE)

### §12.1 — Risk: Schema migration leaves DB in inconsistent state

**Verification gate:** Phase 1 migration's internal assertion block (post-conditions). Plus Phase 1.5 console probe.

**Pass criteria:** All 4 columns present with correct fieldtypes.

**Fail action:** Run rollback (`bench execute vecrm.patches.v1_1.rollback_add_pin_auth_fields.execute`). Adjudicate before retry.

### §12.2 — Risk: `_issue_session` refactor breaks email+password path

**Verification gate:** Phase 4 backend smoke includes existing password-path test (separate from PIN smokes). Specifically: after PIN smokes complete, re-run an email-password lifecycle to confirm S25's auth still works.

**Pass criteria:** Email login + get_session_employee + logout all return HTTP 200 with `login_path:"password"`.

**Fail action:** Revert `_issue_session` refactor; reconsider R1-A vs R1-B; this would mean R1's adjudication was wrong.

**Specific test (run after Smoke 5 cleanup):**

```bash
COOKIE_FILE=/tmp/vecrm-pwd-regression.txt
rm -f "$COOKIE_FILE"

curl -sS -c "$COOKIE_FILE" -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_password \
  -H "Content-Type: application/json" \
  -d '{"email": "test.salesrep@vinayenterprises.co.in", "password": "testrep123"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"

curl -sS -b "$COOKIE_FILE" \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.get_session_employee \
  -w "\nHTTP_STATUS=%{http_code}\n"

# CRITICAL: response above must include "login_path":"password" (NOT "pin")

curl -sS -b "$COOKIE_FILE" -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.vecrm_logout \
  -w "\nHTTP_STATUS=%{http_code}\n"

rm -f "$COOKIE_FILE"
```

### §12.3 — Risk: PIN lockout incorrectly shares state with password lockout

**Verification gate:** Phase 4 Smoke 5 — after locking PIN, password login for the same employee must still succeed.

**Pass criteria:** Test HR Approver's PIN locks, but their password login still works.

**Fail action:** This would be a code bug — `_on_pin_failure` must touch ONLY `failed_pin_attempts` and `pin_locked_until`, never `failed_password_attempts` or `locked_until`. Re-author and re-deploy.

### §12.4 — Risk: Phone normalization breaks edge cases

**Verification gate:** Phase 4 Smoke 4 — both `"9999900001"` (no country code) and `"+91 99999 00001"` (spaces) must succeed.

**Pass criteria:** Both variants resolve to `+91-9999900001` and authenticate cleanly.

**Fail action:** Adjust `_normalize_phone` logic.

### §12.5 — Risk: Frappe `frappe.get_doc` perm gap surfaces

Per OBS-S26-I — the mechanism by which `frappe.get_doc("VECRM Employee", ...)` succeeds for the shared portal user is not understood. If A2's PIN endpoint hits a different path that triggers strict permission checks, login would 403.

**Verification gate:** Phase 4 Smoke 3 — successful PIN login. If this returns 403, perm gap has surfaced.

**Pass criteria:** Smoke 3 returns HTTP 200.

**Fail action:** Investigate immediately. May require adding VECRM Submitter/Approver perms to VECRM Employee tabDocPerm rows as an emergency Phase 4.5 fix. This is the §10.1-shaped risk from S25 re-applied to S26.

---

## §13 — Anti-drift guards specific to A2

1. **Phase 1 + Phase 1.5 are atomic.** Do NOT proceed to Phase 2 if Phase 1.5 verification gate doesn't pass.
2. **All schema work via migrations, not direct ALTER.** Per VECRM-L22.
3. **All file edits via `view` + `str_replace` or `create_file`,** never via heredoc into the live container.
4. **Source artifacts > 30 lines via `present_files`** per VECRM-LOCK-FILE-DELIVERY-NOT-PASTE.
5. **Single-statement bench-console queries only** per OBS-S26-B lesson.
6. **All commits authored on `dispatch/s26-auth-phone-pin-recon`** branch (Option α).
7. **Verify symbols via Phase 0.5 source-read** before using them.
8. **`db_update()` for column-only writes,** not `.save()`. Per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE.
9. **Test password+email auth STILL WORKS after PIN ships** — Phase 4 §12.2 regression test is non-optional.

---

## §14 — File inventory (what A2 creates/modifies)

**Created files (4):**
- `vecrm/patches/v1_1/add_pin_auth_fields.py` (new migration)
- `vecrm/patches/v1_1/rollback_add_pin_auth_fields.py` (new rollback)
- `docs/dispatches/PD-S26-AUTH-PHONE-PIN-A2-dispatch.md` (this document, on disk)
- `docs/dispatches/PD-S26-AUTH-PHONE-PIN-close-handover.md` (Phase 5)

**Modified files (3):**
- `vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json` (add 4 fields)
- `vecrm/patches.txt` (add 1 patch reference)
- `vecrm/api.py` (refactor `_issue_session`, add helpers, add `login_with_pin`)

**Estimated diff size:** ~300 net insertions, ~5 net deletions (refactor + new helpers + new endpoint).

---

## §15 — Authorization checklist

Before Phase 0.5 starts:

- [ ] Operator has reviewed this A2 dispatch
- [ ] Operator confirms scope is backend-only (no portal UI in this A2)
- [ ] Operator authorizes Claude Code to execute Phase 0.5 + Phase 1 file authoring
- [ ] Operator commits to running deploy procedure (Phase 1.5+, all VPS operations)
- [ ] Operator acknowledges the §12.5 risk re: OBS-S26-I (perm-mechanism opacity); accepts that Phase 4 Smoke 3 is the gate

**Operator runs (state-changing):** schema deploy (Phase 1), all VPS console, all curl smokes (Phase 4), git commits/push/PR.

**Executor runs (read-only or local-only):** Phase 0.5 source-reads, file authoring in local repo (Phase 1 patches + Phase 2 API code), py_compile, grep verification.

**Dispatcher (chat):** adjudicates each phase gate, authors close handover (Phase 5) and PR body (Phase 6), files OBS observations as patterns surface.

---

## §16 — Sign-off

**Dispatcher:** Claude (this chat)
**Authorization:** Awaiting operator review + Phase 0.5 kickoff.
**Estimated commit-ready time:** 4-6 hours from Phase 0.5 start.

End of A2 implementation dispatch.
