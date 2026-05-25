"""
PD-S30-LEAD-OWNER-ATTRIBUTION rollback (v1_4 paired with forward patch).

Reverses migrate_lead_owner_attribution.py: restores lead_owner /
inquiry_owner to vecrm-portal@vinayenterprises.co.in.

Run manually via:
    bench --site crm.vinayenterprises.co.in execute \
      vecrm.patches.v1_4.rollback_migrate_lead_owner_attribution.execute

WARNING — Rollback blast radius: this rollback's WHERE clause matches
ALL ajay@-attributed rows, including the 11 S23 pre-bug correct rows
and any post-PR-1 forward-correct rows. **Only run during full v1_4
reversal.** For surgical reversal of specific rows, use targeted manual
SQL with explicit WHERE name IN (...) instead.
"""

import frappe


def execute():
    """Manual rollback — restores buggy state for ALL ajay@-attributed rows."""

    frappe.db.sql(
        """
        UPDATE `tabVECRM Lead`
        SET lead_owner = 'vecrm-portal@vinayenterprises.co.in'
        WHERE lead_owner = 'ajay@vinayenterprises.co.in'
        """
    )

    frappe.db.sql(
        """
        UPDATE `tabVECRM Inquiry`
        SET inquiry_owner = 'vecrm-portal@vinayenterprises.co.in'
        WHERE inquiry_owner = 'ajay@vinayenterprises.co.in'
        """
    )

    frappe.db.commit()
    print(
        "v1_4 LEAD-OWNER-ATTRIBUTION rollback complete. "
        "WARNING: this rolls back ALL ajay@-attributed rows, not just the 2 originally migrated."
    )
