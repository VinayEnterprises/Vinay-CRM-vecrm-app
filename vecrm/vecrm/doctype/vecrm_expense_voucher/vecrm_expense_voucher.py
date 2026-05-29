# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""VECRM Expense Voucher controller.

Layer-2 Phase 3 voucher (PD-S22-EXPENSE-VOUCHER, closed S23).

Mirrors VECRM Travel Voucher (S22 keystone) but with per-line expense
items (Hotel/Food/Supplies/Communication/Misc) instead of km-based
travel computation. Approver set is identical to Travel Voucher
(Sales Head / HR / Admin).

Apply all S23 lessons from day one:
- autoname='' in JSON (OBS-S23-B preventive — no autoname='prompt' here)
- defensive name guard lives in validate() not before_insert()
  (OBS-S23-C: Frappe v16.18.2 runs before_insert at document.py L441
  BEFORE set_new_name at L442, so self.name is None at before_insert
  time)
- `from frappe import _` imported (avoids the latent NameError that
  S23 caught in TV)

Allocator import note: voucher_counter lives at vecrm/vecrm/voucher_counter.py
(module vecrm.vecrm.voucher_counter), the same module TV/Lead/Inquiry
import. fy_label is the allocator's canonical public FY helper — used
here rather than a local re-implementation so FY-boundary logic cannot
drift from the counter that partitions on it.
"""
import json

import frappe
from frappe import _
from frappe.model.document import Document

from vecrm.vecrm.voucher_counter import fy_label, next_number


class VECRMExpenseVoucher(Document):
    """Submittable expense reimbursement voucher.

    Allocator: vecrm.vecrm.voucher_counter.next_number("EV", fy)
    Naming: VE/EV/####/FY (e.g. VE/EV/00001/26-27)
    Approval: module-level approve_expense_voucher() (mirrors TV)
    Audit: VECRM Voucher Audit Log (event: voucher.expense.{submitted,approved})
    """

    def autoname(self) -> None:
        """Allocate name via voucher_counter.

        Per OBS-S23-B: JSON's autoname='' (empty) is the ONLY value that
        guarantees this method is called. autoname='prompt' or 'Prompt'
        would silently skip this method per Frappe v16 naming.py L158.
        """
        if not self.expense_date:
            frappe.throw(
                _("Expense Date is required to allocate voucher name."),
                frappe.ValidationError,
            )
        fy = fy_label(self.expense_date)
        n = next_number(series="EV", fy=fy)
        self.name = f"VE/EV/{n:05d}/{fy}"
        self.fy_label = fy

    def before_insert(self) -> None:
        """Snapshot submitter's role at create.

        Per OBS-S23-C: name guard is NOT placed here. self.name is None
        at before_insert time because Frappe v16.18.2 runs this BEFORE
        set_new_name (document.py L441 < L442). Name guard lives in
        validate() instead.
        """
        if not self.submitter:
            frappe.throw(
                _("Submitter (VECRM Employee) is required."),
                frappe.ValidationError,
            )

        employee = frappe.get_doc("VECRM Employee", self.submitter)
        self.submitter_role = employee.role

    def validate(self) -> None:
        """Validation pipeline:

        1. Defensive name guard (PD-S23-AUTONAME-HYGIENE) — name must be
           canonical VE/EV/####/FY format. validate() runs via
           run_before_save_methods (document.py L447) AFTER set_new_name
           has populated self.name, and runs on every save thereafter —
           so a non-canonical name from any source (hash fallback,
           future rename attempt) is caught here.
        2. expense_lines must have at least one row.
        3. Each expense line's amount must be > 0.
        4. total_amount is recomputed (never trust client-side value).
        """
        # Name guard (OBS-S23-C: placed here, NOT in before_insert)
        if not self.name or not self.name.startswith("VE/EV/"):
            frappe.throw(
                f"VECRM Expense Voucher name must be allocated via "
                f"voucher_counter (VE/EV/####/FY format). Got: {self.name!r}. "
                f"Do not pre-populate name; let autoname() handle allocation.",
                frappe.ValidationError,
            )

        if not self.expense_lines:
            frappe.throw(
                _("At least one expense line is required."),
                frappe.ValidationError,
            )

        # Per-line amount validation
        for idx, line in enumerate(self.expense_lines, start=1):
            if line.amount is None or float(line.amount) <= 0:
                frappe.throw(
                    f"Expense line {idx}: amount must be > 0. Got {line.amount!r}.",
                    frappe.ValidationError,
                )

        # Recompute total_amount (defense against client-side tampering)
        self.total_amount = sum(float(line.amount) for line in self.expense_lines)

    def before_submit(self) -> None:
        """Pre-submit checks: derive approver_set from submitter_role.

        Mirrors Travel Voucher's before_submit. The approver_set is a
        JSON-encoded list of role names eligible to approve this voucher.
        For now (and per S23 spec): same as Travel Voucher — every Expense
        Voucher can be approved by Sales Head, HR, or Admin regardless
        of submitter role. Hardcoded; if amount-threshold logic is added
        later (e.g. >₹X requires Admin), it goes here.
        """
        approver_roles = ["Sales Head", "HR", "Admin"]
        self.approver_set = json.dumps(approver_roles)

    def on_submit(self) -> None:
        """Audit log on submit.

        Writes to VECRM Voucher Audit Log (the doctype built in S23 PR #11).
        Mirrors Travel Voucher's on_submit emission shape.
        """
        self._audit("voucher.expense.submitted", {
            "actor_employee": self.submitter,
            "actor_role": self.submitter_role,
            "total_amount": float(self.total_amount or 0),
            "line_count": len(self.expense_lines),
            "fy_label": self.fy_label,
            "from_state": "draft",
            "to_state": "submitted",
        })

    def on_update_after_submit(self) -> None:
        """Guarded in-place edit of a REJECTED submitted voucher (S35 Model A).

        Fires on doc.save() of a docstatus=1 doc. The approve/reject flows
        use db_set (no controller cycle) so they do NOT reach here — only a
        genuine content edit (visit lines / totals) does.

        Permit the edit ONLY if approval_status == 'Rejected' AND the editor
        is the submitter (or Admin). On a valid edit, transition the voucher
        back to Pending for re-review: clear reject markers, flip status,
        emit a resubmitted audit event. Any other after-submit edit throws.

        IMPORTANT (PD-S35 5.9): Frappe's update_after_submit save path does
        NOT fire validate() automatically. Callers performing in-place edits
        (e.g. voucher_resubmit_travel) MUST call voucher.validate() explicitly
        before voucher.save() to recompute totals from edited child rows.
        Without that, self.total_km/self.total_amount read here will be stale,
        and the audit payload below will record the pre-edit values.
        """
        prior_status = frappe.db.get_value(self.doctype, self.name, "approval_status")

        if prior_status != "Rejected":
            frappe.throw(
                _("This voucher is submitted and cannot be edited. Only a "
                  "rejected voucher can be corrected and resubmitted."),
                frappe.PermissionError,
            )

        role = (frappe.session.data or {}).get("vecrm_employee_role")
        self_phone = (frappe.session.data or {}).get("vecrm_employee_phone")
        if role != "Admin" and self.submitter != self_phone:
            frappe.throw(
                _("You can only correct your own rejected vouchers."),
                frappe.PermissionError,
            )

        self.db_set("approval_status", "Pending", update_modified=False)
        self.db_set("rejected_by_employee", None, update_modified=False)
        self.db_set("rejected_by_role", None, update_modified=False)
        self.db_set("rejected_at", None, update_modified=False)
        self.db_set("rejection_reason", None, update_modified=False)

        self._audit("voucher.expense.resubmitted", {
            "actor_employee": self.submitter,
            "actor_role": self.submitter_role,
            "total_amount": float(self.total_amount or 0),
            "line_count": len(self.expense_lines),
            "from_state": "rejected",
            "to_state": "pending",
        })

    def _audit(self, event: str, payload: dict | None = None) -> None:
        """Append-only audit row in VECRM Voucher Audit Log.

        Identical contract to Travel Voucher's _audit. Auto-merged keys
        (do not override): voucher_name, voucher_doctype, actor_user.
        Caller should add: actor_employee, actor_role, from_state,
        to_state, and event-specific fields.

        Per VECRM Voucher Audit Log doctype contract: this row, once
        inserted, is append-only (controller raises on modification or
        deletion).
        """
        merged_payload = {
            "voucher_name": self.name,
            "voucher_doctype": self.doctype,
            # LEAD-OWNER-ATTRIBUTION fix (S31): record human identity in audit, not BFF service account.
            "actor_user": frappe.session.data.get("vecrm_email") or frappe.session.user,
        }
        if payload:
            merged_payload.update(payload)

        frappe.get_doc({
            "doctype": "VECRM Voucher Audit Log",
            "event": event,
            "event_timestamp": frappe.utils.now_datetime(),
            "payload": json.dumps(merged_payload, default=str),
        }).insert(ignore_permissions=True)


def approve_expense_voucher(
    voucher_name: str,
    approver_employee: str,
    notes: str = "",
) -> str:
    """Approve a submitted Expense Voucher.

    Mirrors approve_travel_voucher (vecrm_travel_voucher.py).

    Steps:
    1. Load voucher; verify docstatus=1 (submitted, not draft, not cancelled).
    2. Verify approver_employee exists and has a role in voucher's approver_set.
    3. Set approved_by_employee, approved_by_role, approved_at, approval_notes
       via db_set (no save → no controller cycle → no false-positive lifecycle hooks).
    4. Emit voucher.expense.approved audit event.
    5. Return voucher_name.

    Returns voucher_name on success. Raises ValidationError or PermissionError
    on any failure.
    """
    voucher = frappe.get_doc("VECRM Expense Voucher", voucher_name)

    if voucher.docstatus != 1:
        frappe.throw(
            f"Voucher {voucher_name} cannot be approved: docstatus={voucher.docstatus} "
            f"(expected 1=Submitted). Drafts and cancelled vouchers cannot be approved.",
            frappe.ValidationError,
        )

    if voucher.approved_by_employee:
        frappe.throw(
            f"Voucher {voucher_name} already approved by "
            f"{voucher.approved_by_employee} ({voucher.approved_by_role}).",
            frappe.ValidationError,
        )

    approver = frappe.get_doc("VECRM Employee", approver_employee)
    if approver.vecrm_account_status != "Active":
        frappe.throw(f"Approver {approver_employee} is not active.", frappe.PermissionError)
    approver_set = json.loads(voucher.approver_set or "[]")

    if approver.role not in approver_set:
        frappe.throw(
            f"Employee {approver_employee} (role={approver.role}) is not in "
            f"the approver_set for voucher {voucher_name}. Eligible roles: {approver_set}.",
            frappe.PermissionError,
        )

    voucher.db_set("approved_by_employee", approver_employee, update_modified=False)
    voucher.db_set("approved_by_role", approver.role, update_modified=False)
    voucher.db_set("approved_at", frappe.utils.now_datetime(), update_modified=False)
    voucher.db_set("approval_status", "Approved", update_modified=False)
    if notes:
        voucher.db_set("approval_notes", notes, update_modified=False)

    voucher._audit("voucher.expense.approved", {
        "actor_employee": approver_employee,
        "actor_role": approver.role,
        "approver_set": approver_set,
        "notes": notes or "",
        "from_state": "submitted",
        "to_state": "approved",
    })

    return voucher.name


def reject_expense_voucher(
    voucher_name: str, approver_employee: str, reason: str
) -> str:
    """Reject a submitted Expense Voucher (S35 Model A).

    Mirrors reject_travel_voucher. Approver action; reason mandatory;
    cannot reject an approved voucher. Sets approval_status='Rejected' +
    reject markers via db_set.
    """
    if not reason or not reason.strip():
        frappe.throw("A rejection reason is required.", frappe.ValidationError)

    voucher = frappe.get_doc("VECRM Expense Voucher", voucher_name)

    if voucher.docstatus != 1:
        frappe.throw(
            f"Voucher {voucher_name} is not in submitted state "
            f"(docstatus={voucher.docstatus}).",
            frappe.ValidationError,
        )

    if voucher.approval_status == "Approved":
        frappe.throw(
            f"Voucher {voucher_name} is already approved and cannot be rejected.",
            frappe.ValidationError,
        )

    approver = frappe.get_doc("VECRM Employee", approver_employee)
    if approver.vecrm_account_status != "Active":
        frappe.throw(f"Approver {approver_employee} is not active.", frappe.PermissionError)

    approver_set = json.loads(voucher.approver_set or "[]")
    if approver.role not in approver_set:
        frappe.throw(
            f"Employee {approver_employee} (role={approver.role}) is not in "
            f"the approver_set for voucher {voucher_name}. Eligible roles: {approver_set}.",
            frappe.PermissionError,
        )

    voucher.db_set("approval_status", "Rejected", update_modified=False)
    voucher.db_set("rejected_by_employee", approver_employee, update_modified=False)
    voucher.db_set("rejected_by_role", approver.role, update_modified=False)
    voucher.db_set("rejected_at", frappe.utils.now_datetime(), update_modified=False)
    voucher.db_set("rejection_reason", reason, update_modified=False)

    voucher._audit("voucher.expense.rejected", {
        "actor_employee": approver_employee,
        "actor_role": approver.role,
        "approver_set": approver_set,
        "reason": reason,
        "from_state": "submitted",
        "to_state": "rejected",
    })

    return voucher.name


def voucher_resubmit_expense(
    voucher,
    expense_lines: str,
    expense_date: str | None = None,
) -> str:
    """Apply edits to a Rejected Expense Voucher and resubmit via doc.save().

    PD-S35 Dispatch 5.8. Sibling of voucher_resubmit_travel; see that
    function for the architectural notes. EV diverges only in:
      - Children field name: expense_lines (vs visit_lines)
      - Top-level date: expense_date (vs business_date)
      - Audit event: voucher.expense.resubmitted (vs travel)
    All hook + validate semantics are otherwise identical.
    """
    if voucher.approval_status != "Rejected":
        frappe.throw(
            f"Voucher {voucher.name} is not in Rejected state "
            f"(approval_status={voucher.approval_status!r}); only Rejected "
            f"vouchers can be resubmitted via edit.",
            frappe.ValidationError,
        )

    try:
        incoming = json.loads(expense_lines)
    except json.JSONDecodeError as exc:
        frappe.throw(
            f"expense_lines is not valid JSON: {exc}",
            frappe.ValidationError,
        )

    if not isinstance(incoming, list) or not incoming:
        frappe.throw(
            "expense_lines must be a non-empty JSON array.",
            frappe.ValidationError,
        )

    existing_names = [
        getattr(child, "name", None) for child in (voucher.expense_lines or [])
    ]

    new_children = []
    for idx, line in enumerate(incoming):
        if not isinstance(line, dict):
            frappe.throw(
                "Each expense_lines entry must be a JSON object.",
                frappe.ValidationError,
            )
        merged = dict(line)
        if idx < len(existing_names) and existing_names[idx]:
            merged["name"] = existing_names[idx]
        new_children.append(merged)
    voucher.set("expense_lines", new_children)

    if business_date is not None:
        voucher.business_date = business_date

    # PD-S35 5.9: Frappe's update_after_submit save path does NOT fire
    # validate() automatically (only the per-field gate
    # validate_update_after_submit fires, and we bypass that via the flag
    # below). Our controller's validate() is where total_km / total_amount
    # are recomputed from child rows + per-line totals are set — without
    # an explicit call, totals stay stale and the audit emits pre-edit
    # values. The flag bypasses Frappe's per-field "not allowed to change
    # after submission" gate, which would otherwise refuse the End KM /
    # Start KM mutations. on_update_after_submit (fires post-save) handles
    # the Rejected→Pending transition + audit emit.
    voucher.flags.ignore_validate_update_after_submit = True
    voucher.validate()
    voucher.save()
    return voucher.name
