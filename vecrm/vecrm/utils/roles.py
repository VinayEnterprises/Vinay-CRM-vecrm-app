"""VECRM Employee role <-> Frappe Role translation.

Earned in S25 §13.3-bis recon: VECRM Employee `role` field values
(Admin/Sales Head/HR/Sales Rep/Field Engineer/Head of Engineers) are NOT
identical to Frappe Role names (VECRM Submitter/VECRM Approver/VECRM Admin
per vecrm/fixtures/role.json).

This module is the single source of truth for app-side role gating.

SECURITY NOTE (OBS-S25-H): app-side gating MUST read
frappe.session.data.vecrm_employee_role (the real employee's role from
session data), NEVER frappe.get_roles() (which returns the SHARED portal
user's roles — same for every session — and is therefore unsuitable for
per-employee permission checks).
"""

from typing import Final


EMPLOYEE_ROLE_TO_FRAPPE_ROLES: Final[dict[str, list[str]]] = {
    "Admin":             ["VECRM Admin", "VECRM Submitter", "VECRM Approver"],
    "Sales Head":        ["VECRM Submitter", "VECRM Approver"],
    "HR":                ["VECRM Approver"],
    "Sales Rep":         ["VECRM Submitter"],
    "Field Engineer":    ["VECRM Submitter"],
    "Head of Engineers": ["VECRM Approver"],
}


def get_frappe_roles_for_employee(employee_role: str) -> list[str]:
    """Translate VECRM Employee `role` to its conceptual Frappe Role list.

    NOTE: This translation is for app-side reasoning only. It does NOT
    grant the shared portal user these roles at runtime. The shared user
    has only VECRM Submitter + VECRM Approver permanently (per OBS-S25-H
    correction). Use this function to gate operations app-side:

        if "VECRM Admin" in get_frappe_roles_for_employee(session_employee_role):
            # employee is conceptually Admin
            ...
    """
    return EMPLOYEE_ROLE_TO_FRAPPE_ROLES.get(employee_role, [])


def is_employee_admin(employee_role: str) -> bool:
    """Convenience: True iff this employee role grants Admin privileges."""
    return employee_role == "Admin"


def is_employee_approver(employee_role: str) -> bool:
    """Convenience: True iff this employee role grants Approver privileges."""
    return "VECRM Approver" in EMPLOYEE_ROLE_TO_FRAPPE_ROLES.get(employee_role, [])
