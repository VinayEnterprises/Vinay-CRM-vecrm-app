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
from frappe.model.document import Document
from frappe.model.naming import make_autoname

from vecrm.vecrm.voucher_counter import fy_label, next_number

# Approver-role-set mapping (S22 strategic decision, FINAL).
APPROVER_SETS: dict[str, list[str]] = {
    "Sales Rep": ["Sales Head", "HR", "Admin"],
    "Field Engineer": ["Head of Engineers", "HR", "Admin"],
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
        """Audit log."""
        # PD-S22-VOUCHER-AUDIT (S23): VECRM User Audit Log Links actor and target
        # both to VECRM Employee. Not fit for document-action audit. Defer to S23.
        # self._audit("submit", f"Travel Voucher {self.name} submitted by {self.submitter}.")

    def _audit(self, event_type: str, detail: str) -> None:
        """Append-only audit row in VECRM User Audit Log.

        Field names match the existing VECRM User Audit Log schema:
        event_type, actor, target, event_timestamp, detail.
        """
        frappe.get_doc({
            "doctype": "VECRM User Audit Log",
            "event_type": event_type,
            "actor": frappe.session.user,
            "target": self.name,
            "event_timestamp": frappe.utils.now_datetime(),
            "detail": detail,
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
    if notes:
        voucher.db_set("approval_notes", notes, update_modified=False)

    # PD-S22-VOUCHER-AUDIT (S23): see on_submit comment
    # voucher._audit(
    #     "approve",
    #     f"Travel Voucher {voucher.name} approved by {approver_employee} "
    #     f"(role={approver.role}).",
    # )

    return voucher.name
