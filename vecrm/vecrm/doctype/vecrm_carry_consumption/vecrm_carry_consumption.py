# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""VECRM Carry Consumption child controller (S132).

One row per (source voucher, consuming voucher) slice of an advance
carry-forward. Parented to the SOURCE Expense Voucher, not the consumer, so
that outstanding is a single-source-of-truth read on the source row:

    outstanding = parent.carry_forward_amount - SUM(child.amount)

This replaces the Ruling B (S75) self-join over consumers, which could express
only ONE source per consumer (a single advance_ref slot). Cycle settlement
(R2, S132) can absorb from several sources at once, which that shape cannot
represent.

Append-only by intent: a correction is a new row on a corrective voucher,
never an edit of an existing row. Nothing here is submittable in its own
right; the parent's docstatus governs.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMCarryConsumption(Document):
    def validate(self) -> None:
        # Structural invariants only. Business rules (FIFO order, which
        # sources are eligible, how much may be pulled) live in the settlement
        # function, which is the single writer of these rows.
        if float(self.amount or 0) <= 0:
            frappe.throw(
                _("Carry consumption amount must be greater than 0. Got {0}.").format(
                    self.amount
                ),
                frappe.ValidationError,
            )

        if not (self.consumer_doctype or "").strip():
            frappe.throw(
                _("consumer_doctype is required on a carry consumption row."),
                frappe.ValidationError,
            )

        if not (self.consumer_name or "").strip():
            frappe.throw(
                _("consumer_name is required on a carry consumption row."),
                frappe.ValidationError,
            )

        # A voucher cannot absorb its own carry-forward.
        if self.consumer_name == self.parent:
            frappe.throw(
                _("A voucher cannot consume its own carry-forward ({0}).").format(
                    self.parent
                ),
                frappe.ValidationError,
            )
