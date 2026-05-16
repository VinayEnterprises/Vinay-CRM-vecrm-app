# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMEmployee(Document):
	def validate(self):
		self._validate_phone_immutable()
		self._validate_base_city_in_rate_card()

	def _validate_phone_immutable(self):
		# Defense-in-depth: set_only_once=1 enforces this at field level;
		# this is an explicit guard because vecrm_phone is the auth identity.
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if before and before.vecrm_phone != self.vecrm_phone:
			frappe.throw(
				_("Phone is the login identity and cannot be changed once set.")
			)

	def _validate_base_city_in_rate_card(self):
		city = (self.vecrm_base_city or "").strip()
		if not city:
			frappe.throw(_("Base City is required."))
		rate_card = frappe.get_single("VECRM Rate Card")
		known = {
			(r.city or "").strip().casefold()
			for r in rate_card.city_rates
		}
		if city.casefold() not in known:
			frappe.throw(
				_(
					"Base City '{0}' has no entry in the VECRM Rate Card. "
					"Add the city + rate to the Rate Card before provisioning this employee."
				).format(city)
			)
