# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""HTTP-callable API surface for the VECRM app.

This module exposes whitelisted top-level functions that wrap internal
doctype methods. The wrappers decouple the HTTP API contract from the
internal implementation, so doctype methods can evolve without breaking
external callers (vecrm-portal, integrations).

Conventions:
  * Every function in this module is decorated with @frappe.whitelist().
  * Wrappers MUST NOT contain business logic. They locate the target
    document and delegate; transformations/validations belong on the
    doctype methods themselves.
  * Function names use snake_case verbs (e.g. ``convert_lead_to_inquiry``).
"""

import json

import frappe


@frappe.whitelist()
def convert_lead_to_inquiry(
	lead_name: str,
	contact_person: str,
	contact_phone: str,
	requirement: str,
	status: str = "Open",
) -> str:
	"""Convert a VECRM Lead to an Inquiry via the Lead's document method.

	Thin HTTP wrapper around ``VECRMLead.convert_to_inquiry``. The
	enclosing transaction, Q9 enqueue, and audit semantics are owned by
	the underlying method; this function only resolves the Lead by name
	and forwards the call.

	Args:
	  lead_name: The Lead document's ``name`` (e.g. ``"VE/LEAD/00001/26-27"``).
	  contact_person: Required Inquiry field, passed through.
	  contact_phone: Required Inquiry field, passed through.
	  requirement: Required Inquiry field, passed through.
	  status: Inquiry status on creation; defaults to ``"Open"``.

	Returns:
	  Whatever ``VECRMLead.convert_to_inquiry`` returns (the created
	  Inquiry's name on success).
	"""
	lead = frappe.get_doc("VECRM Lead", lead_name)
	return lead.convert_to_inquiry(
		contact_person=contact_person,
		contact_phone=contact_phone,
		requirement=requirement,
		status=status,
	)


@frappe.whitelist()
def approve_travel_voucher(
	voucher_name: str, approver_employee: str, notes: str = ""
) -> str:
	"""Approve a submitted VECRM Travel Voucher.

	Thin HTTP wrapper around the doctype module's ``approve_travel_voucher``.
	First-to-approve wins; the approver's ``VECRM Employee.role`` must be in
	the voucher's snapshotted ``approver_role_set``.

	Args:
	  voucher_name: The Travel Voucher's ``name`` (e.g. ``"VE/TV/00001/26-27"``).
	  approver_employee: The approving ``VECRM Employee`` document name.
	  notes: Optional free-text approval note.

	Returns:
	  The voucher's name on success.
	"""
	from vecrm.vecrm.doctype.vecrm_travel_voucher.vecrm_travel_voucher import (
		approve_travel_voucher as _approve,
	)

	return _approve(voucher_name, approver_employee, notes or None)


@frappe.whitelist()
def create_travel_voucher_draft(
	submitter: str,
	business_date: str,
	visit_lines: str,
) -> dict:
	"""Create a VECRM Travel Voucher in DRAFT state (docstatus=0).

	Sub-A (S24) is Admin-only — callers MUST pass submitter explicitly.
	When VECRM Auth ships in S25, the portal's BFF route will resolve
	submitter from the authenticated session and pass it here; the
	backend signature does not change.

	Uses the ORM pattern (new_doc -> append -> insert). The REST
	equivalent (frappe.client.insert with a nested visit_lines array) is
	unverified in-repo per A1 §4.1 and intentionally avoided.

	Args:
	  submitter: VECRM Employee name (= phone-id, e.g. "+91-9999900001").
	  business_date: Date of visits (YYYY-MM-DD). Drives FY.
	  visit_lines: JSON-encoded array of visit-line objects with fields
	    visit_date, customer_name, start_odometer, end_odometer, notes?

	Returns:
	  Dict with name, submitter, business_date, fy_label, total_km,
	  total_amount, rate_per_km_applied, employee_base_city,
	  submitter_role, docstatus, visit_lines (computed children).

	Raises:
	  frappe.ValidationError: invalid JSON, empty visit_lines, or any
	    controller validation failure (employee not found/inactive, rate
	    card missing the base city, etc.)
	"""
	if not submitter:
		frappe.throw(
			"submitter is required (VECRM Employee phone-id).",
			frappe.ValidationError,
		)

	if not frappe.db.exists("VECRM Employee", submitter):
		frappe.throw(
			f"VECRM Employee {submitter!r} does not exist.",
			frappe.ValidationError,
		)

	try:
		lines = json.loads(visit_lines)
	except json.JSONDecodeError as exc:
		frappe.throw(f"visit_lines is not valid JSON: {exc}", frappe.ValidationError)

	if not isinstance(lines, list) or not lines:
		frappe.throw(
			"visit_lines must be a non-empty JSON array.", frappe.ValidationError
		)

	doc = frappe.new_doc("VECRM Travel Voucher")
	doc.submitter = submitter
	doc.business_date = business_date

	for line in lines:
		doc.append("visit_lines", {
			"visit_date": line.get("visit_date"),
			"customer_name": line.get("customer_name"),
			"start_odometer": line.get("start_odometer"),
			"end_odometer": line.get("end_odometer"),
			"notes": line.get("notes", ""),
		})

	# insert() runs before_insert (snapshot rate/role/city), validate
	# (compute totals via Rate Card lookup), and DB insert atomically.
	doc.insert()

	return {
		"name": doc.name,
		"submitter": doc.submitter,
		"business_date": str(doc.business_date),
		"fy_label": doc.fy_label,
		"total_km": doc.total_km,
		"total_amount": doc.total_amount,
		"rate_per_km_applied": doc.rate_per_km_applied,
		"employee_base_city": doc.employee_base_city,
		"submitter_role": doc.submitter_role,
		"docstatus": doc.docstatus,
		"visit_lines": [
			{
				"visit_date": str(line.visit_date),
				"customer_name": line.customer_name,
				"start_odometer": line.start_odometer,
				"end_odometer": line.end_odometer,
				"total_km": line.total_km,
				"line_amount": line.line_amount,
				"notes": line.notes or "",
			}
			for line in doc.visit_lines
		],
	}


@frappe.whitelist()
def submit_travel_voucher_draft(voucher_name: str) -> dict:
	"""Submit a previously-created draft Travel Voucher (docstatus 0 -> 1).

	Sub-A (S24) is Admin-only — the only session in production at this
	point belongs to an Admin who can submit any draft. Ownership checks
	are deferred to S25 when real non-Admin sessions exist.

	Calls doc.submit() which triggers on_submit -> voucher.travel.submitted
	audit emission.

	Args:
	  voucher_name: Name (e.g. 'VE/TV/00090/26-27') of the draft to submit.

	Returns:
	  Dict with name, docstatus (1), total_amount, submitted_at.

	Raises:
	  frappe.ValidationError: voucher doesn't exist or not in draft state.
	"""
	if not frappe.db.exists("VECRM Travel Voucher", voucher_name):
		frappe.throw(
			f"Travel Voucher {voucher_name!r} does not exist.",
			frappe.ValidationError,
		)

	doc = frappe.get_doc("VECRM Travel Voucher", voucher_name)

	if doc.docstatus != 0:
		frappe.throw(
			f"Travel Voucher {voucher_name} is not in draft state "
			f"(docstatus={doc.docstatus}).",
			frappe.ValidationError,
		)

	# No ownership check in Sub-A — Admin-only interim. S25 VECRM Auth
	# will add session-based ownership verification.

	# Submit — triggers on_submit -> _audit("voucher.travel.submitted", ...)
	doc.submit()

	return {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"total_amount": doc.total_amount,
		"submitted_at": str(frappe.utils.now_datetime()),
	}
