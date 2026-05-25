"""S30 PR-1: Add contact_number, contact_email, meeting_brief to VECRM Lead.

Schema-permissive (nullable cols) + code-mandatory + forward-only.
Existing pre-S30 rows (15 at S30-open per pendency) stay NULL in the
3 new columns; API-level enforcement at vecrm.api.create_lead handles
the mandatory-ness for new creates.

Per VECRM-L22: paired rollback exists (rollback_add_lead_required_fields.py).

Mirrors the reload_doc + sync_for + meta-assert pattern from
add_lead_creating_employee.py (S27 PR #20) — the canonical additive-
column template established for VECRM Lead. Per
VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE: existing migration pattern
wins over the dispatch's SHOW COLUMNS variant.

PD-S29-LEAD-FORM-FIELDS / B-phase PR-1.
"""

import frappe


NEW_FIELDS = ("contact_number", "contact_email", "meeting_brief")


def execute() -> None:
    print("PD-S29-LEAD-FORM-FIELDS PR-1: add_lead_required_fields")

    # Step 1: reload doctype + sync app to materialize the columns from JSON
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead")
    from frappe.model.sync import sync_for
    sync_for("vecrm", force=1)

    # Step 2: assert all 3 columns present via meta
    meta = frappe.get_meta("VECRM Lead")
    field_names = {f.fieldname for f in meta.fields}
    for fieldname in NEW_FIELDS:
        if fieldname not in field_names:
            raise Exception(
                f"Patch assertion failed: {fieldname!r} field missing after "
                f"reload_doc + sync_for. JSON change may not have applied. "
                f"Investigate before retrying."
            )

    # Step 3: assert columns are nullable at the DB layer (NOT NULL must be absent
    # for the forward-only no-backfill design to hold — existing 15 rows would
    # block migration if NOT NULL were applied).
    for col_name in NEW_FIELDS:
        cols = frappe.db.sql(
            "SHOW COLUMNS FROM `tabVECRM Lead` WHERE Field = %s",
            (col_name,),
            as_dict=True,
        )
        if not cols:
            raise Exception(
                f"Patch assertion failed: column {col_name!r} missing from "
                f"tabVECRM Lead after sync_for. DB sync may not have applied."
            )
        if cols[0]["Null"] != "YES":
            raise Exception(
                f"Patch assertion failed: column {col_name!r} must be nullable "
                f"(got Null={cols[0]['Null']!r}). The forward-only no-backfill "
                f"design requires NULL-tolerant cols so the existing 15 rows "
                f"remain readable."
            )

    # Step 4: NO backfill — existing rows stay NULL. This is intentional per
    # the dispatch §1 migration lock: schema-permissive + code-mandatory +
    # forward-only. The portal's Lead detail page renders "—" for the new
    # fields on pre-S30 rows.

    total = frappe.db.sql("SELECT COUNT(*) FROM `tabVECRM Lead`")[0][0]
    null_counts = {}
    for col_name in NEW_FIELDS:
        nulls = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabVECRM Lead` WHERE `{col_name}` IS NULL"
        )[0][0]
        null_counts[col_name] = nulls

    print(
        f"  Added 3 columns to {total} total Lead rows. "
        f"NULL counts (expected = total per forward-only design): {null_counts}"
    )
