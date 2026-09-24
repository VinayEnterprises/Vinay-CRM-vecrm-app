# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""VECRM Voucher Declaration (S143).

"No petrol claim this period": one row per (employee, period_key). Written
only by vecrm.vecrm.utils.voucher_due.declare_no_claim, which enforces who may
declare and when. This controller holds the structural invariant.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMVoucherDeclaration(Document):
    def validate(self) -> None:
        if not (self.period_key or "").strip():
            frappe.throw(_("period_key is required."), frappe.ValidationError)
        clash = frappe.db.get_value(
            "VECRM Voucher Declaration",
            {"employee": self.employee, "period_key": self.period_key, "name": ["!=", self.name or ""]},
            "name",
        )
        if clash:
            frappe.throw(
                _("{0} has already declared no petrol claim for {1} ({2}).").format(
                    self.employee, self.period_key, clash),
                frappe.ValidationError,
            )
