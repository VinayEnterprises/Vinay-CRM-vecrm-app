import frappe


def role_is_external(role) -> bool:
    """True when the given VECRM role is flagged is_external on its
    VECRM Role Config record.

    External roles (consultants) draw no per-km petrol reimbursement, so
    the VECRM Rate Card does not apply to them. Fails closed: a blank role,
    an unknown role, or a missing Role Config row all return False, i.e.
    treated as internal, i.e. the rate card still applies.
    """
    role = (role or "").strip()
    if not role:
        return False
    return bool(frappe.db.get_value("VECRM Role Config", role, "is_external"))
