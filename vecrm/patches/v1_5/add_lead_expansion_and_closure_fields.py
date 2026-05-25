"""Add LEAD-EXPANSION fields + extend status enums (v1_5 forward patch).

Schema-permissive (nullable cols). Forward-only.

VECRM Lead additions:
  - contact_person_name (Data, nullable)
  - contact_person_designation (Data, nullable)
  - closure_notes (Small Text, nullable)
  - attachment_1, attachment_2, attachment_3 (Attach, nullable)
  - status enum: Open\\nConverted\\nClosed-Lost → Open\\nConverted\\nClosed-Won\\nClosed-Lost

VECRM Inquiry additions:
  - closure_notes (Small Text, nullable)
  - status enum: Open\\nQuoting\\nClosed-by-Ops → Open\\nQuoting\\nClosed-Won\\nClosed-Lost
    (Closed-by-Ops dropped — probe confirmed 0 rows in that state)

Paired rollback: rollback_add_lead_expansion_and_closure_fields.py
"""

import frappe


def execute():
    """Reload doctypes; Frappe auto-adds nullable columns; verify."""

    # Step 1: Reload both doctype JSONs
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead")
    frappe.reload_doc("vecrm", "doctype", "vecrm_inquiry")

    # Step 2: Verify all new columns exist on tabVECRM Lead
    lead_cols_to_check = [
        "contact_person_name",
        "contact_person_designation",
        "closure_notes",
        "attachment_1",
        "attachment_2",
        "attachment_3",
    ]
    for col in lead_cols_to_check:
        result = frappe.db.sql(
            "SHOW COLUMNS FROM `tabVECRM Lead` LIKE %s",
            (col,),
            as_dict=True,
        )
        if not result:
            frappe.throw(f"v1_5 migration failed: tabVECRM Lead.{col} not created")
        if result[0]["Null"] != "YES":
            frappe.throw(
                f"v1_5 migration failed: tabVECRM Lead.{col} must be nullable (got Null={result[0]['Null']})"
            )

    # Step 3: Verify closure_notes on tabVECRM Inquiry
    result = frappe.db.sql(
        "SHOW COLUMNS FROM `tabVECRM Inquiry` LIKE %s",
        ("closure_notes",),
        as_dict=True,
    )
    if not result:
        frappe.throw("v1_5 migration failed: tabVECRM Inquiry.closure_notes not created")

    # Step 4: Verify any pre-existing Inquiry rows with Closed-by-Ops status
    # (probe-time was 0; double-check now in case any landed since)
    closed_by_ops = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabVECRM Inquiry` WHERE status = 'Closed-by-Ops'"
    )[0][0]
    if closed_by_ops > 0:
        frappe.throw(
            f"v1_5 migration aborted: {closed_by_ops} Inquiry rows still in 'Closed-by-Ops' state. "
            "Migrate to Closed-Lost or Closed-Won manually before re-running."
        )

    frappe.db.commit()
    print(
        "v1_5 LEAD-EXPANSION-AND-CLOSURE migration complete. "
        "6 new Lead fields + 1 new Inquiry field + 2 status enum extensions."
    )
