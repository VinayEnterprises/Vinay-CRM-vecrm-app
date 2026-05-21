# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VECRMVisitLine(Document):
    """Child table — visits inside a Travel Voucher.

    All compute lives in the parent (VECRMTravelVoucher.validate) because the
    rate lookup requires the parent's frozen employee_base_city. The line
    itself only validates that start/end odometer are present and end >= start.
    """

    def validate(self) -> None:
        if self.end_odometer is None or self.start_odometer is None:
            frappe.throw("Both Start KM and End KM are required.")
        if self.end_odometer < self.start_odometer:
            frappe.throw(
                f"End KM ({self.end_odometer}) cannot be less than "
                f"Start KM ({self.start_odometer})."
            )
