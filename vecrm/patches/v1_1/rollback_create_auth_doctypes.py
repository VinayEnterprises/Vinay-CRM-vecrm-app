"""Rollback for create_auth_doctypes.py."""

import frappe


def execute() -> None:
    try:
        frappe.db.sql("DROP TABLE IF EXISTS `tabVECRM Auth Audit Log`")
        print("[rollback] dropped tabVECRM Auth Audit Log")
    except Exception as e:
        print(f"[rollback] error: {e}")
    frappe.db.commit()
