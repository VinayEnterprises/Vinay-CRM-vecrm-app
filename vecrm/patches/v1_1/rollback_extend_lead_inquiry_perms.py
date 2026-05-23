"""Rollback for extend_lead_inquiry_perms.

Reverting requires the JSON to be reverted first (via git revert), then this
patch reloads the doctypes and re-syncs to apply the reverted perms.

If JSON is NOT reverted, this patch is a no-op (reload from current JSON = same state).
"""

import frappe
from frappe.model.sync import sync_for


def execute() -> None:
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead")
    frappe.reload_doc("vecrm", "doctype", "vecrm_inquiry")
    sync_for("vecrm", force=1, reset_permissions=True)
    frappe.clear_cache()
    frappe.db.commit()
    print("[rollback] vecrm_lead + vecrm_inquiry reloaded; perms re-synced from current JSON state")
