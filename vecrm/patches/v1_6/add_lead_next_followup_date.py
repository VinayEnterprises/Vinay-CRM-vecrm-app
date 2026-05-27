# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""
PD-S30-LEAD-FOLLOWUP Phase 1 — add next_followup_date field on VECRM Lead.

Field is nullable (Date, no default). Backward-compat: existing rows have NULL,
which is interpreted by the portal as "no follow-up scheduled" and surfaces in
the dedicated filter chip.

Per Q-LEAD-FOLLOWUP-LOCK Q-13 + Tension 5: existing pre-S30 leads are demo
data; production cutover will truncate VECRM Lead before live use (see
PD-S33-NEXT-LEAD-DATA-WIPE). Therefore no backfill is performed here.

Rollback paired at: rollback_add_lead_next_followup_date.py
"""

import frappe


def execute():
    """Add next_followup_date Date column to tabVECRM Lead.

    Doctype JSON is the source of truth; this patch ensures the SQL column
    exists for installations that migrate via `bench migrate` after the
    doctype edit. On Frappe v15+, `frappe.reload_doc()` followed by
    explicit ALTER TABLE keeps the column add atomic-and-transactional
    with the rest of the patch run.
    """
    # Reload the doctype JSON to refresh the schema cache before column ops
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead")

    # Idempotent column add — guard against re-runs
    columns = frappe.db.get_table_columns("VECRM Lead")
    if "next_followup_date" in columns:
        # Already present (e.g. patch re-run); no-op
        return

    frappe.db.sql(
        """
        ALTER TABLE `tabVECRM Lead`
        ADD COLUMN `next_followup_date` DATE NULL
        """
    )

    # Defensive: clear doctype meta cache so subsequent reads see the new field
    frappe.clear_cache(doctype="VECRM Lead")
