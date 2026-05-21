# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class VECRMVoucherAuditLog(Document):
    """Fail-loud audit ledger for Layer-2 voucher events.

    Written by:
    - VECRMTravelVoucher.on_submit (event: voucher.travel.submitted)
    - vecrm_travel_voucher.approve_travel_voucher (event: voucher.travel.approved)
    - Future: VECRMExpenseVoucher and any other Layer-2 voucher types.

    Disjoint from VECRM User Audit Log on purpose: that doctype's
    event_type Select is locked to user-lifecycle values (User Provisioned /
    User Suspended / User Reactivated); widening it to include voucher
    events would couple Layer-1 to Layer-2. Disjoint from VECRM Inquiry
    Audit Log for the same reason (Layer-3 vs Layer-2).

    Mirrors VECRM Inquiry Audit Log pattern: minimal schema (event +
    timestamp + payload JSON), append-only by controller guard, no
    deletion by any role.

    Append-only by controller guard (defense-in-depth above the JSON's
    write=0 perm). Permission model:
    - System Manager: create/read, no write/delete
    - VECRM Admin: create/read, no write/delete
    - VECRM Approver: read-only
    - VECRM Submitter: no access (audit not visible to submitters; their
      voucher's own approval state is on the voucher itself)
    """

    def before_insert(self):
        # Timestamp integrity is core to an audit row; default it
        # defensively even though the field is reqd (covers programmatic
        # inserts that omit it).
        if not self.event_timestamp:
            self.event_timestamp = now()

    def on_update(self):
        # Append-only: a row may be inserted, never modified thereafter.
        # Frappe 16: on_update also fires DURING insert (run_post_save_methods,
        # _action == "save"); set_new_name() has already run so is_new() is
        # False on the insert path. flags.in_insert is the version-grounded
        # "inside insert()" signal (document.py sets it around the
        # run_post_save_methods call). get_doc_before_save() is None on insert
        # and non-None only on a genuine modification of a committed row -
        # the same predicate the User Audit Log + Inquiry Audit Log
        # controllers use.
        if self.flags.in_insert:
            return
        if self.get_doc_before_save() is not None:
            frappe.throw(
                _("VECRM Voucher Audit Log is append-only. Existing entries cannot be modified."),
                frappe.PermissionError,
            )

    def on_trash(self):
        # Append-only: audit rows are never deletable, by any role,
        # including System Manager / Administrator.
        frappe.throw(
            _("VECRM Voucher Audit Log is append-only. Entries cannot be deleted."),
            frappe.PermissionError,
        )
