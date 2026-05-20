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
