"""S25 PD-S25-VECRM-AUTH v2 — register VECRM Auth Audit Log.

Reset Token doctype deferred to S26.
Idempotent. Paired rollback: rollback_create_auth_doctypes.py.
"""

import frappe


def execute() -> None:
    frappe.reload_doc("vecrm", "doctype", "vecrm_auth_audit_log")
    frappe.db.commit()
    print("[S25 patch] VECRM Auth Audit Log doctype reloaded")
