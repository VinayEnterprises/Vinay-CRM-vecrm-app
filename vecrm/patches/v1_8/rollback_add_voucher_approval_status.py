"""Rollback v1_8 — drop approval_status + reject-marker columns from both vouchers.

PAIRED WITH: add_voucher_approval_status.py. NOT in patches.txt — manual only.

    bench --site crm.vinayenterprises.co.in execute \\
      vecrm.patches.v1_8.rollback_add_voucher_approval_status.execute

WARNING — destructive: all reject-marker + approval_status data lost. Revert
the doctype JSON (git) BEFORE running, or the next bench migrate re-adds the cols.
"""

import frappe

TABLES = ["tabVECRM Travel Voucher", "tabVECRM Expense Voucher"]
COLS = ["approval_status", "rejected_by_employee", "rejected_by_role",
        "rejected_at", "rejection_reason"]


def execute():
    for table in TABLES:
        for col in COLS:
            try:
                frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `{col}`")
                print(f"Dropped {table}.{col}")
            except Exception as e:
                print(f"Warning: could not drop {table}.{col}: {e}")
    frappe.db.commit()
    print("v1_8 rollback complete. Revert doctype JSON to fully restore schema.")
