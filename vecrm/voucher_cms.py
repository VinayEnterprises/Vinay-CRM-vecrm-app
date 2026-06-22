import base64
import io
import json
from datetime import datetime

import frappe
from frappe.utils import flt, getdate

from vecrm.vecrm.utils.voucher_period import period_label, period_key

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

# Human label shown in the split payout breakdown. VECRM Travel Voucher IS the
# petrol voucher in portal/business language.
_TYPE_LABEL = {
    "VECRM Expense Voucher": "Expense Voucher",
    "VECRM Travel Voucher": "Petrol Voucher",
}
ADJUSTMENT_DOCTYPE = "VECRM Payout Adjustment"


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


def _load_overrides(voucher_doctype, names):
    """{voucher_name: advance_override(float)} for the given vouchers.

    Presence of a row IS the override (an explicit 0 means 'pay full, ignore
    the submitter's advance'); absence means fall back to the submitter's
    declared advance_amount. So a 0.0 in this map is meaningful, not 'unset'."""
    if not names:
        return {}
    rows = frappe.get_all(
        ADJUSTMENT_DOCTYPE,
        filters={"voucher_doctype": voucher_doctype, "voucher_name": ["in", list(names)]},
        fields=["voucher_name", "advance_override"],
    )
    return {r["voucher_name"]: flt(r["advance_override"]) for r in rows}


def _collect_vouchers(from_date, to_date):
    """Source of truth for payable vouchers. Returns
    {employee_docname: {'amount': float, 'vouchers': [voucher_dict]}}, where
    'amount' is the sum of NET payables (what actually gets paid) and each
    voucher_dict carries:
      type, name, amount (gross total), net_payable (override-aware), period,
      and for Expense vouchers advance_submitted / advance_override.
    Isolated so a future ERPNext source can replace just this function.

    S42: the payable amount is net_payable, not the gross total. For Expense
    vouchers an Accounts payout-page override (VECRM Payout Adjustment), when
    present, supersedes the submitter's advance. Travel (petrol) vouchers have
    no advance, so net == total."""
    per_emp = {}
    for dt, date_field in VOUCHER_TYPES:
        is_expense = dt == "VECRM Expense Voucher"
        fields = ["name", "submitter", "total_amount", date_field]
        if is_expense:
            fields += ["advance_received", "advance_amount"]
        rows = frappe.get_all(
            dt,
            filters={
                "approval_status": "Approved",
                "payment_status": "Unpaid",
                date_field: ["between", [from_date, to_date]],
            },
            fields=fields,
        )
        overrides = _load_overrides(dt, [r["name"] for r in rows]) if is_expense else {}
        for r in rows:
            emp = r["submitter"]
            if not emp:
                continue
            total = flt(r["total_amount"])
            if is_expense:
                advance_submitted = flt(r.get("advance_amount")) if r.get("advance_received") else 0.0
                override = overrides.get(r["name"])  # None when no override row
                effective_advance = override if override is not None else advance_submitted
                net = total - effective_advance
            else:
                advance_submitted = None
                override = None
                net = total
            if net < 0:
                net = 0.0
            slot = per_emp.setdefault(emp, {"amount": 0.0, "vouchers": []})
            slot["amount"] += net
            slot["vouchers"].append({
                "type": dt,
                "name": r["name"],
                "amount": total,
                "net_payable": net,
                "period": period_label(r.get(date_field)),
                "advance_submitted": advance_submitted,
                "advance_override": override,
            })
    return per_emp


def _employee_label(emp):
    """(employee_name, employee_id, company) for a VECRM Employee docname."""
    try:
        edoc = frappe.get_doc("VECRM Employee", emp)
        return edoc.employee_name, edoc.name, (edoc.company or "").strip()
    except Exception:
        return emp, emp, None


def _shape_people(per_emp, only_emps=None):
    """Shape _collect_vouchers output into the per-person split payout view:
    [{employee, employee_id, name, company, vouchers:[...], total_payable}].
    Each EV voucher carries advance_submitted + advance_override so Accounts
    can see and edit the override. total_payable = Σ net_payable (S42)."""
    people = []
    for emp in sorted(per_emp.keys()):
        if only_emps is not None and emp not in only_emps:
            continue
        slot = per_emp[emp]
        name, emp_id, company = _employee_label(emp)
        vouchers = []
        total_payable = 0.0
        for v in slot["vouchers"]:
            entry = {
                "type": _TYPE_LABEL.get(v["type"], v["type"]),
                "doctype": v["type"],
                "name": v["name"],
                "period": v["period"],
                "amount": v["amount"],
                "net_payable": v["net_payable"],
            }
            if v["type"] == "VECRM Expense Voucher":
                entry["advance_submitted"] = v["advance_submitted"]
                entry["advance_override"] = v["advance_override"]
            vouchers.append(entry)
            total_payable += v["net_payable"]
        # Stable order — petrol then expense (by label), then voucher name.
        vouchers.sort(key=lambda e: (e["type"], e["name"]))
        people.append({
            "employee": emp,
            "employee_id": emp_id,
            "name": name,
            "company": company,
            "vouchers": vouchers,
            "total_payable": total_payable,
        })
    return people


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
        # Compose on NET payable (S42) — the file line pays net, so the per-type
        # split must reconcile to the same net per-emp amount, not the gross.
        raw_total = sum(v["net_payable"] for v in vouchers)
        if raw_total <= 0:
            continue
        # attribute the SAME rounded amount that hits the file line, split by
        # voucher type, so composition totals reconcile to total_amount.
        emp_rounded = int(round(per_emp[emp]["amount"]))
        per_type_raw = {}
        for v in vouchers:
            per_type_raw[v["type"]] = per_type_raw.get(v["type"], 0.0) + v["net_payable"]
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
            # Per-person Petrol/Expense split (S42) for the written employees,
            # so the payout page can show the breakdown alongside the file.
            "breakdown": _shape_people(per_emp, only_emps=written),
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


@frappe.whitelist()
def get_voucher_payout_breakdown(from_date=None, to_date=None):
    """Per-person, per-type, per-period payout breakdown (S42).

    The interactive payout-page source (no bank file generated). Splits Petrol
    (Travel) vs Expense vouchers per person per half-month period, with each
    Expense voucher's submitter advance + any Accounts override, and a
    net-payable total per person. Same auth tier as the file generator —
    exposes amounts but not bank account numbers."""
    _require_payout_access()
    if not (from_date and to_date):
        frappe.throw("from_date and to_date are required")
    from_date = getdate(from_date)
    to_date = getdate(to_date)
    if from_date > to_date:
        frappe.throw("from_date cannot be after to_date")

    per_emp = _collect_vouchers(from_date, to_date)
    people = _shape_people(per_emp)
    grand_total = sum(p["total_payable"] for p in people)
    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "people": people,
        "person_count": len(people),
        "grand_total_payable": grand_total,
    }


@frappe.whitelist()
def set_payout_advance_override(voucher_name, amount=None, voucher_doctype="VECRM Expense Voucher"):
    """Upsert (or clear) the payout-time advance override for a voucher (S42).

    Off-record: writes to VECRM Payout Adjustment, never to the voucher itself,
    so the employee's submitted record stays clean. Single-row-per-voucher
    upsert (no append log). A blank/null amount CLEARS the override (deletes the
    row), reverting to the submitter's declared advance. An explicit 0 means
    'pay full — ignore the submitter's advance'."""
    _require_payout_access()
    if not voucher_name:
        frappe.throw("voucher_name is required")
    if not frappe.db.exists(voucher_doctype, voucher_name):
        frappe.throw(f"{voucher_doctype} {voucher_name!r} does not exist")

    existing = frappe.db.get_value(
        ADJUSTMENT_DOCTYPE,
        {"voucher_doctype": voucher_doctype, "voucher_name": voucher_name},
        "name",
    )

    # Blank / null clears the override (revert to the submitter's advance).
    if amount is None or str(amount).strip() == "":
        if existing:
            frappe.delete_doc(ADJUSTMENT_DOCTYPE, existing, ignore_permissions=True)
            frappe.db.commit()
        return {"voucher_name": voucher_name, "advance_override": None, "cleared": True}

    amt = flt(amount)
    if amt < 0:
        frappe.throw("Advance override cannot be negative")
    total = flt(frappe.db.get_value(voucher_doctype, voucher_name, "total_amount"))
    if amt > total:
        frappe.throw(f"Advance override (₹{amt}) cannot exceed the voucher total (₹{total}).")

    date_field = dict(VOUCHER_TYPES).get(voucher_doctype, "expense_date")
    vdate = frappe.db.get_value(voucher_doctype, voucher_name, date_field)
    pkey = period_key(vdate) if vdate else None
    actor = (frappe.session.data or {}).get("vecrm_email") or frappe.session.user
    now = frappe.utils.now_datetime()

    if existing:
        doc = frappe.get_doc(ADJUSTMENT_DOCTYPE, existing)
        doc.advance_override = amt
        doc.period_key = pkey
        doc.set_by = actor
        doc.set_at = now
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": ADJUSTMENT_DOCTYPE,
            "voucher_doctype": voucher_doctype,
            "voucher_name": voucher_name,
            "advance_override": amt,
            "period_key": pkey,
            "set_by": actor,
            "set_at": now,
        }).insert(ignore_permissions=True)
    frappe.db.commit()

    net = max(0.0, total - amt)
    return {
        "voucher_name": voucher_name,
        "advance_override": amt,
        "net_payable": net,
        "cleared": False,
    }
