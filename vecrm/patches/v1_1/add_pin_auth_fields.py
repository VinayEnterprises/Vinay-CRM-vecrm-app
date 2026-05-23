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

    print("  All 4 PIN fields added with correct types")
    print("  pin_hash uses Data (NOT Password) per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE")

    frappe.db.commit()
