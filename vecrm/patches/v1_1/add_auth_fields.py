"""S25 PD-S25-VECRM-AUTH v2 — add email-login credential fields to VECRM Employee.

Email-only auth (S25). Phone+PIN fields deferred to S26.
Idempotent. Paired rollback: rollback_add_auth_fields.py.
"""

import frappe


def execute() -> None:
    frappe.reload_doc("vecrm", "doctype", "vecrm_employee")

    # Pre-assertion: confirm no duplicate vecrm_email values exist
    duplicates = frappe.db.sql(
        """
        SELECT vecrm_email, COUNT(*) as cnt
        FROM `tabVECRM Employee`
        WHERE vecrm_email IS NOT NULL AND vecrm_email != ''
        GROUP BY vecrm_email
        HAVING cnt > 1
        """,
        as_dict=True,
    )
    if duplicates:
        frappe.throw(
            f"Cannot apply unique constraint on vecrm_email: duplicates exist: {duplicates}",
            frappe.ValidationError,
        )

    frappe.reload_doc("vecrm", "doctype", "vecrm_employee")

    # Initialize integer defaults on existing rows
    frappe.db.sql(
        """
        UPDATE `tabVECRM Employee`
        SET failed_password_attempts = COALESCE(failed_password_attempts, 0)
        WHERE failed_password_attempts IS NULL
        """
    )

    frappe.db.commit()
    print("[S25 patch] add_auth_fields v2 complete — 4 credential fields, vecrm_email unique applied")
