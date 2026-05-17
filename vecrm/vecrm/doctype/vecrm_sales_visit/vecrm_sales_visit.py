# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMSalesVisit(Document):
    def validate(self):
        self._resolve_base_city()
        self._compute_reimbursement()

    def _resolve_base_city(self):
        # Base city is authoritative from the linked employee, never from
        # client input. This is the trust boundary: reimbursement cannot be
        # gamed by selecting a higher-rate city on the form.
        if not self.employee:
            frappe.throw(_("Employee is required."))
        base_city = frappe.db.get_value(
            "VECRM Employee", self.employee, "vecrm_base_city"
        )
        if not base_city or not str(base_city).strip():
            frappe.throw(
                _(
                    "Employee {0} has no Base City set. "
                    "Set it on the VECRM Employee record first."
                ).format(self.employee)
            )
        self.base_city = str(base_city).strip()

    def _compute_reimbursement(self):
        if self.distance_km is None or self.distance_km < 0:
            frappe.throw(_("Distance (KM) must be zero or a positive number."))

        # Same lookup idiom as VECRMEmployee._validate_base_city_in_rate_card:
        # read the singleton rate card and casefold-match the city.
        rate_card = frappe.get_single("VECRM Rate Card")
        target = self.base_city.casefold()
        rate = None
        for row in rate_card.city_rates:
            if (row.city or "").strip().casefold() == target:
                rate = row.rate_per_km
                break

        if rate is None:
            # Fail loudly rather than silently zeroing the reimbursement.
            frappe.throw(
                _(
                    "Base City '{0}' has no entry in the VECRM Rate Card. "
                    "Add the city + rate to the Rate Card before recording "
                    "this visit."
                ).format(self.base_city)
            )

        self.reimbursement_amount = round(
            (self.distance_km or 0) * (rate or 0), 2
        )
