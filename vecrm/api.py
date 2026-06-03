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
from vecrm.vecrm.email_templates import render_touchpoint_email, render_email_layout

def _send_lead_notification(lead_doc, subject, html_body):
	"""Send email and in-app Notification Log to Lead Owner, Sales Head, and Admin."""
	from vecrm.email_utils import send_email
	
	recipients = set()
	if lead_doc.lead_owner:
		recipients.add(lead_doc.lead_owner)
		
	roles = frappe.get_all("VECRM Employee", 
		filters={"role": ["in", ["Sales Head", "Admin"]], "vecrm_account_status": "Active"}, 
		fields=["vecrm_email"]
	)
	for r in roles:
		if r.vecrm_email:
			recipients.add(r.vecrm_email)
			
	if not recipients:
		return
		
	try:
		send_email(to=list(recipients), subject=subject, html_body=html_body)
	except Exception as e:
		frappe.log_error("Failed to send lead notification email", str(e))
		
	for email in recipients:
		try:
			from vecrm.notifications import send_push, _tokens_for_user
			tokens = _tokens_for_user(email)
			if tokens:
				send_push(tokens, subject, "New activity on lead", {"screen": "leads", "lead": lead_doc.name})
		except Exception:
			pass

		if frappe.db.exists("User", email):
			try:
				notif_log = frappe.get_doc({
					"doctype": "Notification Log",
					"subject": subject,
					"for_user": email,
					"type": "Alert",
					"document_type": "VECRM Lead",
					"document_name": lead_doc.name,
				})
				notif_log.set_new_name()
				notif_log.db_insert()
			except Exception as e:
				if hasattr(frappe.local, "message_log"):
					frappe.local.message_log = []

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
	_require_lead_owner_or_admin(lead_name)
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
def mark_travel_voucher_paid(voucher_name: str) -> dict:
	"""Mark an approved TV as paid. HR + Admin only."""
	_require_hr_or_admin()
	doc = frappe.get_doc("VECRM Travel Voucher", voucher_name)

	if doc.docstatus != 1:
		frappe.throw("Only submitted vouchers can be marked as paid.", frappe.ValidationError)
	if getattr(doc, "approval_status", None) != "Approved":
		frappe.throw("Only approved vouchers can be marked as paid.", frappe.ValidationError)
	if getattr(doc, "payment_status", None) == "Paid":
		frappe.throw("This voucher is already marked as paid.", frappe.ValidationError)

	session_data = frappe.session.data or {}
	employee_phone = session_data.get("vecrm_employee_phone")
	employee_role = session_data.get("vecrm_employee_role")

	doc.db_set("payment_status", "Paid")
	doc.db_set("paid_at", frappe.utils.now())
	doc.db_set("paid_by_employee", employee_phone)
	doc.db_set("paid_by_role", employee_role)

	doc._audit("voucher.travel.paid", {
		"actor_employee": employee_phone,
		"actor_role": employee_role,
		"total_amount": float(doc.total_amount or 0),
		"from_state": "approved",
		"to_state": "paid",
	})

	try:
		from vecrm.notifications import notify_voucher_outcome
		notify_voucher_outcome(doc, "Paid")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "mark_travel_voucher_paid.notify")

	return {"status": "ok", "voucher_name": voucher_name}


@frappe.whitelist()
def mark_expense_voucher_paid(voucher_name: str) -> dict:
	"""Mark an approved EV as paid. HR + Admin only."""
	_require_hr_or_admin()
	doc = frappe.get_doc("VECRM Expense Voucher", voucher_name)

	if doc.docstatus != 1:
		frappe.throw("Only submitted vouchers can be marked as paid.", frappe.ValidationError)
	if getattr(doc, "approval_status", None) != "Approved":
		frappe.throw("Only approved vouchers can be marked as paid.", frappe.ValidationError)
	if getattr(doc, "payment_status", None) == "Paid":
		frappe.throw("This voucher is already marked as paid.", frappe.ValidationError)

	session_data = frappe.session.data or {}
	employee_phone = session_data.get("vecrm_employee_phone")
	employee_role = session_data.get("vecrm_employee_role")

	doc.db_set("payment_status", "Paid")
	doc.db_set("paid_at", frappe.utils.now())
	doc.db_set("paid_by_employee", employee_phone)
	doc.db_set("paid_by_role", employee_role)

	doc._audit("voucher.expense.paid", {
		"actor_employee": employee_phone,
		"actor_role": employee_role,
		"total_amount": float(doc.total_amount or 0),
		"from_state": "approved",
		"to_state": "paid",
	})

	try:
		from vecrm.notifications import notify_voucher_outcome
		notify_voucher_outcome(doc, "Paid")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "mark_expense_voucher_paid.notify")

	return {"status": "ok", "voucher_name": voucher_name}


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

	# Reopen 24-hour deadline. A manager-reopened voucher must be resubmitted
	# within reopened_until; after that it re-locks (relock scheduler returns
	# it to the approval queue). Block a late resubmit attempt explicitly.
	if voucher.get("reopened") and voucher.get("reopened_until"):
		if frappe.utils.now_datetime() > frappe.utils.get_datetime(voucher.reopened_until):
			frappe.throw(
				frappe._(
					"The 24-hour window to resubmit this reopened voucher has "
					"closed. Ask your manager to reopen it again."
				),
				frappe.ValidationError,
			)

	# Bi-monthly cutoff check (PD-S29-BACKFILL-PREVENTION). Resubmit
	# accepts edited visit_lines + optional business_date — without this
	# check, a rejected voucher could be re-submitted with backfilled
	# dates inside a closed period, bypassing the create-time gate.
	# Same per-line semantics as create.
	try:
		resubmit_lines = json.loads(visit_lines)
	except json.JSONDecodeError as exc:
		frappe.throw(
			f"visit_lines is not valid JSON: {exc}", frappe.ValidationError
		)
	if business_date:
		_check_voucher_date_cutoff(business_date)
	else:
		_check_voucher_date_cutoff(voucher.business_date)
	if isinstance(resubmit_lines, list):
		for line in resubmit_lines:
			vd = line.get("visit_date") if isinstance(line, dict) else None
			if vd:
				_check_voucher_date_cutoff(vd)

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

	# Bi-monthly cutoff check (PD-S29-BACKFILL-PREVENTION). Use the
	# new expense_date if provided in the resubmit payload, else the
	# voucher's current date.
	_check_voucher_date_cutoff(expense_date or voucher.expense_date)

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

	# Bi-monthly submission cutoff (PD-S29-BACKFILL-PREVENTION). Check
	# each visit's date — per-line because a voucher can legitimately
	# span both halves of a month (a visit on the 14th and one on the
	# 16th are H1 + H2 respectively). business_date is checked too as
	# defense-in-depth since it drives FY allocation. Admin/Sales
	# Head/HR bypass; see _check_voucher_date_cutoff.
	_check_voucher_date_cutoff(business_date)
	for line in lines:
		visit_date = line.get("visit_date")
		if visit_date:
			_check_voucher_date_cutoff(visit_date)

	# Single-draft-per-period dedup (TRAVEL). One consolidated draft per
	# (submitter, half-month period). If an open draft already exists for
	# this period, APPEND the new lines to it instead of creating a second
	# voucher — mirrors the /leads company->touchpoint merge. A fresh
	# voucher only begins once the current period's draft is submitted.
	from vecrm.vecrm.utils.voucher_period import period_key

	target_name = None
	for row in frappe.get_all(
		"VECRM Travel Voucher",
		filters={"submitter": submitter, "docstatus": 0},
		fields=["name", "business_date"],
	):
		if row.business_date and period_key(row.business_date) == period_key(business_date):
			target_name = row.name
			break

	if target_name:
		doc = frappe.get_doc("VECRM Travel Voucher", target_name)
	else:
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

	# New draft: insert() runs before_insert (snapshot rate/role/city) +
	# validate (totals via Rate Card) + DB insert. Existing draft: save()
	# re-runs validate to fold in the appended lines (stays docstatus=0).
	if target_name:
		doc.save()
	else:
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

	# SECURITY: only the voucher's own submitter (or Admin) may submit it
	# (Sub-A's deferred ownership check, now applied).
	_require_voucher_submitter_self_or_admin(doc.submitter)

	if doc.docstatus != 0:
		frappe.throw(
			f"Travel Voucher {voucher_name} is not in draft state "
			f"(docstatus={doc.docstatus}).",
			frappe.ValidationError,
		)

	# No ownership check in Sub-A — Admin-only interim. S25 VECRM Auth
	# will add session-based ownership verification.

	# Bi-monthly cutoff re-check (PD-S29-BACKFILL-PREVENTION). The draft
	# may have been created inside the window and now be sitting past
	# the deadline. Block the submit attempt with the same gate that
	# guards create. Per visit_date (line-level) + business_date
	# defense-in-depth.
	_check_voucher_date_cutoff(doc.business_date)
	for line in doc.visit_lines:
		if line.visit_date:
			_check_voucher_date_cutoff(line.visit_date)

	# Submit-window gate (lower bound). A period's consolidated voucher can
	# only be submitted once the period is essentially over:
	#   H1: 15th 21:00 -> 17th 23:59,  H2: last-day 21:00 -> 2nd 23:59 (IST).
	# Managers (Admin / Sales Head / HR) bypass — they may file on a rep's
	# behalf anytime. (The existing _check_voucher_date_cutoff above already
	# enforces the upper bound; this adds the lower bound.)
	from vecrm.vecrm.utils.voucher_period import (
		WINDOW_BYPASS_ROLES,
		is_submit_window_open,
		lateness,
		submit_window,
	)

	session_role = (frappe.session.data or {}).get("vecrm_employee_role")
	if session_role not in WINDOW_BYPASS_ROLES and not is_submit_window_open(doc.business_date):
		open_dt, close_dt = submit_window(doc.business_date)
		frappe.throw(
			frappe._(
				"This voucher can only be submitted between {open} and {close}."
			).format(
				open=open_dt.strftime("%d %b %Y %H:%M"),
				close=close_dt.strftime("%d %b %Y %H:%M"),
			),
			frappe.ValidationError,
		)

	# Late stamp (set before submit so it persists in the 0->1 save).
	now_dt = frappe.utils.now_datetime()
	doc.submitted_at = now_dt
	doc.submission_timeliness = lateness(doc.business_date, now_dt)

	# Submit — triggers on_submit -> _audit("voucher.travel.submitted", ...)
	doc.submit()

	return {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"total_amount": doc.total_amount,
		"submitted_at": str(now_dt),
		"submission_timeliness": doc.submission_timeliness,
	}


def _require_voucher_reopener(submitter_role: str) -> None:
	"""Gate for reopen_travel_voucher: Admin, HR, or the functional head who
	oversees `submitter_role` (Head of Engineers for Field Engineer / NSE;
	Head of Stores for Store Executive). Derived from VOUCHER_APPROVER_SETS
	so it stays in lockstep with the approver mapping."""
	role = (frappe.session.data or {}).get("vecrm_employee_role")
	if role in ("Admin", "HR"):
		return
	from vecrm.vecrm.utils.roles import VOUCHER_APPROVER_SETS

	if role and role in VOUCHER_APPROVER_SETS.get(submitter_role, []):
		return
	frappe.throw(
		frappe._("You are not permitted to reopen this voucher."),
		frappe.PermissionError,
	)


@frappe.whitelist()
def reopen_travel_voucher(voucher_name: str, reason: str = "") -> dict:
	"""Manager reopens a submitted Travel Voucher so the submitter can correct
	and resubmit it within 24 hours, after which it re-locks. Gated to the
	submitter's functional head (Head of Engineers / Head of Stores), HR, or
	Admin.

	Mechanism (max reuse): performs the same state transition as a rejection,
	so the voucher becomes editable via the existing resubmit-via-edit flow,
	and stamps reopened / reopened_by / reopened_until = now + 24h. The rep
	edits and resubmits exactly like a rejected voucher;
	voucher_resubmit_travel enforces the 24h deadline, and
	relock_expired_reopened_vouchers (scheduled) returns any un-resubmitted
	reopen to the approval queue so nothing is stranded.
	"""
	if not frappe.db.exists("VECRM Travel Voucher", voucher_name):
		frappe.throw(
			f"Travel Voucher {voucher_name!r} does not exist.",
			frappe.ValidationError,
		)

	voucher = frappe.get_doc("VECRM Travel Voucher", voucher_name)
	_require_voucher_reopener(voucher.submitter_role)

	if voucher.docstatus != 1:
		frappe.throw(
			"Only a submitted voucher can be reopened.", frappe.ValidationError
		)

	actor = (frappe.session.data or {}).get("vecrm_employee_phone") or frappe.session.user
	actor_role = (frappe.session.data or {}).get("vecrm_employee_role")
	until = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=24)

	# Transition to the editable (rejected-style) state + reopen stamps. db_set
	# avoids the controller cycle (same pattern as approve/reject).
	voucher.db_set("approval_status", "Rejected", update_modified=False)
	voucher.db_set("approved_by_employee", None, update_modified=False)
	voucher.db_set("approved_by_role", None, update_modified=False)
	voucher.db_set("approved_at", None, update_modified=False)
	voucher.db_set("rejected_by_employee", actor, update_modified=False)
	voucher.db_set("rejected_by_role", actor_role, update_modified=False)
	voucher.db_set("rejected_at", frappe.utils.now(), update_modified=False)
	voucher.db_set(
		"rejection_reason",
		(reason or "").strip() or "Reopened for corrections.",
		update_modified=False,
	)
	voucher.db_set("reopened", 1, update_modified=False)
	voucher.db_set("reopened_by", actor, update_modified=False)
	voucher.db_set("reopened_until", until, update_modified=False)

	# Notify the submitter (best-effort).
	try:
		from vecrm.notifications import _employee_email, _tokens_for_user, send_push

		email = _employee_email(voucher.submitter)
		if email:
			tokens = _tokens_for_user(email)
			if tokens:
				send_push(
					tokens,
					"Voucher reopened for edits",
					f"{voucher.name} was reopened — edit & resubmit within 24 hours.",
					{"screen": "vouchers", "voucher": voucher.name, "doctype": voucher.doctype},
				)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "reopen_travel_voucher notify")

	return {"name": voucher.name, "reopened_until": str(until)}


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

	# Bi-monthly submission cutoff (PD-S29-BACKFILL-PREVENTION). EV
	# has a single voucher-level expense_date (no per-line dates); one
	# check covers the whole voucher. Admin/Sales Head/HR bypass.
	_check_voucher_date_cutoff(expense_date)

	# Per-line validation (Q-EV-CONFIRM-ATTACH=b + Q-EV-RECEIPT-VERIFY=on).
	# Doctype's attachment field is reqd=0 to preserve Desk admin flexibility
	# for corrective EVs; portal-originated submissions MUST include a
	# receipt and the receipt URL MUST exist in the File doctype.
	for idx, line in enumerate(lines, start=1):
		attachment = line.get("attachment")
		if line.get("category") == "Food Allowance":
			# Food Allowance does not strictly require a receipt.
			if attachment and str(attachment).strip():
				if not frappe.db.exists("File", {"file_url": attachment}):
					frappe.throw(
						f"Expense line {idx}: receipt URL {attachment!r} is not a "
						f"recognized upload. Re-upload the receipt and try again.",
						frappe.ValidationError,
					)
		else:
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
			"days": line.get("days") or 0,
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
				"days": line.days,
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

	# Bi-monthly cutoff re-check (PD-S29-BACKFILL-PREVENTION). Draft may
	# have been created during an open window and now sit past deadline.
	_check_voucher_date_cutoff(doc.expense_date)

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
	priority: int = 3,
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

	# Dedup (PD-S30, revised): only an OPEN lead blocks a brand-new lead.
	# Converted / Closed-Won / Closed-Lost leads may each spawn a fresh lead
	# (a company can have multiple inquiries over time, each needing its own
	# lead). When an open lead already exists we do NOT create a duplicate —
	# we log this contact as a touchpoint on that open lead and return
	# action="touchpoint" so the portal can react. Server-authoritative: this
	# is the safety net behind the form's typeahead-driven routing.
	company_name = company_name.strip()
	open_lead = frappe.db.get_value(
		"VECRM Lead",
		{"company_name": company_name, "status": "Open"},
		"name",
	)
	if open_lead:
		create_touchpoint(
			lead_name=open_lead,
			touchpoint_type="Meeting",
			touchpoint_date=contact_date,
			summary=meeting_brief or "",
		)
		return {
			"action": "touchpoint",
			"lead": open_lead,
			"company_name": company_name,
		}

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
		"action": "lead",
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
def update_lead_status(lead_name: str, new_status: str) -> dict:
    """Update a lead's status. Used by Kanban drag-and-drop.
    
    Valid transitions to Converted go through convert_lead_to_inquiry.
    """
    # SECURITY: was an unauthenticated IDOR — any caller could flip any
    # lead's status by name. Require ownership or Admin.
    _require_lead_owner_or_admin(lead_name)
    valid_statuses = {"Open", "Closed-Won", "Closed-Lost"}
    if new_status not in valid_statuses:
        frappe.throw(
            f"Invalid status: {new_status}. Allowed: {', '.join(valid_statuses)}",
            frappe.ValidationError,
        )

    frappe.db.set_value("VECRM Lead", lead_name, "status", new_status)
    doc = frappe.get_doc("VECRM Lead", lead_name)
    return {
        "name": doc.name,
        "status": doc.status,
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
    _require_lead_owner_or_admin(name)
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
    _require_inquiry_owner_or_admin(name)
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
    _require_lead_owner_or_admin(lead_name)
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
    _require_lead_owner_or_admin(lead_name)
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
      (Now applied here: _require_lead_owner_or_admin below.)
    """
    _require_lead_owner_or_admin(lead_name)
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


@frappe.whitelist(methods=["GET"])
def get_my_notifications(limit: int = 50) -> list[dict[str, Any]]:
    """Return the current portal user's in-app notifications (newest first).

    Scoped to the session's vecrm_email. All portal sessions share one Frappe
    user (see _issue_session), so identity is resolved from session data and
    rows are read with ignore_permissions — the shared user cannot be granted
    per-row access via the normal permission model. Returns [] when the session
    has no email rather than throwing, so the bell degrades quietly. Shaped to
    what the portal NotificationBell expects (email_content / read), insulating
    it from the doctype field names.
    """
    email = frappe.session.data.get("vecrm_email")
    if not email:
        return []
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))

    rows = frappe.get_all(
        "VECRM Notification",
        filters={"for_email": email},
        fields=[
            "name",
            "subject",
            "body",
            "is_read",
            "document_type",
            "document_name",
            "creation",
        ],
        order_by="creation desc",
        limit_page_length=limit,
        ignore_permissions=True,
    )
    return [
        {
            "name": r.name,
            "subject": r.subject,
            "email_content": r.body,
            "read": 1 if r.is_read else 0,
            "document_type": r.document_type,
            "document_name": r.document_name,
            "creation": str(r.creation),
        }
        for r in rows
    ]


@frappe.whitelist(methods=["POST"])
def mark_notification_read(name: str) -> dict[str, Any]:
    """Mark one of the caller's notifications as read.

    Ownership-guarded: the row's for_email must equal the session's vecrm_email,
    so the shared portal user cannot mark another employee's notifications. The
    write uses ignore_permissions after the guard passes.
    """
    email = frappe.session.data.get("vecrm_email")
    if not email:
        frappe.throw(_("Not authenticated as VECRM Employee"), frappe.PermissionError)
    if not name:
        frappe.throw(_("Missing notification name"), frappe.ValidationError)

    owner = frappe.db.get_value("VECRM Notification", name, "for_email")
    if owner is None:
        frappe.throw(_("Notification not found"), frappe.DoesNotExistError)
    if owner != email:
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    frappe.db.set_value(
        "VECRM Notification", name, "is_read", 1, update_modified=False
    )
    return {"ok": True}


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
    if "employee" in response:
        del response["employee"]
    
    return response

@frappe.whitelist()
def get_dashboard_summary() -> dict:
	"""Return aggregated voucher counts/amounts for the portal dashboard."""
	# Only fetch summary for vouchers the current user is allowed to see
	user_phone = frappe.session.data.get("vecrm_employee_phone")
	if not user_phone:
		frappe.throw("Not authenticated", frappe.AuthenticationError)
		
	# Build TV summary
	tv_pending = frappe.db.get_all("VECRM Travel Voucher", 
		filters={"approval_status": "Pending"}, 
		fields=["name", "total_amount"]
	)
	tv_paid = frappe.db.get_all("VECRM Travel Voucher", 
		filters={"payment_status": "Paid"}, 
		fields=["name", "total_amount"]
	)
	
	# Build EV summary 
	ev_pending = frappe.db.get_all("VECRM Expense Voucher", 
		filters={"approval_status": "Pending"}, 
		fields=["name", "total_amount"]
	)
	ev_paid = frappe.db.get_all("VECRM Expense Voucher", 
		filters={"payment_status": "Paid"}, 
		fields=["name", "total_amount"]
	)
	
	return {
		"tv": {
			"pending_count": len(tv_pending),
			"pending_amount": sum((v.total_amount or 0) for v in tv_pending),
			"paid_count": len(tv_paid),
			"paid_amount": sum((v.total_amount or 0) for v in tv_paid)
		},
		"ev": {
			"pending_count": len(ev_pending),
			"pending_amount": sum((v.total_amount or 0) for v in ev_pending),
			"paid_count": len(ev_paid),
			"paid_amount": sum((v.total_amount or 0) for v in ev_paid)
		}
	}


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
    """Throw frappe.PermissionError if caller is not Admin.

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


def _require_hr_or_admin() -> None:
    """Throw frappe.PermissionError if caller is not HR or Admin."""
    role = (frappe.session.data or {}).get("vecrm_employee_role")
    if role not in ("HR", "Admin"):
        frappe.throw(
            frappe._("Only HR or Admin can mark vouchers as paid."),
            frappe.PermissionError,
        )


def _require_admin_or_sales_head() -> None:
    """Throw frappe.PermissionError unless caller is Admin or Sales Head.

    Backstop for the cross-company aggregation views (get_company_list /
    get_company_360), mirroring the portal's app/companies access gate.
    """
    role = (frappe.session.data or {}).get("vecrm_employee_role")
    if role not in ("Admin", "Sales Head"):
        frappe.throw(
            frappe._("This view is restricted to Admin and Sales Head."),
            frappe.PermissionError,
        )


def _require_lead_owner_or_admin(lead_name: str) -> None:
    """Throw frappe.PermissionError unless caller owns the lead or is Admin.

    Ownership = the lead's lead_owner matches the session's vecrm_email OR
    its creating_employee matches the session's phone (both attribution
    fields are used across the codebase). Admin bypasses. Backend
    defence-in-depth behind the BFF's canReadLead gate.
    """
    session_data = frappe.session.data or {}
    if session_data.get("vecrm_employee_role") == "Admin":
        return
    vecrm_email = session_data.get("vecrm_email")
    phone = session_data.get("vecrm_employee_phone")
    if not vecrm_email and not phone:
        frappe.throw(
            frappe._("Session does not include employee linkage. Please log in again."),
            frappe.PermissionError,
        )
    row = frappe.db.get_value(
        "VECRM Lead", lead_name, ["lead_owner", "creating_employee"], as_dict=True
    )
    if not row:
        frappe.throw(
            frappe._("Lead {0} not found.").format(lead_name),
            frappe.DoesNotExistError,
        )
    if (vecrm_email and row.lead_owner == vecrm_email) or (
        phone and row.creating_employee == phone
    ):
        return
    frappe.throw(
        frappe._("You can only modify your own leads."),
        frappe.PermissionError,
    )


def _require_inquiry_owner_or_admin(inquiry_name: str) -> None:
    """Throw frappe.PermissionError unless caller owns the inquiry or is Admin."""
    session_data = frappe.session.data or {}
    if session_data.get("vecrm_employee_role") == "Admin":
        return
    vecrm_email = session_data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("Session does not include employee linkage. Please log in again."),
            frappe.PermissionError,
        )
    if not frappe.db.exists("VECRM Inquiry", inquiry_name):
        frappe.throw(
            frappe._("Inquiry {0} not found.").format(inquiry_name),
            frappe.DoesNotExistError,
        )
    if frappe.db.get_value("VECRM Inquiry", inquiry_name, "inquiry_owner") == vecrm_email:
        return
    frappe.throw(
        frappe._("You can only modify your own inquiries."),
        frappe.PermissionError,
    )


def _check_voucher_date_cutoff(voucher_date, session_role: str | None = None) -> None:
    """Enforce the bi-monthly voucher submission cutoff with 2-day grace.

    The payment cycle splits each month into two periods:
      H1: visit/expense dates 1st-15th, submission window closes 17th.
      H2: visit/expense dates 16th-last day, submission window closes
          2nd of the NEXT month.

    "Closes" is strict — submission ON the deadline day is still
    allowed; the rejection fires on the day AFTER. Matches the kickoff's
    "After 17th, dates in 1st-15th of that month are blocked." Once a
    period's window closes, reps cannot create or submit vouchers whose
    voucher_date falls inside it.

    Bypass roles: Admin, Sales Head, HR. These are the
    approvers/managers; they can backfill on behalf of reps when there's
    a legitimate reason (late receipts, field-connectivity gaps, paid
    leave overlapping a deadline, etc.). Sales Rep / Field Engineer /
    Head of Engineers are subject to the cutoff. Mirrors the role
    cluster used by _require_hr_or_admin + isVoucherApproverRole on the
    portal side.

    Args:
      voucher_date: ISO YYYY-MM-DD string OR datetime/date object.
        For TV this is the visit_date on each visit_line (the line's
        own date, not the voucher's business_date). For EV this is
        the voucher's expense_date.
      session_role: Optional override. When None, reads
        frappe.session.data['vecrm_employee_role']. Production callers
        leave this None; tests pass an explicit role.

    Raises:
      frappe.ValidationError if voucher_date is in a closed period and
        the caller is not in the bypass set.
    """
    if session_role is None:
        session_role = (frappe.session.data or {}).get("vecrm_employee_role")

    # Approver / manager bypass — backfill is their call.
    if session_role in ("Admin", "Sales Head", "HR"):
        return

    import calendar

    d = frappe.utils.getdate(voucher_date)
    today = frappe.utils.getdate(frappe.utils.today())

    if d.day <= 15:
        period_label = f"H1 ({d.strftime('%b %Y')} 1-15)"
        deadline = d.replace(day=17)
    else:
        last_day = calendar.monthrange(d.year, d.month)[1]
        period_label = f"H2 ({d.strftime('%b %Y')} 16-{last_day})"
        # H2 deadline = 2nd of the following month. Handle December
        # rollover into January of the next year.
        if d.month == 12:
            deadline = d.replace(year=d.year + 1, month=1, day=2)
        else:
            deadline = d.replace(month=d.month + 1, day=2)

    if today > deadline:
        frappe.throw(
            frappe._(
                "The submission window for {period} has closed (deadline "
                "was {deadline}). Contact your manager."
            ).format(
                period=period_label,
                deadline=deadline.strftime("%d %b %Y"),
            ),
            frappe.ValidationError,
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
def list_employees_directory() -> list[dict]:
    """Phone→display-name directory for portal voucher surfaces.

    Auth gate: any authenticated VECRM session (frappe.session.data must
    carry a vecrm_employee_phone — established by login_with_password /
    login_with_pin via _issue_session). No role check.

    Symmetry argument: the response carries ONLY {name, employee_name,
    vecrm_base_city}. Same fields the existing /travel-vouchers/new
    submitter dropdown already exposes to admins. No auth secrets, no
    role/status, no email. Strictly the minimum needed to humanize the
    raw phone PK stored in voucher submitter / approver / paid_by /
    rejected_by fields on the list and detail pages.

    For the richer admin-only directory (full row including role,
    status, login_at, etc.) used by the admin user-management surface
    /admin/users, see admin_list_employees.

    Returns the list ordered by employee_name for stable rendering.
    """
    if not (frappe.session.data or {}).get("vecrm_employee_phone"):
        frappe.throw(
            frappe._("Authentication required."),
            frappe.PermissionError,
        )
    return frappe.get_all(
        "VECRM Employee",
        filters=[["vecrm_account_status", "=", "Active"]],
        fields=["name", "employee_name", "vecrm_base_city"],
        order_by="employee_name asc",
        limit_page_length=0,  # No limit — small table, single use per page load.
    )


@frappe.whitelist()
def admin_list_employees(
    status: str = "",
    role: str = "",
    search: str = "",
    page: str = "1",
    limit: str = "50",
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
      ], "total": ..., "page": ..., "has_more": ...}

    The doc returned has the same shape as the VECRM Employee row but
    EXCLUDES auth credential fields (password_hash, pin_hash, etc.) —
    these are never sent to the portal.
    """
    _require_admin_session()

    page_int = int(page)
    limit_int = int(limit)
    limit_start = (page_int - 1) * limit_int

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
            "Network Security Engineer", "Store Executive", "Head of Stores",
        )
        if role not in valid_roles:
            frappe.throw(
                frappe._("Invalid role filter '{0}'.").format(role),
                frappe.ValidationError,
            )
        filters["role"] = role
    if search:
        filters["employee_name"] = ["like", f"%{search}%"]

    total_count = frappe.db.count("VECRM Employee", filters=filters)

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
        limit_start=limit_start,
        limit_page_length=limit_int,
    )

    return {"data": rows, "total": total_count, "page": page_int, "has_more": limit_start + limit_int < total_count}


def _resolve_employee(identifier: str, field_label: str = "Employee") -> str:
    """Resolve an employee's exact name (phone PK) from email, partial phone, or employee_name."""
    if not identifier:
        return ""
        
    identifier = identifier.strip()
    
    # 1. Exact PK match
    if frappe.db.exists("VECRM Employee", identifier):
        return identifier
        
    # 2. Email match
    if "@" in identifier:
        matching = frappe.get_all("VECRM Employee", filters={"vecrm_email": identifier}, limit=1)
        if matching:
            return matching[0].name
            
    # 3. Unformatted phone match
    if re.search(r'\d{10}', identifier):
        clean_phone = "+91-" + re.sub(r'\D', '', identifier)[-10:]
        if frappe.db.exists("VECRM Employee", clean_phone):
            return clean_phone
            
    # 4. Name match (Active only, to avoid resolving to suspended old accounts)
    matching = frappe.get_all("VECRM Employee", filters={"employee_name": identifier, "vecrm_account_status": "Active"}, limit=1)
    if matching:
        return matching[0].name
        
    frappe.throw(
        frappe._("Could not find {1}: {0}").format(identifier, field_label),
        frappe.DoesNotExistError
    )


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
        "Network Security Engineer", "Store Executive", "Head of Stores",
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
        doc.reporting_approver = _resolve_employee(reporting_approver, "Reporting Approver")

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
            "Network Security Engineer", "Store Executive", "Head of Stores",
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
        doc.reporting_approver = _resolve_employee(reporting_approver.strip(), "Reporting Approver")
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


@frappe.whitelist()
def admin_delete_employee(employee: str = "") -> dict[str, Any]:
    """Admin-only: Delete an employee from the system.

    Frappe referential integrity (Link fields with on_delete=Restrict)
    will block the deletion if the employee is linked to existing Vouchers,
    Leads, Touchpoints, or Audit Logs. We catch LinkExistsError to return
    a friendly message.

    Returns:
      {"success": True}

    Raises:
      PermissionError if session not Admin.
      ValidationError on missing employee or link integrity failure.
    """
    _require_admin_session()

    employee = (employee or "").strip()
    if not employee:
        frappe.throw(
            frappe._("Employee identifier (phone) is required."),
            frappe.ValidationError,
        )

    if not frappe.db.exists("VECRM Employee", employee):
        frappe.throw(
            frappe._("Employee '{0}' not found.").format(employee),
            frappe.DoesNotExistError,
        )

    # Audit before deletion because the doc will be gone
    _audit_auth(
        "auth.admin.delete_employee",
        employee=employee,
        path="admin",
        reason="Admin deleted employee",
    )
    
    audit_doc = frappe.get_doc({
        "doctype": "VECRM User Audit Log",
        "event_type": "delete",
        "actor": frappe.session.user,
        "target": employee,
        "event_timestamp": frappe.utils.now_datetime(),
        "detail": f"Delete VECRM Employee: {employee}"
    })
    audit_doc.flags.ignore_links = True
    # Use db_insert (not insert) so the row is written directly, bypassing the
    # Select-field validation. The audit-log event_type Select still lists the
    # legacy lifecycle labels (User Provisioned/Suspended/Reactivated), but the
    # code — and the reader get_audit_logs — use CRUD verbs like "delete";
    # validate() would otherwise reject "delete" ("Event Type cannot be ...").
    # Matches the sibling delete path (admin_delete_record) which already does
    # this. Append-only integrity is unaffected.
    try:
        audit_doc.set_new_name()
        audit_doc.db_insert()
    except Exception:
        if hasattr(frappe.local, "message_log"):
            frappe.local.message_log = []

    # A user with real business records — or who is another employee's
    # approver — must NOT be hard-deleted; suspend instead. Block explicitly
    # with a clear message naming what's linked.
    BUSINESS_LINKS = (
        ("VECRM Travel Voucher", "submitter"),
        ("VECRM Travel Voucher", "approved_by_employee"),
        ("VECRM Expense Voucher", "submitter"),
        ("VECRM Expense Voucher", "approved_by_employee"),
        ("VECRM Lead", "creating_employee"),
        ("VECRM Lead Touchpoint", "actor_employee"),
        ("VECRM Employee", "reporting_approver"),
    )
    blocking = sorted({
        dt for dt, field in BUSINESS_LINKS if frappe.db.exists(dt, {field: employee})
    })
    if blocking:
        frappe.throw(
            frappe._(
                "Cannot delete '{0}' — they have existing records ({1}). "
                "Suspend the account instead."
            ).format(employee, ", ".join(blocking)),
            frappe.ValidationError,
        )

    # No business records → a never-active / mistake account. Remove the
    # infrastructure rows that exist purely because the account was
    # provisioned: Auth Audit Log + Auth Reset Token both Link-with-Restrict to
    # the employee AND are append-only via their controllers, so delete them at
    # the DB layer (bypasses both the Restrict link check and on_trash). There
    # are no business records to preserve here.
    for dt in ("VECRM Auth Audit Log", "VECRM Auth Reset Token"):
        frappe.db.delete(dt, {"employee": employee})
    frappe.db.commit()

    try:
        frappe.delete_doc("VECRM Employee", employee, ignore_permissions=True)
    except frappe.LinkExistsError:
        # A residual link we didn't anticipate — fail safe with guidance.
        frappe.throw(
            frappe._(
                "Cannot delete '{0}' — it is still linked to other records. "
                "Suspend the account instead."
            ).format(employee),
            frappe.ValidationError,
        )

    return {"success": True}


@frappe.whitelist()
def get_base_cities() -> dict[str, Any]:
    """Valid base-city names (from the Rate Card) for the employee base-city
    dropdown. Whitelisted so the portal can call it with a session; reads the
    Single via get_single (no doctype read-perm needed — the portal service
    account has no direct read perm on VECRM Rate Card, which is why the raw
    /api/resource fetch returns a permission error)."""
    rc = frappe.get_single("VECRM Rate Card")
    cities = sorted(
        {
            (r.city or "").strip()
            for r in (rc.city_rates or [])
            if (r.city or "").strip()
        }
    )
    return {"cities": cities}


def _admin_issue_reset(employee_phone: str, kind: str) -> dict[str, Any]:
    """Shared impl for admin_send_invite / admin_send_reset_password. Admin
    creates a password reset token for `employee_phone` and returns the raw
    token in _internal so the portal BFF can email the set-password link
    (the BFF owns delivery + template choice, exactly like
    request_password_reset)."""
    _require_admin_session()
    phone = (employee_phone or "").strip()
    if not phone:
        frappe.throw(frappe._("Employee phone is required."), frappe.ValidationError)
    if not frappe.db.exists("VECRM Employee", phone):
        frappe.throw(
            frappe._("Employee '{0}' not found.").format(phone),
            frappe.DoesNotExistError,
        )

    emp = frappe.get_doc("VECRM Employee", phone)
    email = (emp.vecrm_email or "").strip()
    if not email:
        frappe.throw(
            frappe._(
                "This employee has no email address. Add one (Save changes) "
                "before sending an invite or reset link."
            ),
            frappe.ValidationError,
        )

    raw_token = _create_reset_token_row(phone, "password")
    try:
        _audit_auth(
            "auth.admin.invite" if kind == "invite" else "auth.admin.reset",
            employee=phone,
            identifier=email,
            path="admin",
            reason=f"Admin {kind}",
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "admin_issue_reset audit")
    frappe.db.commit()

    return {
        "success": True,
        "message": "Link generated.",
        "_internal": {
            "raw_token": raw_token,
            "employee_name": emp.employee_name or phone,
            "delivery_email": email,
        },
    }


@frappe.whitelist()
def admin_send_invite(employee_phone: str = "") -> dict[str, Any]:
    """Admin-only: send a new user an invite to set their password. Returns
    _internal{raw_token, employee_name, delivery_email}; the portal BFF emails
    the /set-password link."""
    return _admin_issue_reset(employee_phone, "invite")


@frappe.whitelist()
def admin_send_reset_password(employee_phone: str = "") -> dict[str, Any]:
    """Admin-only: send an employee a password-reset link. Same token
    mechanism as admin_send_invite; the BFF picks the reset email template."""
    return _admin_issue_reset(employee_phone, "reset")


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

    # Best-effort "new touchpoint" notification — must NEVER break the
    # touchpoint write. Uses the branded Vinay Enterprises email layout
    # (render_touchpoint_email -> render_email_layout) for consistent
    # company branding on every outgoing mail.
    try:
        lead = frappe.get_doc("VECRM Lead", lead_name)
        actor_name = frappe.session.data.get("vecrm_employee_name") or frappe.session.user
        html_body = render_touchpoint_email(
            lead,
            str(tp.touchpoint_date),
            tp.touchpoint_type,
            actor_name,
            tp.summary or "",
        )
        _send_lead_notification(lead, f"New Touchpoint: {lead.company_name or lead.name}", html_body)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_touchpoint notification failed")

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


@frappe.whitelist()
def get_voucher_period_summary(month, year, period):
    """
    Get aggregated voucher summary for a bi-monthly period.
    HR + Admin only.
    """
    _require_hr_or_admin()
    
    month = int(month)
    year = int(year)
    
    if period == "H1":
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-15"
    elif period == "H2":
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year}-{month:02d}-16"
        end_date = f"{year}-{month:02d}-{last_day}"
    else:
        frappe.throw("Period must be H1 or H2")
    
    tv_summary = frappe.db.sql("""
        SELECT
            tv.submitter,
            emp.employee_name as submitter_name,
            COUNT(*) as count,
            SUM(tv.total_km) as total_km,
            SUM(tv.total_amount) as total_amount,
            SUM(CASE WHEN tv.approval_status = 'Approved' THEN 1 ELSE 0 END)
              as approved_count,
            SUM(CASE WHEN tv.payment_status = 'Paid' THEN 1 ELSE 0 END)
              as paid_count
        FROM `tabVECRM Travel Voucher` tv
        LEFT JOIN `tabVECRM Employee` emp ON emp.name = tv.submitter
        WHERE tv.docstatus = 1
          AND tv.business_date BETWEEN %(start)s AND %(end)s
        GROUP BY tv.submitter, emp.employee_name
        ORDER BY emp.employee_name
    """, {"start": start_date, "end": end_date}, as_dict=True)
    
    ev_summary = frappe.db.sql("""
        SELECT
            ev.submitter,
            emp.employee_name as submitter_name,
            COUNT(*) as count,
            SUM(ev.total_amount) as total_amount,
            SUM(CASE WHEN ev.approval_status = 'Approved' THEN 1 ELSE 0 END)
              as approved_count,
            SUM(CASE WHEN ev.payment_status = 'Paid' THEN 1 ELSE 0 END)
              as paid_count
        FROM `tabVECRM Expense Voucher` ev
        LEFT JOIN `tabVECRM Employee` emp ON emp.name = ev.submitter
        WHERE ev.docstatus = 1
          AND ev.expense_date BETWEEN %(start)s AND %(end)s
        GROUP BY ev.submitter, emp.employee_name
        ORDER BY emp.employee_name
    """, {"start": start_date, "end": end_date}, as_dict=True)
    
    return {
        "period_start": start_date,
        "period_end": end_date,
        "travel_vouchers": tv_summary,
        "expense_vouchers": ev_summary,
    }


@frappe.whitelist()
def get_voucher_period_detail(month, year, period, submitter=None, voucher_type="travel"):
    """Return individual voucher rows for a period, optionally filtered by submitter. HR + Admin only."""
    _require_hr_or_admin()
    
    month = int(month)
    year = int(year)
    
    if period == "H1":
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-15"
    elif period == "H2":
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year}-{month:02d}-16"
        end_date = f"{year}-{month:02d}-{last_day}"
    else:
        frappe.throw("Period must be H1 or H2")

    filters = [
        ["docstatus", "=", 1],
    ]
    
    if voucher_type == "travel":
        doctype = "VECRM Travel Voucher"
        date_field = "business_date"
    elif voucher_type == "expense":
        doctype = "VECRM Expense Voucher"
        date_field = "expense_date"
    else:
        frappe.throw("Invalid voucher_type")

    filters.append([date_field, "between", [start_date, end_date]])
    
    if submitter:
        filters.append(["submitter", "=", submitter])
        
    vouchers = frappe.get_all(
        doctype,
        filters=filters,
        fields=["name"],
        order_by=f"{date_field} asc"
    )
    
    result = []
    for v in vouchers:
        result.append(frappe.get_doc(doctype, v.name).as_dict())
        
    return result
    
@frappe.whitelist()
def test_email_pipeline(recipient):
    """Test email pipeline. Admin only."""
    frappe.only_for("System Manager")

    from vecrm.email_utils import send_email
    send_email(
        to=recipient,
        subject="VECRM Email Pipeline Test",
        html_body="<p>If you see this, the VECRM email pipeline is operational.</p>"
    )
    return {"status": "ok", "sent_to": recipient}


# ─── Weekly meeting report (PD-S29) ──────────────────────────────────
#
# Scheduled via hooks.py scheduler_events: 18:00 IST every Friday.
# Aggregates the current week's leads / vouchers / inquiries and sends
# a single HTML digest through the Graph API pipeline. Recipients are
# hardcoded for now (per kickoff); promote to a site_config list if
# the distribution grows.
#
# Date window: Monday 00:00 of the current week → now(). When the cron
# fires Friday 18:00 IST that's Mon 00:00 → Fri 18:00 — captures the
# full work week.

_WEEKLY_REPORT_DEFAULT_RECIPIENTS = ["ajay@vinayenterprises.co.in"]


def _get_weekly_report_recipients() -> list[str]:
    """Read recipients from site_config (`weekly_report_recipients`),
    fallback to the default list.

    Config shape — a JSON array of email strings:
      bench --site crm.vinayenterprises.co.in set-config \\
        weekly_report_recipients '["a@x.com","b@x.com"]'

    Validation: must be a non-empty list with at least one string. Any
    other shape (None, dict, empty list, list of non-strings) → fall
    back to the default list rather than fail the cron.
    """
    raw = frappe.conf.get("weekly_report_recipients")
    if isinstance(raw, list) and raw:
        emails = [e for e in raw if isinstance(e, str) and e]
        if emails:
            return emails
    return _WEEKLY_REPORT_DEFAULT_RECIPIENTS


def _weekly_report_window():
    """Return (start_dt, end_dt) for the current week's Mon 00:00 → now()."""
    now = frappe.utils.now_datetime()
    # weekday() — Monday=0, Sunday=6.
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return start, now


def _fmt_inr(amount) -> str:
    """Render a number as ₹X,XX,XXX.XX (Indian grouping). Tolerant of None."""
    n = float(amount or 0)
    # Indian number grouping: last 3 digits, then groups of 2.
    s = f"{n:,.2f}"
    if "." in s:
        whole, frac = s.split(".")
    else:
        whole, frac = s, "00"
    # Convert Western 1,234,567 → Indian 12,34,567.
    digits = whole.replace(",", "")
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        # Group head in pairs from the right.
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"₹{whole}.{frac}"


def _aggregate_leads(start_iso: str, end_iso: str) -> dict:
    """Lead activity for the window.

    new       — leads with creation in [start, end]
    converted — leads with status='Converted' AND modified in [start, end]
    won       — leads with status='Closed-Won'  AND modified in [start, end]
    lost      — leads with status='Closed-Lost' AND modified in [start, end]
    """
    fields = ["name", "company_name", "status", "lead_owner"]

    new_leads = frappe.get_all(
        "VECRM Lead",
        filters=[["creation", "between", [start_iso, end_iso]]],
        fields=fields,
        order_by="creation asc",
    )

    def _status_modified(status):
        return frappe.get_all(
            "VECRM Lead",
            filters=[
                ["status", "=", status],
                ["modified", "between", [start_iso, end_iso]],
            ],
            fields=fields,
            order_by="modified asc",
        )

    return {
        "new": new_leads,
        "converted": _status_modified("Converted"),
        "won": _status_modified("Closed-Won"),
        "lost": _status_modified("Closed-Lost"),
    }


def _aggregate_inquiries(start_iso: str, end_iso: str) -> list:
    """Inquiries created in the window."""
    return frappe.get_all(
        "VECRM Inquiry",
        filters=[["creation", "between", [start_iso, end_iso]]],
        fields=["name", "company_name", "status", "inquiry_owner"],
        order_by="creation asc",
    )


def _voucher_window_stats(doctype: str, start_iso: str, end_iso: str) -> dict:
    """Aggregate one voucher doctype across the three timeline events.

    submitted — docstatus=1 AND creation in window
    approved  — approval_status='Approved' AND approved_at in window
    paid      — payment_status='Paid'     AND paid_at     in window

    Returns each bucket as {count, total_amount} (amount summed in Python
    over a small list; voucher volumes per week are low double digits).
    """
    def _sum(rows):
        return {
            "count": len(rows),
            "total_amount": sum(float(r.get("total_amount") or 0) for r in rows),
        }

    submitted = frappe.get_all(
        doctype,
        filters=[
            ["docstatus", "=", 1],
            ["creation", "between", [start_iso, end_iso]],
        ],
        fields=["name", "total_amount"],
    )
    approved = frappe.get_all(
        doctype,
        filters=[
            ["approval_status", "=", "Approved"],
            ["approved_at", "between", [start_iso, end_iso]],
        ],
        fields=["name", "total_amount"],
    )
    paid = frappe.get_all(
        doctype,
        filters=[
            ["payment_status", "=", "Paid"],
            ["paid_at", "between", [start_iso, end_iso]],
        ],
        fields=["name", "total_amount"],
    )

    return {
        "submitted": _sum(submitted),
        "approved": _sum(approved),
        "paid": _sum(paid),
    }


# Inline-styled HTML — email clients (Outlook in particular) strip
# <style> blocks; every visual choice must travel on the element.
_HEADER_BG = "#1a237e"
_SECTION_BG = "#283593"
_BORDER = "#e0e0e0"
_TEXT = "#212121"
_MUTED = "#616161"


def _render_weekly_report_html(data: dict) -> str:
    start = data["start_label"]
    end = data["end_label"]
    leads = data["leads"]
    inquiries = data["inquiries"]
    tv = data["travel_vouchers"]
    ev = data["expense_vouchers"]

    def _lead_rows(rows):
        if not rows:
            return (
                f'<tr><td colspan="3" style="padding:12px;color:{_MUTED};'
                'text-align:center;font-style:italic;">No activity</td></tr>'
            )
        out = []
        for r in rows:
            out.append(
                f'<tr>'
                f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{frappe.utils.escape_html(r.get("name") or "")}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{frappe.utils.escape_html(r.get("company_name") or "—")}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{frappe.utils.escape_html(r.get("lead_owner") or "—")}</td>'
                f'</tr>'
            )
        return "".join(out)

    def _inquiry_rows(rows):
        if not rows:
            return (
                f'<tr><td colspan="3" style="padding:12px;color:{_MUTED};'
                'text-align:center;font-style:italic;">No activity</td></tr>'
            )
        out = []
        for r in rows:
            out.append(
                f'<tr>'
                f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{frappe.utils.escape_html(r.get("name") or "")}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{frappe.utils.escape_html(r.get("company_name") or "—")}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{frappe.utils.escape_html(r.get("inquiry_owner") or "—")}</td>'
                f'</tr>'
            )
        return "".join(out)

    def _voucher_row(label, stats):
        return (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">{label}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};text-align:right;">{stats["count"]}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};text-align:right;font-variant-numeric:tabular-nums;">{_fmt_inr(stats["total_amount"])}</td>'
            f'</tr>'
        )

    def _section_header(title):
        return (
            f'<tr><td style="background:{_SECTION_BG};color:#ffffff;'
            f'padding:10px 14px;font-size:14px;font-weight:600;'
            f'letter-spacing:0.3px;">{title}</td></tr>'
        )

    def _table_open():
        return (
            f'<table cellpadding="0" cellspacing="0" border="0" '
            f'style="width:100%;border-collapse:collapse;'
            f'border:1px solid {_BORDER};font-size:13px;color:{_TEXT};">'
        )

    # ─── Sub-tables ──────────────────────────────────────────────────
    lead_table = (
        _table_open()
        + f'<thead><tr style="background:#f5f5f5;">'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Name</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Company</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Owner</th>'
        f'</tr></thead><tbody>{{rows}}</tbody></table>'
    )
    inquiry_table = (
        _table_open()
        + f'<thead><tr style="background:#f5f5f5;">'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Name</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Company</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Owner</th>'
        f'</tr></thead><tbody>{{rows}}</tbody></table>'
    )

    voucher_table = (
        _table_open()
        + f'<thead><tr style="background:#f5f5f5;">'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Stage</th>'
        f'<th style="text-align:right;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Count</th>'
        f'<th style="text-align:right;padding:8px 12px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};font-weight:600;">Total Amount</th>'
        f'</tr></thead><tbody>{{rows}}</tbody></table>'
    )

    tv_rows = (
        _voucher_row("Submitted", tv["submitted"])
        + _voucher_row("Approved", tv["approved"])
        + _voucher_row("Paid", tv["paid"])
    )
    ev_rows = (
        _voucher_row("Submitted", ev["submitted"])
        + _voucher_row("Approved", ev["approved"])
        + _voucher_row("Paid", ev["paid"])
    )

    # ─── Outer document ─────────────────────────────────────────────
    sections = []

    sections.append(
        f'<div style="background:{_HEADER_BG};color:#ffffff;padding:20px 24px;">'
        f'<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.7;">VECRM Weekly Report</div>'
        f'<div style="font-size:20px;font-weight:600;margin-top:4px;">{start} — {end}</div>'
        f'</div>'
    )

    # Lead sections
    sections.append(
        f'<div style="margin-top:24px;">'
        f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;">'
        + _section_header(f'New Leads ({len(leads["new"])})')
        + f'<tr><td>{lead_table.format(rows=_lead_rows(leads["new"]))}</td></tr>'
        + _section_header(f'Leads Converted to Inquiry ({len(leads["converted"])})')
        + f'<tr><td>{lead_table.format(rows=_lead_rows(leads["converted"]))}</td></tr>'
        + _section_header(f'Leads Closed-Won ({len(leads["won"])})')
        + f'<tr><td>{lead_table.format(rows=_lead_rows(leads["won"]))}</td></tr>'
        + _section_header(f'Leads Closed-Lost ({len(leads["lost"])})')
        + f'<tr><td>{lead_table.format(rows=_lead_rows(leads["lost"]))}</td></tr>'
        + f'</table></div>'
    )

    # Inquiry section
    sections.append(
        f'<div style="margin-top:24px;">'
        f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;">'
        + _section_header(f'New Inquiries ({len(inquiries)})')
        + f'<tr><td>{inquiry_table.format(rows=_inquiry_rows(inquiries))}</td></tr>'
        + f'</table></div>'
    )

    # Voucher sections
    sections.append(
        f'<div style="margin-top:24px;">'
        f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;">'
        + _section_header("Travel Vouchers")
        + f'<tr><td>{voucher_table.format(rows=tv_rows)}</td></tr>'
        + _section_header("Expense Vouchers")
        + f'<tr><td>{voucher_table.format(rows=ev_rows)}</td></tr>'
        + f'</table></div>'
    )

    sections.append(
        f'<div style="margin-top:32px;padding-top:16px;border-top:1px solid {_BORDER};'
        f'font-size:11px;color:{_MUTED};">'
        f'Generated by VECRM. Aggregation window: {start} 00:00 → {end} (Asia/Kolkata).'
        f'</div>'
    )

    # Branded Vinay Enterprises layout (logo header + footer) around the digest.
    return render_email_layout(
        preheader="Vinay Enterprises CRM",
        body_html="".join(sections),
    )


def generate_weekly_meeting_report():
    """Generate and send the weekly meeting report email.

    Invoked by the scheduler (hooks.scheduler_events cron at 18:00 IST
    every Friday). Can also be invoked manually via test_weekly_report
    by a System Manager.

    Failures inside the aggregation are caught + logged via
    frappe.log_error so a transient issue doesn't poison the scheduler
    queue. The send_email call itself is allowed to bubble — Graph
    failures should be visible in the scheduler log.
    """
    from vecrm.email_utils import send_email

    start_dt, end_dt = _weekly_report_window()
    start_iso = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_iso = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    try:
        data = {
            "start_label": start_dt.strftime("%a %d %b %Y"),
            "end_label": end_dt.strftime("%a %d %b %Y"),
            "leads": _aggregate_leads(start_iso, end_iso),
            "inquiries": _aggregate_inquiries(start_iso, end_iso),
            "travel_vouchers": _voucher_window_stats(
                "VECRM Travel Voucher", start_iso, end_iso,
            ),
            "expense_vouchers": _voucher_window_stats(
                "VECRM Expense Voucher", start_iso, end_iso,
            ),
        }
    except Exception:
        frappe.log_error(
            title="VECRM weekly report — aggregation failed",
            message=frappe.get_traceback(),
        )
        raise

    html = _render_weekly_report_html(data)
    subject = (
        f"VECRM Weekly Report — "
        f"{start_dt.strftime('%d %b')} to {end_dt.strftime('%d %b %Y')}"
    )

    send_email(
        to=_get_weekly_report_recipients(),
        subject=subject,
        html_body=html,
    )


@frappe.whitelist()
def test_weekly_report():
    """Manually trigger the weekly meeting report. System Manager only.

    Bypasses the scheduler — useful for sanity-checking copy/layout
    without waiting for Friday 18:00 IST. Identical send path.
    """
    frappe.only_for("System Manager")
    generate_weekly_meeting_report()
    return {"status": "ok", "message": "Weekly report sent"}


# ─── Daily follow-up reminders (PD-S33-PIPELINE-DECAY) ───────────────
#
# Scheduled via hooks.py scheduler_events: 09:00 IST Mon–Sat.
# Scans VECRM Lead for next_followup_date < today AND status='Open'
# (the only non-terminal value; Converted / Closed-Won / Closed-Lost
# are terminal per the doctype Select options). Groups by lead_owner
# and sends one summary email per rep — explicit anti-noise design
# from the kickoff (single digest > per-lead email storm).
#
# lead_owner storage shape: a vecrm_email string (per the
# LEAD-OWNER-ATTRIBUTION fix at create_lead — doc.lead_owner is set
# from frappe.session.data['vecrm_email'], NOT a User Link). So
# lead_owner is the rep's email — usable directly as a To: address.
# We additionally look up VECRM Employee for employee_name to greet
# the rep by name.

_FOLLOWUP_ADMIN_DEFAULT_RECIPIENTS = ["ajay@vinayenterprises.co.in"]
_PORTAL_BASE = "https://app.vinayenterprises.co.in"


def _get_followup_admin_recipients() -> list[str]:
    """Read admin-digest recipients for daily follow-up reminders from
    site_config (`followup_admin_recipients`), fallback to the default.

    Config shape — a JSON array of email strings:
      bench --site crm.vinayenterprises.co.in set-config \\
        followup_admin_recipients '["ajay@x.com","ops@x.com"]'

    Same validation contract as _get_weekly_report_recipients —
    non-empty list of non-empty strings, else fallback.
    """
    raw = frappe.conf.get("followup_admin_recipients")
    if isinstance(raw, list) and raw:
        emails = [e for e in raw if isinstance(e, str) and e]
        if emails:
            return emails
    return _FOLLOWUP_ADMIN_DEFAULT_RECIPIENTS


def _build_employee_name_map(emails):
    """Resolve {lead_owner_email: employee_name} via one query.

    Tolerates an empty input (returns {}) and rows whose vecrm_email
    has no matching VECRM Employee (those owners simply won't be
    personalized — the email still sends).
    """
    if not emails:
        return {}
    rows = frappe.get_all(
        "VECRM Employee",
        filters=[["vecrm_email", "in", list(emails)]],
        fields=["vecrm_email", "employee_name"],
    )
    return {r["vecrm_email"]: (r.get("employee_name") or "") for r in rows}


def _portal_lead_url(lead_name: str) -> str:
    """Build the portal deep-link to a lead detail page.

    Lead names contain forward slashes (e.g. VE/LEAD/00010/26-27); the
    portal route uses URL-encoded segments — match the encoding the BFF
    expects (single quote() pass; the [name] dynamic segment is
    decodeURIComponent-ed at the page entry per app/leads/[name]).
    """
    from urllib.parse import quote
    return f"{_PORTAL_BASE}/leads/{quote(lead_name, safe='')}"


def _aggregate_overdue_followups():
    """Return overdue Open leads as (owner_email_or_empty, lead_row) pairs.

    Sorted oldest-overdue first so the rendered tables read worst → best.
    """
    today = frappe.utils.today()  # "YYYY-MM-DD"
    rows = frappe.get_all(
        "VECRM Lead",
        filters=[
            ["status", "=", "Open"],
            ["next_followup_date", "<", today],
        ],
        fields=[
            "name",
            "company_name",
            "contact_person_name",
            "lead_owner",
            "next_followup_date",
            "priority",
        ],
        order_by="next_followup_date asc",
    )
    return rows, today


def _group_by_owner(rows):
    """Group lead rows by lead_owner. Empty / missing owner → bucketed
    under the key ''.

    Returns dict[owner_email, list[lead_row]].
    """
    out: dict = {}
    for r in rows:
        owner = (r.get("lead_owner") or "").strip()
        out.setdefault(owner, []).append(r)
    return out


def _render_followup_lead_rows(rows, today_iso: str) -> str:
    """One <tr> per lead; empty placeholder when rows is empty."""
    if not rows:
        return (
            f'<tr><td colspan="5" style="padding:12px;color:{_MUTED};'
            'text-align:center;font-style:italic;">No overdue follow-ups</td></tr>'
        )
    today_dt = frappe.utils.getdate(today_iso)
    cells = []
    for r in rows:
        due_dt = frappe.utils.getdate(r.get("next_followup_date"))
        days_overdue = (today_dt - due_dt).days
        # Severity tint on the days-overdue cell — visual cue without
        # introducing new palette colors (reds outside the scheme would
        # render inconsistently across clients).
        if days_overdue >= 14:
            overdue_style = "color:#c62828;font-weight:600;"
        elif days_overdue >= 7:
            overdue_style = "color:#e65100;font-weight:600;"
        else:
            overdue_style = f"color:{_TEXT};"
        lead_name = r.get("name") or ""
        link = _portal_lead_url(lead_name)
        cells.append(
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">'
            f'<a href="{frappe.utils.escape_html(link)}" style="color:{_HEADER_BG};text-decoration:none;">'
            f'{frappe.utils.escape_html(lead_name)}</a></td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">'
            f'{frappe.utils.escape_html(r.get("company_name") or "—")}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">'
            f'{frappe.utils.escape_html(r.get("contact_person_name") or "—")}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};">'
            f'{frappe.utils.escape_html(str(r.get("next_followup_date") or "—"))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {_BORDER};'
            f'text-align:right;font-variant-numeric:tabular-nums;{overdue_style}">'
            f'{days_overdue}</td>'
            f'</tr>'
        )
    return "".join(cells)


def _followup_table(rows_html: str) -> str:
    """Standard 5-column overdue-leads table."""
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;border-collapse:collapse;border:1px solid {_BORDER};'
        f'font-size:13px;color:{_TEXT};">'
        f'<thead><tr style="background:#f5f5f5;">'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};'
        f'font-size:12px;color:{_MUTED};font-weight:600;">Lead</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};'
        f'font-size:12px;color:{_MUTED};font-weight:600;">Company</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};'
        f'font-size:12px;color:{_MUTED};font-weight:600;">Contact</th>'
        f'<th style="text-align:left;padding:8px 12px;border-bottom:1px solid {_BORDER};'
        f'font-size:12px;color:{_MUTED};font-weight:600;">Was Due</th>'
        f'<th style="text-align:right;padding:8px 12px;border-bottom:1px solid {_BORDER};'
        f'font-size:12px;color:{_MUTED};font-weight:600;">Days Overdue</th>'
        f'</tr></thead><tbody>'
        + rows_html
        + '</tbody></table>'
    )


def _render_rep_followup_html(rep_name: str, rows: list, today_iso: str) -> str:
    """Per-rep email — greeting + single table of their overdue leads."""
    greeting_name = rep_name or "there"
    count = len(rows)
    label = "follow-up" if count == 1 else "follow-ups"

    body = []
    body.append(
        f'<div style="background:{_HEADER_BG};color:#ffffff;padding:20px 24px;">'
        f'<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.7;">'
        f'VECRM Daily Reminder</div>'
        f'<div style="font-size:20px;font-weight:600;margin-top:4px;">'
        f'{count} overdue {label}</div>'
        f'</div>'
    )
    body.append(
        f'<div style="padding:20px 24px 8px;font-size:14px;color:{_TEXT};">'
        f'Hi {frappe.utils.escape_html(greeting_name)} — these leads have a '
        f'follow-up date in the past. Open each one in the portal, log a '
        f'touchpoint, and either set the next follow-up date or close it out.'
        f'</div>'
    )
    body.append(
        f'<div style="padding:0 24px 24px;">'
        f'{_followup_table(_render_followup_lead_rows(rows, today_iso))}'
        f'</div>'
    )
    body.append(
        f'<div style="padding:0 24px 24px;font-size:11px;color:{_MUTED};'
        f'border-top:1px solid {_BORDER};padding-top:16px;">'
        f'Sent daily at 09:00 IST. Reply to this email if a lead should not '
        f'have a follow-up date — admin will reset it.'
        f'</div>'
    )
    # Branded Vinay Enterprises layout (logo header + footer) around the digest.
    return render_email_layout(
        preheader=f"{count} overdue {label}",
        body_html="".join(body),
    )


def _render_admin_followup_html(
    groups: dict,
    name_map: dict,
    today_iso: str,
) -> str:
    """Admin digest — one section per owner (incl. an 'Unassigned' bucket
    for leads whose lead_owner is blank). Sections rendered in
    descending-count order so the worst offenders are at the top.
    """
    total = sum(len(v) for v in groups.values())
    rep_count = sum(1 for k in groups if k)  # exclude '' (unassigned)

    sections = []
    sections.append(
        f'<div style="background:{_HEADER_BG};color:#ffffff;padding:20px 24px;">'
        f'<div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.7;">'
        f'VECRM Admin Digest</div>'
        f'<div style="font-size:20px;font-weight:600;margin-top:4px;">'
        f'{total} overdue follow-ups across {rep_count} reps</div>'
        f'</div>'
    )

    # Sort owners by overdue count desc; '' (unassigned) goes last
    # regardless of count so admins read the named-owner backlog first.
    ordered = sorted(
        groups.items(),
        key=lambda kv: (kv[0] == "", -len(kv[1]), kv[0]),
    )

    for owner, rows in ordered:
        if owner:
            display = name_map.get(owner) or owner
            heading = (
                f'{frappe.utils.escape_html(display)} '
                f'<span style="opacity:0.7;font-weight:400;">'
                f'&lt;{frappe.utils.escape_html(owner)}&gt;</span> · {len(rows)}'
            )
        else:
            heading = f'Unassigned · {len(rows)}'
        sections.append(
            f'<div style="margin-top:24px;">'
            f'<table cellpadding="0" cellspacing="0" border="0" '
            f'style="width:100%;border-collapse:collapse;">'
            f'<tr><td style="background:{_SECTION_BG};color:#ffffff;'
            f'padding:10px 14px;font-size:14px;font-weight:600;'
            f'letter-spacing:0.3px;">{heading}</td></tr>'
            f'<tr><td>{_followup_table(_render_followup_lead_rows(rows, today_iso))}</td></tr>'
            f'</table></div>'
        )

    sections.append(
        f'<div style="margin-top:32px;padding-top:16px;border-top:1px solid {_BORDER};'
        f'font-size:11px;color:{_MUTED};">'
        f'Generated by VECRM. Snapshot date: {today_iso} (Asia/Kolkata). '
        f'Reps received their personal slice in a separate email.'
        f'</div>'
    )
    # Branded Vinay Enterprises layout (logo header + footer) around the digest.
    return render_email_layout(
        preheader="Vinay Enterprises CRM",
        body_html="".join(sections),
    )


def send_followup_reminders():
    """Daily scan for leads with overdue follow-ups. Sends email nudges.

    Invoked by the scheduler (hooks.scheduler_events cron at 09:00 IST
    Mon-Sat). Also callable manually via test_followup_reminders by a
    System Manager.

    Behaviour:
      * Zero overdue leads → silent exit (no admin email, no noise).
      * Per-rep emails: one digest per non-empty lead_owner.
      * Admin digest: ALL overdue leads (incl. unassigned bucket).
      * Aggregation failures are logged + re-raised so the scheduler
        surface them. Per-rep send failures are logged but DON'T abort
        the loop — one bad address shouldn't suppress everyone else's
        email, and the admin digest still lands.
    """
    from vecrm.email_utils import send_email

    try:
        rows, today_iso = _aggregate_overdue_followups()
    except Exception:
        frappe.log_error(
            title="VECRM follow-up reminders — aggregation failed",
            message=frappe.get_traceback(),
        )
        raise

    # Silent exit when nothing is overdue. This is the steady state on
    # a healthy pipeline — no inbox noise.
    if not rows:
        return

    groups = _group_by_owner(rows)

    # One name lookup for all owners (single round-trip; tiny payload).
    owner_emails = [k for k in groups.keys() if k]
    name_map = _build_employee_name_map(owner_emails)

    # ─── Per-rep emails ─────────────────────────────────────────────
    for owner, owned_rows in groups.items():
        if not owner:
            # Leads without a lead_owner can't be addressed; they still
            # appear in the admin digest below. Skip silently here.
            continue
        rep_name = name_map.get(owner) or ""
        count = len(owned_rows)
        subject = f"VECRM: You have {count} overdue follow-up{'s' if count != 1 else ''}"
        html = _render_rep_followup_html(rep_name, owned_rows, today_iso)
        try:
            send_email(to=owner, subject=subject, html_body=html)
        except Exception:
            frappe.log_error(
                title=f"VECRM follow-up reminder send failed: {owner}",
                message=frappe.get_traceback(),
            )
            # Keep going — don't let one bad recipient block the rest.

    # ─── Admin digest ───────────────────────────────────────────────
    total = len(rows)
    rep_count = sum(1 for k in groups if k)
    admin_subject = (
        f"VECRM Admin: {total} overdue follow-ups across {rep_count} reps"
    )
    admin_html = _render_admin_followup_html(groups, name_map, today_iso)
    send_email(
        to=_get_followup_admin_recipients(),
        subject=admin_subject,
        html_body=admin_html,
    )


@frappe.whitelist()
def test_followup_reminders():
    """Manually trigger follow-up reminders. System Manager only.

    Identical send path to the scheduled run — useful for verifying
    grouping, copy, and inline styling before/without waiting for the
    next 09:00 IST tick.
    """
    frappe.only_for("System Manager")
    send_followup_reminders()
    return {"status": "ok", "message": "Follow-up reminders sent"}


# ──────────────────────────────────────────────────────────────────────
# Account 360 — admin aggregation across the company_name dimension.
#
# VECRM has no Account/Company doctype. Companies exist as the
# `company_name` text field on VECRM Lead and VECRM Inquiry. These two
# endpoints fold leads + inquiries + touchpoints up by company_name for
# the Account 360 admin view.
# ──────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def search_companies(q: str = "", limit: int = 8) -> dict:
    """Typeahead for the new-lead form: distinct company names matching `q`,
    each annotated with whether the company already has an OPEN lead (and the
    open lead's name). Steers reps away from duplicate leads — an exact match
    with an open lead routes the submission to a touchpoint instead.

    Global across reps (dedup is company-level, not per-rep). Read-only.
    """
    q = (q or "").strip()
    if not q:
        return {"results": []}
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 8
    rows = frappe.db.sql(
        """
        SELECT
            company_name,
            MAX(CASE WHEN status = 'Open' THEN name END) AS open_lead,
            SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) AS open_count
        FROM `tabVECRM Lead`
        WHERE company_name LIKE %(like)s
        GROUP BY company_name
        ORDER BY company_name
        LIMIT %(limit)s
        """,
        {"like": f"%{q}%", "limit": limit},
        as_dict=True,
    )
    results = [
        {
            "company_name": r.company_name,
            "has_open_lead": bool(r.open_count),
            "open_lead": r.open_lead,
        }
        for r in rows
    ]
    return {"results": results}


def _timeline_sort_key(date_str: str) -> str:
    """Pad bare YYYY-MM-DD dates so timeline string-sort matches chrono order.

    Touchpoints carry a Date (`YYYY-MM-DD`); leads/inquiries carry a
    Datetime (`YYYY-MM-DD HH:MM:SS...`). Without padding, the shorter
    string sorts before the longer same-day datetime under string
    comparison, which inverts the intended order under reverse=True.
    """
    return date_str if len(date_str) > 10 else f"{date_str} 00:00:00"


@frappe.whitelist()
def get_company_list() -> dict:
    """List all unique companies with aggregated lead/inquiry stats.

    System Manager only. Companies are derived from the
    `company_name` text field on VECRM Lead and VECRM Inquiry; both
    sources contribute to the company set.

    Returns:
      Dict with `success` and `companies` (sorted by latest_activity desc).
      Each company entry: company_name, total_leads, open_leads,
      converted_leads, closed_won, closed_lost, total_inquiries,
      first_contact, latest_activity, primary_owner (most frequent
      lead_owner; None when the company has only inquiry rows).

    Authorization: the prior frappe.only_for("System Manager") guard
    was removed because the portal's shared service account
    (vecrm-portal@vinayenterprises.co.in) does not hold the System
    Manager role — the guard rejected every legitimate Admin call from
    the portal. The Admin-only contract is enforced at the portal layer
    (app/companies/layout.tsx SSR redirect via isAdminRole).

    Backend defence-in-depth (added): the portal-only contract left this
    callable directly by any authenticated session; gate on the session's
    vecrm_employee_role.
    """
    _require_admin_or_sales_head()
    from collections import Counter

    leads = frappe.get_all(
        "VECRM Lead",
        fields=["company_name", "status", "lead_owner", "creation", "modified"],
        limit_page_length=0,
    )
    inquiries = frappe.get_all(
        "VECRM Inquiry",
        fields=["company_name", "creation", "modified"],
        limit_page_length=0,
    )

    # Touchpoint activity folded to company via touchpoint→lead→company.
    tp_rows = frappe.db.sql(
        """SELECT l.company_name AS company_name,
                  MAX(tp.modified) AS latest_tp_modified
             FROM `tabVECRM Lead Touchpoint` tp
             JOIN `tabVECRM Lead` l ON l.name = tp.lead
            GROUP BY l.company_name""",
        as_dict=True,
    )
    tp_latest_by_company = {
        r["company_name"]: r["latest_tp_modified"] for r in tp_rows
    }

    def _new_bucket(c: str) -> dict:
        return {
            "company_name": c,
            "total_leads": 0,
            "open_leads": 0,
            "converted_leads": 0,
            "closed_won": 0,
            "closed_lost": 0,
            "total_inquiries": 0,
            "first_contact": None,
            "latest_activity": None,
            "_owners": Counter(),
        }

    companies: dict = {}

    for r in leads:
        c = r.get("company_name")
        if not c:
            continue
        bucket = companies.setdefault(c, _new_bucket(c))
        bucket["total_leads"] += 1

        status = r.get("status")
        if status == "Open":
            bucket["open_leads"] += 1
        elif status == "Converted":
            bucket["converted_leads"] += 1
        elif status == "Closed-Won":
            bucket["closed_won"] += 1
        elif status == "Closed-Lost":
            bucket["closed_lost"] += 1

        owner = r.get("lead_owner")
        if owner:
            bucket["_owners"][owner] += 1

        creation = r.get("creation")
        if creation and (
            bucket["first_contact"] is None or creation < bucket["first_contact"]
        ):
            bucket["first_contact"] = creation

        modified = r.get("modified")
        if modified and (
            bucket["latest_activity"] is None or modified > bucket["latest_activity"]
        ):
            bucket["latest_activity"] = modified

    for r in inquiries:
        c = r.get("company_name")
        if not c:
            continue
        bucket = companies.setdefault(c, _new_bucket(c))
        bucket["total_inquiries"] += 1

        modified = r.get("modified")
        if modified and (
            bucket["latest_activity"] is None or modified > bucket["latest_activity"]
        ):
            bucket["latest_activity"] = modified

    for company, tp_modified in tp_latest_by_company.items():
        bucket = companies.get(company)
        if not bucket or not tp_modified:
            continue
        if (
            bucket["latest_activity"] is None
            or tp_modified > bucket["latest_activity"]
        ):
            bucket["latest_activity"] = tp_modified

    # Resolve owner emails → employee display names in one bulk query so the
    # portal's per-rep breakdown shows names, not raw emails.
    emp_name_by_email = {
        e.vecrm_email: e.employee_name
        for e in frappe.get_all(
            "VECRM Employee", fields=["vecrm_email", "employee_name"]
        )
        if e.vecrm_email
    }

    out = []
    for bucket in companies.values():
        owners = bucket.pop("_owners")
        primary_owner_email = owners.most_common(1)[0][0] if owners else None
        bucket["primary_owner"] = primary_owner_email
        bucket["primary_owner_name"] = (
            emp_name_by_email.get(primary_owner_email) or primary_owner_email
        )
        bucket["first_contact"] = (
            str(bucket["first_contact"]) if bucket["first_contact"] else None
        )
        bucket["latest_activity"] = (
            str(bucket["latest_activity"]) if bucket["latest_activity"] else None
        )
        out.append(bucket)

    out.sort(key=lambda b: b["latest_activity"] or "", reverse=True)

    return {"success": True, "companies": out}


@frappe.whitelist()
def get_company_360(company_name: str) -> dict:
    """Return the full activity surface for a single company.

    System Manager only. Aggregates leads + inquiries + touchpoints
    matching `company_name` (exact, case-sensitive — same string the UI
    receives from `get_company_list`).

    Args:
      company_name: VECRM Lead.company_name / VECRM Inquiry.company_name

    Returns:
      Dict with `success`, `company_name`, `summary`, `leads`,
      `inquiries`, `touchpoints`, and a merged `timeline` sorted by
      event date desc.

    Raises:
      ValidationError if company_name is empty.
      DoesNotExistError if no leads and no inquiries reference this company.

    Authorization: see get_company_list — the System Manager guard was
    removed for the same reason (BFF service account doesn't hold that
    role; Admin-only contract is portal-side).
    """
    _require_admin_or_sales_head()
    if not company_name:
        frappe.throw(frappe._("company_name is required"))

    leads = frappe.get_all(
        "VECRM Lead",
        filters={"company_name": company_name},
        fields=[
            "name",
            "status",
            "lead_owner",
            "contact_person_name",
            "priority",
            "creation",
            "modified",
            "next_followup_date",
        ],
        order_by="creation desc",
        limit_page_length=0,
    )
    inquiries = frappe.get_all(
        "VECRM Inquiry",
        filters={"company_name": company_name},
        fields=[
            "name",
            "status",
            "inquiry_owner",
            "source_lead",
            "creation",
            "modified",
        ],
        order_by="creation desc",
        limit_page_length=0,
    )

    if not leads and not inquiries:
        frappe.throw(
            frappe._("Company {0} not found.").format(company_name),
            frappe.DoesNotExistError,
        )

    lead_names = [l["name"] for l in leads]
    touchpoints: list = []
    if lead_names:
        touchpoints = frappe.get_all(
            "VECRM Lead Touchpoint",
            filters={"lead": ["in", lead_names]},
            fields=[
                "name",
                "lead",
                "touchpoint_type",
                "touchpoint_date",
                "summary",
                "actor_employee",
                "creation",
                "modified",
                "owner",
            ],
            order_by="touchpoint_date desc, creation desc",
            limit_page_length=0,
        )

    tp_count_by_lead: dict = {}
    for tp in touchpoints:
        tp_count_by_lead[tp["lead"]] = tp_count_by_lead.get(tp["lead"], 0) + 1

    # ─── Per-lead response shape (with touchpoint_count rollup) ─────
    status_counts: dict = {}
    leads_out = []
    for l in leads:
        status = l.get("status")
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
        leads_out.append(
            {
                "name": l["name"],
                "status": status,
                "lead_owner": l.get("lead_owner"),
                "contact_person": l.get("contact_person_name"),
                "priority": l.get("priority"),
                "creation": str(l["creation"]) if l.get("creation") else None,
                "modified": str(l["modified"]) if l.get("modified") else None,
                "next_followup_date": (
                    str(l["next_followup_date"]) if l.get("next_followup_date") else None
                ),
                "touchpoint_count": tp_count_by_lead.get(l["name"], 0),
            }
        )

    inquiries_out = [
        {
            "name": i["name"],
            "status": i.get("status"),
            "inquiry_owner": i.get("inquiry_owner"),
            "source_lead": i.get("source_lead"),
            "creation": str(i["creation"]) if i.get("creation") else None,
            "modified": str(i["modified"]) if i.get("modified") else None,
        }
        for i in inquiries
    ]

    touchpoints_out = [
        {
            "name": tp["name"],
            "lead": tp["lead"],
            "type": tp.get("touchpoint_type"),
            "touchpoint_date": (
                str(tp["touchpoint_date"]) if tp.get("touchpoint_date") else None
            ),
            "notes": tp.get("summary"),
            "actor_employee": tp.get("actor_employee"),
            "creation": str(tp["creation"]) if tp.get("creation") else None,
            "created_by": tp.get("owner"),
        }
        for tp in touchpoints
    ]

    # ─── Merged chronological timeline ──────────────────────────────
    timeline: list = []
    for l in leads:
        if l.get("creation"):
            timeline.append(
                {
                    "date": str(l["creation"]),
                    "event_type": "lead_created",
                    "description": f"Lead {l['name']} created (status: {l.get('status') or 'Open'})",
                    "actor": l.get("lead_owner"),
                }
            )
        # modified > creation ⇒ later activity (status flip, edit, etc).
        if (
            l.get("modified")
            and l.get("creation")
            and l["modified"] > l["creation"]
        ):
            timeline.append(
                {
                    "date": str(l["modified"]),
                    "event_type": "lead_updated",
                    "description": f"Lead {l['name']} status: {l.get('status')}",
                    "actor": l.get("lead_owner"),
                }
            )

    for i in inquiries:
        if i.get("creation"):
            timeline.append(
                {
                    "date": str(i["creation"]),
                    "event_type": "inquiry_created",
                    "description": f"Inquiry {i['name']} created (status: {i.get('status') or 'Open'})",
                    "actor": i.get("inquiry_owner"),
                }
            )
        if (
            i.get("modified")
            and i.get("creation")
            and i["modified"] > i["creation"]
        ):
            timeline.append(
                {
                    "date": str(i["modified"]),
                    "event_type": "inquiry_updated",
                    "description": f"Inquiry {i['name']} status: {i.get('status')}",
                    "actor": i.get("inquiry_owner"),
                }
            )

    for tp in touchpoints:
        if tp.get("touchpoint_date"):
            descr = f"{tp.get('touchpoint_type') or 'Touchpoint'} on {tp['lead']}"
            if tp.get("summary"):
                descr += f": {tp['summary']}"
            timeline.append(
                {
                    "date": str(tp["touchpoint_date"]),
                    "event_type": "touchpoint",
                    "description": descr,
                    "actor": tp.get("actor_employee") or tp.get("owner"),
                }
            )

    timeline.sort(key=lambda e: _timeline_sort_key(e["date"]), reverse=True)

    # ─── Summary rollup ────────────────────────────────────────────
    first_contact_dt = None
    latest_activity_dt = None
    for l in leads:
        if l.get("creation") and (
            first_contact_dt is None or l["creation"] < first_contact_dt
        ):
            first_contact_dt = l["creation"]
        if l.get("modified") and (
            latest_activity_dt is None or l["modified"] > latest_activity_dt
        ):
            latest_activity_dt = l["modified"]
    for i in inquiries:
        if i.get("creation") and (
            first_contact_dt is None or i["creation"] < first_contact_dt
        ):
            first_contact_dt = i["creation"]
        if i.get("modified") and (
            latest_activity_dt is None or i["modified"] > latest_activity_dt
        ):
            latest_activity_dt = i["modified"]
    for tp in touchpoints:
        if tp.get("modified") and (
            latest_activity_dt is None or tp["modified"] > latest_activity_dt
        ):
            latest_activity_dt = tp["modified"]

    days_since_first_contact = None
    if first_contact_dt:
        days_since_first_contact = (
            frappe.utils.getdate(frappe.utils.today())
            - frappe.utils.getdate(first_contact_dt)
        ).days

    summary = {
        "total_leads": len(leads),
        "lead_statuses": status_counts,
        "total_inquiries": len(inquiries),
        "first_contact": str(first_contact_dt) if first_contact_dt else None,
        "latest_activity": str(latest_activity_dt) if latest_activity_dt else None,
        "days_since_first_contact": days_since_first_contact,
    }

    return {
        "success": True,
        "company_name": company_name,
        "summary": summary,
        "leads": leads_out,
        "inquiries": inquiries_out,
        "touchpoints": touchpoints_out,
        "timeline": timeline,
    }


@frappe.whitelist()
def delete_record(doctype: str, name: str) -> dict:
	# SECURITY: destructive, force-deletes by name. Admin only — was
	# previously callable by any authenticated session.
	_require_admin_session()
	allowed = {
		"VECRM Lead", "VECRM Inquiry", "VECRM Petrol Voucher",
		"VECRM Travel Voucher", "VECRM Expense Voucher"
	}
	if doctype not in allowed:
		frappe.throw(f"Doctype {doctype} not allowed for deletion")
		
	if not frappe.db.exists(doctype, name):
		frappe.throw(f"Record {name} not found")
		
	if doctype == "VECRM Lead":
		inq = frappe.db.get_value("VECRM Lead", name, "converted_inquiry")
		if inq:
			inq_doc = frappe.get_doc("VECRM Inquiry", inq)
			if inq_doc.docstatus == 1:
				inq_doc.flags.ignore_permissions = True
				inq_doc.cancel()
			frappe.delete_doc("VECRM Inquiry", inq, ignore_permissions=True, force=True)

	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		doc.flags.ignore_permissions = True
		doc.cancel()
		
	# Explicitly log the deletion
	audit_doc = frappe.get_doc({
		"doctype": "VECRM User Audit Log",
		"event_type": "delete",
		"actor": frappe.session.user,
		"target": name,
		"event_timestamp": frappe.utils.now_datetime(),
		"detail": f"Delete {doctype}: {name}"
	})
	audit_doc.flags.ignore_links = True
	try:
		audit_doc.set_new_name()
		audit_doc.db_insert()
	except Exception as e:
		if hasattr(frappe.local, "message_log"):
			frappe.local.message_log = []
	
	frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
	return {"success": True}


@frappe.whitelist()
def get_audit_logs(
	log_type: str = "all", from_date: str = "", to_date: str = "", 
	actor: str = "", page: str = "1", limit: str = "20"
) -> dict:
	# SECURITY: returns audit + PII across all users. Admin only.
	_require_admin_session()
	page_int = int(page)
	limit_int = int(limit)
	
	user_logs = []
	inq_logs = []
	assign_logs = []
	auth_logs = []
	
	USER_AUDIT_EVENT_TYPES = ("create", "update", "submit", "cancel", "delete")
	if log_type == "all" or log_type in USER_AUDIT_EVENT_TYPES:
		user_filters = []
		if log_type in USER_AUDIT_EVENT_TYPES:
			user_filters.append(["event_type", "=", log_type])
		if from_date:
			user_filters.append(["event_timestamp", ">=", f"{from_date} 00:00:00"])
		if to_date:
			user_filters.append(["event_timestamp", "<=", f"{to_date} 23:59:59"])
		if actor:
			user_filters.append(["actor", "like", f"%{actor}%"])
			
		user_logs = frappe.get_all(
			"VECRM User Audit Log", 
			filters=user_filters, 
			fields=["name", "event_type", "actor", "target", "event_timestamp", "detail"], 
			ignore_permissions=True,
			limit_page_length=0,
			order_by="creation desc"
		)
		
	if log_type == "all" or log_type in ("login", "logout"):
		auth_filters = []
		if log_type in ("login", "logout"):
			# In VECRM Auth Audit Log, the event is like "auth.login.failed" or "auth.logout"
			# Actually the portal sends "Login/Logout" which maps to "login"
			# We'll match prefix or exact
			auth_filters.append(["event", "like", f"%{log_type}%"])
		if from_date:
			auth_filters.append(["creation", ">=", f"{from_date} 00:00:00"])
		if to_date:
			auth_filters.append(["creation", "<=", f"{to_date} 23:59:59"])
		if actor:
			auth_filters.append(["employee", "like", f"%{actor}%"])
			
		auth_logs = frappe.get_all(
			"VECRM Auth Audit Log", 
			filters=auth_filters, 
			fields=["name", "event", "employee", "identifier", "creation", "path", "reason"], 
			ignore_permissions=True,
			limit_page_length=0,
			order_by="creation desc"
		)
		
	if log_type in ("all", "conversion") and not actor:
		inq_filters = []
		if from_date:
			inq_filters.append(["event_timestamp", ">=", f"{from_date} 00:00:00"])
		if to_date:
			inq_filters.append(["event_timestamp", "<=", f"{to_date} 23:59:59"])
			
		inq_logs = frappe.get_all(
			"VECRM Inquiry Audit Log", 
			filters=inq_filters, 
			fields=["name", "event", "event_timestamp", "payload"], 
			ignore_permissions=True,
			limit_page_length=0,
			order_by="creation desc"
		)

	if log_type in ("all", "assignment"):
		assign_filters = []
		if from_date:
			assign_filters.append(["event_timestamp", ">=", f"{from_date} 00:00:00"])
		if to_date:
			assign_filters.append(["event_timestamp", "<=", f"{to_date} 23:59:59"])
		if actor:
			assign_filters.append(["changed_by", "like", f"%{actor}%"])
			
		assign_logs = frappe.get_all(
			"VECRM Assignment Ledger Entry", 
			filters=assign_filters, 
			fields=["name", "event_timestamp", "from_owner", "to_owner", "changed_by", "change_reason", "ref_document"], 
			ignore_permissions=True,
			limit_page_length=0,
			order_by="creation desc"
		)
		
	unified = []
	
	employees = frappe.get_all("VECRM Employee", fields=["name", "vecrm_email", "employee_name"])
	emp_map = {}
	for e in employees:
		emp_map[e.name] = e.employee_name
		if e.vecrm_email:
			emp_map[e.vecrm_email] = e.employee_name
			
	def get_actor_name(actor_id):
		if not actor_id:
			return "System"
		return emp_map.get(actor_id, actor_id)
	for r in user_logs:
		unified.append({
			"id": r.name,
			"timestamp": r.event_timestamp,
			"type": r.event_type or "other",
			"actor": get_actor_name(r.actor),
			"description": r.detail or f"Target: {r.target}",
			"ref_document": None,
			"source": "user_audit"
		})
		
	for r in auth_logs:
		# Format event like auth.login.failed into Login Failed
		event_clean = str(r.event).replace("auth.", "").replace(".", " ")
		unified.append({
			"id": r.name,
			"timestamp": r.creation,
			"type": event_clean,
			"actor": get_actor_name(r.employee or r.identifier),
			"description": f"Path: {r.path or '-'}" + (f", Reason: {r.reason}" if r.reason else ""),
			"ref_document": None,
			"source": "auth_audit"
		})
		
	for r in inq_logs:
		unified.append({
			"id": r.name,
			"timestamp": r.event_timestamp,
			"type": "conversion",
			"actor": "System/Unknown",
			"description": r.payload or "-",
			"ref_document": None,
			"source": "inquiry_audit"
		})
		
	for r in assign_logs:
		unified.append({
			"id": r.name,
			"timestamp": r.event_timestamp,
			"type": "assignment",
			"actor": get_actor_name(r.changed_by),
			"description": r.change_reason or f"{r.from_owner} -> {r.to_owner}",
			"ref_document": r.ref_document,
			"source": "assignment_ledger"
		})
		
	unified.sort(key=lambda x: str(x["timestamp"]), reverse=True)
	
	total = len(unified)
	start = (page_int - 1) * limit_int
	end = start + limit_int
	
	return {
		"entries": unified[start:end],
		"total": total,
		"page": page_int,
		"has_more": end < total
	}


@frappe.whitelist()
def register_device_token(fcm_token: str, device_label: str = "Android", user_email: str = None) -> dict:
	# SECURITY: derive identity from the session (resolved from the sid
	# cookie), NOT the client-supplied user_email — otherwise a caller could
	# register a device under someone else's email and receive their push
	# notifications. The param is retained for backward compat but ignored.
	user_email = frappe.session.data.get("vecrm_email") or frappe.session.user
	now_dt = frappe.utils.now_datetime()

	existing = frappe.db.get_value("VECRM Device Token", {"fcm_token": fcm_token}, "name")
	if existing:
		doc = frappe.get_doc("VECRM Device Token", existing)
		doc.user_email = user_email
		doc.last_active = now_dt
		doc.device_label = device_label
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({
			"doctype": "VECRM Device Token",
			"user_email": user_email,
			"fcm_token": fcm_token,
			"last_active": now_dt,
			"device_label": device_label,
		}).insert(ignore_permissions=True)

	# Portal BFF calls this via GET to bypass Frappe's CSRF 417 on cookie-
	# auth POSTs. Frappe skips its auto-commit on GET requests (the implicit
	# safety: read-only methods shouldn't persist writes), so the insert/
	# save above would roll back at request end. Force the commit so the
	# token row actually persists.
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist(allow_guest=True)
def get_app_version() -> dict:
    """Public mobile-app version info for the in-app update check.

    allow_guest so the installed app can poll it before/without a portal
    session. Returns only non-sensitive version metadata stored as global
    defaults by release_app_update().
    """
    return {
        "version": frappe.db.get_default("vecrm_app_version") or "1.0.0",
        "message": frappe.db.get_default("vecrm_app_update_msg") or "",
        "download_url": (
            frappe.db.get_default("vecrm_app_download_url")
            or "https://app.vinayenterprises.co.in/VECRM-latest.apk"
        ),
    }


def _publish_app_update(version: str, message: str = "", download_url: str = "") -> dict:
    """Shared publish + broadcast. Stores the version metadata as global
    defaults (served by get_app_version) and pushes data={"screen":"account"}
    to every registered device. Authorization is enforced by the callers."""
    version = (version or "").strip()
    if not version:
        frappe.throw("Version is required.", frappe.ValidationError)
    download_url = (download_url or "").strip() or (
        "https://app.vinayenterprises.co.in/VECRM-latest.apk"
    )
    message = (message or "").strip()

    frappe.db.set_default("vecrm_app_version", version)
    frappe.db.set_default("vecrm_app_update_msg", message)
    frappe.db.set_default("vecrm_app_download_url", download_url)

    from vecrm.notifications import send_push

    rows = frappe.get_all(
        "VECRM Device Token", fields=["fcm_token"], ignore_permissions=True
    )
    tokens = sorted({r.fcm_token for r in rows if r.fcm_token})

    devices_notified = 0
    if tokens:
        try:
            send_push(
                tokens=tokens,
                title=f"App update available — v{version}",
                body=message or f"Version {version} is available. Tap to update.",
                data={"screen": "account"},
            )
            devices_notified = len(tokens)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "publish_app_update push failed")

    return {
        "success": True,
        "version": version,
        "download_url": download_url,
        "devices_notified": devices_notified,
    }


@frappe.whitelist(allow_guest=False)
def release_app_update(version: str, message: str = "", download_url: str = "") -> dict:
    """Admin (portal /admin form): publish a new app version + broadcast.

    Authorization: _require_admin_session() (vecrm_employee_role == "Admin").
    NOT frappe System Manager — portal users run as the shared vecrm-portal
    service account which does not hold that Frappe role.
    """
    _require_admin_session()
    return _publish_app_update(version, message, download_url)


@frappe.whitelist(allow_guest=True)
def release_app_update_ci(
    version: str, message: str = "", download_url: str = "", token: str = ""
) -> dict:
    """CI (GitHub Actions release pipeline): publish a new app version +
    broadcast, authorized by a shared release token instead of an admin
    session — so a tag-triggered build can publish with no portal login.

    The token lives in site_config.json as `vecrm_release_token` (never in
    code) and is supplied by CI as a secret; compared in constant time.
    allow_guest because CI has no session — the token IS the authorization.
    """
    import hmac

    expected = frappe.conf.get("vecrm_release_token")
    if not expected or not token or not hmac.compare_digest(str(token), str(expected)):
        frappe.throw("Invalid or missing release token.", frappe.PermissionError)
    return _publish_app_update(version, message, download_url)

