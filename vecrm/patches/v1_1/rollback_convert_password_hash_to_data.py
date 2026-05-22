"""Rollback for convert_password_hash_to_data.

Clears the runtime state (NULLs the column). The fieldtype revert
(Data → Password) requires reverting the JSON change via git revert
and re-running bench migrate.
"""

import frappe


def execute() -> None:
    frappe.db.sql("""
        UPDATE `tabVECRM Employee`
        SET password_hash = NULL
    """)
    frappe.db.commit()
    print("[rollback] cleared password_hash on VECRM Employee parent table")
