# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""Add approval_status + reject-marker fields to voucher doctypes (v1_8).

PD-S29-VOUCHER-APPROVER-PORTAL-B2 / S35 approval-status lifecycle refactor.

Adds to BOTH VECRM Travel Voucher and VECRM Expense Voucher:
  - approval_status (Select: Pending/Approved/Rejected, default Pending)
  - rejected_by_employee, rejected_by_role (Data, nullable)
  - rejected_at (Datetime, nullable)
  - rejection_reason (Small Text, nullable)

approval_status becomes the SINGLE SOURCE OF TRUTH for voucher lifecycle
state. The existing presence-based markers (approved_by_employee etc.)
remain as detail attributes OF that state, not the state itself.

Backfill (docstatus-aware — see S35 inventory recon):
  - docstatus=1 AND approved_by_employee IS NOT NULL → 'Approved'
  - everything else                                  → 'Pending' (column default)
  docstatus=2 (cancelled) rows stay 'Pending' — legacy, outside the new
  lifecycle (Frappe docstatus already carries 'cancelled'; approval_status
  deliberately does NOT duplicate it, to avoid dual-source-of-truth).

Pre/post assertions per VECRM-L22. Expected approved-row counts from S35
recon: 8 travel + 1 expense = 9 total at docstatus=1 with approver set.

Paired rollback: rollback_add_voucher_approval_status.py
"""

import frappe

DOCTYPES = [
    ("vecrm_travel_voucher", "VECRM Travel Voucher", "tabVECRM Travel Voucher"),
    ("vecrm_expense_voucher", "VECRM Expense Voucher", "tabVECRM Expense Voucher"),
]
NEW_COLS = [
    "approval_status",
    "rejected_by_employee",
    "rejected_by_role",
    "rejected_at",
    "rejection_reason",
]


def execute():
    # Step 1: reload both doctype JSONs → Frappe auto-adds the columns
    for module_dt, _label, _table in DOCTYPES:
        frappe.reload_doc("vecrm", "doctype", module_dt)

    # Step 2: verify every new column materialized on both tables
    for _m, _label, table in DOCTYPES:
        for col in NEW_COLS:
            result = frappe.db.sql(
                f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,), as_dict=True
            )
            if not result:
                frappe.throw(f"v1_8 failed: {table}.{col} not created after doctype sync")
        # approval_status must be NOT NULL with a default (Frappe Select default)
        status_col = frappe.db.sql(
            f"SHOW COLUMNS FROM `{table}` LIKE %s", ("approval_status",), as_dict=True
        )[0]
        # reject markers must be nullable
        for col in NEW_COLS[1:]:
            r = frappe.db.sql(
                f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,), as_dict=True
            )[0]
            if r["Null"] != "YES":
                frappe.throw(f"v1_8 failed: {table}.{col} must be nullable (got Null={r['Null']})")

    # Step 3: PRE-assertion — capture expected Approved count per table
    expected = {}
    for _m, _label, table in DOCTYPES:
        n = frappe.db.sql(
            f"SELECT COUNT(*) FROM `{table}` "
            f"WHERE docstatus=1 AND approved_by_employee IS NOT NULL"
        )[0][0]
        expected[table] = n

    # Step 4: BACKFILL — docstatus-aware, idempotent (re-runnable)
    for _m, _label, table in DOCTYPES:
        frappe.db.sql(
            f"""UPDATE `{table}` SET approval_status = CASE
                    WHEN docstatus = 1 AND approved_by_employee IS NOT NULL THEN 'Approved'
                    ELSE 'Pending'
                END"""
        )

    # Step 5: POST-assertion — Approved count must equal pre-captured expected;
    # zero NULL approval_status rows
    for _m, _label, table in DOCTYPES:
        approved_now = frappe.db.sql(
            f"SELECT COUNT(*) FROM `{table}` WHERE approval_status='Approved'"
        )[0][0]
        if approved_now != expected[table]:
            frappe.throw(
                f"v1_8 POST-assert failed: {table} approval_status='Approved' "
                f"= {approved_now}, expected {expected[table]}"
            )
        nulls = frappe.db.sql(
            f"SELECT COUNT(*) FROM `{table}` WHERE approval_status IS NULL"
        )[0][0]
        if nulls:
            frappe.throw(f"v1_8 POST-assert failed: {table} has {nulls} NULL approval_status rows")

    frappe.db.commit()
    for _m, _label, table in DOCTYPES:
        frappe.clear_cache(doctype=_label)
    print(
        "v1_8 complete. 5 fields × 2 voucher doctypes added; approval_status "
        f"backfilled. Approved rows: {expected}"
    )
