"""
PD-S30-LEAD-OWNER-ATTRIBUTION migration (v1_4 forward patch).

Rewrites lead_owner and inquiry_owner from the BFF service account
(vecrm-portal@vinayenterprises.co.in) to the human operator
(ajay@vinayenterprises.co.in) for the 2 Lead rows (and 0 Inquiry rows)
affected by the S24-S30 bug.

Case A applies (Frappe User ajay@vinayenterprises.co.in exists, enabled,
System User) per S30-close F-1.4 probe.

Administrator-attributed rows are NOT migrated (historical truth per ATT-9).
Already-correct ajay@-attributed rows are not touched (WHERE clause filters).

Paired rollback: rollback_migrate_lead_owner_attribution.py (per VECRM-L22).
"""

import frappe


def execute():
    """Forward-only migration of buggy lead_owner / inquiry_owner rows."""

    # Lead migration
    frappe.db.sql(
        """
        UPDATE `tabVECRM Lead`
        SET lead_owner = 'ajay@vinayenterprises.co.in'
        WHERE lead_owner = 'vecrm-portal@vinayenterprises.co.in'
        """
    )
    lead_remaining = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabVECRM Lead`
        WHERE lead_owner = 'vecrm-portal@vinayenterprises.co.in'
        """
    )[0][0]
    if lead_remaining != 0:
        raise Exception(
            f"v1_4 migration incomplete: {lead_remaining} Lead rows still attributed to service account"
        )

    # Inquiry migration
    frappe.db.sql(
        """
        UPDATE `tabVECRM Inquiry`
        SET inquiry_owner = 'ajay@vinayenterprises.co.in'
        WHERE inquiry_owner = 'vecrm-portal@vinayenterprises.co.in'
        """
    )
    inquiry_remaining = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabVECRM Inquiry`
        WHERE inquiry_owner = 'vecrm-portal@vinayenterprises.co.in'
        """
    )[0][0]
    if inquiry_remaining != 0:
        raise Exception(
            f"v1_4 migration incomplete: {inquiry_remaining} Inquiry rows still attributed to service account"
        )

    frappe.db.commit()
    print(
        "v1_4 LEAD-OWNER-ATTRIBUTION migration complete. "
        "Buggy lead_owner / inquiry_owner rows rewritten to ajay@vinayenterprises.co.in."
    )
