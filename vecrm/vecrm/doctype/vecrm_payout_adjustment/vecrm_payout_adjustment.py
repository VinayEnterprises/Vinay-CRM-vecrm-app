# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""VECRM Payout Adjustment controller (S42).

Off-record, payout-page-only state. Lets Accounts override the advance used
for an Expense Voucher's net payable AT PAYOUT TIME without mutating the
employee's submitted voucher record. One row per voucher — a single-row
upsert, NOT an append log (the modified / modified_by standard fields already
carry who-changed-it-when, so no separate history table is needed).

The (voucher_doctype, voucher_name) pair is enforced unique at two levels:
  - a DB composite UNIQUE index added by patch v1_11 (the authoritative guard);
  - the validate() check below (a friendly, race-free-enough application guard
    so the upsert path in voucher_cms never silently creates a duplicate).
"""

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMPayoutAdjustment(Document):
    def validate(self) -> None:
        # Enforce one override row per (voucher_doctype, voucher_name).
        dup = frappe.db.get_value(
            "VECRM Payout Adjustment",
            {
                "voucher_doctype": self.voucher_doctype,
                "voucher_name": self.voucher_name,
                "name": ["!=", self.name],
            },
            "name",
        )
        if dup:
            frappe.throw(
                _("A payout adjustment for {0} {1} already exists ({2}). "
                  "Update it rather than creating a second.").format(
                    self.voucher_doctype, self.voucher_name, dup
                ),
                frappe.DuplicateEntryError,
            )
