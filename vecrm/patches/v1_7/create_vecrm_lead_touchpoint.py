# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""
PD-S30-LEAD-FOLLOWUP Phase 2 — create VECRM Lead Touchpoint doctype.

The doctype JSON at vecrm/vecrm/doctype/vecrm_lead_touchpoint/ is the source
of truth. Frappe's `bench migrate` runs its doctype-sync pass BEFORE this
patch (post_model_sync registration), so the `tabVECRM Lead Touchpoint`
table is created automatically from the JSON.

This patch is a verifier per VECRM-L22 (atomic transaction with assertions):
it confirms the table materialized and raises loud if not. No DDL is issued
here — that would be redundant and could conflict with Frappe's own
doctype-sync output.

Rollback paired at: rollback_create_vecrm_lead_touchpoint.py
"""

import frappe


def execute():
    """Verify VECRM Lead Touchpoint table exists post doctype-sync.

    The forward patch is a no-op-then-assert pattern. Frappe creates the
    table from doctype JSON during the bench migrate doctype-sync phase;
    this patch confirms that happened and clears the doctype meta cache.
    """
    # Reload the doctype JSON to refresh schema cache before verifying
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead_touchpoint")

    # Verifier: assert the table materialized
    if not frappe.db.table_exists("VECRM Lead Touchpoint"):
        frappe.throw(
            "v1_7 patch: tabVECRM Lead Touchpoint did not materialize after "
            "doctype sync. Investigate vecrm/vecrm/doctype/vecrm_lead_touchpoint/ "
            "JSON validity and Frappe's migrate output."
        )

    # Defensive: clear doctype meta cache so subsequent reads see the new doctype
    frappe.clear_cache(doctype="VECRM Lead Touchpoint")
