# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class VECRMInquiryAuditLog(Document):
	"""Fail-loud audit ledger for Layer-3 inquiry events (currently
	the inquiry.converted.notify_intent event written by
	VECRMInquiry._enqueue_conversion_email). istable=0.

	Disjoint from VECRM User Audit Log on purpose: that doctype's
	event_type Select is locked to user-lifecycle values
	(User Provisioned / User Suspended / User Reactivated); widening
	it to include inquiry events would couple Layer-1 to Layer-3.
	A separate audit doctype keeps the audit surfaces clean.

	Append-only by controller guard (defense-in-depth above the
	JSON's write=0 perm).
	"""

	def before_insert(self):
		# Timestamp integrity is core to an audit row; default it
		# defensively even though the field is reqd (covers
		# programmatic inserts).
		if not self.event_timestamp:
			self.event_timestamp = now()

	def on_update(self):
		# Append-only: a row may be inserted, never modified thereafter.
		# Frappe 16: on_update also fires DURING insert (run_post_save_methods,
		# _action == "save"); set_new_name() has already run so is_new() is
		# False on the insert path. flags.in_insert is the version-grounded
		# "inside insert()" signal (document.py sets it around the
		# run_post_save_methods call). get_doc_before_save() is None on insert
		# and non-None only on a genuine modification of a committed row -
		# the same predicate the User Audit Log controller uses.
		if self.flags.in_insert:
			return
		if self.get_doc_before_save() is not None:
			frappe.throw(
				_("VECRM Inquiry Audit Log is append-only. Existing entries cannot be modified."),
				frappe.PermissionError,
			)

	def on_trash(self):
		# Append-only: audit rows are never deletable, by any role,
		# including System Manager / Administrator.
		frappe.throw(
			_("VECRM Inquiry Audit Log is append-only. Entries cannot be deleted."),
			frappe.PermissionError,
		)
