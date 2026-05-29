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
import re
import secrets

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
	_require_voucher_approver_self_or_admin(approver_employee)

	from vecrm.vecrm.doctype.vecrm_travel_voucher.vecrm_travel_voucher import (
		approve_travel_voucher as _approve,
	)

	return _approve(voucher_name, approver_employee, notes or None)


@frappe.whitelist()
def approve_expense_voucher(
	voucher_name: str, approver_employee: str, notes: str = ""
) -> str:
	"""Approve a submitted VECRM Expense Voucher. Self-or-admin guard, then delegate."""
	_require_voucher_approver_self_or_admin(approver_employee)

	from vecrm.vecrm.doctype.vecrm_expense_voucher.vecrm_expense_voucher import (
		approve_expense_voucher as _approve,
	)

	return _approve(voucher_name, approver_employee, notes)


@frappe.whitelist()
def reject_travel_voucher(
	voucher_name: str, approver_employee: str, reason: str
) -> str:
	"""Reject a submitted VECRM Travel Voucher. reason mandatory; self-or-admin guard."""
	_require_voucher_approver_self_or_admin(approver_employee)

	from vecrm.vecrm.doctype.vecrm_travel_voucher.vecrm_travel_voucher import (
		reject_travel_voucher as _reject,
	)

	return _reject(voucher_name, approver_employee, reason)


@frappe.whitelist()
def reject_expense_voucher(
	voucher_name: str, approver_employee: str, reason: str
) -> str:
	"""Reject a submitted VECRM Expense Voucher. reason mandatory; self-or-admin guard."""
	_require_voucher_approver_self_or_admin(approver_employee)

	from vecrm.vecrm.doctype.vecrm_expense_voucher.vecrm_expense_voucher import (
		reject_expense_voucher as _reject,
	)

	return _reject(voucher_name, approver_employee, reason)


@frappe.whitelist()
def voucher_resubmit_travel(
	voucher_name: str, visit_lines: str, business_date: str = ""
) -> str:
	"""Submitter or admin edits a Rejected Travel Voucher in place and resubmits.

	PD-S35 Dispatch 5.8 (S82). The HTTP-layer DocPerm system requires
	`amend` permission to update docstatus=1 docs via /api/method/
	frappe.client.save or /api/resource PUT. The portal's service-account
	role (VECRM Submitter) intentionally has amend=0 (amend in Frappe =
	cancel + create new versioned copy, NOT in-place edit, which would be
	wrong here). This wrapper bypasses HTTP DocPerm by running as a
	whitelisted backend method; auth is enforced via the same
	submitter-or-admin gate as the on_update_after_submit hook.

	Args:
	  voucher_name: VECRM Travel Voucher PK.
	  visit_lines: JSON-encoded array of visit-line objects (visit_date,
	    customer_name, start_odometer, end_odometer, notes). Existing
	    child-row names are re-applied by index inside the doctype-module
	    impl so Frappe matches existing rows instead of insert/delete.
	  business_date: Optional ISO YYYY-MM-DD; if non-empty, overwrites.

	Returns: voucher name on success. validate() recomputes totals;
	on_update_after_submit flips Rejected→Pending + clears reject
	markers + emits voucher.travel.resubmitted audit.
	"""
	voucher = frappe.get_doc("VECRM Travel Voucher", voucher_name)
	_require_voucher_submitter_self_or_admin(voucher.submitter)

	from vecrm.vecrm.doctype.vecrm_travel_voucher.vecrm_travel_voucher import (
		voucher_resubmit_travel as _resubmit,
	)

	return _resubmit(voucher, visit_lines, business_date or None)


@frappe.whitelist()
def voucher_resubmit_expense(
	voucher_name: str, expense_lines: str, expense_date: str = ""
) -> str:
	"""Submitter or admin edits a Rejected Expense Voucher in place and resubmits.

	Sibling of voucher_resubmit_travel; same DocPerm-bypass rationale.
	See vecrm.api.voucher_resubmit_travel for the architectural notes.
	"""
	voucher = frappe.get_doc("VECRM Expense Voucher", voucher_name)
	_require_voucher_submitter_self_or_admin(voucher.submitter)

	from vecrm.vecrm.doctype.vecrm_expense_voucher.vecrm_expense_voucher import (
		voucher_resubmit_expense as _resubmit,
	)

	return _resubmit(voucher, expense_lines, expense_date or None)


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

	# PD-S32-VOUCHER-SUBMITTER-PERMISSION: non-admin callers may only file
	# vouchers for themselves. Admin can file on behalf of anyone. Backend
	# is authoritative — portal UX hides the dropdown for non-admin, but
	# this gate catches any attempt to bypass via direct API call.
	_require_voucher_submitter_self_or_admin(submitter)

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


# ============================================================================
# Expense Voucher endpoints (PD-S25-PORTAL-SUB-B-EXPENSE-VOUCHER, S32 Phase 2)
# ============================================================================
#
# Mirror structure of TV endpoints:
#   create_expense_voucher_draft  <->  create_travel_voucher_draft
#   submit_expense_voucher_draft  <->  submit_travel_voucher_draft
#
# Differences from TV (verified via S32 Phase 2 recon):
#   - business_date -> expense_date
#   - visit_lines -> expense_lines
#   - line fields: category / amount / description / attachment
#   - No per-line rate computation (amount is user-supplied)
#   - No APPROVER_SETS gate in EV controller before_insert (portal
#     authorization handled by _require_voucher_submitter_self_or_admin)
#   - Attachment is REQUIRED at API endpoint level (Q-EV-CONFIRM-ATTACH=b)
#   - Attachment URL existence is verified via File doctype lookup
#     (Q-EV-RECEIPT-VERIFY=on, defense-in-depth)


@frappe.whitelist()
def create_expense_voucher_draft(
	submitter: str,
	expense_date: str,
	expense_lines: str,
) -> dict:
	"""Create a VECRM Expense Voucher in DRAFT state (docstatus=0).

	Args:
	  submitter: VECRM Employee name (phone-id, e.g. "+91-9998583596").
	  expense_date: Date of expenses (YYYY-MM-DD). Drives FY allocation.
	  expense_lines: JSON-encoded array of line objects with fields:
	    category   (str, one of: Hotel/Food/Supplies/Communication/Misc)
	    amount     (number, > 0)
	    description (str, non-empty)
	    attachment (str, Frappe file URL, REQUIRED per Q-EV-CONFIRM-ATTACH=b)

	Returns:
	  Dict with name, submitter, expense_date, fy_label, total_amount,
	  submitter_role, docstatus, expense_lines (computed children).

	Raises:
	  frappe.ValidationError: invalid JSON, empty lines, missing
	    attachment, attachment URL not in File doctype, employee not
	    found/inactive, etc.
	  frappe.PermissionError (via _require_voucher_submitter_self_or_admin):
	    non-admin caller attempting to file for someone else.
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

	# Reuse the PR #43 / PD-S32-VOUCHER-SUBMITTER-PERMISSION helper.
	# Non-admin callers may only file vouchers for themselves; admin
	# can file on behalf of anyone.
	_require_voucher_submitter_self_or_admin(submitter)

	try:
		lines = json.loads(expense_lines)
	except json.JSONDecodeError as exc:
		frappe.throw(
			f"expense_lines is not valid JSON: {exc}",
			frappe.ValidationError,
		)

	if not isinstance(lines, list) or not lines:
		frappe.throw(
			"expense_lines must be a non-empty JSON array.",
			frappe.ValidationError,
		)

	# Per-line validation (Q-EV-CONFIRM-ATTACH=b + Q-EV-RECEIPT-VERIFY=on).
	# Doctype's attachment field is reqd=0 to preserve Desk admin flexibility
	# for corrective EVs; portal-originated submissions MUST include a
	# receipt and the receipt URL MUST exist in the File doctype.
	for idx, line in enumerate(lines, start=1):
		attachment = line.get("attachment")
		if not attachment or not str(attachment).strip():
			frappe.throw(
				f"Expense line {idx}: receipt attachment is required. "
				f"Upload a receipt (jpg/png/pdf, max 5MB) before submitting.",
				frappe.ValidationError,
			)
		# Defense-in-depth: confirm the URL refers to a real File row.
		# Prevents spoofed/fabricated URLs from being attached to a voucher.
		if not frappe.db.exists("File", {"file_url": attachment}):
			frappe.throw(
				f"Expense line {idx}: receipt URL {attachment!r} is not a "
				f"recognized upload. Re-upload the receipt and try again.",
				frappe.ValidationError,
			)

	doc = frappe.new_doc("VECRM Expense Voucher")
	doc.submitter = submitter
	doc.expense_date = expense_date

	for line in lines:
		doc.append("expense_lines", {
			"category": line.get("category"),
			"amount": line.get("amount"),
			"description": line.get("description"),
			"attachment": line.get("attachment"),
		})

	# insert() runs autoname (VE/EV/####/FY via voucher_counter),
	# before_insert (snapshot submitter_role), validate (per-line
	# amount > 0, total_amount recomputed), and DB insert atomically.
	doc.insert()

	return {
		"name": doc.name,
		"submitter": doc.submitter,
		"submitter_role": doc.submitter_role,
		"expense_date": str(doc.expense_date),
		"fy_label": doc.fy_label,
		"total_amount": doc.total_amount,
		"docstatus": doc.docstatus,
		"expense_lines": [
			{
				"category": line.category,
				"amount": line.amount,
				"description": line.description,
				"attachment": line.attachment,
			}
			for line in doc.expense_lines
		],
	}


@frappe.whitelist()
def submit_expense_voucher_draft(voucher_name: str) -> dict:
	"""Submit a previously-created draft Expense Voucher (docstatus 0 -> 1).

	Args:
	  voucher_name: Name (e.g. 'VE/EV/00001/26-27') of the draft to submit.

	Returns:
	  Dict with name, docstatus (1), total_amount, submitted_at.

	Raises:
	  frappe.ValidationError: voucher doesn't exist or not in draft state.
	  frappe.PermissionError: non-admin caller attempting to submit
	    someone else's voucher.
	"""
	if not frappe.db.exists("VECRM Expense Voucher", voucher_name):
		frappe.throw(
			f"Expense Voucher {voucher_name!r} does not exist.",
			frappe.ValidationError,
		)

	doc = frappe.get_doc("VECRM Expense Voucher", voucher_name)

	if doc.docstatus != 0:
		frappe.throw(
			f"Expense Voucher {voucher_name} is not in draft state "
			f"(docstatus={doc.docstatus}).",
			frappe.ValidationError,
		)

	# Reuse PR #43 helper: only the submitter (or admin) may submit.
	_require_voucher_submitter_self_or_admin(doc.submitter)

	# doc.submit() triggers on_submit -> _audit("voucher.expense.submitted")
	doc.submit()

	return {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"total_amount": doc.total_amount,
		"submitted_at": str(frappe.utils.now_datetime()),
	}


@frappe.whitelist()
def create_lead(
	company_name: str,
	territory: str,
	contact_date: str,
	priority: int,
	contact_number: str = None,
	contact_email: str = None,
	meeting_brief: str = None,
	contact_person_name: str = None,
	contact_person_designation: str = None,
) -> dict:
	"""Create a VECRM Lead from the portal.

	PD-S24-PORTAL-LEAD-CREATE original; PD-S29-LEAD-FORM-FIELDS (S30)
	added contact_number / contact_email / meeting_brief as
	API-boundary-mandatory. Column-level reqd stays 0 (nullable) so
	the existing pre-S30 rows remain readable as NULL.

	lead_owner and status are set server-side (session user / "Open")
	— the client cannot supply or spoof either. priority is validated
	to the documented 1-5 range here, at the API boundary, in addition
	to the controller's own validate() check.

	Lead is not submittable; the row lands usable (docstatus 0, status
	"Open") and is immediately convertible to an Inquiry.

	Args:
	  company_name: Company / lead name (reqd).
	  territory: Free-text territory, e.g. "Ahmedabad" (reqd).
	  contact_date: Date of contact (YYYY-MM-DD). Drives FY allocation.
	  priority: Integer 1-5 (1=Cold .. 5=Very Hot).
	  contact_number: 10-digit Indian phone; any reasonable input form
	    accepted (with/without +91-, spaces, parens). Canonicalised
	    to '+91-XXXXXXXXXX' via _normalize_phone; rejected loud on
	    malformed (NOT the silent-pass behaviour of the login paths
	    that need no-enumeration). PD-S29-LEAD-FORM-FIELDS.
	  contact_email: Email; validated via frappe.utils.validate_email_address.
	    PD-S29-LEAD-FORM-FIELDS.
	  meeting_brief: Short text summary of the contact. Non-empty.
	    PD-S29-LEAD-FORM-FIELDS.

	Returns:
	  Dict with name, company_name, territory, contact_date, priority,
	  status, lead_owner, contact_number, contact_email, meeting_brief.

	Raises:
	  frappe.ValidationError: priority outside 1-5, missing/malformed
	    contact_number, missing/malformed contact_email, missing
	    meeting_brief, or any controller validation failure.
	"""
	try:
		priority_int = int(priority)
	except (TypeError, ValueError):
		frappe.throw("Priority must be an integer 1-5.", frappe.ValidationError)

	if not (1 <= priority_int <= 5):
		frappe.throw("Priority must be 1-5.", frappe.ValidationError)

	# PD-S29-LEAD-FORM-FIELDS — 3 new mandatory fields validated at API
	# boundary. Column-level reqd stays 0 (nullable) so the pre-S30 rows
	# stay readable as NULL; mandatory-ness is enforced ONLY at create-time
	# via this block. Forward-only; no backfill.
	contact_number = (contact_number or "").strip()
	if not contact_number:
		frappe.throw("Contact number is required.", frappe.ValidationError)
	# _normalize_phone returns input unchanged on failure (no-throw,
	# caller-decides contract — see helper docstring). For the create-lead
	# path we want loud rejection, so post-check the canonical shape
	# (+91- + 10 digits = 14 chars).
	contact_number_norm = _normalize_phone(contact_number)
	if not (contact_number_norm.startswith("+91-") and len(contact_number_norm) == 14):
		frappe.throw(
			f"Contact number must be a 10-digit Indian phone (got: {contact_number!r}).",
			frappe.ValidationError,
		)
	contact_number = contact_number_norm

	contact_email = (contact_email or "").strip()
	if not contact_email:
		frappe.throw("Contact email is required.", frappe.ValidationError)
	# validate_email_address raises frappe.InvalidEmailAddressError on
	# malformed input; we wrap to surface a ValidationError consistent
	# with the other fields here.
	try:
		validate_email_address(contact_email, throw=True)
	except Exception:
		frappe.throw(
			f"Contact email is not a valid email address (got: {contact_email!r}).",
			frappe.ValidationError,
		)

	meeting_brief = (meeting_brief or "").strip()
	if not meeting_brief:
		frappe.throw("Meeting brief is required.", frappe.ValidationError)

	doc = frappe.new_doc("VECRM Lead")
	doc.company_name = company_name
	doc.territory = territory
	doc.contact_date = contact_date
	doc.priority = priority_int
	doc.contact_number = contact_number
	doc.contact_email = contact_email
	doc.meeting_brief = meeting_brief
	# PD-S30-LEAD-CONTACT-FIELDS: optional contact-person fields
	if contact_person_name:
		doc.contact_person_name = contact_person_name.strip()
	if contact_person_designation:
		doc.contact_person_designation = contact_person_designation.strip()
	doc.status = "Open"
	# LEAD-OWNER-ATTRIBUTION fix (S31): use human's vecrm_email from session data,
	# NOT frappe.session.user (which is the BFF service account in portal context).
	vecrm_email = frappe.session.data.get("vecrm_email")
	if not vecrm_email:
		frappe.throw(
			frappe._("VECRM session missing vecrm_email. Re-login required."),
			frappe.SessionStopped,
		)
	if vecrm_email == "vecrm-portal@vinayenterprises.co.in":
		# ATT-5 assertion: belt-and-braces against future regression
		frappe.throw(
			frappe._("Service account cannot be lead_owner. Session-data corruption."),
			frappe.ValidationError,
		)
	doc.lead_owner = vecrm_email
	# Per-rep attribution for PD-S28 scoping (S27 PR #20). Reads the
	# session-data key set by _issue_session at portal login. None for
	# Desk-side admin creation — the column stays NULL there, which is
	# acceptable per the schema (no NOT NULL constraint) since Desk-side
	# leads are admin-created and not subject to per-rep scoping.
	doc.creating_employee = frappe.session.data.get("vecrm_employee_phone")
	doc.insert()

	return {
		"name": doc.name,
		"company_name": doc.company_name,
		"territory": doc.territory,
		"contact_date": str(doc.contact_date),
		"priority": doc.priority,
		"status": doc.status,
		"lead_owner": doc.lead_owner,
		"contact_number": doc.contact_number,
		"contact_email": doc.contact_email,
		"meeting_brief": doc.meeting_brief,
		"contact_person_name": doc.contact_person_name or "",
		"contact_person_designation": doc.contact_person_designation or "",
	}


@frappe.whitelist()
def close_lead(name: str, outcome: str, notes: str = "") -> dict:
    """Close a VECRM Lead with a final outcome.

    PD-S29-LEAD-INQUIRY-CLOSURE-UI: operator-driven manual closure.
    Outcomes: 'Closed-Won' (sale made) or 'Closed-Lost' (sale lost).
    Status is immutable once Closed-*; closure_notes optional but recommended.

    Args:
        name: VECRM Lead PK (e.g. 'VE/LEAD/00020/26-27')
        outcome: 'Closed-Won' or 'Closed-Lost'
        notes: free-form text captured at closure (stored in closure_notes)

    Returns:
        {"success": True, "name": name, "status": outcome}

    Raises:
        ValidationError on: invalid outcome, lead already in terminal state,
        invalid lead name, or session lacking vecrm_email.
    """
    if outcome not in ("Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Invalid outcome '{0}'. Must be Closed-Won or Closed-Lost.").format(outcome),
            frappe.ValidationError,
        )

    # Session identity (same pattern as create_lead)
    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    doc = frappe.get_doc("VECRM Lead", name)

    # Reject if already in terminal state
    if doc.status in ("Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Lead {0} is already in terminal state '{1}'.").format(name, doc.status),
            frappe.ValidationError,
        )

    # Capture transition for audit (mirrors lead_owner change pattern)
    doc.status = outcome
    if notes:
        doc.closure_notes = notes.strip()
    doc.save()

    return {
        "success": True,
        "name": doc.name,
        "status": doc.status,
        "closure_notes": doc.closure_notes or "",
    }


@frappe.whitelist()
def close_inquiry(name: str, outcome: str, notes: str = "") -> dict:
    """Close a VECRM Inquiry with a final outcome.

    PD-S29-LEAD-INQUIRY-CLOSURE-UI: operator-driven manual closure.
    Outcomes: 'Closed-Won' (sale made) or 'Closed-Lost' (sale lost).
    Status is immutable once Closed-*; closure_notes optional.

    Args:
        name: VECRM Inquiry PK (e.g. 'VE/INQ/00015/26-27')
        outcome: 'Closed-Won' or 'Closed-Lost'
        notes: free-form text captured at closure

    Returns:
        {"success": True, "name": name, "status": outcome}

    Raises:
        ValidationError on: invalid outcome, inquiry already in terminal state,
        or session lacking vecrm_email.
    """
    if outcome not in ("Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Invalid outcome '{0}'. Must be Closed-Won or Closed-Lost.").format(outcome),
            frappe.ValidationError,
        )

    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    doc = frappe.get_doc("VECRM Inquiry", name)

    if doc.status in ("Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Inquiry {0} is already in terminal state '{1}'.").format(name, doc.status),
            frappe.ValidationError,
        )

    doc.status = outcome
    if notes:
        doc.closure_notes = notes.strip()
    doc.save()

    return {
        "success": True,
        "name": doc.name,
        "status": doc.status,
        "closure_notes": doc.closure_notes or "",
    }


@frappe.whitelist()
def upload_lead_attachment(lead_name: str, slot: int) -> dict:
    """Upload a file to a specific attachment slot on a Lead.

    PD-S30-LEAD-ATTACHMENTS: supports up to 3 attachments per Lead.
    File arrives via Frappe's standard /api/method/upload_file mechanism;
    this endpoint wires the resulting file URL into the requested slot.

    Args:
        lead_name: VECRM Lead PK
        slot: 1, 2, or 3 (which attachment_N field to set)

    Returns:
        {"success": True, "slot": slot, "file_url": <url>}

    Raises:
        ValidationError on: invalid slot, slot already filled, lead in terminal
        state, missing session identity, or no file in request.
    """
    if slot not in (1, 2, 3):
        frappe.throw(
            frappe._("Invalid slot {0}. Must be 1, 2, or 3.").format(slot),
            frappe.ValidationError,
        )

    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    # File must be in request as multipart (Frappe's standard upload_file pattern)
    files = frappe.request.files
    if "file" not in files:
        frappe.throw(
            frappe._("No file in upload request."),
            frappe.ValidationError,
        )

    doc = frappe.get_doc("VECRM Lead", lead_name)

    # Block uploads on closed leads
    if doc.status in ("Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Cannot modify attachments on closed Lead {0}.").format(lead_name),
            frappe.ValidationError,
        )

    # Block overwriting an existing attachment without explicit delete first
    slot_field = f"attachment_{slot}"
    current = getattr(doc, slot_field, None)
    if current:
        frappe.throw(
            frappe._("Slot {0} already filled. Delete first or use a different slot.").format(slot),
            frappe.ValidationError,
        )

    # Upload via Frappe's standard mechanism (writes to private/files/)
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": files["file"].filename,
        "attached_to_doctype": "VECRM Lead",
        "attached_to_name": lead_name,
        "attached_to_field": slot_field,
        "is_private": 1,
        "content": files["file"].read(),
    }).insert(ignore_permissions=True)

    # Wire URL into the slot
    setattr(doc, slot_field, file_doc.file_url)
    doc.save()

    return {
        "success": True,
        "slot": slot,
        "file_url": file_doc.file_url,
    }


@frappe.whitelist()
def delete_lead_attachment(lead_name: str, slot: int) -> dict:
    """Delete an attachment from a specific slot on a Lead.

    PD-S30-LEAD-ATTACHMENTS: clears the slot's file URL and removes the
    underlying File doctype row.

    Args:
        lead_name: VECRM Lead PK
        slot: 1, 2, or 3

    Returns:
        {"success": True, "slot": slot}
    """
    if slot not in (1, 2, 3):
        frappe.throw(
            frappe._("Invalid slot {0}. Must be 1, 2, or 3.").format(slot),
            frappe.ValidationError,
        )

    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    doc = frappe.get_doc("VECRM Lead", lead_name)

    if doc.status in ("Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Cannot modify attachments on closed Lead {0}.").format(lead_name),
            frappe.ValidationError,
        )

    slot_field = f"attachment_{slot}"
    current_url = getattr(doc, slot_field, None)
    if not current_url:
        # Idempotent: deleting an empty slot is a no-op success
        return {"success": True, "slot": slot, "noop": True}

    # Delete the underlying File doctype row
    file_doc = frappe.db.get_value(
        "File",
        {"file_url": current_url, "attached_to_doctype": "VECRM Lead", "attached_to_name": lead_name},
        "name",
    )
    if file_doc:
        frappe.delete_doc("File", file_doc, ignore_permissions=True)

    # Clear the slot
    setattr(doc, slot_field, None)
    doc.save()

    return {"success": True, "slot": slot}


# ============================================================
# S25 v2 PD-S25-VECRM-AUTH — email-login portal authentication
#
# SECURITY NOTES (OBS-S25-H, -I, -J corrections + Phase 0.5 probes):
# - Shared VECRM Portal User has ONLY VECRM Submitter + VECRM Approver
#   roles. No VECRM Admin. This is the architectural floor.
# - App-side privileged-operation gating MUST read
#   frappe.session.data.vecrm_employee_role, NEVER frappe.get_roles().
#   The latter returns shared-user roles, same for every session.
# - admin_set_credential is INTENTIONALLY NOT a whitelisted endpoint
#   in S25. Credential setting is bench-console-only until S26 ships
#   a properly-gated session-data path.
# - Phone+PIN login deferred to S26.
# - @frappe.rate_limiter NOT used: Probe 4 confirmed hasattr(frappe,
#   'rate_limiter') is False in v16.18.2. Lockout (5 attempts / 15 min
#   per employee) is the sole defense.
# ============================================================

from datetime import timedelta
from typing import Any

from frappe import _
from frappe.utils import now_datetime, get_datetime, validate_email_address
from frappe.utils.password import passlibctx

from vecrm.vecrm.utils.auth_reset import (
    DEFAULT_TOKEN_TTL_MINUTES,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_MINUTES,
    generate_token,
    hash_token,
)


# Constants
_VECRM_PORTAL_USER: str = "vecrm-portal@vinayenterprises.co.in"
_MAX_FAILED_ATTEMPTS: int = 5
_LOCKOUT_MINUTES: int = 15

@frappe.whitelist()
def update_lead_followup(
    lead_name: str,
    next_followup_date: str,
    notes: str = "",
) -> dict:
    """Update the next_followup_date on a VECRM Lead.

    PD-S30-LEAD-FOLLOWUP Phase 1. Sets next_followup_date on the lead
    document. Logs the transition via the existing reassignment_history
    child table + VECRM Assignment Ledger Entry dual-write pattern
    (handled by the controller's before_save hook — we only set the field
    here; the controller picks up the change).

    Args:
      lead_name: VECRM Lead PK (e.g. 'VE/LEAD/00020/26-27')
      next_followup_date: ISO date string (YYYY-MM-DD). Required.
      notes: free-form text captured at follow-up logging. Optional;
        appended to closure_notes is NOT done here — notes is reserved for
        Phase 2 touchpoint doctype. Phase 1 logs notes into the
        reassignment_history row's change_reason field via the controller.

    Returns:
      Dict with name, next_followup_date (as ISO string), status,
      lead_owner. Matches the close_lead return shape.

    Raises:
      ValidationError on: invalid date format, lead in terminal state,
      missing session vecrm_email.
      SessionStopped on: missing vecrm_email in session data.

    Permission model (Q-LEAD-FOLLOWUP-11 = (a) revised):
      Authorization is enforced at the BFF layer via canReadLead
      (creating_employee match + Admin). This whitelisted method does
      NOT re-check at the backend — consistent with close_lead and
      convert_lead_to_inquiry. See PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT (P3)
      for the future cross-cutting backend-side defense-in-depth refactor.
    """
    from frappe.utils import getdate

    # Validate date format
    try:
        parsed_date = getdate(next_followup_date)
    except Exception:
        frappe.throw(
            frappe._("Invalid date format for next_followup_date. Expected YYYY-MM-DD, got: {0}").format(next_followup_date),
            frappe.ValidationError,
        )

    # Session identity (same pattern as close_lead)
    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    doc = frappe.get_doc("VECRM Lead", lead_name)

    # Terminal-state guard (Q-LEAD-FOLLOWUP-12 = (a))
    if doc.status in ("Converted", "Closed-Won", "Closed-Lost"):
        frappe.throw(
            frappe._("Lead {0} is in terminal state '{1}'. Follow-up actions are not permitted on terminal leads.").format(lead_name, doc.status),
            frappe.ValidationError,
        )

    # Set the field. The controller's before_save hook will detect the
    # change and log it via reassignment_history + Assignment Ledger Entry.
    # NOTE: the existing before_save change-detection only handles
    # lead_owner and status changes (per vecrm_lead.py). It does NOT
    # currently detect next_followup_date changes. The Phase 1 controller
    # update below extends before_save to also log next_followup_date
    # transitions, using the same reassignment_history dual-write.
    doc.next_followup_date = parsed_date
    if notes:
        # Notes are stored transiently in flags for the controller to read
        # during before_save. Not persisted to the lead row itself; the
        # change_reason on the reassignment_history row carries the notes.
        doc.flags.followup_notes = notes.strip()
    doc.save()

    return {
        "success": True,
        "name": doc.name,
        "next_followup_date": str(doc.next_followup_date) if doc.next_followup_date else None,
        "status": doc.status,
        "lead_owner": doc.lead_owner,
    }
    
def _audit_auth(
    event: str,
    *,
    employee: str | None = None,
    identifier: str | None = None,
    path: str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a row to VECRM Auth Audit Log. Never raises (best-effort)."""
    try:
        log = frappe.new_doc("VECRM Auth Audit Log")
        log.event = event
        log.employee = employee
        log.identifier = identifier
        log.path = path
        log.reason = reason
        log.ip_address = getattr(frappe.local, "request_ip", None)
        log.user_agent = (
            frappe.get_request_header("User-Agent")
            if getattr(frappe.local, "request", None) else None
        )
        log.extra = json.dumps(extra) if extra else None
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(f"audit emission failed: {e}", "vecrm.api._audit_auth")


def _is_locked(employee_doc: Any) -> bool:
    """True if employee is currently within a lockout window."""
    if not employee_doc.locked_until:
        return False
    return get_datetime(employee_doc.locked_until) > now_datetime()


def _on_failure(employee_doc: Any) -> None:
    """Increment failed attempts; set lockout if threshold reached."""
    current = (employee_doc.failed_password_attempts or 0) + 1
    employee_doc.failed_password_attempts = current
    if current >= _MAX_FAILED_ATTEMPTS:
        employee_doc.locked_until = now_datetime() + timedelta(minutes=_LOCKOUT_MINUTES)
        _audit_auth(
            "auth.account_locked",
            employee=employee_doc.name,
            path="password",
            extra={"locked_until": str(employee_doc.locked_until)},
        )
    employee_doc.db_update()
    frappe.db.commit()


def _on_success(employee_doc: Any) -> None:
    """Reset failed attempts + record last login."""
    employee_doc.failed_password_attempts = 0
    employee_doc.locked_until = None
    employee_doc.last_login_at = now_datetime()
    employee_doc.db_update()
    frappe.db.commit()


def _normalize_phone(phone: str) -> str:
    """Canonicalize portal-submitted phone to match VECRM Employee.name format.

    Target: '+91-' followed by exactly 10 digits.
    Accepts variants: with/without country code, with/without separators
    (spaces, dashes, parens), with/without leading 0.

    Returns the input unchanged if normalization fails — the caller is
    expected to emit invalid_credentials on lookup failure (R5).
    """
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        return phone
    return f"+91-{digits}"


def _is_pin_locked(employee_doc: Any) -> bool:
    """True if PIN auth is currently within a lockout window.

    Mirrors _is_locked exactly but reads pin_locked_until — independent
    lockout state per R6.
    """
    if not employee_doc.pin_locked_until:
        return False
    return get_datetime(employee_doc.pin_locked_until) > now_datetime()


def _on_pin_failure(employee_doc: Any) -> None:
    """Increment failed PIN attempts; set PIN-specific lockout if threshold reached.

    Mirrors _on_failure but operates on pin_ prefixed fields. Independent
    state — password lockout is NOT affected (R6).
    """
    current = (employee_doc.failed_pin_attempts or 0) + 1
    employee_doc.failed_pin_attempts = current
    if current >= _MAX_FAILED_ATTEMPTS:
        employee_doc.pin_locked_until = now_datetime() + timedelta(minutes=_LOCKOUT_MINUTES)
        _audit_auth(
            "auth.account_locked",
            employee=employee_doc.name,
            path="pin",
            extra={"pin_locked_until": str(employee_doc.pin_locked_until)},
        )
    employee_doc.db_update()
    frappe.db.commit()


def _on_pin_success(employee_doc: Any) -> None:
    """Reset failed PIN attempts + record last PIN login."""
    employee_doc.failed_pin_attempts = 0
    employee_doc.pin_locked_until = None
    employee_doc.last_pin_login_at = now_datetime()
    employee_doc.db_update()
    frappe.db.commit()


def _issue_session(employee_doc: Any, login_path: str) -> None:
    """Issue a Frappe session as the shared VECRM Portal User; stash employee
    identity in session data per D8.

    The login_as call runs Session.start() → insert_session_record(), which
    persists self.data["data"] BEFORE our custom keys exist. We then mutate
    frappe.session.data (which IS self.data["data"]) to add the vecrm_*
    keys, and call frappe.local.session_obj.update(force=True) to re-persist
    BOTH the DB sessiondata row AND the cache slot with the correct outer
    Session.data shape.

    force=True is required: Session.update()'s default time-threshold gate
    no-ops on a fresh session where last_updated was just set by start().
    OBS-S25-AL.
    """
    frappe.local.login_manager.login_as(_VECRM_PORTAL_USER)
    frappe.session.data.vecrm_employee_phone = employee_doc.vecrm_phone
    frappe.session.data.vecrm_employee_name = employee_doc.employee_name
    frappe.session.data.vecrm_employee_role = employee_doc.role
    frappe.session.data.vecrm_login_path = login_path
    # LEAD-OWNER-ATTRIBUTION fix (S31): stash vecrm_email for downstream
    # attribution writes (api.py:334 create_lead, vecrm_lead.py:84
    # reassignment ledger, voucher audit logs). Per ATT-4: reject loud if
    # the Employee record lacks vecrm_email — that's a data-integrity bug
    # we want surfaced immediately, not silently degraded.
    if not employee_doc.vecrm_email:
        frappe.throw(
            frappe._(
                "VECRM Employee {0} missing vecrm_email; cannot issue session."
            ).format(employee_doc.name),
            frappe.ValidationError,
        )
    frappe.session.data.vecrm_email = employee_doc.vecrm_email
    frappe.local.session_obj.update(force=True)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def login_with_password(email: str = "", password: str = "") -> dict[str, Any]:
    """Authenticate VECRM Employee via email + password.

    Returns:
        {"success": True, "employee": "<phone>", "name": "<full_name>",
         "role": "<role>"}

    Raises:
        frappe.AuthenticationError with generic "Invalid credentials" for
        all failure modes (no enumeration: bad password, unknown email,
        locked account, and inactive employee all return the same error).
    """
    if not email or not password:
        _audit_auth("auth.login.failed", identifier=email, path="password", reason="missing_input")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    employee_name = frappe.db.get_value("VECRM Employee", {"vecrm_email": email}, "name")
    if not employee_name:
        _audit_auth("auth.login.failed", identifier=email, path="password", reason="unknown_email")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    employee_doc = frappe.get_doc("VECRM Employee", employee_name)

    if employee_doc.vecrm_account_status != "Active":
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=email, path="password",
            reason="account_inactive",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if _is_locked(employee_doc):
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=email, path="password",
            reason="account_locked",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if not employee_doc.password_hash:
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=email, path="password",
            reason="no_password_configured",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if not passlibctx.verify(password, employee_doc.password_hash):
        _on_failure(employee_doc)
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=email, path="password",
            reason="invalid_credentials",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    _on_success(employee_doc)
    _issue_session(employee_doc, "password")
    _audit_auth("auth.login.success", employee=employee_doc.name, path="password")

    return {
        "success": True,
        "employee": employee_doc.name,
        "name": employee_doc.employee_name,
        "role": employee_doc.role,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def login_with_pin(phone: str = "", pin: str = "") -> dict[str, Any]:
    """Authenticate VECRM Employee via phone + PIN.

    Companion to login_with_password (S25). Independent lockout state per R6.

    Returns:
        {"success": True, "employee": "<phone>", "name": "<full_name>",
         "role": "<role>"}

    Raises:
        frappe.AuthenticationError with generic "Invalid credentials" for
        all failure modes (no enumeration: bad PIN, unknown phone, locked
        account, inactive employee — all return the same error).
    """
    if not phone or not pin:
        _audit_auth("auth.login.failed", identifier=phone, path="pin", reason="missing_input")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    # PD-S29-PIN-INPUT-SEGMENTED-6BOX (S30): exact-6-digit length check.
    # Pre-DB-lookup gate; rejects malformed PINs (non-digit, wrong length)
    # before they can compete with hash verification. Matches change_pin
    # (api.py:1377) and post-tightening complete_pin_reset. Generic
    # "Invalid credentials" + audit-only-with-specific-reason maintains
    # no-enumeration: a malformed PIN looks identical to a wrong PIN
    # externally; only the audit row carries the discriminator.
    if not pin.isdigit() or len(pin) != 6:
        _audit_auth("auth.login.failed", identifier=phone, path="pin", reason="invalid_pin_format")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    normalized = _normalize_phone(phone)
    employee_name = frappe.db.get_value("VECRM Employee", normalized, "name")
    if not employee_name:
        _audit_auth("auth.login.failed", identifier=phone, path="pin", reason="unknown_phone")
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    employee_doc = frappe.get_doc("VECRM Employee", employee_name)

    if employee_doc.vecrm_account_status != "Active":
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="account_inactive",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if _is_pin_locked(employee_doc):
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="account_locked",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if not employee_doc.pin_hash:
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="no_pin_configured",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    if not passlibctx.verify(pin, employee_doc.pin_hash):
        _on_pin_failure(employee_doc)
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=phone, path="pin",
            reason="invalid_credentials",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    _on_pin_success(employee_doc)
    _issue_session(employee_doc, "pin")
    _audit_auth("auth.login.success", employee=employee_doc.name, path="pin")

    return {
        "success": True,
        "employee": employee_doc.name,
        "name": employee_doc.employee_name,
        "role": employee_doc.role,
    }


@frappe.whitelist(methods=["POST"])
def vecrm_logout() -> dict[str, Any]:
    """Invalidate current VECRM portal session.

    Emits an `auth.logout` audit row carrying the session's `vecrm_login_path`
    (set by _issue_session at login) as the `path` discriminator, so logout
    events pair with the originating login_with_password / login_with_pin
    event in the audit trail. Closes PD-S26-AUTH-LOGOUT-PATH-RECORD.
    """
    employee_phone = frappe.session.data.get("vecrm_employee_phone")
    login_path = frappe.session.data.get("vecrm_login_path")
    _audit_auth("auth.logout", employee=employee_phone, path=login_path)
    frappe.local.login_manager.logout()
    return {"success": True}


@frappe.whitelist(methods=["GET"])
def get_session_employee() -> dict[str, Any]:
    """Return VECRM Employee identity for the current session.

    Reads vecrm_employee_phone from session data. Raises PermissionError
    if no VECRM employee is associated.
    """
    employee_phone = frappe.session.data.get("vecrm_employee_phone")
    if not employee_phone:
        frappe.throw(_("Not authenticated as VECRM Employee"), frappe.PermissionError)

    employee_doc = frappe.get_doc("VECRM Employee", employee_phone)
    return {
        "employee": employee_doc.name,
        "name": employee_doc.employee_name,
        "vecrm_email": employee_doc.vecrm_email,
        "role": employee_doc.role,
        "base_city": employee_doc.vecrm_base_city,
        "login_path": frappe.session.data.get("vecrm_login_path"),
    }


# ============================================================
# S28 PD-S28-AUTH-RESET-BACKEND-API — token mgmt + credential write
#
# Four whitelisted methods backing the password/PIN reset flow:
#   request_password_reset(email)  — create token, return raw for portal email
#   request_pin_reset(phone)       — create token, return raw for portal email
#   complete_password_reset(token, new_password) — consume token, update password
#   complete_pin_reset(token, new_pin)           — consume token, update PIN
#
# Schema substrate shipped in S27 PR #21 (VECRM Auth Reset Token doctype).
# Portal-side email send + Forgot UI + accept pages ship in
# PD-S28-AUTH-RESET-PORTAL-{BFF,UI,EMAIL-TEMPLATE}.
#
# Security invariants enforced here:
#   1. Raw token NEVER persisted; only sha256 hash via hash_token()
#   2. Token lookup is SQL equality on the HASH (timing-safe: candidate
#      hash is fully known to the requester, no oracle leak)
#   3. Single-use: consumed_at check precedes any credential write
#   4. Time-bounded: expires_at check precedes any credential write
#   5. reset_for discriminator enforced: password tokens can't update PIN
#      and vice versa
#   6. No-enumeration: request_*_reset always returns identical response
#      shape regardless of email/phone match (only `_internal.raw_token`
#      differs internally; portal BFF strips _internal before client relay)
#   7. Rate-limited: RATE_LIMIT_MAX_REQUESTS=3 per employee per
#      RATE_LIMIT_WINDOW_MINUTES=15
#   8. Audit log emitted on every path (requested/consumed/expired/
#      invalid_token/rate_limited) -- vocabulary extension per S27 addendum §3
#   9. Lockout state cleared on successful reset (failed_*_attempts=0,
#      *_locked_until=None) so a user who just reset can immediately log in
#  10. All methods type-annotated per Frappe v16 require_type_annotated_api_methods
# ============================================================


_RESET_GENERIC_ERROR: str = "Invalid or expired reset token"


def _make_reset_response(message: str) -> dict[str, Any]:
    """Build the no-enumeration response envelope for request_*_reset.

    Shape is identical regardless of whether the input matched a real
    employee, was rate-limited, or referenced an inactive account. The
    portal BFF MUST strip `_internal` before relaying to the client; only
    the BFF needs the raw token (to construct the emailed link), the
    employee_name (the *display name* used in the email greeting -- e.g.
    "Hi Ajay,"), and the delivery_email (the address to send to).
    """
    return {
        "success": True,
        "message": message,
        "_internal": {
            "raw_token": None,
            "employee_name": None,
            "delivery_email": None,
        },
    }


def _count_recent_reset_tokens(employee_name: str, reset_for: str) -> int:
    """Count tokens issued for this employee+reset_for in the rate-limit window."""
    cutoff = now_datetime() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    return frappe.db.count(
        "VECRM Auth Reset Token",
        filters={
            "employee": employee_name,
            "reset_for": reset_for,
            "creation": [">", cutoff],
        },
    )


def _create_reset_token_row(employee_name: str, reset_for: str) -> str:
    """Insert a VECRM Auth Reset Token row and return the raw token.

    The raw token is returned to the caller (request_*_reset) for inclusion
    in the emailed link. Only the sha256 hash is persisted.
    """
    raw_token, token_hash = generate_token()
    token_doc = frappe.get_doc(
        {
            "doctype": "VECRM Auth Reset Token",
            "token_hash": token_hash,
            "employee": employee_name,
            "reset_for": reset_for,
            "expires_at": now_datetime()
            + timedelta(minutes=DEFAULT_TOKEN_TTL_MINUTES),
            "ip_address": getattr(frappe.local, "request_ip", None),
        }
    )
    token_doc.insert(ignore_permissions=True)
    return raw_token


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_password_reset(email: str = "") -> dict[str, Any]:
    """Initiate a password reset flow.

    Always returns the same success-shaped response regardless of whether
    `email` matches a real employee (no-enumeration). If a real match
    exists AND the rate limit hasn't been hit AND the account is Active,
    a VECRM Auth Reset Token row is created and the raw token is returned
    in `_internal.raw_token` so the portal BFF can construct the emailed
    link.

    Args:
        email: User email to request reset for.

    Returns:
        {
          "success": True,
          "message": "If an account exists for this email, a reset link has been sent.",
          "_internal": {
              "raw_token": <str or None>,
              "employee_name": <str or None>,
              "delivery_email": <str or None>,
          },
        }

    The portal MUST NOT relay `_internal` to the client. It exists so the
    BFF can construct the emailed link without a second API roundtrip.
    `employee_name` is the VECRM Employee display name (e.g. "Ajay Salvi")
    -- NOT the doctype autoname, which is the phone. Falls back to the
    autoname (phone) only if the display name field is NULL on the row.
    `delivery_email` is the address `sendMailNoreply` should target -- for
    password reset it's the user-submitted email (echoed back); for PIN
    reset it's the employee's `vecrm_email` looked up from the phone.
    """
    response = _make_reset_response(
        "If an account exists for this email, a reset link has been sent."
    )

    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        # Empty input: don't audit (no signal to log), no-enumeration.
        return response

    employee_name = frappe.db.get_value(
        "VECRM Employee", {"vecrm_email": normalized_email}, "name"
    )

    if not employee_name:
        # No match: audit with employee=None for forensics; return success.
        _audit_auth(
            "auth.reset.requested",
            identifier=normalized_email,
            path="password",
        )
        return response

    # Rate limit BEFORE the inactive-status check so we don't burn audit
    # rows / lookups on a rate-limited probe.
    if _count_recent_reset_tokens(employee_name, "password") >= RATE_LIMIT_MAX_REQUESTS:
        _audit_auth(
            "auth.reset.rate_limited",
            employee=employee_name,
            identifier=normalized_email,
            path="password",
        )
        return response

    employee_doc = frappe.get_doc("VECRM Employee", employee_name)
    if employee_doc.vecrm_account_status != "Active":
        # Audit but don't issue a token -- no-enumeration: response identical.
        _audit_auth(
            "auth.reset.requested",
            employee=employee_name,
            identifier=normalized_email,
            path="password",
            reason="account_inactive",
        )
        return response

    # All checks pass: create token, audit, return raw for portal email.
    raw_token = _create_reset_token_row(employee_name, "password")
    _audit_auth(
        "auth.reset.requested",
        employee=employee_name,
        identifier=normalized_email,
        path="password",
    )
    frappe.db.commit()

    response["_internal"]["raw_token"] = raw_token
    # _internal["employee_name"] is the DISPLAY name (for "Hi Ajay," in
    # the email greeting), NOT the local `employee_name` variable above
    # -- which is the doctype autoname (phone, e.g. "+91-9999900001").
    # Naming clash is in the VECRM Employee schema itself: `name` is the
    # autoname; the display name is in the `employee_name` field. Fall
    # back to the autoname if the display field is NULL (preserves the
    # "always-some-value" invariant the BFF relies on).
    response["_internal"]["employee_name"] = (
        employee_doc.employee_name or employee_doc.name
    )
    response["_internal"]["delivery_email"] = normalized_email
    return response


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_pin_reset(phone: str = "") -> dict[str, Any]:
    """Initiate a PIN reset flow.

    Mirrors request_password_reset, but keyed by phone (E.164 +91-XXXXXXXXXX).
    Lookup is by VECRM Employee name (autoname == vecrm_phone), so no
    User-email indirection. reset_for="pin", audit path="pin". The emailed
    reset link is still delivered to the employee's vecrm_email -- this is
    a V1 trade-off (PIN reset via email channel) documented in the
    addendum.

    Args:
        phone: User phone, accepts country-code / dash / leading-0 variants
            (normalized via _normalize_phone).

    Returns:
        Same no-enumeration response shape as request_password_reset.
    """
    response = _make_reset_response(
        "If an account exists for this phone, a reset link has been sent."
    )

    normalized_phone = _normalize_phone(phone or "")
    if not normalized_phone:
        return response

    # Autoname invariant: VECRM Employee.name == vecrm_phone
    employee_name = frappe.db.get_value(
        "VECRM Employee", normalized_phone, "name"
    )

    if not employee_name:
        _audit_auth(
            "auth.reset.requested",
            identifier=normalized_phone,
            path="pin",
        )
        return response

    if _count_recent_reset_tokens(employee_name, "pin") >= RATE_LIMIT_MAX_REQUESTS:
        _audit_auth(
            "auth.reset.rate_limited",
            employee=employee_name,
            identifier=normalized_phone,
            path="pin",
        )
        return response

    employee_doc = frappe.get_doc("VECRM Employee", employee_name)
    if employee_doc.vecrm_account_status != "Active":
        _audit_auth(
            "auth.reset.requested",
            employee=employee_name,
            identifier=normalized_phone,
            path="pin",
            reason="account_inactive",
        )
        return response

    raw_token = _create_reset_token_row(employee_name, "pin")
    _audit_auth(
        "auth.reset.requested",
        employee=employee_name,
        identifier=normalized_phone,
        path="pin",
    )
    frappe.db.commit()

    response["_internal"]["raw_token"] = raw_token
    # Display name (with autoname/phone fallback) -- see the matching
    # comment in request_password_reset for the autoname-vs-display-name
    # naming clash rationale.
    response["_internal"]["employee_name"] = (
        employee_doc.employee_name or employee_doc.name
    )
    # vecrm_email is varchar(140) UNIQUE NULL — `or None` normalises the
    # empty-string-on-NULL Frappe quirk so the BFF can do a clean
    # `if internal.delivery_email` check.
    response["_internal"]["delivery_email"] = employee_doc.vecrm_email or None
    return response


def _consume_reset_token(token: str, expected_reset_for: str) -> Any:
    """Validate a raw reset token and return its loaded doc, OR throw generic.

    All failure modes throw frappe.AuthenticationError with a single generic
    message (no-enumeration of token state). The audit log carries the
    discriminator for forensics. On success, returns the loaded token doc;
    caller is responsible for setting consumed_at + db_update.

    Failure paths emitted:
      - auth.reset.invalid_token (token_hash not found)
      - auth.reset.invalid_token reason=already_consumed
      - auth.reset.invalid_token reason=wrong_reset_for (password token
        used for PIN reset or vice versa)
      - auth.reset.expired
    """
    token_hash = hash_token(token)

    # Lookup by token_hash field (NOT by name -- name is the autoname hash,
    # unrelated). SQL equality on a hash is timing-safe (the candidate hash
    # is fully known to the requester).
    token_doc_name = frappe.db.get_value(
        "VECRM Auth Reset Token", {"token_hash": token_hash}, "name"
    )

    if not token_doc_name:
        _audit_auth("auth.reset.invalid_token", path=expected_reset_for)
        frappe.throw(_(_RESET_GENERIC_ERROR), frappe.AuthenticationError)

    token_doc = frappe.get_doc("VECRM Auth Reset Token", token_doc_name)

    if token_doc.consumed_at:
        _audit_auth(
            "auth.reset.invalid_token",
            employee=token_doc.employee,
            path=expected_reset_for,
            reason="already_consumed",
        )
        frappe.throw(_(_RESET_GENERIC_ERROR), frappe.AuthenticationError)

    if token_doc.reset_for != expected_reset_for:
        _audit_auth(
            "auth.reset.invalid_token",
            employee=token_doc.employee,
            path=expected_reset_for,
            reason="wrong_reset_for",
        )
        frappe.throw(_(_RESET_GENERIC_ERROR), frappe.AuthenticationError)

    if get_datetime(token_doc.expires_at) < now_datetime():
        _audit_auth(
            "auth.reset.expired",
            employee=token_doc.employee,
            path=expected_reset_for,
        )
        frappe.throw(_(_RESET_GENERIC_ERROR), frappe.AuthenticationError)

    return token_doc


@frappe.whitelist(allow_guest=True, methods=["POST"])
def complete_password_reset(token: str = "", new_password: str = "") -> dict[str, Any]:
    """Consume a password reset token and set the new password.

    Atomic: token consume + password update + lockout clear all happen in
    one transaction (one frappe.db.commit at the end). If any step throws,
    the entire operation rolls back (no half-applied state).

    Args:
        token: Raw reset token from the emailed link.
        new_password: New password to set. Minimum 8 characters.

    Returns:
        {"success": True, "message": "Password updated."}

    Raises:
        frappe.AuthenticationError with generic "Invalid or expired reset
        token" for all failure modes (no-enumeration of token state);
        specifics written to audit log.
        frappe.ValidationError for password format violations.
    """
    if not token or not new_password:
        frappe.throw(_(_RESET_GENERIC_ERROR), frappe.AuthenticationError)

    # Minimum length: 8 chars. Mirrors industry-standard floor; tuneable
    # via a future password-policy doctype if needed. Surfaced as
    # ValidationError (not AuthenticationError) because the failure mode
    # is genuinely the user's input shape, not credential validity.
    if len(new_password) < 8:
        frappe.throw(
            _("Password must be at least 8 characters"), frappe.ValidationError
        )

    token_doc = _consume_reset_token(token, expected_reset_for="password")

    employee_doc = frappe.get_doc("VECRM Employee", token_doc.employee)

    # Set the new password on the in-memory doc so that db_update() below
    # persists it alongside the lockout-clear fields in a single write.
    # NOT update_password() — that writes to __Auth (Frappe Password-
    # fieldtype encrypted storage) which S25 phase 4.7 deprecated for this
    # doctype. db_update() does not touch `modified`/`modified_by`, keeping
    # the row reflecting real operator-meaningful edits rather than
    # credential-rotation noise.
    #
    # BUG-FIX: previously used frappe.db.set_value (direct SQL) followed by
    # employee_doc.db_update() — but db_update() serializes ALL in-memory
    # fields, overwriting the new hash with the stale in-memory value.
    employee_doc.password_hash = passlibctx.hash(new_password)

    # Clear the password-side lockout state. A user who just successfully
    # reset their credential should be able to log in immediately. PIN
    # lockout state is intentionally untouched (independent per S26 R6).
    employee_doc.failed_password_attempts = 0
    employee_doc.locked_until = None
    employee_doc.db_update()

    # Mark token consumed (single-use enforcement).
    token_doc.consumed_at = now_datetime()
    token_doc.db_update()

    _audit_auth(
        "auth.reset.consumed",
        employee=employee_doc.name,
        path="password",
    )

    frappe.db.commit()

    return {"success": True, "message": "Password updated."}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def complete_pin_reset(token: str = "", new_pin: str = "") -> dict[str, Any]:
    """Consume a PIN reset token and set the new PIN.

    Atomic: token consume + PIN update + PIN-lockout clear all happen in
    one transaction. Password-side lockout state is intentionally untouched
    (independent per S26 R6).

    Args:
        token: Raw reset token from the emailed link.
        new_pin: New PIN to set. Must be 4-6 digits (matches login_with_pin
            validation domain).

    Returns:
        {"success": True, "message": "PIN updated."}

    Raises:
        frappe.AuthenticationError generic for token-state failures.
        frappe.ValidationError for PIN format violations.
    """
    if not token or not new_pin:
        frappe.throw(_(_RESET_GENERIC_ERROR), frappe.AuthenticationError)

    # PIN format: EXACTLY 6 numeric digits (tightened S30 per
    # PD-S29-PIN-INPUT-SEGMENTED-6BOX; matches change_pin at api.py:1377
    # and login_with_pin's new pre-DB-lookup gate). The portal's
    # segmented PinInput6Box enforces 6-digit structurally on the client
    # side; this server-side check is the load-bearing defense per
    # OBS-S29-E (UI structural enforcement shifts server-side validation
    # from belt-and-braces to load-bearing).
    if not new_pin.isdigit() or len(new_pin) != 6:
        frappe.throw(
            _("PIN must be exactly 6 digits."), frappe.ValidationError
        )

    token_doc = _consume_reset_token(token, expected_reset_for="pin")

    employee_doc = frappe.get_doc("VECRM Employee", token_doc.employee)

    # See complete_password_reset for the write-pattern rationale + BUG-FIX
    # comment (db.set_value + db_update overwrite race).
    employee_doc.pin_hash = passlibctx.hash(new_pin)
    employee_doc.failed_pin_attempts = 0
    employee_doc.pin_locked_until = None
    employee_doc.db_update()

    token_doc.consumed_at = now_datetime()
    token_doc.db_update()

    _audit_auth(
        "auth.reset.consumed",
        employee=employee_doc.name,
        path="pin",
    )

    frappe.db.commit()

    return {"success": True, "message": "PIN updated."}


# ============================================================
# S29 PD-S29-ACCOUNT-SELF-SERVICE — authenticated change methods
#
# Two whitelist methods for authenticated portal users to change own
# credentials without traversing the forgot-* flow. Both require
# knowledge of the current credential.
#
# SEMANTICS (from B-phase dispatch §0 + findings §5):
#   - Authenticated-only (@whitelist without allow_guest)
#   - Verify current credential before accepting new
#   - On success: clear lockout state (mirrors complete_*_reset; correct
#     current-credential is sufficient proof of legitimacy — don't carry
#     login-side typing-fatigue lockout forward)
#   - On current-mismatch failure: audit, throw generic, do NOT increment
#     failed_*_attempts (change-* decoupled from login lockout counter;
#     prevents change-flow probing from rate-limiting login)
#   - New audit event vocabulary: auth.change.{password,pin}.{success,failed}
#   - New audit reason value: current_mismatch (joins existing 10-value
#     reason taxonomy)
#
# PIN policy on change_pin: EXACTLY 6 digits (OBS-S29-E policy A,
# OBS-S29-EE carry-forward). Intentionally tighter than complete_pin_reset
# (4-6 range at line 1093). Workstream B will tighten complete_pin_reset
# and add length check to login_with_pin for full policy A consistency.
# ============================================================


@frappe.whitelist(methods=["POST"])
def change_password(current_password: str = "", new_password: str = "") -> dict[str, Any]:
    """Authenticated portal user changes own password.

    Requires knowledge of current_password. On success: writes new hash,
    clears password-side lockout state (matches complete_password_reset
    semantics -- successful current-credential proof is a recovery signal,
    not just a routine change).

    Does NOT increment failed_password_attempts on current-mismatch --
    the change-* surface is independent of the login lockout counter.
    A failed change is a single audit row, not a step toward account-lock.

    PIN-side state untouched (independent per S26 R6, mirrored in S28
    reset flow).

    Args:
        current_password: User's current password for verification.
        new_password: New password to set. Minimum 8 characters
            (matches complete_password_reset policy at api.py:1027).

    Returns:
        {"success": True, "message": "Password updated."}

    Raises:
        frappe.PermissionError if no authenticated VECRM Employee session.
        frappe.AuthenticationError ("Invalid credentials") on current
            password mismatch (generic, no-enumeration).
        frappe.ValidationError on new password format violation.
    """
    # 1. Resolve session -> employee (mirrors get_session_employee at api.py:646)
    employee_phone = frappe.session.data.get("vecrm_employee_phone")
    if not employee_phone:
        frappe.throw(
            _("Not authenticated as VECRM Employee"), frappe.PermissionError
        )

    employee_doc = frappe.get_doc("VECRM Employee", employee_phone)

    # 2. Missing-input check
    if not current_password or not new_password:
        _audit_auth(
            "auth.change.password.failed",
            employee=employee_doc.name,
            path="password",
            reason="missing_input",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    # 3. New-password format check (same policy as complete_password_reset)
    if len(new_password) < 8:
        _audit_auth(
            "auth.change.password.failed",
            employee=employee_doc.name,
            path="password",
            reason="invalid_format",
        )
        frappe.throw(
            _("Password must be at least 8 characters"), frappe.ValidationError
        )

    # 4. Verify current (passlibctx.verify returns bool; mirrors api.py:530)
    if not employee_doc.password_hash or not passlibctx.verify(
        current_password, employee_doc.password_hash
    ):
        _audit_auth(
            "auth.change.password.failed",
            employee=employee_doc.name,
            path="password",
            reason="current_mismatch",
        )
        # NOTE: do NOT increment failed_password_attempts here. The change-*
        # surface is independent of the login lockout counter (rationale in
        # docstring above).
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    # 5. Write new + 6. Clear lockout — single db_update() to avoid the
    #    db.set_value + db_update overwrite race (see complete_password_reset
    #    BUG-FIX comment). Knowing the current credential is sufficient
    #    proof of legitimacy; don't carry login-side lockout forward.
    employee_doc.password_hash = passlibctx.hash(new_password)
    employee_doc.failed_password_attempts = 0
    employee_doc.locked_until = None
    employee_doc.db_update()

    # 7. Audit success + commit
    _audit_auth(
        "auth.change.password.success",
        employee=employee_doc.name,
        path="password",
    )
    frappe.db.commit()

    return {"success": True, "message": "Password updated."}


@frappe.whitelist(methods=["POST"])
def change_pin(current_pin: str = "", new_pin: str = "") -> dict[str, Any]:
    """Authenticated portal user changes own PIN.

    PIN policy: NEW PIN must be EXACTLY 6 digits (per OBS-S29-E policy A,
    carried forward from Workstream B even though B hasn't shipped yet --
    policy decisions apply to every new entry point added after the
    decision, regardless of impl order). This is INTENTIONALLY tighter
    than the existing complete_pin_reset policy (4-6 digits at line
    1093); when Workstream B ships, complete_pin_reset will tighten to
    match. login_with_pin will also gain a length check then.

    See change_password docstring for rationale on lockout-clear-on-success
    and independence from login attempt counters.

    Args:
        current_pin: User's current PIN for verification.
        new_pin: New PIN. EXACTLY 6 numeric digits (no whitespace, no
            mixed alphanumeric).

    Returns:
        {"success": True, "message": "PIN updated."}

    Raises:
        frappe.PermissionError if no authenticated VECRM Employee session.
        frappe.AuthenticationError ("Invalid credentials") on current PIN
            mismatch.
        frappe.ValidationError on new PIN format violation.
    """
    employee_phone = frappe.session.data.get("vecrm_employee_phone")
    if not employee_phone:
        frappe.throw(
            _("Not authenticated as VECRM Employee"), frappe.PermissionError
        )

    employee_doc = frappe.get_doc("VECRM Employee", employee_phone)

    if not current_pin or not new_pin:
        _audit_auth(
            "auth.change.pin.failed",
            employee=employee_doc.name,
            path="pin",
            reason="missing_input",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    # PIN format: EXACTLY 6 digits (OBS-S29-E policy A).
    if not new_pin.isdigit() or len(new_pin) != 6:
        _audit_auth(
            "auth.change.pin.failed",
            employee=employee_doc.name,
            path="pin",
            reason="invalid_format",
        )
        frappe.throw(
            _("PIN must be exactly 6 digits"), frappe.ValidationError
        )

    if not employee_doc.pin_hash or not passlibctx.verify(
        current_pin, employee_doc.pin_hash
    ):
        _audit_auth(
            "auth.change.pin.failed",
            employee=employee_doc.name,
            path="pin",
            reason="current_mismatch",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    # See complete_password_reset BUG-FIX comment (db.set_value + db_update
    # overwrite race).
    employee_doc.pin_hash = passlibctx.hash(new_pin)
    employee_doc.failed_pin_attempts = 0
    employee_doc.pin_locked_until = None
    employee_doc.db_update()

    _audit_auth(
        "auth.change.pin.success",
        employee=employee_doc.name,
        path="pin",
    )
    frappe.db.commit()

    return {"success": True, "message": "PIN updated."}


# ============================================================
# ADMIN — USER MANAGEMENT (PD-S29-ADMIN-USER-MGMT, S32)
# ============================================================
#
# Endpoints for the portal Admin user-management page. Admin-only —
# enforced by `_require_admin_session` which throws PermissionError if
# the session's `vecrm_employee_role` is not "Admin".
#
# These endpoints are the first practical application of
# VECRM-LOCK-ROLE-CAPABILITY-MATRIX §3.1 (single admin role) at the
# whitelist layer. The matrix lock §4.6 enumerates admin capabilities.
#
# All three endpoints accept the shared portal user's session and
# differentiate authorization on `vecrm_employee_role` per
# VECRM-LOCK-PORTAL-USER-ROLES.
#
# ============================================================


def _require_admin_session() -> None:
    """Throw frappe.PermissionError if the current session is not Admin.

    Reads role from `frappe.session.data.vecrm_employee_role`, NOT from
    `frappe.get_roles()` — per VECRM-LOCK-PORTAL-USER-ROLES, the shared
    Frappe user always has the same Frappe roles, so role-differentiated
    authorization MUST consult session.data.

    No-session is treated as not-admin (throws). Missing role field is
    treated as not-admin (throws). Anything other than the literal string
    "Admin" is not-admin (throws).
    """
    role = (frappe.session.data or {}).get("vecrm_employee_role")
    if role != "Admin":
        frappe.throw(
            frappe._("This action requires Admin role."),
            frappe.PermissionError,
        )


def _require_voucher_submitter_self_or_admin(submitter: str) -> None:
    """Throw frappe.PermissionError if non-admin caller targets someone else.

    Used by voucher-creation endpoints to prevent privilege escalation
    where a non-admin user files a voucher claiming a different employee
    as submitter. Admin can file on behalf of anyone (Sub-A behavior
    preserved).

    Reads role + self-phone from frappe.session.data per
    VECRM-LOCK-PORTAL-USER-ROLES, mirroring _require_admin_session.

    Args:
      submitter: VECRM Employee phone-id from the API caller.

    Raises:
      frappe.PermissionError:
        - Session has no employee linkage (defensive deny).
        - Caller is not Admin AND submitter != session's own phone.
    """
    session_data = frappe.session.data or {}
    role = session_data.get("vecrm_employee_role")

    if role == "Admin":
        return  # admin can file on behalf of anyone

    self_phone = session_data.get("vecrm_employee_phone")
    if not self_phone:
        frappe.throw(
            frappe._(
                "Session does not include employee linkage. Please log in again."
            ),
            frappe.PermissionError,
        )

    if submitter != self_phone:
        frappe.throw(
            frappe._(
                "You can only file vouchers for yourself ({self}), not for "
                "{other}. Ask an admin to file on behalf if needed."
            ).format(self=self_phone, other=submitter),
            frappe.PermissionError,
        )


def _require_voucher_approver_self_or_admin(approver_employee: str) -> None:
    """Throw frappe.PermissionError if non-admin caller approves/rejects as someone else.

    Sibling of _require_voucher_submitter_self_or_admin. Identity from
    session.data (the human), NOT frappe.session.user (the BFF service
    account in portal context - S31 LEAD-OWNER-ATTRIBUTION). Admin may act
    on behalf of any eligible approver; non-admin may only act AS themselves.
    """
    session_data = frappe.session.data or {}
    role = session_data.get("vecrm_employee_role")
    if role == "Admin":
        return
    self_phone = session_data.get("vecrm_employee_phone")
    if not self_phone:
        frappe.throw(
            frappe._("Session does not include employee linkage. Please log in again."),
            frappe.PermissionError,
        )
    if approver_employee != self_phone:
        frappe.throw(
            frappe._(
                "You can only approve or reject vouchers as yourself ({self}), "
                "not as {other}."
            ).format(self=self_phone, other=approver_employee),
            frappe.PermissionError,
        )


def _generate_temp_password() -> str:
    """Generate a cryptographically secure temp password.

    Returns ~11 chars of url-safe base64 (letters + digits + `-`/`_`).
    Example: 'Xj9-2bk3Fw1'.

    The byte count (8) yields ~11 base64 chars (ceil(8 * 4/3) = 11).
    Strength: 64 bits — adequate for a single-use temp credential the
    new employee will change after first login. (Permanent passwords
    have an 8-char minimum policy elsewhere; this 11-char output
    exceeds that.)
    """
    return secrets.token_urlsafe(8)


@frappe.whitelist()
def admin_list_employees(
    status: str = "",
    role: str = "",
    search: str = "",
) -> dict[str, Any]:
    """Admin-only: list all VECRM Employees with optional filters.

    Filters (all optional, combinable):
      status: "Active" | "Suspended" | "" (no filter)
      role: any of the 6 VecrmRole strings | "" (no filter)
      search: substring match against employee_name (case-insensitive)

    Returns:
      {"data": [
        {"name": <phone>, "employee_name": ..., "vecrm_phone": ...,
         "vecrm_email": ..., "role": ..., "vecrm_base_city": ...,
         "vecrm_account_status": ..., "reporting_approver": ...,
         "last_login_at": ..., "creation": ...},
        ...
      ]}

    The doc returned has the same shape as the VECRM Employee row but
    EXCLUDES auth credential fields (password_hash, pin_hash, etc.) —
    these are never sent to the portal.
    """
    _require_admin_session()

    filters: dict[str, Any] = {}
    if status:
        if status not in ("Active", "Suspended"):
            frappe.throw(
                frappe._("Invalid status filter '{0}'.").format(status),
                frappe.ValidationError,
            )
        filters["vecrm_account_status"] = status
    if role:
        valid_roles = (
            "Admin", "Sales Head", "HR",
            "Sales Rep", "Field Engineer", "Head of Engineers",
        )
        if role not in valid_roles:
            frappe.throw(
                frappe._("Invalid role filter '{0}'.").format(role),
                frappe.ValidationError,
            )
        filters["role"] = role
    if search:
        filters["employee_name"] = ["like", f"%{search}%"]

    rows = frappe.get_all(
        "VECRM Employee",
        filters=filters,
        fields=[
            "name",
            "employee_name",
            "vecrm_phone",
            "vecrm_email",
            "role",
            "vecrm_base_city",
            "vecrm_account_status",
            "reporting_approver",
            "last_login_at",
            "creation",
        ],
        order_by="employee_name asc",
        limit_page_length=200,
    )

    return {"data": rows}


@frappe.whitelist()
def admin_create_employee(
    employee_name: str = "",
    vecrm_phone: str = "",
    role: str = "",
    vecrm_base_city: str = "",
    vecrm_email: str = "",
    reporting_approver: str = "",
) -> dict[str, Any]:
    """Admin-only: create a new VECRM Employee with a generated temp password.

    The temp password is generated server-side (Option 3 per
    PD-S29-ADMIN-USER-MGMT recon) and returned ONCE in the response.
    Admin communicates it to the new employee via existing channels
    (WhatsApp / in-person). Cleartext is never persisted.

    Required: employee_name, vecrm_phone, role, vecrm_base_city.
    Optional: vecrm_email, reporting_approver.

    Returns:
      {"success": True,
       "name": <phone>,
       "employee_name": ...,
       "temp_password": "<one-time cleartext>"}

    Raises:
      PermissionError if session not Admin.
      ValidationError for: missing required fields, invalid role,
        invalid phone format, invalid base_city (not in Rate Card —
        controller throws), duplicate phone (unique constraint),
        duplicate email.
    """
    _require_admin_session()

    # Required-field shape narrowing (BFF should pre-validate, but
    # whitelist endpoints defend in depth).
    employee_name = (employee_name or "").strip()
    vecrm_phone = (vecrm_phone or "").strip()
    role = (role or "").strip()
    vecrm_base_city = (vecrm_base_city or "").strip()
    vecrm_email = (vecrm_email or "").strip()
    reporting_approver = (reporting_approver or "").strip()

    if not employee_name:
        frappe.throw(
            frappe._("Employee name is required."),
            frappe.ValidationError,
        )
    if not vecrm_phone:
        frappe.throw(
            frappe._("Phone is required."),
            frappe.ValidationError,
        )
    valid_roles = (
        "Admin", "Sales Head", "HR",
        "Sales Rep", "Field Engineer", "Head of Engineers",
    )
    if role not in valid_roles:
        frappe.throw(
            frappe._("Invalid role '{0}'.").format(role),
            frappe.ValidationError,
        )
    # Phone format defense-in-depth: enforce +91-XXXXXXXXXX shape.
    # Controller has set_only_once=1 + unique=1 but no format check;
    # without this, an admin could create an employee with malformed
    # phone (e.g. "9999999999" missing +91 prefix) which then breaks
    # the autoname PK + downstream voucher/session lookups.
    if not re.match(r"^\+91-\d{10}$", vecrm_phone):
        frappe.throw(
            frappe._("Phone must be in format +91-XXXXXXXXXX (10 digits after +91-)."),
            frappe.ValidationError,
        )
    if not vecrm_base_city:
        frappe.throw(
            frappe._("Base city is required."),
            frappe.ValidationError,
        )

    # Build the new doc. The controller's validate() runs on insert and
    # will throw on: base_city not in Rate Card, phone immutability
    # violation (n/a here — new doc). Uniqueness on phone + email is
    # enforced by the schema (unique=1).
    doc = frappe.get_doc({
        "doctype": "VECRM Employee",
        "employee_name": employee_name,
        "vecrm_phone": vecrm_phone,
        "role": role,
        "vecrm_base_city": vecrm_base_city,
        "vecrm_account_status": "Active",
    })
    if vecrm_email:
        doc.vecrm_email = vecrm_email
    if reporting_approver:
        doc.reporting_approver = reporting_approver

    doc.insert(ignore_permissions=True)

    # Generate + hash + store temp password using the S25-canonical
    # pattern (mirrors complete_password_reset).
    temp_password = _generate_temp_password()
    hashed = passlibctx.hash(temp_password)
    frappe.db.set_value(
        "VECRM Employee",
        doc.name,
        "password_hash",
        hashed,
        update_modified=False,
    )

    # Audit trail — record which admin created which employee.
    _audit_auth(
        "auth.admin.create_employee",
        employee=doc.name,
        path="admin",
        reason=None,
    )

    frappe.db.commit()

    return {
        "success": True,
        "name": doc.name,
        "employee_name": doc.employee_name,
        "temp_password": temp_password,
    }


@frappe.whitelist()
def admin_update_employee(
    employee: str = "",
    employee_name: str = "",
    role: str = "",
    vecrm_base_city: str = "",
    vecrm_email: str = "",
    reporting_approver: str = "",
    vecrm_account_status: str = "",
) -> dict[str, Any]:
    """Admin-only: update editable fields on an existing VECRM Employee.

    Phone (PK) is NOT editable per controller's _validate_phone_immutable.

    All non-employee args are optional; empty string means "do not change
    this field". Empty employee arg means error.

    Returns:
      {"success": True, "name": <phone>}

    Raises:
      PermissionError if session not Admin.
      ValidationError for: missing employee, invalid role, invalid status,
        invalid base_city (controller throws), invalid email format.
      DoesNotExistError if employee doesn't exist.
    """
    _require_admin_session()

    employee = (employee or "").strip()
    if not employee:
        frappe.throw(
            frappe._("Employee identifier (phone) is required."),
            frappe.ValidationError,
        )

    doc = frappe.get_doc("VECRM Employee", employee)

    # Apply only the fields the admin actually supplied.
    if employee_name:
        doc.employee_name = employee_name.strip()
    if role:
        valid_roles = (
            "Admin", "Sales Head", "HR",
            "Sales Rep", "Field Engineer", "Head of Engineers",
        )
        if role not in valid_roles:
            frappe.throw(
                frappe._("Invalid role '{0}'.").format(role),
                frappe.ValidationError,
            )
        doc.role = role
    if vecrm_base_city:
        doc.vecrm_base_city = vecrm_base_city.strip()
    if vecrm_email:
        doc.vecrm_email = vecrm_email.strip()
    if reporting_approver:
        doc.reporting_approver = reporting_approver.strip()
    if vecrm_account_status:
        if vecrm_account_status not in ("Active", "Suspended"):
            frappe.throw(
                frappe._("Invalid account status '{0}'.").format(vecrm_account_status),
                frappe.ValidationError,
            )
        doc.vecrm_account_status = vecrm_account_status

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "name": doc.name,
    }
# ============================================================================
# PD-S30-LEAD-FOLLOWUP Phase 2 — Touchpoint API
# ============================================================================

@frappe.whitelist()
def create_touchpoint(
    lead_name: str,
    touchpoint_type: str,
    touchpoint_date: str,
    summary: str = "",
) -> dict:
    """Create a VECRM Lead Touchpoint append-only audit record.

    PD-S30-LEAD-FOLLOWUP Phase 2. Per Q-LEAD-FOLLOWUP-PHASE-2-ADDENDUM:
      - Q-LFL-P2-2: BFF-layer auth via canReadLead (creator + Admin)
      - Q-LFL-P2-6: independent of next_followup_date (touchpoint logging
        does NOT clear or modify follow-up scheduling)
      - Q-LFL-P2-8: append-only, no delete endpoint
      - Q-LFL-P2-10: actor_employee Link to VECRM Employee, on_delete=Restrict
      - Terminal-state behavior (S34 dispatch decision): ALLOWED on leads in
        any status including Converted/Closed-Won/Closed-Lost. Post-close
        contact is valid audit history.

    Args:
      lead_name: VECRM Lead PK (e.g. 'VE/LEAD/00020/26-27')
      touchpoint_type: One of Call / Email / Meeting / Other
      touchpoint_date: ISO date string (YYYY-MM-DD)
      summary: Optional free-text summary (Small Text, ~140 chars)

    Returns:
      Dict with success flag + the new touchpoint's name (hash) + the
      lead's updated last_contact_date and touchpoint_count (virtual fields
      computed at read time).

    Raises:
      ValidationError on: invalid date, unknown touchpoint_type, lead not
        found, missing session vecrm_email, missing VECRM Employee for actor.
      SessionStopped on: missing vecrm_email in session data.

    Permission model: BFF-layer enforcement only, consistent with
    update_lead_followup (PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT P3 covers future
    backend-side defense-in-depth across all lead-write surfaces).
    """
    from frappe.utils import getdate

    # Validate touchpoint_type against enum (defense-in-depth beyond doctype Select)
    valid_types = ("Call", "Email", "Meeting", "Other")
    if touchpoint_type not in valid_types:
        frappe.throw(
            frappe._("Invalid touchpoint_type. Must be one of: {0}. Got: {1}").format(
                ", ".join(valid_types), touchpoint_type
            ),
            frappe.ValidationError,
        )

    # Validate date format
    try:
        parsed_date = getdate(touchpoint_date)
    except Exception:
        frappe.throw(
            frappe._("Invalid date format for touchpoint_date. Expected YYYY-MM-DD, got: {0}").format(touchpoint_date),
            frappe.ValidationError,
        )

    # Session identity (same pattern as update_lead_followup)
    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    # Resolve VECRM Employee for actor_employee. Session stash holds the
    # canonical mapping; we look up the Employee by vecrm_email.
    employee_name = frappe.db.get_value(
        "VECRM Employee",
        {"vecrm_email": vecrm_email},
        "name",
    )
    if not employee_name:
        frappe.throw(
            frappe._("No VECRM Employee found for session email {0}.").format(vecrm_email),
            frappe.ValidationError,
        )

    # Confirm lead exists (will raise DoesNotExistError if not — surfaces as 404)
    if not frappe.db.exists("VECRM Lead", lead_name):
        frappe.throw(
            frappe._("VECRM Lead {0} not found.").format(lead_name),
            frappe.DoesNotExistError,
        )

    # Create the touchpoint. Append-only by doctype permission (write=0 across
    # all roles), so this insert is the ONLY write operation on this doc.
    tp = frappe.get_doc({
        "doctype": "VECRM Lead Touchpoint",
        "lead": lead_name,
        "touchpoint_date": parsed_date,
        "touchpoint_type": touchpoint_type,
        "summary": (summary or "").strip(),
        "actor_employee": employee_name,
    })
    tp.insert(ignore_permissions=True)

    # Read-time virtual-field computation for the response (Q-LFL-P2-3 = (b)
    # virtual fields, read-time computed)
    last_contact_date, touchpoint_count = _compute_lead_touchpoint_stats(lead_name)

    return {
        "success": True,
        "name": tp.name,
        "lead": lead_name,
        "touchpoint_date": str(tp.touchpoint_date),
        "touchpoint_type": tp.touchpoint_type,
        "summary": tp.summary,
        "actor_employee": tp.actor_employee,
        "last_contact_date": str(last_contact_date) if last_contact_date else None,
        "touchpoint_count": touchpoint_count,
    }


@frappe.whitelist()
def list_touchpoints_for_lead(lead_name: str) -> dict:
    """List all touchpoints for a given VECRM Lead, newest first.

    PD-S30-LEAD-FOLLOWUP Phase 2. Read-only query — no pagination in Phase 2
    (defer until any single lead accumulates >50 touchpoints, see
    Q-LEAD-FOLLOWUP-PHASE-2-ADDENDUM "Open items for Phase 2 dispatch recon").

    Args:
      lead_name: VECRM Lead PK

    Returns:
      Dict with success flag + touchpoints array (each item: name, date, type,
      summary, actor_employee) + derived stats (last_contact_date, count).

    Raises:
      DoesNotExistError on: lead not found.
      SessionStopped on: missing vecrm_email.

    Permission model: BFF-layer enforcement (same as create_touchpoint).
    """
    # Session check
    vecrm_email = frappe.session.data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("VECRM session missing vecrm_email. Re-login required."),
            frappe.SessionStopped,
        )

    if not frappe.db.exists("VECRM Lead", lead_name):
        frappe.throw(
            frappe._("VECRM Lead {0} not found.").format(lead_name),
            frappe.DoesNotExistError,
        )

    # Pull touchpoints for this lead, newest first.
    # Note: order_by is on touchpoint_date DESC, then creation DESC as a
    # secondary tiebreaker (multiple touchpoints same date sorted by insertion order).
    rows = frappe.get_all(
        "VECRM Lead Touchpoint",
        filters={"lead": lead_name},
        fields=[
            "name",
            "touchpoint_date",
            "touchpoint_type",
            "summary",
            "actor_employee",
            "creation",
        ],
        order_by="touchpoint_date DESC, creation DESC",
        limit_page_length=0,  # no pagination in Phase 2
    )

    # Normalize date to ISO string for JSON serialization
    touchpoints = [
        {
            "name": r["name"],
            "touchpoint_date": str(r["touchpoint_date"]) if r["touchpoint_date"] else None,
            "touchpoint_type": r["touchpoint_type"],
            "summary": r["summary"],
            "actor_employee": r["actor_employee"],
            "creation": str(r["creation"]) if r["creation"] else None,
        }
        for r in rows
    ]

    last_contact_date, touchpoint_count = _compute_lead_touchpoint_stats(lead_name)

    return {
        "success": True,
        "lead": lead_name,
        "touchpoints": touchpoints,
        "last_contact_date": str(last_contact_date) if last_contact_date else None,
        "touchpoint_count": touchpoint_count,
    }


def _compute_lead_touchpoint_stats(lead_name: str) -> tuple:
    """Internal helper: derive (last_contact_date, touchpoint_count) for a lead.

    Q-LFL-P2-3 = (b): virtual fields, computed at read time. This helper is
    the single source of truth for derived stats; both create_touchpoint and
    list_touchpoints_for_lead call it so the response shape is consistent.

    Returns a (date | None, int) tuple. Date is None if no touchpoints exist.
    """
    result = frappe.db.sql(
        """SELECT MAX(touchpoint_date)
           FROM `tabVECRM Lead Touchpoint`
           WHERE lead = %s""",
        (lead_name,),
    )
    last = result[0][0] if result and result[0] else None

    count = frappe.db.count("VECRM Lead Touchpoint", filters={"lead": lead_name})

    return (last, count)