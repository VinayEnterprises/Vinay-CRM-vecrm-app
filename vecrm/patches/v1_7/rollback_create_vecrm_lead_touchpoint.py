# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""
Rollback for PD-S30-LEAD-FOLLOWUP Phase 2 — drop VECRM Lead Touchpoint table.

PAIRED WITH: create_vecrm_lead_touchpoint.py

This is NOT registered in patches.txt. It is invoked manually only when
rolling back a deploy that introduced the touchpoint doctype. The forward
patch is idempotent; this rollback is destructive and intentional.

Usage:
    bench --site crm.vinayenterprises.co.in execute \\
        vecrm.patches.v1_7.rollback_create_vecrm_lead_touchpoint.execute
"""

import frappe


def execute():
    """Drop tabVECRM Lead Touchpoint and clear doctype meta cache.

    Idempotent: no-op if table is already absent.

    This rollback assumes the operator has already:
      1. Reverted the doctype JSON file (via git checkout or rollback PR).
      2. Confirmed no production data exists in the table that would be lost
         (or has been backed up separately).
    """
    if not frappe.db.table_exists("VECRM Lead Touchpoint"):
        # Already absent; idempotent no-op
        return

    # Drop the table
    frappe.db.sql("DROP TABLE IF EXISTS `tabVECRM Lead Touchpoint`")

    # Clear doctype meta cache
    frappe.clear_cache(doctype="VECRM Lead Touchpoint")
