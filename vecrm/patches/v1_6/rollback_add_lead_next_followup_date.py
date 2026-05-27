# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""
Rollback for v1_6/add_lead_next_followup_date.py.

WARNING: This drops the next_followup_date column and ALL data in it.
Only run during rollback to a pre-S33 state. Not run as part of normal
forward migration; must be invoked explicitly via:

  bench --site crm.vinayenterprises.co.in execute \\
    vecrm.patches.v1_6.rollback_add_lead_next_followup_date.execute
"""

import frappe


def execute():
    """Drop next_followup_date column from tabVECRM Lead."""
    columns = frappe.db.get_table_columns("VECRM Lead")
    if "next_followup_date" not in columns:
        # Already absent; no-op
        return

    frappe.db.sql(
        """
        ALTER TABLE `tabVECRM Lead`
        DROP COLUMN `next_followup_date`
        """
    )

    frappe.clear_cache(doctype="VECRM Lead")
