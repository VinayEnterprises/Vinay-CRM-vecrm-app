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


@frappe.whitelist()
def create_lead(
	company_name: str,
	territory: str,
	contact_date: str,
	priority: int,
) -> dict:
	"""Create a VECRM Lead from the portal.

	PD-S24-PORTAL-LEAD-CREATE. lead_owner and status are set server-side
	(session user / "Open") — the client cannot supply or spoof either.
	priority is validated to the documented 1-5 range here, at the API
	boundary, in addition to the controller's own validate() check.

	Lead is not submittable; the row lands usable (docstatus 0, status
	"Open") and is immediately convertible to an Inquiry.

	Args:
	  company_name: Company / lead name (reqd).
	  territory: Free-text territory, e.g. "Ahmedabad" (reqd).
	  contact_date: Date of contact (YYYY-MM-DD). Drives FY allocation.
	  priority: Integer 1-5 (1=Cold .. 5=Very Hot).

	Returns:
	  Dict with name, company_name, territory, contact_date, priority,
	  status, lead_owner.

	Raises:
	  frappe.ValidationError: priority outside 1-5, or any controller
	    validation failure.
	"""
	try:
		priority_int = int(priority)
	except (TypeError, ValueError):
		frappe.throw("Priority must be an integer 1-5.", frappe.ValidationError)

	if not (1 <= priority_int <= 5):
		frappe.throw("Priority must be 1-5.", frappe.ValidationError)

	doc = frappe.new_doc("VECRM Lead")
	doc.company_name = company_name
	doc.territory = territory
	doc.contact_date = contact_date
	doc.priority = priority_int
	doc.status = "Open"
	doc.lead_owner = frappe.session.user
	doc.insert()

	return {
		"name": doc.name,
		"company_name": doc.company_name,
		"territory": doc.territory,
		"contact_date": str(doc.contact_date),
		"priority": doc.priority,
		"status": doc.status,
		"lead_owner": doc.lead_owner,
	}


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
from frappe.utils import now_datetime, get_datetime
from frappe.utils.password import passlibctx, get_decrypted_password, set_encrypted_password
# Note: set_encrypted_password imported for S26 reset flow; unused in S25 scope (OBS-S25-AB)


# Constants
_VECRM_PORTAL_USER: str = "vecrm-portal@vinayenterprises.co.in"
_MAX_FAILED_ATTEMPTS: int = 5
_LOCKOUT_MINUTES: int = 15


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


def _issue_session(employee_doc: Any) -> None:
    """Issue a Frappe session as the shared VECRM Portal User; stash employee
    identity in session data per D8."""
    frappe.local.login_manager.login_as(_VECRM_PORTAL_USER)
    frappe.session.data.vecrm_employee_phone = employee_doc.vecrm_phone
    frappe.session.data.vecrm_employee_name = employee_doc.employee_name
    frappe.session.data.vecrm_employee_role = employee_doc.role
    frappe.session.data.vecrm_login_path = "password"
    frappe.cache.hset("session", frappe.session.sid, frappe.session.data)


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

    # Verify against stored hash (Frappe encrypts the Password field at rest)
    try:
        stored_hash = get_decrypted_password("VECRM Employee", employee_doc.name, "password_hash")
    except frappe.AuthenticationError:
        stored_hash = None

    if not stored_hash or not passlibctx.verify(password, stored_hash):
        _on_failure(employee_doc)
        _audit_auth(
            "auth.login.failed",
            employee=employee_doc.name, identifier=email, path="password",
            reason="invalid_credentials",
        )
        frappe.throw(_("Invalid credentials"), frappe.AuthenticationError)

    _on_success(employee_doc)
    _issue_session(employee_doc)
    _audit_auth("auth.login.success", employee=employee_doc.name, path="password")

    return {
        "success": True,
        "employee": employee_doc.name,
        "name": employee_doc.employee_name,
        "role": employee_doc.role,
    }


@frappe.whitelist(methods=["POST"])
def vecrm_logout() -> dict[str, Any]:
    """Invalidate current VECRM portal session."""
    employee_phone = frappe.session.data.get("vecrm_employee_phone")
    _audit_auth("auth.logout", employee=employee_phone)
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
