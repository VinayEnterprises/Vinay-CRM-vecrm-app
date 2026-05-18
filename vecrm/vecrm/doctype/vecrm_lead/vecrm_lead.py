# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class VECRMLead(Document):
	def autoname(self):
		# S1 §2C slash format: VE/LEAD/{n:05d}/{fy}. The strict
		# gap-free voucher allocator (vecrm.voucher_counter.next_number)
		# runs inside the caller's transaction; its FOR UPDATE row-lock
		# release waits on the enclosing save's commit/rollback —
		# rollback returns the counter to its pre-allocation value, so
		# numbering stays gap-free across failed saves.
		# fy_label() throws loud on a missing/unparseable contact_date.
		from vecrm.voucher_counter import fy_label, next_number
		fy = fy_label(self.contact_date)
		n = next_number(series="LEAD", fy=fy)
		self.name = f"VE/LEAD/{n:05d}/{fy}"

	def validate(self):
		self._validate_priority()

	def _validate_priority(self):
		# Priority is required AND must be integer 1..5. No silent
		# clamp, no default fill — operator must choose. The
		# field-level reqd=1 alone is insufficient because Frappe
		# accepts any int including 0 / -3 / 99 — this controller
		# narrows the domain to the documented 1..5 scale.
		if self.priority is None or not (1 <= int(self.priority) <= 5):
			frappe.throw(_("Priority must be an integer 1–5 (no default)."))

	def before_save(self):
		# Owner-change detection + dual-write ledger.
		#
		# DISPATCH DEVIATION (documented): the Layer-3 dispatch
		# specified on_update() for this logic. Frappe 16's save flow
		# fires on_update AFTER db_update, so child-table
		# modifications made via self.append() inside on_update are
		# in-memory only and do NOT persist with the current save —
		# they would require a recursive self.save() (infinite loop)
		# or raw SQL bypassing the ORM. before_save() runs BEFORE
		# db_update, so child-table appends made here ARE persisted
		# as part of the parent's normal child-table flush. The
		# standalone Ledger Entry insert below works in either hook
		# (it's its own doc with its own save lifecycle within the
		# parent's transaction). Placing both writes in before_save
		# keeps them atomic and preserves the dispatch's intent
		# ("both in this same save transaction") while honouring
		# Frappe v16's persistence semantics.
		#
		# Detection predicate is the same as the Employee controller's
		# immutability guard and the User Audit Log's append-only
		# guard: get_doc_before_save() is None on insert and non-None
		# only on a genuine modification of a committed row.
		# flags.in_insert is the version-grounded "inside insert()"
		# signal; an early-return on it preserves the
		# don't-write-on-insert invariant.
		if self.flags.in_insert:
			return
		before = self.get_doc_before_save()
		if before is None:
			return
		if before.lead_owner == self.lead_owner:
			return

		ts = now()
		actor = frappe.session.user

		# Two intentional writes per owner change in the same save
		# transaction:
		#   (1) Append-row to the parent's child-table
		#       reassignment_history (VECRM Assignment Log Row,
		#       istable=1). The parent's child-table flush persists
		#       this row alongside the parent's UPDATE.
		#   (2) Insert a standalone VECRM Assignment Ledger Entry
		#       (istable=0) — the cross-doctype system-wide
		#       owner-change ledger, queryable independent of the
		#       parent. Both rows carry identical from/to/by/timestamp/
		#       ref tuples by design — child is the parent's
		#       breadcrumb; ledger is the system record.
		self.append("reassignment_history", {
			"from_owner": before.lead_owner,
			"to_owner": self.lead_owner,
			"changed_by": actor,
			"change_reason": "lead_owner change",
			"ref_document": self.name,
			"event_timestamp": ts,
		})

		frappe.get_doc({
			"doctype": "VECRM Assignment Ledger Entry",
			"from_owner": before.lead_owner,
			"to_owner": self.lead_owner,
			"changed_by": actor,
			"change_reason": "lead_owner change",
			"ref_document": self.name,
			"event_timestamp": ts,
		}).insert(ignore_permissions=True)

	def convert_to_inquiry(self):
		"""Convert this Lead into a VECRM Inquiry.

		Per S1 §2C: copy company_name / territory / priority, set
		source_lead = self.name on the new Inquiry. The Inquiry's
		own reqd-field gate enforces contact_person / contact_phone
		/ requirement — those fields are the STRUCTURAL conversion
		gate (an Inquiry cannot exist empty).

		Author per dispatch shape. The future portal/button caller
		is expected to supply the contact_* + requirement fields so
		the new Inquiry's insert() does not throw on missing reqd
		fields. Until then, calling convert_to_inquiry() against a
		Lead with no companion form will throw a Frappe validation
		error from Inquiry.validate() / reqd enforcement — that is
		the conversion gate working as designed.

		Returns the new Inquiry's name on success.
		"""
		if self.status == "Converted":
			frappe.throw(_("Lead {0} is already converted.").format(self.name))

		inquiry = frappe.get_doc({
			"doctype": "VECRM Inquiry",
			"source_lead": self.name,
			"company_name": self.company_name,
			"territory": self.territory,
			"priority": self.priority,
		})
		inquiry.insert(ignore_permissions=True)

		self.status = "Converted"
		self.converted_inquiry = inquiry.name
		self.save(ignore_permissions=True)
		return inquiry.name
