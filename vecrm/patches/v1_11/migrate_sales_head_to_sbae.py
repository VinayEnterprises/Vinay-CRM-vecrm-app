"""S41 role reconciliation — migrate VECRM role "Sales Head" to the canonical
"Senior Business Acceleration Executive" (SBAE), matching the VEHRMS designation.

ADDITIVE ALIAS migration: both role names carry IDENTICAL capabilities (see
vecrm/vecrm/utils/roles.py — EMPLOYEE_ROLE_TO_FRAPPE_ROLES + VOUCHER_APPROVER_SETS
both define SBAE as a peer of Sales Head, and "Sales Head" is intentionally kept
for reversibility). So sales / voucher / CRM gating is unaffected by the value
change. Only Mohit holds "Sales Head" today.

Idempotent (re-running is a no-op once migrated) and reversible (see
rollback_migrate_sales_head_to_sbae.py). DRY-RUN FIRST:

    bench --site <site> execute vecrm.patches.v1_11.migrate_sales_head_to_sbae.dry_run

then apply via `bench migrate` (this module's execute()).
"""
import frappe

OLD_ROLE = "Sales Head"
NEW_ROLE = "Senior Business Acceleration Executive"


def _affected():
    return frappe.get_all(
        "VECRM Employee", filters={"role": OLD_ROLE},
        fields=["name", "employee_name"],
    )


def _report(rows):
    if not rows:
        print(f"[migrate_sbae] No VECRM Employee with role '{OLD_ROLE}'.")
        return
    print(f"[migrate_sbae] {len(rows)} employee(s) with role '{OLD_ROLE}':")
    for r in rows:
        print(f"  - {r.employee_name} ({r.name})")
    # Backfill-validate: surface in-flight vouchers whose FROZEN approver
    # snapshot names the old role. They stay approvable because "Sales Head"
    # remains a valid alias — logged for awareness, snapshots are NOT rewritten.
    for r in rows:
        for dt in ("VECRM Travel Voucher", "VECRM Expense Voucher"):
            field = "approver_role_set" if dt == "VECRM Travel Voucher" else "approver_set"
            pend = frappe.db.sql(
                f"""SELECT name FROM `tab{dt}`
                    WHERE docstatus = 1
                      AND approval_status NOT IN ('Approved', 'Rejected')
                      AND {field} LIKE %s""",
                (f"%{OLD_ROLE}%",),
            )
            if pend:
                print(f"  NOTE: {len(pend)} in-flight {dt}(s) snapshotted with "
                      f"'{OLD_ROLE}' approver — still approvable via the kept alias.")


def dry_run():
    """Read-only: print what execute() WOULD change. Mutates nothing."""
    rows = _affected()
    print("[migrate_sbae] DRY RUN — no changes will be made.")
    _report(rows)


def execute():
    rows = _affected()
    _report(rows)
    for r in rows:
        frappe.db.set_value("VECRM Employee", r.name, "role", NEW_ROLE, update_modified=False)
    if rows:
        frappe.db.commit()
        print(f"[migrate_sbae] Migrated {len(rows)} employee(s) '{OLD_ROLE}' -> '{NEW_ROLE}'.")
