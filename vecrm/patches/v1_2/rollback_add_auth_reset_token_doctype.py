# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""PD-S28-AUTH-RESET-SCHEMA -- paired rollback for add_auth_reset_token_doctype.

This file is NOT registered in patches.txt. It exists per VECRM-L22
paired-rollback discipline. Invoke manually only if the forward patch
must be reversed.

Manual invocation:
    bench --site crm.vinayenterprises.co.in execute \\
        vecrm.patches.v1_2.rollback_add_auth_reset_token_doctype.execute

Effect: drops `tabVECRM Auth Reset Token`. ALL TOKEN ROWS WILL BE LOST.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    """Drop VECRM Auth Reset Token doctype.

    DESTRUCTIVE. Removes all reset tokens. Use only to reverse the forward
    patch in a recovery scenario.
    """
    print("PD-S28-AUTH-RESET-SCHEMA: rollback_add_auth_reset_token_doctype (DESTRUCTIVE)")

    # Count rows before dropping (informational)
    if frappe.db.table_exists("tabVECRM Auth Reset Token"):
        count = frappe.db.sql("SELECT COUNT(*) FROM `tabVECRM Auth Reset Token`")[0][0]
        print(f"  Dropping tabVECRM Auth Reset Token (had {count} rows)")
    else:
        print("  tabVECRM Auth Reset Token does not exist; nothing to drop")
        return

    # Drop the table
    frappe.db.sql("DROP TABLE IF EXISTS `tabVECRM Auth Reset Token`")

    # Remove the doctype registration
    if frappe.db.exists("DocType", "VECRM Auth Reset Token"):
        frappe.delete_doc("DocType", "VECRM Auth Reset Token", force=True)

    frappe.db.commit()

    print("  VECRM Auth Reset Token doctype + table dropped.")
