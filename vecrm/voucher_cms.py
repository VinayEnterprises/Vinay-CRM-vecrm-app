import base64
import io
import json
from datetime import datetime

import frappe
from frappe.utils import flt, getdate

# --- Kotak CMS format (mirrors VEHRMS payroll kotak_cms.py) ---
CLIENT_CODE = "ENTERPRISE"
PRODUCT_CODE = "VPAY"
DR_AC_NO = "5447647641"            # Kotak debit/source (same as payroll)
BANK_CODE_INDICATOR = "M"
KOTAK_IFSC_PREFIX = "KKBK"
CMS_COLUMN_COUNT = 49

VE_COMPANY = "Vinay Enterprises"
VECS_COMPANY = "VECS"

# Voucher VECS clubbed line credits the VECS YES BANK account (NOT the Axis
# account salary uses). NEFT is chosen automatically because YESB != KKBK.
VECS_BANK_DETAILS = {
    "beneficiary_name": "VE COMPUTER SERVICES",
    "beneficiary_bank": "YES BANK",
    "ifsc_code": "YESB0000101",
    "account_no": "010127000001070",
}

VOUCHER_TYPES = (
    ("VECRM Expense Voucher", "expense_date"),
    ("VECRM Travel Voucher", "business_date"),
)


def _payment_type(ifsc_code):
    if ifsc_code and str(ifsc_code).upper().startswith(KOTAK_IFSC_PREFIX):
        return "IFT"
    return "NEFT"


def _is_vecs(company):
    return str(company or "").strip().upper() in ("VECS", "VE COMPUTER SERVICES")


def _is_ve(company):
    return str(company or "").strip() == VE_COMPANY


def _build_row(payment_date, amount, beneficiary_name, beneficiary_bank, ifsc_code, account_no):
    row = [""] * CMS_COLUMN_COUNT
    row[0] = CLIENT_CODE
    row[1] = PRODUCT_CODE
    row[2] = _payment_type(ifsc_code)
    row[4] = payment_date
    row[5] = payment_date
    row[6] = DR_AC_NO
    row[7] = int(round(flt(amount)))
    row[8] = BANK_CODE_INDICATOR
    row[10] = beneficiary_name
    row[11] = beneficiary_bank
    row[12] = ifsc_code
    row[13] = str(account_no or "")
    return row


def _collect_vouchers(from_date, to_date):
    """Source of truth for payable vouchers. Returns
    {employee_docname: {'amount': float, 'vouchers': [{'type','name','amount'}]}}.
    Isolated so a future ERPNext source can replace just this function."""
    per_emp = {}
    for dt, date_field in VOUCHER_TYPES:
        rows = frappe.get_all(
            dt,
            filters={
                "approval_status": "Approved",
                "payment_status": "Unpaid",
                date_field: ["between", [from_date, to_date]],
            },
            fields=["name", "submitter", "total_amount"],
        )
        for r in rows:
            emp = r["submitter"]
            if not emp:
                continue
            slot = per_emp.setdefault(emp, {"amount": 0.0, "vouchers": []})
            slot["amount"] += flt(r["total_amount"])
            slot["vouchers"].append({"type": dt, "name": r["name"], "amount": flt(r["total_amount"])})
    return per_emp


# --- Authorization -------------------------------------------------------
# The payout file exposes every employee's bank account number, IFSC, holder
# name, and exact amounts. Restrict to the finance/HR-ops tier. Defined locally
# (not reusing api._require_hr_or_admin) so the payout tier stays independent
# and can be tightened later without touching voucher-approval authz.
_PAYOUT_ROLES = ("Admin", "HR", "Head of Accounts & HR")


def _require_payout_access():
    role = (frappe.session.data or {}).get("vecrm_employee_role")
    if role not in _PAYOUT_ROLES:
        frappe.throw(
            frappe._("Only HR, Head of Accounts & HR, or Admin can generate payout files."),
            frappe.PermissionError,
        )


@frappe.whitelist()
def generate_voucher_payment_file(from_date=None, to_date=None, payment_date=None):
    _require_payout_access()
    try:
        import xlwt
    except ImportError:
        frappe.throw("xlwt is not installed in this environment — add it to the VECRM image build")

    if not (from_date and to_date):
        frappe.throw("from_date and to_date are required")
    from_date = getdate(from_date)
    to_date = getdate(to_date)
    if from_date > to_date:
        frappe.throw("from_date cannot be after to_date")

    pay_date = getdate(payment_date) if payment_date else getdate()
    payment_date_value = pay_date.strftime("%d/%m/%Y")

    per_emp = _collect_vouchers(from_date, to_date)
    if not per_emp:
        frappe.throw("No approved-unpaid vouchers found in the selected period")

    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("electronic")
    text_style = xlwt.easyxf("", num_format_str="@")

    rows_written = []
    skipped = []
    vecs_total = 0.0
    vecs_emps = []
    total_amount = 0.0
    state = {"row": 0}

    def _write(values):
        for col, value in enumerate(values):
            if col in (6, 13):
                sheet.write(state["row"], col, value, text_style)
            else:
                sheet.write(state["row"], col, value)
        state["row"] += 1

    for emp in sorted(per_emp.keys()):
        amount = int(round(per_emp[emp]["amount"]))
        if amount <= 0:
            continue
        try:
            edoc = frappe.get_doc("VECRM Employee", emp)
        except Exception:
            skipped.append({"employee": emp, "reason": "VECRM Employee not found", "amount": amount})
            continue

        comp = (edoc.company or "").strip()
        if _is_vecs(comp):
            vecs_total += amount
            vecs_emps.append({"employee": emp, "employee_name": edoc.employee_name, "amount": amount})
            continue
        if not _is_ve(comp):
            skipped.append({"employee": emp, "employee_name": edoc.employee_name,
                            "reason": "unknown/blank company: %r" % comp, "amount": amount})
            continue

        ac = (edoc.get("bank_ac_no") or "").strip()
        ifsc = (edoc.get("ifsc_code") or "").strip().upper()
        bank = (edoc.get("bank_name") or "").strip()
        holder = (edoc.get("bank_account_holder_name") or edoc.employee_name or "").strip().upper()
        missing = [f for f, v in (("bank_ac_no", ac), ("ifsc_code", ifsc), ("bank_name", bank)) if not v]
        if missing:
            skipped.append({"employee": emp, "employee_name": edoc.employee_name,
                            "reason": "missing " + ", ".join(missing), "amount": amount})
            continue

        _write(_build_row(payment_date_value, amount, holder, bank, ifsc, ac))
        total_amount += amount
        rows_written.append({"employee": emp, "employee_name": edoc.employee_name,
                             "company": comp, "amount": amount, "payment_type": _payment_type(ifsc)})

    if vecs_total > 0:
        _write(_build_row(payment_date_value, int(round(vecs_total)),
                          VECS_BANK_DETAILS["beneficiary_name"], VECS_BANK_DETAILS["beneficiary_bank"],
                          VECS_BANK_DETAILS["ifsc_code"], VECS_BANK_DETAILS["account_no"]))
        total_amount += int(round(vecs_total))
        rows_written.append({"employee": None, "employee_name": VECS_BANK_DETAILS["beneficiary_name"],
                             "company": VECS_COMPANY, "amount": int(round(vecs_total)),
                             "payment_type": _payment_type(VECS_BANK_DETAILS["ifsc_code"]),
                             "clubbed_count": len(vecs_emps), "clubbed_employees": vecs_emps})

    if not rows_written:
        frappe.throw("No payable lines built — every employee was skipped (check bank details)")

    buf = io.BytesIO()
    workbook.save(buf)
    content_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    filename = f"voucher_cms_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xls"

    written = set(r["employee"] for r in rows_written if r["employee"]) | set(v["employee"] for v in vecs_emps)
    paid_targets = {dt: [] for dt, _ in VOUCHER_TYPES}
    for emp in written:
        for v in per_emp.get(emp, {}).get("vouchers", []):
            paid_targets[v["type"]].append(v["name"])

    by_type = {dt: {"count": 0, "total": 0} for dt, _ in VOUCHER_TYPES}
    for emp in written:
        vouchers = per_emp.get(emp, {}).get("vouchers", [])
        for v in vouchers:
            by_type[v["type"]]["count"] += 1
        raw_total = sum(v["amount"] for v in vouchers)
        if raw_total <= 0:
            continue
        # attribute the SAME rounded amount that hits the file line, split by
        # voucher type, so composition totals reconcile to total_amount.
        emp_rounded = int(round(per_emp[emp]["amount"]))
        per_type_raw = {}
        for v in vouchers:
            per_type_raw[v["type"]] = per_type_raw.get(v["type"], 0.0) + v["amount"]
        types = list(per_type_raw)
        assigned = 0
        for i, t in enumerate(types):
            if i < len(types) - 1:
                share = int(round(emp_rounded * per_type_raw[t] / raw_total))
                by_type[t]["total"] += share
                assigned += share
            else:
                by_type[t]["total"] += emp_rounded - assigned

    return {
        "filename": filename,
        "content_base64": content_b64,
        "summary": {
            "from_date": str(from_date), "to_date": str(to_date), "payment_date": payment_date_value,
            "ve_line_count": len([r for r in rows_written if r.get("company") == VE_COMPANY]),
            "vecs_clubbed_count": 1 if vecs_total > 0 else 0,
            "vecs_employee_count": len(vecs_emps),
            "vecs_total_amount": int(round(vecs_total)),
            "total_amount": int(round(total_amount)),
            "lines": rows_written, "skipped": skipped, "by_type": by_type,
        },
        "paid_targets": paid_targets,
    }


@frappe.whitelist()
def mark_voucher_targets_paid(targets):
    """Atomically mark a payout file's vouchers as Paid.

    `targets` is the paid_targets map from generate_voucher_payment_file:
    {doctype: [voucher_name, ...]}. Reuses the canonical single-voucher
    mark-paid logic (api.mark_*_voucher_paid) so payment_status / paid_at /
    paid_by / audit / notification stay identical to the per-voucher path.
    Pre-checks skip already-Paid (idempotent), missing, and not-eligible
    targets and REPORT them rather than aborting (the bank file is already
    submitted by the time this runs, so leaving a payable voucher Unpaid is the
    dangerous outcome). Single transaction; unexpected error rolls the whole
    batch back; idempotent so retry is safe.
    """
    from vecrm.api import mark_travel_voucher_paid, mark_expense_voucher_paid

    _require_payout_access()

    if isinstance(targets, str):
        targets = json.loads(targets)
    if not isinstance(targets, dict):
        frappe.throw("targets must be a {doctype: [names]} map")

    fns = {
        "VECRM Travel Voucher": mark_travel_voucher_paid,
        "VECRM Expense Voucher": mark_expense_voucher_paid,
    }
    marked, already_paid, missing, not_eligible = [], [], [], []

    for dt, names in targets.items():
        fn = fns.get(dt)
        if not fn:
            continue
        for name in (names or []):
            try:
                doc = frappe.get_doc(dt, name)
            except frappe.DoesNotExistError:
                missing.append({"type": dt, "name": name})
                continue
            if getattr(doc, "payment_status", None) == "Paid":
                already_paid.append({"type": dt, "name": name})
                continue
            if doc.docstatus != 1 or getattr(doc, "approval_status", None) != "Approved":
                not_eligible.append({"type": dt, "name": name})
                continue
            fn(name)  # canonical single-voucher mark-paid (db_set + audit + notify)
            marked.append({"type": dt, "name": name, "amount": float(doc.total_amount or 0)})

    return {
        "marked_count": len(marked),
        "marked": marked,
        "already_paid": already_paid,
        "missing": missing,
        "not_eligible": not_eligible,
    }
