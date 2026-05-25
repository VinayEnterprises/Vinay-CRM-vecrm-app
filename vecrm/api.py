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
	contact_number: str = None,
	contact_email: str = None,
	meeting_brief: str = None,
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
	doc.status = "Open"
	doc.lead_owner = frappe.session.user
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

    # Set the new password via the S25 canonical pattern: passlibctx.hash
    # + frappe.db.set_value to the Data-typed column on tabVECRM Employee.
    # NOT update_password() — that writes to __Auth (Frappe Password-
    # fieldtype encrypted storage) which S25 phase 4.7 deprecated for this
    # doctype. update_modified=False keeps the row's `modified`/`modified_by`
    # columns reflecting real operator-meaningful edits rather than
    # credential-rotation noise. See PD-S29-AUTH-WRITE-PATTERN-FIX findings.
    hashed = passlibctx.hash(new_password)
    frappe.db.set_value(
        "VECRM Employee",
        employee_doc.name,
        "password_hash",
        hashed,
        update_modified=False,
    )

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

    # PIN format: 4-6 numeric digits (mirrors login_with_pin's accepted
    # domain). All-digit + length check is sufficient; no complexity rules
    # for PINs (they're a secondary credential).
    if not new_pin.isdigit() or not (4 <= len(new_pin) <= 6):
        frappe.throw(
            _("PIN must be 4 to 6 digits"), frappe.ValidationError
        )

    token_doc = _consume_reset_token(token, expected_reset_for="pin")

    employee_doc = frappe.get_doc("VECRM Employee", token_doc.employee)

    # See complete_password_reset for the S25-canonical write-pattern rationale.
    hashed = passlibctx.hash(new_pin)
    frappe.db.set_value(
        "VECRM Employee",
        employee_doc.name,
        "pin_hash",
        hashed,
        update_modified=False,
    )

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

    # 5. Write new (mirrors complete_password_reset; see canonical-pattern
    #    comment there for the S25 rationale).
    hashed = passlibctx.hash(new_password)
    frappe.db.set_value(
        "VECRM Employee",
        employee_doc.name,
        "password_hash",
        hashed,
        update_modified=False,
    )

    # 6. Clear lockout (mirrors complete_password_reset at api.py:1048-1049).
    #    Knowing the current credential is sufficient proof of legitimacy;
    #    don't carry login-side typing-fatigue lockout forward.
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

    # See complete_password_reset for the S25-canonical write-pattern rationale.
    hashed = passlibctx.hash(new_pin)
    frappe.db.set_value(
        "VECRM Employee",
        employee_doc.name,
        "pin_hash",
        hashed,
        update_modified=False,
    )

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
