# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""VECRM Travel Voucher controller.

Layer-2 keystone consumer of the Voucher Counter allocator. Implements:
- Snapshot freeze at create (employee_base_city, rate_per_km_applied,
  submitter_role) per S1 §2C
- Per-line km + amount compute (no user-entered km, ever)
- FY-aware voucher number allocation via voucher_counter.next_number on submit
- approver_role_set computation (Sales Rep -> {Sales Head,HR,Admin}; Field
  Engineer -> {Head of Engineers,HR,Admin}) - S22 adjudication
- Append-only audit log emission on submit + approve
"""
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname

from vecrm.vecrm.voucher_counter import fy_label, next_number

# Approver-role-set mapping.
#
# PD-S32-TV-APPROVER-SETS-EXPAND: expanded from 2 to 5 submitter roles per
# VECRM-LOCK-ROLE-CAPABILITY-MATRIX (S32) and Q-EV-6 self-service scope.
# The original S22 dict only covered Sales Rep + Field Engineer because
# Sub-A (S24) was Admin-only and Admin filed every voucher manually with
# submitter=<rep>. After S32 self-service shipped (PR portal #29 + vecrm
# #43), Sales Head / Head of Engineers / Admin can also submit on their
# own behalf; before_insert's `if emp.role not in APPROVER_SETS` gate
# rejected them with 417, blocking ALL voucher submits in production.
#
# Approver policy (operator-locked S32):
#   Sales Rep         -> escalates to Sales Head, then HR / Admin
#   Field Engineer    -> escalates to Head of Engineers, then HR / Admin
#   Sales Head        -> HR or Admin (no peer-approval)
#   Head of Engineers -> HR or Admin (no peer-approval)
#   Admin             -> HR or Admin (self-approval permitted; single-
#                        person-company edge case acknowledged)
#
# HR is NOT a submitter (approver-only role) per Q-EV-6 scope.
APPROVER_SETS: dict[str, list[str]] = {
    "Sales Rep":         ["Sales Head", "HR", "Admin"],
    "Field Engineer":    ["Head of Engineers", "HR", "Admin"],
    "Sales Head":        ["HR", "Admin"],
    "Head of Engineers": ["HR", "Admin"],
    "Admin":             ["HR", "Admin"],
}

# Voucher series prefix for Travel Vouchers (Layer 2 - VECRM-L8 anchor).
TRAVEL_VOUCHER_SERIES = "TV"


class VECRMTravelVoucher(Document):
    def autoname(self) -> None:
        """Allocate the final VE/TV/####/FY name at insert time.

        S22 §6 fix: allocation moved from before_submit to autoname. This runs
        BEFORE any other row locks are acquired in the transaction, eliminating
        the lock-ordering deadlock between our allocator's SELECT FOR UPDATE
        and Frappe's submit-path row locks (Travel Voucher, Visit Line,
        Employee, Rate Card, etc.).

        Trade-off: drafts that don't submit "consume" their allocated
        sequence number. Acceptable for internal CRM with low draft-abandon
        rate. The gap-free guarantee is at counter-level (no allocator-side
        gaps), not at name-level (drafts may leave name gaps).

        L8/L10 invariants preserved: voucher_counter.next_number() is
        unchanged; the SELECT FOR UPDATE row lock still serializes
        allocation. Only the CALLER lifecycle changes.
        """
        from vecrm.vecrm import voucher_counter

        if not self.business_date:
            frappe.throw(_("business_date is required to allocate voucher number."))

        fy = voucher_counter.fy_label(self.business_date)
        seq = voucher_counter.next_number(TRAVEL_VOUCHER_SERIES, fy)
        self.name = f"VE/{TRAVEL_VOUCHER_SERIES}/{seq:05d}/{fy}"
        # Freeze FY snapshot here — it must not change once allocated.
        self.fy_label = fy

    def before_insert(self) -> None:
        """Snapshot submitter's role, base_city, applicable rate (S1 §2C)."""
        if not self.submitter:
            frappe.throw("Submitter (VECRM Employee) is required.")

        emp = frappe.get_doc("VECRM Employee", self.submitter)

        if emp.vecrm_account_status != "Active":
            frappe.throw(f"Employee {emp.name} is not active.")

        if emp.role not in APPROVER_SETS:
            frappe.throw(
                f"Submitter role '{emp.role}' is not eligible to submit Travel "
                f"Vouchers. Eligible: {list(APPROVER_SETS.keys())}."
            )

        if not emp.vecrm_base_city:
            frappe.throw(f"Employee {emp.name} has no base city set.")

        # Snapshot fields.
        self.submitter_role = emp.role
        self.employee_base_city = emp.vecrm_base_city
        self.rate_per_km_applied = self._lookup_rate(emp.vecrm_base_city)

    def _lookup_rate(self, city: str) -> float:
        """Lookup rate_per_km in the Rate Card Single by city. Fail loud."""
        rate_card = frappe.get_single("VECRM Rate Card")
        for row in rate_card.city_rates or []:
            if row.city == city:
                return float(row.rate_per_km)
        frappe.throw(
            f"No rate configured for city '{city}' in VECRM Rate Card. "
            f"Add it via Frappe Desk (Rate Card -> City Rates)."
        )

    def validate(self) -> None:
        """Recompute line + total amounts; recompute approver_role_set.

        Runs on every save (draft + submit). The rate, base_city, and
        submitter_role are read from snapshot fields (never re-fetched).
        """
        # Defensive name guard (PD-S23-AUTONAME-HYGIENE): name MUST be
        # canonical VE/TV/####/FY format, set by autoname(). Validated
        # at validate() (not before_insert) because Frappe v16.18.2 runs
        # before_insert BEFORE set_new_name (document.py L441 before L442),
        # so self.name is None at before_insert time. validate() runs via
        # run_before_save_methods (L447) after autoname has populated
        # self.name, and runs on every save thereafter — so a non-canonical
        # name from any source (prompt-mode user input, hash fallback,
        # future rename attempt) is caught here.
        if not self.name or not self.name.startswith("VE/TV/"):
            frappe.throw(
                f"VECRM Travel Voucher name must be allocated via "
                f"voucher_counter (VE/TV/####/FY format). Got: {self.name!r}. "
                f"Do not pre-populate name; let autoname() handle allocation.",
                frappe.ValidationError,
            )

        if not self.visit_lines:
            frappe.throw("At least one visit line is required.")

        if not self.rate_per_km_applied:
            frappe.throw("rate_per_km_applied is unset (snapshot failure).")

        total_km = 0.0
        total_amount = 0.0
        rate = float(self.rate_per_km_applied)

        for line in self.visit_lines:
            if line.end_odometer is None or line.start_odometer is None:
                frappe.throw("Both Start KM and End KM are required on every line.")
            if line.end_odometer < line.start_odometer:
                frappe.throw(
                    f"End KM ({line.end_odometer}) cannot be less than "
                    f"Start KM ({line.start_odometer})."
                )
            line.total_km = round(float(line.end_odometer) - float(line.start_odometer), 1)
            line.line_amount = round(line.total_km * rate, 2)
            total_km += line.total_km
            total_amount += line.line_amount

        self.total_km = round(total_km, 1)
        self.total_amount = round(total_amount, 2)

        # Approver set snapshot (recomputed every save; frozen at submit).
        approver_set = APPROVER_SETS.get(self.submitter_role, [])
        if not approver_set:
            frappe.throw(
                f"submitter_role '{self.submitter_role}' has no approver mapping."
            )
        self.approver_role_set = json.dumps(approver_set)

    def before_submit(self) -> None:
        """S22 §6 fix: allocation moved to autoname (insert time).

        Previously this method allocated the voucher number and called
        rename_doc to rename TV-DRAFT-X → VE/TV/####/FY. Both operations
        are now performed in autoname() at insert time, where no other
        row locks are held in the transaction (eliminating the
        lock-ordering deadlock observed in S22 §6 hard-gate).

        Submit path is now simply: validate snapshot still consistent
        (employee role unchanged, rate card unchanged) — no allocation,
        no rename. The voucher already has its final name from creation.
        """
        # No-op. Snapshot validation could be added here in the future
        # if we want to refuse submit when employee role changed since
        # draft creation, but that's a separate guard not part of S22 §6.
    def on_submit(self) -> None:
        """Audit log on submit (PD-S22-VOUCHER-AUDIT — wired S23 PR via VECRM Voucher Audit Log)."""
        self._audit("voucher.travel.submitted", {
            "actor_employee": self.submitter,
            "actor_role": self.submitter_role,
            "total_amount": float(self.total_amount or 0),
            "total_km": float(self.total_km or 0),
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

        self._audit("voucher.travel.resubmitted", {
            "actor_employee": self.submitter,
            "actor_role": self.submitter_role,
            "total_amount": float(self.total_amount or 0),
            "total_km": float(self.total_km or 0),
            "from_state": "rejected",
            "to_state": "pending",
        })

    def _audit(self, event: str, payload: dict | None = None) -> None:
        """Append-only audit row in VECRM Voucher Audit Log.

        Args:
          event: Dotted event name, e.g. "voucher.travel.submitted",
            "voucher.travel.approved". Convention: voucher.<type>.<state>.
          payload: Optional dict, JSON-serialized into the audit row's
            payload field. Auto-merged keys (do not override): voucher_name,
            voucher_doctype, actor_user. Caller should add: actor_employee,
            actor_role, from_state, to_state, and event-specific fields.

        Per VECRM Voucher Audit Log doctype contract: this row, once
        inserted, is append-only (controller raises on modification or
        deletion).
        """
        import json as _json

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
            "payload": _json.dumps(merged_payload, default=str),
        }).insert(ignore_permissions=True)

def approve_travel_voucher(
    voucher_name: str, approver_employee: str, notes: str | None = None
) -> str:
    """Approve a submitted Travel Voucher.

    First-to-approve wins. Approver's VECRM Employee.role must be in the
    voucher's snapshotted approver_role_set.
    """
    voucher = frappe.get_doc("VECRM Travel Voucher", voucher_name)

    if voucher.docstatus != 1:
        frappe.throw(
            f"Voucher {voucher_name} is not in submitted state "
            f"(docstatus={voucher.docstatus})."
        )

    if voucher.approved_by_employee:
        frappe.throw(
            f"Voucher {voucher_name} already approved by "
            f"{voucher.approved_by_employee} ({voucher.approved_by_role})."
        )

    approver = frappe.get_doc("VECRM Employee", approver_employee)
    if approver.vecrm_account_status != "Active":
        frappe.throw(f"Approver {approver_employee} is not active.")

    approver_set = json.loads(voucher.approver_role_set or "[]")
    if approver.role not in approver_set:
        frappe.throw(
            f"Approver role '{approver.role}' not in voucher's approver "
            f"set {approver_set}."
        )

    voucher.db_set("approved_by_employee", approver_employee, update_modified=False)
    voucher.db_set("approved_by_role", approver.role, update_modified=False)
    voucher.db_set("approved_at", frappe.utils.now(), update_modified=False)
    voucher.db_set("approval_status", "Approved", update_modified=False)
    if notes:
        voucher.db_set("approval_notes", notes, update_modified=False)

    voucher._audit("voucher.travel.approved", {
        "actor_employee": approver_employee,
        "actor_role": approver.role,
        "approver_set": approver_set,
        "notes": notes or "",
        "from_state": "submitted",
        "to_state": "approved",
    })

    return voucher.name


def reject_travel_voucher(
    voucher_name: str, approver_employee: str, reason: str
) -> str:
    """Reject a submitted Travel Voucher (S35 Model A).

    Approver action: only an employee whose role is in the voucher's
    approver_role_set may reject. Cannot reject an already-approved voucher.
    Sets approval_status='Rejected' + reject markers via db_set (no controller
    cycle). reason is MANDATORY. The rep can then correct + resubmit in place
    (on_update_after_submit flips Rejected->Pending).
    """
    if not reason or not reason.strip():
        frappe.throw("A rejection reason is required.", frappe.ValidationError)

    voucher = frappe.get_doc("VECRM Travel Voucher", voucher_name)

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

    approver_set = json.loads(voucher.approver_role_set or "[]")
    if approver.role not in approver_set:
        frappe.throw(
            f"Approver role '{approver.role}' not in voucher's approver "
            f"set {approver_set}.",
            frappe.PermissionError,
        )

    voucher.db_set("approval_status", "Rejected", update_modified=False)
    voucher.db_set("rejected_by_employee", approver_employee, update_modified=False)
    voucher.db_set("rejected_by_role", approver.role, update_modified=False)
    voucher.db_set("rejected_at", frappe.utils.now(), update_modified=False)
    voucher.db_set("rejection_reason", reason, update_modified=False)

    voucher._audit("voucher.travel.rejected", {
        "actor_employee": approver_employee,
        "actor_role": approver.role,
        "approver_set": approver_set,
        "reason": reason,
        "from_state": "submitted",
        "to_state": "rejected",
    })

    return voucher.name


def voucher_resubmit_travel(
    voucher,
    visit_lines: str,
    business_date: str | None = None,
) -> str:
    """Apply edits to a Rejected Travel Voucher and resubmit via doc.save().

    PD-S35 Dispatch 5.8. The api.py wrapper has already loaded the doc
    and gated via _require_voucher_submitter_self_or_admin. This function:

    1. Verifies approval_status == 'Rejected' (defense in depth; the
       on_update_after_submit hook also enforces).
    2. Parses visit_lines JSON; refuses if not a non-empty array.
    3. Captures existing child-row names by index — the portal form does
       NOT round-trip the name field (form's internal VisitLine type has
       only key/open/visit_date/customer_name/odometers/notes). Re-applying
       names here means Frappe matches existing rows on save instead of
       delete-all + insert-all, preserving child-row PKs across resubmit.
    4. Rebuilds voucher.visit_lines with merged dicts (incoming fields +
       preserved names by index where available).
    5. Optionally overlays business_date.
    6. Calls doc.save() — fires validate() (recompute totals + line
       integrity) + on_update_after_submit (status flip Rejected→Pending
       + clear reject markers + emit voucher.travel.resubmitted audit).

    Args:
      voucher: already-loaded VECRM Travel Voucher document (loaded by
        the api.py wrapper before gating).
      visit_lines: JSON-encoded array of visit-line dicts.
      business_date: optional ISO YYYY-MM-DD overlay.

    Returns:
      voucher.name on success.

    Raises:
      frappe.ValidationError: voucher not in Rejected state, invalid
        JSON, empty array, or any validate() failure.
      frappe.PermissionError: only if on_update_after_submit's gate
        re-rejects (shouldn't happen since the api.py wrapper already
        gated, but defense in depth).
    """
    if voucher.approval_status != "Rejected":
        frappe.throw(
            f"Voucher {voucher.name} is not in Rejected state "
            f"(approval_status={voucher.approval_status!r}); only Rejected "
            f"vouchers can be resubmitted via edit.",
            frappe.ValidationError,
        )

    try:
        incoming = json.loads(visit_lines)
    except json.JSONDecodeError as exc:
        frappe.throw(
            f"visit_lines is not valid JSON: {exc}",
            frappe.ValidationError,
        )

    if not isinstance(incoming, list) or not incoming:
        frappe.throw(
            "visit_lines must be a non-empty JSON array.",
            frappe.ValidationError,
        )

    # Capture existing child-row names BEFORE rebuild, indexed for re-apply.
    existing_names = [
        getattr(child, "name", None) for child in (voucher.visit_lines or [])
    ]

    # Rebuild children with name preservation by index. Incoming rows
    # beyond existing count get no name → Frappe inserts as new. Trailing
    # existing rows beyond incoming count are dropped on save_children.
    new_children = []
    for idx, line in enumerate(incoming):
        if not isinstance(line, dict):
            frappe.throw(
                "Each visit_lines entry must be a JSON object.",
                frappe.ValidationError,
            )
        merged = dict(line)
        if idx < len(existing_names) and existing_names[idx]:
            merged["name"] = existing_names[idx]
        new_children.append(merged)
    voucher.set("visit_lines", new_children)

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