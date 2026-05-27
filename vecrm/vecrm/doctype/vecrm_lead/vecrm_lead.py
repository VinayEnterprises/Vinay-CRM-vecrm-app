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
		from vecrm.vecrm.voucher_counter import fy_label, next_number
		fy = fy_label(self.contact_date)
		n = next_number(series="LEAD", fy=fy)
		self.name = f"VE/LEAD/{n:05d}/{fy}"

	def validate(self):
		# Defensive name guard (PD-S23-AUTONAME-HYGIENE): name MUST be
		# canonical VE/LEAD/####/FY format, set by autoname(). Validated
		# at validate() (not before_insert) because Frappe v16.18.2 runs
		# before_insert BEFORE set_new_name (document.py L441 before L442),
		# so self.name is None at before_insert time. validate() runs after
		# autoname has populated self.name.
		if not self.name or not self.name.startswith("VE/LEAD/"):
			frappe.throw(
				f"VECRM Lead name must be allocated via voucher_counter "
				f"(VE/LEAD/####/FY format). Got: {self.name!r}. Do not "
				f"pre-populate name; let autoname() handle allocation.",
				frappe.ValidationError,
			)
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

		ts = now()
		# Actor identity for any audit row written below. PD-S30-LEAD-OWNER-ATTRIBUTION (S31):
		# read the human's vecrm_email from session data, fall back to session.user only if
		# the session lacks the stash (defensive — covers Desk admin paths that don't go through
		# _issue_session).
		actor = frappe.session.data.get("vecrm_email") or frappe.session.user

		# === Owner-change detection (PD-S30-LEAD-OWNER-ATTRIBUTION) ===
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
		if before.lead_owner != self.lead_owner:
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

		# === Status-change detection (PD-S29-LEAD-INQUIRY-CLOSURE-UI) ===
		# Parallel to owner-change above. Same reassignment_history child table is
		# reused as a generic transition log; change_reason disambiguates event type.
		# Same dual-write pattern: append to parent's child table + insert ledger entry.
		if before.status != self.status:
			self.append("reassignment_history", {
				"from_owner": before.status,
				"to_owner": self.status,
				"changed_by": actor,
				"change_reason": f"status: {before.status} → {self.status}",
				"ref_document": self.name,
				"event_timestamp": ts,
			})

			frappe.get_doc({
				"doctype": "VECRM Assignment Ledger Entry",
				"from_owner": before.status,
				"to_owner": self.status,
				"changed_by": actor,
				"change_reason": f"status: {before.status} → {self.status}",
				"ref_document": self.name,
				"event_timestamp": ts,
			}).insert(ignore_permissions=True)
# === Follow-up date change detection (PD-S30-LEAD-FOLLOWUP Phase 1) ===
		# Same dual-write pattern as owner + status. The flags-borne notes
		# (set by vecrm.api.update_lead_followup) become the change_reason
		# suffix so the audit row carries the rep's note context.
		if before.next_followup_date != self.next_followup_date:
			notes = (self.flags.get("followup_notes") or "").strip()
			before_d = str(before.next_followup_date) if before.next_followup_date else "null"
			after_d = str(self.next_followup_date) if self.next_followup_date else "null"
			change_reason = f"followup: {before_d} → {after_d}"
			if notes:
				change_reason = f"{change_reason} | note: {notes}"

			self.append("reassignment_history", {
				"from_owner": before_d,
				"to_owner": after_d,
				"changed_by": actor,
				"change_reason": change_reason,
				"ref_document": self.name,
				"event_timestamp": ts,
			})

			frappe.get_doc({
				"doctype": "VECRM Assignment Ledger Entry",
				"from_owner": before_d,
				"to_owner": after_d,
				"changed_by": actor,
				"change_reason": change_reason,
				"ref_document": self.name,
				"event_timestamp": ts,
			}).insert(ignore_permissions=True)
	def convert_to_inquiry(
		self,
		contact_person,
		contact_phone,
		requirement,
		status="Open",
	):
		"""Convert this Lead into a VECRM Inquiry.

		Per S1 §2C: copy company_name / territory / priority, set
		source_lead = self.name on the new Inquiry. The four
		Inquiry-stage reqd fields (contact_person, contact_phone,
		requirement, status) are supplied by the caller — typically
		a future portal/button form that prompts the rep for them
		at conversion time. Lead does not store these fields; they
		are the structural Lead→Inquiry boundary per §2C.

		S19 WIRING (PD-S18-Q9WIRE Option b): after the Inquiry is
		inserted, Q9 is fired directly via
		inquiry.enqueue_conversion_email(). Inquiry is NOT submittable
		in this install, by design — Inquiries are mutable living
		documents that move through Open / Quoting / Closed-by-Ops.

		Inquiry ownership: the rep who owned the Lead at conversion
		time is the rep who needs to handle the Inquiry. Set
		inquiry_owner = self.lead_owner so the Q9 email carries the
		rep's identity and Krunal's team knows who to talk to.

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
			"contact_person": contact_person,
			"contact_phone": contact_phone,
			"requirement": requirement,
			"status": status,
			"inquiry_owner": self.lead_owner,
		})
		inquiry.insert(ignore_permissions=True)

		# Q9 fan-out fires at the semantic event (Lead → Inquiry),
		# not the lifecycle event. Per S19 Option b. Errors from
		# transport are logged-and-swallowed inside _q9_transport;
		# the durable audit row is written before transport.
		inquiry.enqueue_conversion_email()

		self.status = "Converted"
		self.converted_inquiry = inquiry.name
		self.save(ignore_permissions=True)
		return inquiry.name
	def get_last_contact_date(self):
		"""Virtual field: latest touchpoint_date for this lead, or None.

		Q-LEAD-FOLLOWUP-PHASE-2-ADDENDUM Q-LFL-P2-3 = (b) virtual fields,
		read-time computed. NOT a doctype JSON field — accessed via this
		method by callers that need the value (typically the portal BFF
		when rendering Lead detail).
		"""
		return frappe.db.get_value(
			"VECRM Lead Touchpoint",
			filters={"lead": self.name},
			fieldname="MAX(touchpoint_date)",
		)

	def get_touchpoint_count(self):
		"""Virtual field: count of touchpoints for this lead.

		Companion to get_last_contact_date. See Q-LFL-P2-3 rationale.
		"""
		return frappe.db.count("VECRM Lead Touchpoint", filters={"lead": self.name})