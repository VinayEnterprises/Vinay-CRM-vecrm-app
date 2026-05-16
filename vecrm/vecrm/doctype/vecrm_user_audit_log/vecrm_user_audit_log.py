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
		# is_new() is True only during the insert path; any later save throws.
		if not self.is_new():
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
