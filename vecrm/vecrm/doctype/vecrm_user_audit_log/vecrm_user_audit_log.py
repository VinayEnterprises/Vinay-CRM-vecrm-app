# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class VECRMUserAuditLog(Document):
	def before_insert(self):
		# Timestamp integrity is core to an audit row; default it defensively
		# even though the field is reqd (covers programmatic inserts).
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
		# the same predicate the Employee controller uses for immutability.
		if self.flags.in_insert:
			return
		if self.get_doc_before_save() is not None:
			frappe.throw(
				_("VECRM User Audit Log is append-only. Existing entries cannot be modified."),
				frappe.PermissionError,
			)

	def on_trash(self):
		# Append-only: audit rows are never deletable, by any role,
		# including System Manager / Administrator.
		frappe.throw(
			_("VECRM User Audit Log is append-only. Entries cannot be deleted."),
			frappe.PermissionError,
		)
