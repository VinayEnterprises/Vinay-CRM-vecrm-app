"""Rollback for migrate_sales_head_to_sbae (S41). MANUAL ONLY — not registered
in patches.txt. Reverts "Senior Business Acceleration Executive" back to
"Sales Head".

Run with:
    bench --site <site> execute vecrm.patches.v1_11.rollback_migrate_sales_head_to_sbae.execute

CAUTION: this flips EVERY employee currently on SBAE back to Sales Head. If any
genuinely-new SBAE employees were created after the migration, restrict the
filter or handle them by name before running.
"""
import frappe

NEW_ROLE = "Senior Business Acceleration Executive"
OLD_ROLE = "Sales Head"


def execute():
    rows = frappe.get_all("VECRM Employee", filters={"role": NEW_ROLE}, fields=["name", "employee_name"])
    if not rows:
        print(f"[rollback_sbae] No VECRM Employee with role '{NEW_ROLE}'.")
        return
    for r in rows:
        print(f"  - reverting {r.employee_name} ({r.name}) -> '{OLD_ROLE}'")
        frappe.db.set_value("VECRM Employee", r.name, "role", OLD_ROLE, update_modified=False)
    frappe.db.commit()
    print(f"[rollback_sbae] Reverted {len(rows)} employee(s) to '{OLD_ROLE}'.")
