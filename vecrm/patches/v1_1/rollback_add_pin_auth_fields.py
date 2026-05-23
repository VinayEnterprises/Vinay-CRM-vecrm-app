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
            print(f"  Dropped column {col}")
        else:
            print(f"  Column {col} already absent (idempotent)")

    frappe.db.commit()
