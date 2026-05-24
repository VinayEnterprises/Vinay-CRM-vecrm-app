# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def execute() -> None:
    """PD-S28-AUTH-RESET-SCHEMA: Create VECRM Auth Reset Token doctype.

    Forward patch -- reloads the doctype definition into the database,
    creating the `tabVECRM Auth Reset Token` table if it doesn't exist,
    and asserts the table is present with the expected columns.

    Paired rollback: rollback_add_auth_reset_token_doctype.py
    Ref: PD-S28-AUTH-RESET-INFRA-recon-findings-ADDENDUM.md §3
    """
    print("PD-S28-AUTH-RESET-SCHEMA: add_auth_reset_token_doctype")

    # Reload the doctype from the JSON definition on disk
    frappe.reload_doc("vecrm", "doctype", "vecrm_auth_reset_token")

    # Assert the table exists
    if not frappe.db.exists("DocType", "VECRM Auth Reset Token"):
        frappe.throw("VECRM Auth Reset Token doctype did not register after reload_doc")

    # Assert all required columns are present
    expected_columns = {
        "name",
        "token_hash",
        "employee",
        "reset_for",
        "expires_at",
        "consumed_at",
        "ip_address",
        "creation",
        "modified",
        "modified_by",
        "owner",
        "docstatus",
        "idx",
    }
    actual_columns = {
        row[0]
        for row in frappe.db.sql(
            "SHOW COLUMNS FROM `tabVECRM Auth Reset Token`",
        )
    }
    missing = expected_columns - actual_columns
    if missing:
        frappe.throw(
            f"VECRM Auth Reset Token missing expected columns after reload: {missing}",
        )

    # Assert unique constraint on token_hash (per JSON definition)
    indexes = frappe.db.sql(
        """
        SELECT INDEX_NAME, NON_UNIQUE
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'tabVECRM Auth Reset Token'
          AND COLUMN_NAME = 'token_hash'
        """,
        as_dict=True,
    )
    if not any(idx["NON_UNIQUE"] == 0 for idx in indexes):
        frappe.throw(
            "VECRM Auth Reset Token: token_hash unique constraint missing after reload",
        )

    # Assert zero pre-existing rows (this is a brand-new doctype)
    count = frappe.db.count("VECRM Auth Reset Token")
    if count != 0:
        frappe.throw(
            f"VECRM Auth Reset Token unexpectedly has {count} rows; expected 0 for new doctype",
        )

    print("  VECRM Auth Reset Token doctype registered, all columns present, unique constraint active, 0 rows.")
