"""Rollback for add_auth_fields.py.

Drops the 4 added fields and the unique constraint on vecrm_email.
"""

import frappe


def execute() -> None:
    columns_to_drop = [
        "password_hash",
        "failed_password_attempts",
        "locked_until",
        "last_login_at",
    ]

    for col in columns_to_drop:
        try:
            frappe.db.sql(f"ALTER TABLE `tabVECRM Employee` DROP COLUMN `{col}`")
            print(f"[rollback] dropped column: {col}")
        except Exception as e:
            print(f"[rollback] skipping {col}: {e}")

    try:
        frappe.db.sql("ALTER TABLE `tabVECRM Employee` DROP INDEX `vecrm_email`")
        print("[rollback] dropped unique index on vecrm_email")
    except Exception as e:
        print(f"[rollback] skipping unique index drop: {e}")

    frappe.db.commit()
