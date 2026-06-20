# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMTrustedDevice(Document):
	def validate(self):
		if not self.employee or not self.device_id:
			frappe.throw(_("Employee and Device ID are required"))

		# Enforce unique constraint on (employee, device_id)
		duplicate = frappe.db.exists(
			"VECRM Trusted Device",
			{
				"employee": self.employee,
				"device_id": self.device_id,
				"name": ["!=", self.name]
			}
		)
		if duplicate:
			frappe.throw(_("Device is already trusted for this employee"))
