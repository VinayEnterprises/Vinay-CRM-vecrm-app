# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMEmployee(Document):
	def on_update(self):
		# S143: a role or account-status change ends this employee's live
		# portal sessions, so no session keeps acting on the old role.
		before = self.get_doc_before_save()
		if not before:
			return
		if before.role != self.role or before.vecrm_account_status != self.vecrm_account_status:
			end_employee_sessions(self.vecrm_phone or self.name, "role or status changed")

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
		from vecrm.vecrm.utils.role_config import role_is_external
		if role_is_external(self.role):
			# External roles draw no per-km petrol reimbursement, so rate
			# card membership does not apply to them. Base City stays
			# mandatory above, for posting and reporting.
			return
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


def end_employee_sessions(phone, reason):
	"""S143 (Rule E). Delete the live sessions of ONE VECRM employee. Every
	portal session shares one Frappe user, so sessions are matched on the
	vecrm_employee_phone stored in each session's data, exactly (an OFFB key
	never matches); clear_sessions(user) would log everyone out. The audit
	row commits (via _audit_auth). Returns the count ended."""
	import ast

	phone = (phone or "").strip()
	if not phone:
		return 0
	rows = frappe.db.sql(
		"SELECT sid, sessiondata FROM `tabSessions` WHERE sessiondata LIKE %s",
		("%" + phone + "%",),
		as_dict=True,
	)
	ended = []
	for r in rows:
		try:
			data = ast.literal_eval(r.sessiondata or "{}")
		except Exception:
			continue
		if not isinstance(data, dict) or data.get("vecrm_employee_phone") != phone:
			continue
		frappe.cache().hdel("session", r.sid)
		frappe.db.delete("Sessions", {"sid": r.sid})
		ended.append(r.sid[:8])
	if ended:
		try:
			from vecrm.api import _audit_auth
			_audit_auth("auth.sessions_ended", employee=phone, reason=reason,
				extra={"count": len(ended), "sids": ended})
		except Exception:
			frappe.log_error(frappe.get_traceback(), "end_employee_sessions.audit")
	return len(ended)
