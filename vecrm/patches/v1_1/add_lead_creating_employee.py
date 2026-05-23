"""S27 PR #20: Add creating_employee field on VECRM Lead.

Adds a Link -> VECRM Employee column to tabVECRM Lead, populated at
creation by vecrm.api.create_lead from frappe.session.data["vecrm_employee_phone"].
Backfills existing rows to Ajay Salvi's VECRM Employee record per S27
dispatch decision (3a) -- pre-S27 leads are demo/test data with no
real rep attribution.

This patch ships the SCHEMA SUBSTRATE only; no scoping logic. S28
(PD-S28-LEAD-SCOPING-CUTOVER) will consume the field via scoped
get_lead / list_leads API methods.

Per VECRM-L22: paired rollback exists (rollback_add_lead_creating_employee.py).

Mirrors the reload_doc + sync_for + meta-assert pattern from
add_pin_auth_fields.py (VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE:
existing code wins over the dispatch's illustrative ALTER pattern).
"""

import frappe


# Ajay's VECRM Employee primary key (= vecrm_phone), verified via
# recon R7 in PD-S27-A1-LEAD-DETAIL-recon-findings.md.
# If this value is wrong, the patch fails fast in Step 1.
AJAY_EMPLOYEE_NAME = "+91-9327547536"


def execute() -> None:
    print("PD-S27-LEAD-SCOPING Phase B PR #20: add_lead_creating_employee")

    # Step 1: precondition -- assert Ajay's employee record exists (fail fast)
    if not frappe.db.exists("VECRM Employee", AJAY_EMPLOYEE_NAME):
        raise Exception(
            f"Patch precondition failed: VECRM Employee {AJAY_EMPLOYEE_NAME!r} "
            f"does not exist. Re-verify per recon R7 / dispatch §3.2."
        )

    # Step 2: reload doctype + sync app to materialize the column from JSON
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead")
    from frappe.model.sync import sync_for
    sync_for("vecrm", force=1)

    # Step 3: assert column present via meta
    meta = frappe.get_meta("VECRM Lead")
    field_names = {f.fieldname for f in meta.fields}
    if "creating_employee" not in field_names:
        raise Exception(
            "Patch assertion failed: creating_employee field missing after "
            "reload_doc + sync_for. JSON change may not have applied. "
            "Investigate before retrying."
        )

    # Step 4: backfill NULL rows to Ajay
    frappe.db.sql(
        """
        UPDATE `tabVECRM Lead`
        SET creating_employee = %s
        WHERE creating_employee IS NULL
        """,
        (AJAY_EMPLOYEE_NAME,),
    )
    frappe.db.commit()

    # Step 5: assertion -- no NULLs remain
    null_count = frappe.db.sql(
        """SELECT COUNT(*) FROM `tabVECRM Lead` WHERE creating_employee IS NULL"""
    )[0][0]
    if null_count > 0:
        raise Exception(
            f"Patch assertion failed: {null_count} VECRM Lead rows still have "
            f"NULL creating_employee after backfill. Investigate."
        )

    total = frappe.db.sql("""SELECT COUNT(*) FROM `tabVECRM Lead`""")[0][0]
    print(
        f"  Synced + backfilled {total} rows to {AJAY_EMPLOYEE_NAME}, "
        f"0 NULLs remaining."
    )
