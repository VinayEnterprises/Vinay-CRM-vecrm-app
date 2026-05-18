# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now, today


# S1 §2C priority scale. Carry-then-independent: priority is copied
# from Lead at creation by Lead.convert_to_inquiry; after creation
# the Inquiry's priority is INDEPENDENT — this controller does NOT
# re-fetch from source_lead. Independence is structural: there is no
# read-from-link here, by design.
PRIORITY_LABELS = {
	1: "Cold",
	2: "Cool",
	3: "Warm",
	4: "Hot",
	5: "Very Hot",
}


class VECRMInquiry(Document):
	def autoname(self):
		# S1 §2C slash format: VE/INQ/{n:05d}/{fy}. FY-of-record follows
		# the Inquiry's OWN date (operator-confirmed S14): an Inquiry is an
		# independent document with its own INQ series and counter — its FY
		# is NOT inherited from source_lead.contact_date. self.creation may
		# be a datetime (Frappe pre-stamp), a str, or unset on a fresh doc;
		# normalize to an explicit datetime.date BEFORE fy_label so a
		# financial-series allocator never receives an ambiguous type
		# (CR-class hardening — the counter mints permanent numbers).
		from datetime import date, datetime
		from frappe.utils import getdate
		from vecrm.vecrm.voucher_counter import fy_label, next_number
		raw = self.creation or now()
		basis = getdate(raw)  # frappe.utils.getdate -> datetime.date, parses
		                      # date | datetime | ISO str uniformly; raises
		                      # loud on garbage (consistent with fy_label's
		                      # own fail-loud contract).
		if not isinstance(basis, date):
			frappe.throw(_("Inquiry autoname: could not derive a date basis for FY."))
		fy = fy_label(basis)
		n = next_number(series="INQ", fy=fy)
		self.name = f"VE/INQ/{n:05d}/{fy}"

	def validate(self):
		# Priority gate: integer 1..5, no default. Same rule as Lead.
		# contact_person / contact_phone / requirement reqd at the
		# field level — Frappe's reqd enforcement is the structural
		# conversion gate (an Inquiry cannot exist empty); this
		# controller does NOT re-validate them here.
		if self.priority is None or not (1 <= int(self.priority) <= 5):
			frappe.throw(_("Priority must be an integer 1–5 (no default)."))

	def on_submit(self):
		# Conversion-creation Q9 fan-out. Triggers on submit; if this
		# install keeps Inquiry docs editable (no submit lifecycle),
		# the convert path can call _enqueue_conversion_email directly.
		self._enqueue_conversion_email()

	def _enqueue_conversion_email(self):
		"""Build the S1 §2C Q9 payload, write a fail-loud audit row,
		then call the (currently no-op) transport.

		The audit row is the source-of-truth fail-loud record. Even if
		the transport silently no-ops (current state per the Q9-build
		dependency), the intent is recoverable from the audit log.
		"""
		recipients = [
			"ajay@vinayenterprises.co.in",
			"krunal@vinayenterprises.co.in",
			"info@vinayenterprises.co.in",
		]
		subject = (
			f"[VECRM Inquiry] {self.name} — {self.company_name} — {self.territory}"
		)
		priority_int = int(self.priority) if self.priority is not None else 0
		priority_label = PRIORITY_LABELS.get(priority_int, "Unknown")
		deep_link = (
			f"https://crm.vinayenterprises.co.in/app/vecrm-inquiry/{self.name}"
		)
		body = {
			"inquiry_ref": self.name,
			"company_name": self.company_name,
			"territory": self.territory,
			"contact_person": self.contact_person,
			"contact_phone": self.contact_phone,
			"requirement": self.requirement,
			"priority": priority_int,
			"priority_label": priority_label,
			"originating_rep": self.inquiry_owner,
			"deep_link": deep_link,
		}
		payload = {
			"recipients": recipients,
			"subject": subject,
			"body": body,
		}

		# Fail-loud audit row to VECRM Inquiry Audit Log (Layer-3
		# doctype authored in this PR; the existing VECRM User Audit
		# Log schema does not accommodate inquiry events — its
		# event_type Select is locked to user-lifecycle values). The
		# audit row is the durable intent record; it must be written
		# BEFORE transport invocation so a transport failure does not
		# erase the trail.
		frappe.get_doc({
			"doctype": "VECRM Inquiry Audit Log",
			"event": "inquiry.converted.notify_intent",
			"payload": json.dumps(payload),
			"event_timestamp": now(),
		}).insert(ignore_permissions=True)

		self._q9_transport(payload)

	def _q9_transport(self, payload):
		# Q9-TRANSPORT: pending — see S14 Q9-build dispatch (vemio-dashboard
		# HMAC route + email-sender vecrm-inquiry-converted template +
		# catchall tenant_id resolution). Until then this is a no-op by
		# design: conversion succeeds, intent is audit-logged above, the
		# built payload is correct and ready. Swap this single function
		# body when the Q9-build workstream lands. Do NOT add SMTP/
		# frappe.sendmail here (architectural drift — host uses the
		# email_jobs queue + email-sender worker exclusively).
		return
