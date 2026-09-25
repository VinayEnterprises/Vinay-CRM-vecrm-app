# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""VECRM Advance Request (S144).

An expense advance an employee asks for before an out-of-city trip. Every
state change goes through vecrm.vecrm.utils.advance (whitelisted wrappers in
vecrm.api). This controller only guards structure and refuses any write that
did not come through that module, so the REST resource cannot move a request
to Paid (the S144 finding on the old custom "VECRM Expense Advance").

Naming: VE/ADV/#####/FY via voucher_counter, series "ADV", FY of travel_from.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from vecrm.vecrm.voucher_counter import fy_label, next_number

STATUSES = ("Pending Approval", "Approved", "Paid", "Rejected",
            "Payment Declined", "Cancelled")
MAX_TRIP_DAYS = 60


class VECRMAdvanceRequest(Document):
    def autoname(self) -> None:
        if not self.travel_from:
            frappe.throw(_("The travel date is required to allocate the advance number."),
                         frappe.ValidationError)
        fy = fy_label(self.travel_from)
        n = next_number(series="ADV", fy=fy)
        self.name = f"VE/ADV/{n:05d}/{fy}"
        self.fy_label = fy

    def validate(self) -> None:
        if not self.flags.vecrm_advance_write:
            frappe.throw(_("Advance requests change only through the Anusuya app."),
                         frappe.PermissionError)
        if not self.name or not str(self.name).startswith("VE/ADV/"):
            frappe.throw(f"Advance name must be allocated as VE/ADV/#####/FY. Got {self.name!r}.",
                         frappe.ValidationError)
        if self.status not in STATUSES:
            frappe.throw(f"Unknown status {self.status!r}.", frappe.ValidationError)
        if flt(self.amount) <= 0:
            frappe.throw(_("The advance amount must be more than zero."), frappe.ValidationError)
        # S146: site and one travel date are required; location and purpose are optional.
        if not (self.site or "").strip():
            frappe.throw(_("Site is required."), frappe.ValidationError)
        if not self.travel_from:
            frappe.throw(_("The travel date is required."), frappe.ValidationError)
        if not self.travel_to:
            self.travel_to = self.travel_from
        tf, tt = getdate(self.travel_from), getdate(self.travel_to)
        if tt < tf:
            frappe.throw(_("Travel To cannot be before Travel From."), frappe.ValidationError)
        if (tt - tf).days > MAX_TRIP_DAYS:
            frappe.throw(_("A single advance can cover at most {0} days of travel.").format(MAX_TRIP_DAYS),
                         frappe.ValidationError)
        if self.trip_type == "Top-up" and not self.parent_advance:
            frappe.throw(_("A top-up must name the advance it tops up."), frappe.ValidationError)
        if self.trip_type != "Top-up":
            self.parent_advance = None
        if self.status == "Paid":
            if flt(self.paid_amount) <= 0 or flt(self.paid_amount) > flt(self.amount) + 0.005:
                frappe.throw(_("The paid amount must be more than zero and not more than the "
                               "approved amount."), frappe.ValidationError)
        else:
            self.paid_amount = 0

    def on_trash(self) -> None:
        if not self.flags.vecrm_advance_write:
            frappe.throw(_("Advance requests cannot be deleted."), frappe.PermissionError)
