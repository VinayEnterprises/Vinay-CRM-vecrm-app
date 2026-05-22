"""S25 PD-S25-VECRM-AUTH v2 Phase 1.5 — fix shared portal user user_type.

OBS-S25-Y: role.json had desk_access:1 on Submitter+Approver, which caused
Frappe to auto-promote vecrm-portal@vinayenterprises.co.in from Website User
to System User during create_vecrm_portal_user.py's save(). With role.json
now corrected to desk_access:0 on those two roles, this patch:

1. Reloads the role fixtures
2. Forces the shared user back to Website User
3. Verifies the save() does NOT re-promote

Idempotent. Paired rollback: rollback_fix_portal_user_type.py.
"""

import frappe


VECRM_PORTAL_USER_EMAIL = "vecrm-portal@vinayenterprises.co.in"


def execute() -> None:
    # 1. Apply desk_access:0 directly to the two roles in the database.
    # The role.json fixture file is already corrected on disk; this patch
    # propagates the change to the running site's DB. Future `bench migrate`
    # reloads will use the corrected fixture file.
    for role_name in ("VECRM Submitter", "VECRM Approver"):
        if frappe.db.exists("Role", role_name):
            current = frappe.db.get_value("Role", role_name, "desk_access")
            if current == 1:
                frappe.db.set_value("Role", role_name, "desk_access", 0)
                print(f"[S25 patch 1.5] {role_name} desk_access: 1 -> 0")
            else:
                print(f"[S25 patch 1.5] {role_name} desk_access already {current}, no change")
        else:
            print(f"[S25 patch 1.5] WARNING: Role {role_name} not found")
    frappe.db.commit()

    if not frappe.db.exists("User", VECRM_PORTAL_USER_EMAIL):
        print(f"[S25 patch 1.5] {VECRM_PORTAL_USER_EMAIL} doesn't exist, skipping")
        return

    user = frappe.get_doc("User", VECRM_PORTAL_USER_EMAIL)
    if user.user_type == "Website User":
        print(f"[S25 patch 1.5] {VECRM_PORTAL_USER_EMAIL} already Website User, no change")
        return

    print(f"[S25 patch 1.5] correcting user_type: {user.user_type} -> Website User")
    user.user_type = "Website User"
    user.save(ignore_permissions=True)
    frappe.db.commit()

    # Verify the save didn't auto-promote
    user.reload()
    if user.user_type != "Website User":
        frappe.throw(
            f"[S25 patch 1.5] CRITICAL: user_type re-promoted to {user.user_type} "
            f"after save. role.json desk_access fix did not take effect. "
            f"Investigate Frappe auto-promotion logic.",
            frappe.ValidationError,
        )

    print(f"[S25 patch 1.5] {VECRM_PORTAL_USER_EMAIL} now Website User (verified post-save)")
