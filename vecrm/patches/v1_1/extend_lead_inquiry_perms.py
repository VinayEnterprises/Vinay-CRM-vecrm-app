"""S25 PD-S25-VECRM-AUTH v2 Phase 5.5 — extend VECRM Lead and VECRM Inquiry permissions.

OBS-S25-AR + OBS-S25-AV: Phase 5 §10.1 risk landed at browser smoke (Step 5.E).
The shared portal user `vecrm-portal@vinayenterprises.co.in` has roles
[VECRM Submitter, VECRM Approver] (post-Phase-1.5 OBS-S25-H fix; no VECRM Admin).
But VECRM Lead doctype perms grant access only to [System Manager, VECRM Admin],
and VECRM Inquiry doctype perms grant access only to [System Manager]. So the
portal's /api/leads and /api/inquiries calls (which hit Frappe's generic resource
API and enforce per-doctype perms) return 403.

Pre-S25 production did not surface this because Ajay logged in as the Frappe
`Administrator` user (superuser bypass), not as a role-bound user.

This patch reloads the affected doctypes to apply permission changes from JSON,
then forces a schema/perm sync via sync_for, then clears the permission cache.

Verified Frappe internals (Phase 4.6/4.7 patches):
- frappe.model.sync.sync_for exists with signature (app_name, force=0, reset_permissions=False)
- reset_permissions=True reapplies DocPerm rows from JSON on reload

Coupled with JSON changes in:
- vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.json (appended 2 perm rows)
- vecrm/vecrm/doctype/vecrm_inquiry/vecrm_inquiry.json (appended 3 perm rows)

Permission matrix (mirrors VECRM Travel Voucher's shape, stripped of
submittable-only keys since Lead and Inquiry are not is_submittable):
  VECRM Lead     <- VECRM Submitter (r/w/c, print) + VECRM Approver (r, print)
  VECRM Inquiry  <- VECRM Admin (r/w/c, email/share/print) + Submitter + Approver

Idempotent. Paired rollback: rollback_extend_lead_inquiry_perms.py.
"""

import frappe
from frappe.model.sync import sync_for


def execute() -> None:
    # 1. Reload both doctypes so JSON perm changes apply
    frappe.reload_doc("vecrm", "doctype", "vecrm_lead")
    print("[S25 patch 5.5] vecrm_lead doctype reloaded")

    frappe.reload_doc("vecrm", "doctype", "vecrm_inquiry")
    print("[S25 patch 5.5] vecrm_inquiry doctype reloaded")

    # 2. Force schema sync with reset_permissions=True to reapply DocPerm rows
    sync_for("vecrm", force=1, reset_permissions=True)
    print("[S25 patch 5.5] schema sync forced for vecrm app with reset_permissions=True")

    # 3. Clear permission cache so runtime picks up new rows immediately
    frappe.clear_cache()
    print("[S25 patch 5.5] permission cache cleared")

    frappe.db.commit()
    print("[S25 patch 5.5] complete - VECRM Lead + VECRM Inquiry perms extended")
