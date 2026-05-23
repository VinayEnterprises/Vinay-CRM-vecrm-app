"""Rollback for fix_portal_user_type.py.

Reverts user_type back to System User. Note: this does NOT revert the
role.json fixture change; that requires a manual git revert.
"""

import frappe


VECRM_PORTAL_USER_EMAIL = "vecrm-portal@vinayenterprises.co.in"


def execute() -> None:
    if not frappe.db.exists("User", VECRM_PORTAL_USER_EMAIL):
        print(f"[rollback] {VECRM_PORTAL_USER_EMAIL} doesn't exist, skipping")
        return
    frappe.db.set_value("User", VECRM_PORTAL_USER_EMAIL, "user_type", "System User")
    frappe.db.commit()
    print(f"[rollback] reverted {VECRM_PORTAL_USER_EMAIL} user_type to System User")
