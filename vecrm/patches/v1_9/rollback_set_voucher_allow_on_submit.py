"""Rollback v1_9 — revert allow_on_submit flags. Manual only, not in patches.txt.

allow_on_submit is metadata (no column to drop). Rollback = revert the doctype
JSON (git) then bench migrate; doctype-sync clears the flags. This script just
clears caches + documents the procedure.

    bench --site crm.vinayenterprises.co.in execute \\
      vecrm.patches.v1_9.rollback_set_voucher_allow_on_submit.execute
"""

import frappe


def execute():
    for doctype in ("VECRM Travel Voucher", "VECRM Expense Voucher"):
        frappe.clear_cache(doctype=doctype)
    print("v1_9 rollback: caches cleared. REVERT the doctype JSON via git + "
          "bench migrate to actually clear allow_on_submit flags (metadata, not DDL).")
