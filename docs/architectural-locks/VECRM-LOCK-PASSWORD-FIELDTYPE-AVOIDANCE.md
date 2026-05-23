# VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE

**Earned:** S25 (Phase 4.7, OBS-S25-AK)
**Status:** ACTIVE
**Severity:** Critical (silent credential loss)

## Statement

VECRM doctype fields storing values that are ALREADY one-way hashes (passlib, scrypt, argon2, bcrypt — anything irreversible) MUST use fieldtype `Data`, NOT fieldtype `Password`.

The Frappe Password fieldtype has a delete-on-save footgun: `get_doc()` loads Password values as `None` (the actual value lives in `__Auth`, not in the parent table). Any subsequent `.save()` propagates `None` to `__Auth` → Frappe treats it as "clear password" and DELETES the `__Auth` row, silently destroying the stored hash.

Since one-way hashes are already irreversible, the Password fieldtype's encryption-at-rest provides zero additional security but introduces the delete-on-save mechanism. Data fieldtype stores the value in the parent table column, loads correctly via `get_doc`, and survives any doc mutation.

## Pattern (correct)

In doctype JSON, for hash-storage fields:

```json
{
    "fieldname": "password_hash",
    "fieldtype": "Data",
    "label": "Password Hash",
    "read_only": 1,
    "no_copy": 1
}
```

To set the value:

```python
from frappe.utils.password import passlibctx
hashed = passlibctx.hash(plaintext)
frappe.db.set_value("VECRM Employee", phone, "password_hash", hashed)
frappe.db.commit()
```

To verify:

```python
from frappe.utils.password import passlibctx
doc = frappe.get_doc("VECRM Employee", phone)
if doc.password_hash and passlibctx.verify(plaintext, doc.password_hash):
    # authenticated
```

## Anti-pattern (WRONG — this caused OBS-S25-AK)

```json
{
    "fieldname": "password_hash",
    "fieldtype": "Password"
}
```

```python
# Anywhere downstream that does this is a footgun:
doc = frappe.get_doc("VECRM Employee", phone)
doc.failed_password_attempts = 5
doc.save()  # ❌ password_hash __Auth row now DELETED
```

## When the footgun fires

ANY code path that:
1. Calls `frappe.get_doc()` on a row with a Password field, AND
2. Calls `.save()` (with or without modifying other fields)

This includes:
- Lockout-cleanup helpers
- Audit-log-emitting controllers
- Frappe Desk UI edits
- Background workers that touch the doctype
- Migration patches that reload rows

## Safer alternatives even with Data fieldtype

When updating only specific columns, prefer `db.set_value()` or `doc.db_update()` over full `.save()`:

```python
# Update specific columns without triggering full doc lifecycle:
frappe.db.set_value("VECRM Employee", phone, "failed_password_attempts", 5)

# Or, for an already-loaded doc:
doc.failed_password_attempts = 5
doc.db_update()  # writes only column-level changes, no __Auth interaction
```

With password_hash as Data, full `.save()` no longer destroys the hash. But `.db_update()` remains the cleanest primitive for column-only updates.

## What about the encryption_key?

Frappe's `encryption_key` (site_config) encrypts Password fieldtype values stored in `__Auth`. After the Phase 4.7 conversion:
- `vecrm.VECRM Employee.password_hash` no longer uses `__Auth` (it's a Data column)
- Other Password fields elsewhere in Frappe core (e.g., User.password) still depend on encryption_key
- Rotating encryption_key remains worthwhile per PD-S26-AUTH-CREDS-ROTATE, but is no longer load-bearing for VECRM portal auth

## Where this is enforced

- `vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json` — password_hash is Data (post-Phase 4.7)
- Future fields storing PIN hashes (PD-S26-AUTH-PHONE-PIN) MUST also use Data
- Future fields storing API keys, tokens, or any hashed/derived secrets MUST use Data unless they need decryption

## Mechanism (verified via S25 Phase 4 Smoke 5 + Phase 4.7 diagnostic)

Smoke 5 surfaced: Test HR Approver's password_hash was wiped between Phase 2.8 bootstrap and Phase 4 smoke. Diagnostic probe showed `__Auth` row deleted after a `frappe.get_doc(HR).save()` in Phase 4 — even though `.save()` was called only to clear lockout (no intent to touch the password).

Root cause confirmed via Frappe source: Password fields are not populated on `get_doc`; they hold `None`. When `.save()` runs, the controller's `db_update` path sees the field is "set" to None and propagates None into `__Auth`, which Frappe interprets as "user wants to clear this credential" — deletion follows.

## Related observations

- OBS-S25-AK — root cause (Password fieldtype delete-on-save)
- OBS-S25-AH — earlier-iteration workaround that was reverted (`get_decrypted_password` dance)

## Migration discipline

When converting a Password field to Data (as in Phase 4.7):
1. Update the doctype JSON
2. Write a forward migration that:
   - `frappe.reload_doc(app, "doctype", name)` — applies fieldtype change
   - `from frappe.model.sync import sync_for; sync_for(app, force=1)` — forces schema sync so the new column lands on the parent table
   - `DELETE FROM __Auth WHERE doctype = ... AND fieldname = ...` — drops orphaned __Auth rows
   - `UPDATE tabName SET fieldname = NULL` — clears the parent column for fresh re-bootstrap (since old __Auth values cannot be recovered)
3. Write a paired rollback (clears the column on revert)
4. Re-bootstrap any data the migration cleared
