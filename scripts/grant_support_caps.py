# -*- coding: utf-8 -*-
# grant_support_caps.py — RECORD COPY (re-authored S3, 2026-07-02).
#
# Faithful re-authoring of the one-shot executed on
# crm.vinayenterprises.co.in during S2 (2026-07-02, original artifact
# sha256 210757e...d16d; the /tmp copy died with a container recreate
# before it could be committed — see S3 close, P-2.9).
# Field specs below were verified against the LIVE Custom Field rows
# on 2026-07-02 (S3) — this file matches production exactly.
# The grants are LIVE. Committed for record discipline only.
# Idempotent by construction; do not re-run without a reason.
#
# What it did (S2 §3.6):
#   1. Added 3 Custom Fields to "VECRM Role Config" (following the
#      existing cap_erp_* pattern): section_support (Section Break),
#      cap_support_base (Check, default "1"),
#      cap_asset_admin (Check, default "0").
#   2. Set cap_support_base = 1 on ALL 16 existing role rows
#      (default "1" covers future roles).
#   3. Set cap_asset_admin = 1 on exactly: Admin, HR,
#      "Head of Accounts & HR".
#
# Run form (as executed): copied to /tmp in the vecrm backend container,
# then invoked via bench execute on crm.vinayenterprises.co.in.

import frappe

DT = "VECRM Role Config"

FIELDS = [
    {
        "doctype": "Custom Field",
        "dt": DT,
        "fieldname": "section_support",
        "fieldtype": "Section Break",
        "label": "Support Capabilities",
        "insert_after": "cap_erp_admin",
    },
    {
        "doctype": "Custom Field",
        "dt": DT,
        "fieldname": "cap_support_base",
        "fieldtype": "Check",
        "label": "Support Base",
        "default": "1",
        "insert_after": "section_support",
    },
    {
        "doctype": "Custom Field",
        "dt": DT,
        "fieldname": "cap_asset_admin",
        "fieldtype": "Check",
        "label": "Asset Admin",
        "default": "0",
        "insert_after": "cap_support_base",
    },
]

ASSET_ADMIN_ROLES = ("Admin", "HR", "Head of Accounts & HR")


def run():
    created = []
    for spec in FIELDS:
        if not frappe.db.exists(
                "Custom Field", {"dt": DT, "fieldname": spec["fieldname"]}):
            frappe.get_doc(spec).insert(ignore_permissions=True)
            created.append(spec["fieldname"])

    roles = [r["name"] for r in frappe.db.sql(
        "select name from `tab{0}`".format(DT), as_dict=True)]

    for role in roles:
        frappe.db.set_value(DT, role, "cap_support_base", 1)

    granted = []
    for role in roles:
        if role in ASSET_ADMIN_ROLES:
            frappe.db.set_value(DT, role, "cap_asset_admin", 1)
            granted.append(role)

    frappe.db.commit()
    return frappe.as_json({
        "fields_created": created,
        "roles_touched": len(roles),
        "cap_support_base": "all",
        "cap_asset_admin": granted,
    })
