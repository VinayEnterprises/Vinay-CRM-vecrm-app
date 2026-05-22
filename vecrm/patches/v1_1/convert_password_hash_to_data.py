"""S25 PD-S25-VECRM-AUTH v2 Phase 4.7 — convert password_hash from Password to Data.

OBS-S25-AK + OBS-S25-AH: Password fieldtype on password_hash had a delete-on-save
footgun (get_doc loads Password fields as None; .save() propagates None and Frappe
deletes the __Auth row). The stored value is already a one-way passlib hash —
encrypting it at rest adds no security, only fragility. Data fieldtype stores
the hash in the parent table column, loads correctly via get_doc, survives
.save() unchanged.

This patch:
1. Reloads the doctype to apply the fieldtype change from JSON.
2. Forces schema sync via sync_for so the new Data column lands on the parent table.
3. Drops orphaned __Auth rows for VECRM Employee password_hash (cleanup).
4. NULLs the parent column on all rows (fresh state; re-bootstrap happens in a
   console block immediately after migrate, NOT in this patch).

Idempotent. Paired rollback: rollback_convert_password_hash_to_data.py.

Verified Frappe internals (Phase 4.6 probe):
- frappe.model.sync.sync_for exists with signature (app_name, force=0, reset_permissions=False)
"""

import frappe
from frappe.model.sync import sync_for


def execute() -> None:
    # 1. Apply the fieldtype change from JSON
    frappe.reload_doc("vecrm", "doctype", "vecrm_employee")
    print("[S25 patch 4.7] vecrm_employee doctype reloaded")

    # 2. Force schema sync — ensure the new Data column lands on the parent table
    sync_for("vecrm", force=1)
    print("[S25 patch 4.7] schema sync forced for vecrm app (sync_for)")

    # 3. Drop orphaned __Auth rows for VECRM Employee password_hash
    frappe.db.sql(
        """
        DELETE FROM `__Auth`
        WHERE doctype = 'VECRM Employee'
        AND fieldname = 'password_hash'
        """
    )
    print("[S25 patch 4.7] dropped any __Auth rows for VECRM Employee password_hash")

    # 4. NULL the parent column on all rows (fresh state for re-bootstrap)
    frappe.db.sql(
        """
        UPDATE `tabVECRM Employee`
        SET password_hash = NULL
        """
    )
    frappe.db.commit()
    print("[S25 patch 4.7] cleared password_hash column on all VECRM Employee rows")
    print("[S25 patch 4.7] NOTE: re-bootstrap test employees via console post-migrate")
