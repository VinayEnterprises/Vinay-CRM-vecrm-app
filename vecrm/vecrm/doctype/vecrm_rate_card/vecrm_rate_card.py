# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMRateCard(Document):
	def validate(self):
		self._enforce_unique_cities()

	def _enforce_unique_cities(self):
		seen = set()
		for row in self.city_rates:
			key = (row.city or "").strip().casefold()
			if not key:
				frappe.throw(_("Row {0}: City is required.").format(row.idx))
			if key in seen:
				frappe.throw(
					_("Duplicate city '{0}' in rate card. Each city must appear once.").format(row.city)
				)
			seen.add(key)
