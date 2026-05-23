"""Rollback for add_lead_creating_employee (S27 PR #20).

DROPS the creating_employee column from tabVECRM Lead. All backfilled
values are lost. Use only if the forward patch must be reverted
(e.g., before re-applying with a different backfill target).

Per VECRM-L22: paired rollback exists for every forward migration.

NOTE: this does NOT revert the doctype JSON change. To fully revert,
also `git revert` the JSON change and re-run `bench migrate`, otherwise
the next migrate's model sync will re-add the column from the JSON.

Mirrors the DESCRIBE-then-ALTER idempotent pattern from
rollback_add_pin_auth_fields.py.
"""

import frappe


def execute() -> None:
    print("S27 PR #20 ROLLBACK: rollback_add_lead_creating_employee")

    existing = frappe.db.sql("DESCRIBE `tabVECRM Lead`", as_dict=True)
    existing_cols = {c["Field"] for c in existing}

    if "creating_employee" in existing_cols:
        frappe.db.sql("ALTER TABLE `tabVECRM Lead` DROP COLUMN `creating_employee`")
        frappe.db.commit()
        print("  Dropped column creating_employee")
    else:
        print("  Column creating_employee already absent (idempotent)")
