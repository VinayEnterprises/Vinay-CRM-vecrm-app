"""Rollback for add_lead_required_fields (S30 PR-1).

DROPS contact_number, contact_email, meeting_brief columns from
tabVECRM Lead. Any data in those columns is destroyed.

Per VECRM-L22: paired rollback exists for every forward migration.

NOTE: this does NOT revert the doctype JSON change. To fully revert,
also `git revert` the JSON change and re-run `bench migrate`, otherwise
the next migrate's model sync will re-add the columns from the JSON.

Mirrors the DESCRIBE-then-ALTER idempotent pattern from
rollback_add_lead_creating_employee.py.
"""

import frappe


COLS_TO_DROP = ("contact_number", "contact_email", "meeting_brief")


def execute() -> None:
    print("S30 PR-1 ROLLBACK: rollback_add_lead_required_fields")

    existing = frappe.db.sql("DESCRIBE `tabVECRM Lead`", as_dict=True)
    existing_cols = {c["Field"] for c in existing}

    for col_name in COLS_TO_DROP:
        if col_name in existing_cols:
            frappe.db.sql(f"ALTER TABLE `tabVECRM Lead` DROP COLUMN `{col_name}`")
            print(f"  Dropped column {col_name}")
        else:
            print(f"  Column {col_name} already absent (idempotent)")

    frappe.db.commit()
