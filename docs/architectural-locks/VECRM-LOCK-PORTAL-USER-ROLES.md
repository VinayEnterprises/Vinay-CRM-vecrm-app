# VECRM-LOCK-PORTAL-USER-ROLES

**Earned:** S25 (Phase 1, OBS-S25-H + Phase 1.5, OBS-S25-Y)
**Status:** ACTIVE
**Severity:** Critical (privilege escalation; account-type drift)

## Statement

The shared VECRM Portal User (`vecrm-portal@vinayenterprises.co.in`) MUST be:

- **User type:** Website User (NOT System User)
- **Roles:** VECRM Submitter + VECRM Approver ONLY (NEVER VECRM Admin, NEVER System Manager)

Additionally, the role JSON files for **VECRM Submitter** and **VECRM Approver** MUST have `desk_access: 0`. If any portal-facing role has `desk_access: 1`, Frappe auto-promotes the assigned user from Website User → System User on next role evaluation, breaking the Website-User-only invariant.

## Why VECRM Admin must be excluded

Portal sessions run as the shared portal user. Any code path that fires `frappe.get_roles()` or `frappe.has_permission()` from within a session sees the union of the shared user's roles. If the shared user has VECRM Admin, every portal-authenticated request operates with Admin-level perms — regardless of which employee is actually logged in via VECRM Employee + password.

This is the classic confused-deputy: the portal user's roles must be the LOWEST common denominator of access the portal session needs. Per-employee role differentiation happens above that floor via `vecrm.session.data.vecrm_employee_role` and explicit role checks in custom endpoints.

## Why desk_access: 0 matters

Discovered via OBS-S25-Y in S25 Phase 1.5:

- The shared portal user was bootstrapped as Website User (correctly)
- VECRM Submitter role JSON had `desk_access: 1` (incorrectly, from earlier session)
- Frappe auto-promoted the user to System User on first session
- This silently violated the Website-User-only invariant

Frappe's logic: "If a user has any role with desk_access=1, that user must be System User to use Desk." The auto-promotion is the framework's helpful behavior, but for portal-only users it's exactly wrong.

## Where this is enforced

- `vecrm/patches/v1_1/create_vecrm_portal_user.py` (Phase 1 bootstrap — creates user as Website User)
- `vecrm/patches/v1_1/fix_portal_user_type.py` (Phase 1.5 — corrects user_type via `frappe.db.set_value`, NOT `import_file_by_path`)
- `vecrm/fixtures/role.json` — VECRM Submitter and VECRM Approver have `desk_access: 0`; VECRM Admin retains `desk_access: 1`

## Validation procedure

At any session-open, verify with:

```python
import frappe
user = "vecrm-portal@vinayenterprises.co.in"
user_type = frappe.db.get_value("User", user, "user_type")
roles = sorted(frappe.get_roles(user))
print(f"user_type: {user_type}")  # expect: Website User
print(f"roles: {roles}")  # expect: ['All', 'Guest', 'VECRM Approver', 'VECRM Submitter']
```

Plus for each role:

```python
for r in ["VECRM Submitter", "VECRM Approver"]:
    desk = frappe.db.get_value("Role", r, "desk_access")
    print(f"{r}.desk_access = {desk}")  # expect: 0
```

## Mechanism for role-differentiated behavior in custom endpoints

Since the underlying Frappe session is always the same shared user, per-employee role differentiation requires reading `frappe.session.data`:

```python
@frappe.whitelist()
def some_admin_only_action(...) -> ...:
    role = (frappe.session.data or {}).get("vecrm_employee_role")
    if role != "Admin":
        frappe.throw(_("Not authorized"), frappe.PermissionError)
    # ... proceed
```

This is the discipline downstream code MUST use. NEVER rely on `frappe.has_permission(...)` alone for fine-grained portal authorization — that only sees the shared user's permissions.

## When this lock can be relaxed

NEVER for the shared portal user. If a future architecture introduces per-employee Frappe Users (instead of the shared-user pattern), those individual users CAN safely hold VECRM Admin if they're real admins — but the shared portal user remains Submitter+Approver only.

## Related observations

- OBS-S25-H — Phase 1 review caught the proposed-VECRM-Admin in the bootstrap patch before it shipped
- OBS-S25-Y — Phase 1.5 caught the desk_access auto-promotion footgun
- OBS-S25-Z — dispatcher reached for unverified `import_file_by_path` when `frappe.db.set_value` was the right tool for the fix
