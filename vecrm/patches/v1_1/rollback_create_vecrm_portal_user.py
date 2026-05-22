"""Rollback for create_vecrm_portal_user.py.

Disables (does NOT delete) the shared portal user.
"""

import frappe

VECRM_PORTAL_USER_EMAIL = "vecrm-portal@vinayenterprises.co.in"


def execute() -> None:
    if not frappe.db.exists("User", VECRM_PORTAL_USER_EMAIL):
        print(f"[rollback] {VECRM_PORTAL_USER_EMAIL} doesn't exist, skipping")
        return
    frappe.db.set_value("User", VECRM_PORTAL_USER_EMAIL, "enabled", 0)
    frappe.db.commit()
    print(f"[rollback] disabled {VECRM_PORTAL_USER_EMAIL} (NOT deleted)")
