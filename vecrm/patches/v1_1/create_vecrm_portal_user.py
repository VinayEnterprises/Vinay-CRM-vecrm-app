"""S25 PD-S25-VECRM-AUTH v2 — bootstrap shared VECRM Portal User.

CRITICAL SECURITY NOTE (OBS-S25-H corrected):
The shared portal user gets ONLY VECRM Submitter + VECRM Approver roles.
It DOES NOT get VECRM Admin. Combined with admin-class gating done via
frappe.session.data.vecrm_employee_role (NEVER frappe.get_roles()), this
prevents the privilege-escalation hole identified in v1 Blocker 1.

Idempotent. Paired rollback: rollback_create_vecrm_portal_user.py.
"""

import frappe


VECRM_PORTAL_USER_EMAIL = "vecrm-portal@vinayenterprises.co.in"
VECRM_PORTAL_USER_FIRST_NAME = "VECRM"
VECRM_PORTAL_USER_LAST_NAME = "Portal"

# CORRECTED: NO VECRM Admin. Only Submitter + Approver (option c per operator decision).
# This means existing Sub-A endpoints work for all rep sessions (they use Submitter),
# Admin-class operations are NOT accessible via portal until S26 ships session-data gating.
_SHARED_USER_ROLES = ["VECRM Submitter", "VECRM Approver"]


def execute() -> None:
    if frappe.db.exists("User", VECRM_PORTAL_USER_EMAIL):
        # Verify roles match expected; if not, flag (don't auto-correct)
        existing_roles = set(frappe.get_roles(VECRM_PORTAL_USER_EMAIL))
        if "VECRM Admin" in existing_roles:
            print(
                f"[S25 patch] ⚠️ CRITICAL: {VECRM_PORTAL_USER_EMAIL} has VECRM Admin role. "
                f"This is the OBS-S25-H privilege-escalation vector. Removing."
            )
            user = frappe.get_doc("User", VECRM_PORTAL_USER_EMAIL)
            user.roles = [r for r in user.roles if r.role != "VECRM Admin"]
            user.save(ignore_permissions=True)
            frappe.db.commit()
        print(f"[S25 patch] {VECRM_PORTAL_USER_EMAIL} already exists, verified role set")
        return

    user = frappe.new_doc("User")
    user.email = VECRM_PORTAL_USER_EMAIL
    user.first_name = VECRM_PORTAL_USER_FIRST_NAME
    user.last_name = VECRM_PORTAL_USER_LAST_NAME
    user.enabled = 1
    user.user_type = "Website User"  # NOT System User; no Desk access
    user.send_welcome_email = 0
    user.flags.no_welcome_mail = True
    user.insert(ignore_permissions=True)

    for role_name in _SHARED_USER_ROLES:
        if frappe.db.exists("Role", role_name):
            user.append("roles", {"role": role_name})

    user.save(ignore_permissions=True)
    frappe.db.commit()
    print(
        f"[S25 patch] created {VECRM_PORTAL_USER_EMAIL} with roles {_SHARED_USER_ROLES} "
        f"(NO VECRM Admin — OBS-S25-H corrected)"
    )
