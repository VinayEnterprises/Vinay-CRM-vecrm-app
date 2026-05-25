"""Rollback PD-S31-LEAD-EXPANSION-AND-CLOSURE migration (v1_5 paired).

Drops the 6 new Lead columns + the 1 new Inquiry column.

Run manually via:
    bench --site crm.vinayenterprises.co.in execute \
      vecrm.patches.v1_5.rollback_add_lead_expansion_and_closure_fields.execute

WARNING — destructive:
  - Any data in contact_person_name, contact_person_designation, closure_notes,
    attachment_1, attachment_2, attachment_3 is permanently lost.
  - Any Inquiry rows in status='Closed-Won' or 'Closed-Lost' must be migrated
    to 'Open' or 'Quoting' BEFORE running rollback, or the doctype JSON revert
    will fail (Frappe will refuse to remove enum values that have referencing rows).

Paired with: add_lead_expansion_and_closure_fields.py
"""

import frappe


def execute():
    """Manual rollback — drops the v1_5 columns."""

    # Drop Lead columns
    for col in (
        "contact_person_name",
        "contact_person_designation",
        "closure_notes",
        "attachment_1",
        "attachment_2",
        "attachment_3",
    ):
        try:
            frappe.db.sql(f"ALTER TABLE `tabVECRM Lead` DROP COLUMN `{col}`")
            print(f"Dropped tabVECRM Lead.{col}")
        except Exception as e:
            print(f"Warning: could not drop tabVECRM Lead.{col}: {e}")

    # Drop Inquiry column
    try:
        frappe.db.sql("ALTER TABLE `tabVECRM Inquiry` DROP COLUMN `closure_notes`")
        print("Dropped tabVECRM Inquiry.closure_notes")
    except Exception as e:
        print(f"Warning: could not drop tabVECRM Inquiry.closure_notes: {e}")

    frappe.db.commit()
    print(
        "v1_5 rollback complete. WARNING: doctype JSON must also be reverted "
        "to fully restore pre-v1_5 schema."
    )
