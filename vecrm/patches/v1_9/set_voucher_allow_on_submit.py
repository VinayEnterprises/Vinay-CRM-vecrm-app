# Copyright (c) 2026, Vinay Enterprises and contributors
"""Set allow_on_submit on voucher content fields (v1_9).

S35 / PD-S29 Model A: enable in-place editing of REJECTED submitted vouchers.

allow_on_submit on visit_lines/expense_lines + recomputed totals + approver
set + approval_status lets a docstatus=1 voucher's content be edited via
doc.save(). The on_update_after_submit controller hook GUARDS this so only
approval_status='Rejected' vouchers (edited by submitter/admin) are mutable;
all other after-submit content edits throw.

This is a property-flag change: Frappe applies allow_on_submit from the
doctype JSON during doctype-sync (before this patch). This patch is a
VERIFIER (per L22 + the v1_7 verifier idiom): confirm the flags took, raise
loud if not. No DDL — allow_on_submit is metadata, not a column.

Paired rollback: rollback_set_voucher_allow_on_submit.py
"""

import frappe

EXPECTED = {
    "VECRM Travel Voucher": ["visit_lines","total_km","total_amount","rate_per_km_applied","approver_role_set","approval_status"],
    "VECRM Expense Voucher": ["expense_lines","total_amount","approver_set","approval_status"],
}


def execute():
    for doctype, fields in EXPECTED.items():
        frappe.reload_doc("vecrm", "doctype", frappe.scrub(doctype))
        meta = frappe.get_meta(doctype)
        missing = []
        for fn in fields:
            df = meta.get_field(fn)
            if not df or not df.allow_on_submit:
                missing.append(fn)
        if missing:
            frappe.throw(
                f"v1_9: allow_on_submit not set on {doctype} fields {missing} "
                f"after doctype sync. Check the JSON edit landed."
            )
        frappe.clear_cache(doctype=doctype)
    print("v1_9 complete. allow_on_submit verified on voucher content fields "
          f"({sum(len(v) for v in EXPECTED.values())} fields across 2 doctypes).")
