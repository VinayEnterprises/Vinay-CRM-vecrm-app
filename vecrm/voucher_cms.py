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
VOUCHER_LAST_DATA_COL = 13          # S73: last written column (see _write)

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
            fields += ["advance_received", "advance_amount", "site",
                       "advance_consumed", "advance_ref", "carry_forward_amount"]
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
        travel_sites = {}
        if not is_expense and rows:
            v_lines = frappe.get_all(
                "VECRM Visit Line",
                filters={"parent": ["in", [r["name"] for r in rows]]},
                fields=["parent", "customer_name"],
                order_by="idx asc",
            )
            for line in v_lines:
                parent = line["parent"]
                cust = (line["customer_name"] or "").strip()
                if cust:
                    travel_sites.setdefault(parent, []).append(cust)
            for parent, cust_list in list(travel_sites.items()):
                unique_custs = list(dict.fromkeys(cust_list))
                travel_sites[parent] = ", ".join(unique_custs)

        for r in rows:
            emp = r["submitter"]
            if not emp:
                continue
            total = flt(r["total_amount"])
            if is_expense:
                # S132 R3: the Accounts override is ON-RECORD — it writes back to
                # the voucher's own advance_received / advance_amount — so the
                # voucher is the single source of the advance figure. The
                # adjustment row is read ONLY to badge the row as Accounts-set;
                # its value no longer enters the arithmetic. One fact, one writer.
                advance_submitted = flt(r.get("advance_amount")) if r.get("advance_received") else 0.0
                override = overrides.get(r["name"])  # presence == set by Accounts
                consumed = flt(r.get("advance_consumed"))
                net = total - advance_submitted - consumed
                site_val = (r.get("site") or "").strip() or "—"
            else:
                advance_submitted = None
                override = None
                consumed = 0.0
                net = total
                site_val = travel_sites.get(r["name"]) or "—"
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
                "advance_consumed": consumed if is_expense else None,
                "advance_ref": r.get("advance_ref") if is_expense else None,
                "carry_forward_amount": flt(r.get("carry_forward_amount")) if is_expense else None,
                "site": site_val,
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
                "site": v["site"],
            }
            if v["type"] == "VECRM Expense Voucher":
                entry["advance_submitted"] = v["advance_submitted"]
                entry["advance_override"] = v["advance_override"]
                # S132: carried through to the payout page so a recovery can be
                # read off the row. S42 collected these and dropped them here,
                # which is why the page showed unexplained deductions for two
                # months and why the P1 portal had to re-fetch them itself.
                entry["advance_consumed"] = v["advance_consumed"]
                entry["advance_ref"] = v["advance_ref"]
                entry["carry_forward_amount"] = v["carry_forward_amount"]
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

    # S132: report carry still outstanding for the people in this run.
    #
    # WARNS, does not refuse. Deliberate, and the sequencing matters: the
    # portal has no Settle action yet, so a hard refusal here would block the
    # payout with no way for Accounts to clear the block, which is how you
    # strand a payroll. Mirrors PF-14's warn-before-export in the HRMS lane.
    # This becomes a hard gate in the same release that ships the Settle
    # button, not before. Best-effort: a failure to compute the warning must
    # never stop a bank file that is otherwise correct.
    unsettled = []
    try:
        from vecrm.vecrm.doctype.vecrm_expense_voucher.vecrm_expense_voucher import (
            list_outstanding_carry_forward as _outstanding,
        )
        for _emp in per_emp:
            for _row in _outstanding(_emp):
                if flt(_row.get("outstanding")) > 0:
                    unsettled.append({
                        "employee": _emp,
                        "source": _row["name"],
                        "expense_date": str(_row.get("expense_date") or ""),
                        "carry_forward_amount": flt(_row.get("carry_forward_amount")),
                        "outstanding": flt(_row["outstanding"]),
                    })
    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         "generate_voucher_payment_file.unsettled_carry")

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
        # S73: match kotak_cms._write_cms_row exactly —
        #   1. EVERY cell written with the Text ('@') style, not just cols 6/13,
        #      so IFSC / codes / dates never infer General/Number.
        #   2. str()-coerce every value — xlwt infers Number from Python
        #      int/float (the amount in col 7) even under a Text style.
        #   3. Only cols 0..LAST_DATA_COL are written — no phantom trailing
        #      cells, so Ctrl+End lands on the last real column.
        for col in range(VOUCHER_LAST_DATA_COL + 1):
            sheet.write(state["row"], col, str(values[col]), text_style)
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
            # S132: advance still owed by people in this run, not recovered by
            # it. Informational; run settle_payout_cycle to absorb what this
            # cycle can absorb before generating the file.
            "unsettled_carry": {
                "count": len(unsettled),
                "employees": len(set(u["employee"] for u in unsettled)),
                "total": round(sum(u["outstanding"] for u in unsettled), 2),
                "rows": unsettled,
            },
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
    """Record (or clear) the advance Accounts holds against a voucher.

    S132 R1 + R3. ON-RECORD, reversing S42's off-record ruling, deliberately.

    Accounts hold the authority to record an advance the submitter forgot to
    declare — field engineers are non-technical and miss the tick routinely —
    and that authority is only useful if the recorded figure IS the advance.
    So this writes back to the voucher's own advance_received / advance_amount,
    recomputes net_payable and carry_forward_amount by the same formula
    validate() uses, and emits an audit event the employee's own voucher view
    renders. One fact, one writer. Every defect in the S132 chain traced back
    to one fact (how much cash the employee holds) having two shadows.

    The VECRM Payout Adjustment row survives as the AUDIT of who set it, when,
    and what it replaced (advance_before) — not as the override itself.

    R1: the amount MAY exceed the voucher total. A ₹2,000 advance against a
    ₹1,520 claim is the ordinary case, not an error. The excess becomes
    carry_forward_amount and settles at the next payout run.

    Clearing restores advance_before, the submitter's own declaration.
    """
    _require_payout_access()
    if not voucher_name:
        frappe.throw("voucher_name is required")
    if voucher_doctype != "VECRM Expense Voucher":
        # Travel vouchers carry no advance fields at all, so an on-record
        # override has nowhere to land. Narrowed deliberately in S132; the
        # portal has only ever sent Expense vouchers here.
        frappe.throw(
            f"Advance overrides apply only to VECRM Expense Voucher, not {voucher_doctype!r}."
        )
    if not frappe.db.exists(voucher_doctype, voucher_name):
        frappe.throw(f"{voucher_doctype} {voucher_name!r} does not exist")

    voucher = frappe.get_doc(voucher_doctype, voucher_name)
    if voucher.docstatus != 1:
        frappe.throw(
            f"{voucher_name} is not submitted (docstatus={voucher.docstatus}); "
            f"an advance can only be recorded against a submitted voucher."
        )

    total = flt(voucher.total_amount)
    consumed = flt(voucher.advance_consumed)
    already_drawn = _carry_already_consumed(voucher_name)
    before_received = 1 if voucher.advance_received else 0
    before_amount = flt(voucher.advance_amount) if voucher.advance_received else 0.0

    existing = frappe.db.get_value(
        ADJUSTMENT_DOCTYPE,
        {"voucher_doctype": voucher_doctype, "voucher_name": voucher_name},
        "name",
    )

    # Blank / null clears: restore the submitter's own declaration exactly.
    if amount is None or str(amount).strip() == "":
        if not existing:
            return {"voucher_name": voucher_name, "advance_override": None, "cleared": True}
        restore = flt(frappe.db.get_value(ADJUSTMENT_DOCTYPE, existing, "advance_before"))
        _apply_advance_on_record(
            voucher, restore, consumed, already_drawn,
            reason="override cleared, restored to the submitter's declaration",
        )
        frappe.delete_doc(ADJUSTMENT_DOCTYPE, existing, ignore_permissions=True)
        frappe.db.commit()
        _audit_override(voucher, before_received, before_amount, restore, cleared=True)
        return {
            "voucher_name": voucher_name,
            "advance_override": None,
            "advance_amount": restore,
            "net_payable": flt(frappe.db.get_value(voucher_doctype, voucher_name, "net_payable")),
            "cleared": True,
        }

    amt = flt(amount)
    if amt < 0:
        frappe.throw("Advance recorded by Accounts cannot be negative")
    # R1: NO upper bound against the voucher total. An advance larger than the
    # claim is the ordinary case and becomes carry_forward_amount.

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
        # advance_before is written ONCE, at first override. Later edits must
        # not overwrite it or a clear would restore the previous OVERRIDE
        # instead of the submitter's own declaration.
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": ADJUSTMENT_DOCTYPE,
            "voucher_doctype": voucher_doctype,
            "voucher_name": voucher_name,
            "advance_override": amt,
            "advance_before": before_amount,
            "period_key": pkey,
            "set_by": actor,
            "set_at": now,
        }).insert(ignore_permissions=True)

    _apply_advance_on_record(
        voucher, amt, consumed, already_drawn,
        reason=f"advance recorded by Accounts ({actor})",
    )
    frappe.db.commit()
    _audit_override(voucher, before_received, before_amount, amt, cleared=False)

    fresh = frappe.db.get_value(
        voucher_doctype, voucher_name,
        ["advance_amount", "net_payable", "carry_forward_amount"],
        as_dict=True,
    )
    return {
        "voucher_name": voucher_name,
        "advance_override": amt,
        "advance_amount": flt(fresh.advance_amount),
        "net_payable": flt(fresh.net_payable),
        "carry_forward_amount": flt(fresh.carry_forward_amount),
        "cleared": False,
    }


def _carry_already_consumed(voucher_name):
    """Rupees already drawn from this voucher's carry by later vouchers."""
    row = frappe.db.sql(
        """SELECT COALESCE(SUM(amount), 0) FROM `tabVECRM Carry Consumption`
           WHERE parent = %s AND parenttype = 'VECRM Expense Voucher'
             AND parentfield = 'carry_consumptions'""",
        (voucher_name,),
    )
    return flt(row[0][0]) if row else 0.0


def _apply_advance_on_record(voucher, advance, consumed, already_drawn, reason=""):
    """Write the advance onto the voucher and recompute, with a read-back gate.

    Mirrors VECRMExpenseVoucher.validate() exactly:
        applied = min(advance, total)
        net_payable = total - applied      (floored at 0, less carry consumed)
        carry_forward_amount = max(0, advance - total)

    Refuses to shrink a carry below what later vouchers have ALREADY drawn from
    it — that would leave an over-consumed source and silently double-recover
    from the employee. The remedy for such a case is a corrective voucher, not
    a quieter number here.
    """
    total = flt(voucher.total_amount)
    advance = flt(advance)
    applied = min(advance, total)
    new_carry = max(0.0, advance - total)
    new_net = max(0.0, total - applied - flt(consumed))

    if new_carry + 0.005 < flt(already_drawn):
        frappe.throw(
            f"Cannot set the advance on {voucher.name} to ₹{advance}: that leaves a "
            f"carry-forward of ₹{new_carry}, but ₹{already_drawn} has already been "
            f"recovered from it by later vouchers. Raise a corrective voucher instead."
        )

    voucher.db_set("advance_received", 1 if advance > 0 else 0, update_modified=False)
    voucher.db_set("advance_amount", advance, update_modified=False)
    voucher.db_set("net_payable", new_net, update_modified=False)
    voucher.db_set("carry_forward_amount", new_carry, update_modified=False)

    # Rule E: never trust the writer's return. Re-SELECT and compare.
    check = frappe.db.get_value(
        voucher.doctype, voucher.name,
        ["advance_received", "advance_amount", "net_payable", "carry_forward_amount"],
        as_dict=True,
    )
    expected_recv = 1 if advance > 0 else 0
    if (
        int(check.advance_received or 0) != expected_recv
        or abs(flt(check.advance_amount) - advance) > 0.0001
        or abs(flt(check.net_payable) - new_net) > 0.0001
        or abs(flt(check.carry_forward_amount) - new_carry) > 0.0001
    ):
        frappe.throw(
            f"Advance write verification FAILED on {voucher.name} ({reason}): "
            f"read-back {dict(check)} vs expected received={expected_recv}, "
            f"advance={advance}, net={new_net}, carry={new_carry}."
        )
    return {"advance": advance, "net_payable": new_net, "carry_forward_amount": new_carry}


def _audit_override(voucher, before_received, before_amount, after_amount, cleared):
    """Emit the advance-override audit event, best-effort.

    The employee's own voucher view renders this, so a debt Accounts recorded
    is never invisible to the person carrying it. Best-effort by design: an
    audit-log failure must not roll back a money write that already verified.
    """
    try:
        voucher._audit("voucher.expense.advance_overridden", {
            "actor_employee": (frappe.session.data or {}).get("vecrm_employee_phone"),
            "actor_role": (frappe.session.data or {}).get("vecrm_employee_role"),
            "advance_before": float(before_amount or 0),
            "advance_received_before": int(before_received or 0),
            "advance_after": float(after_amount or 0),
            "cleared": bool(cleared),
            "total_amount": float(voucher.total_amount or 0),
            "from_state": "advance_declared_by_submitter" if not before_received
            else "advance_%s" % before_amount,
            "to_state": "advance_%s" % after_amount,
        })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "set_payout_advance_override.audit")


@frappe.whitelist()
def settle_payout_cycle(from_date=None, to_date=None, dry_run=1):
    """Settle advance carry-forward across a whole payout cycle (S132 R2).

    Ruling B (S75) consumed carry at APPROVAL time. That made the outcome a
    function of the order the approver happened to click: consumption looked
    backwards only at sources already approved, and returned immediately when
    the consumer's own net was zero. Measured on Gunjan Pandya's batch,
    approved inside 66 seconds on 5 Sep 2026, the source raising a Rs 480 carry
    was approved second from last and nothing remained to absorb it.

    Settlement now happens once, here, over the whole cycle:

      consumers  the employee's EXPENSE vouchers in [from_date, to_date] that
                 are Approved + Unpaid and still have net_payable > 0,
                 ordered by voucher name (deterministic, and voucher numbers
                 are sequential so this is also chronological in practice)
      sources    that same employee's vouchers with outstanding carry, ANY
                 date, oldest approved_at first — a carry raised in July
                 settles against a September claim, which is the point
      apply      FIFO: min(source_remaining, consumer_remaining), walking
                 sources outer and consumers inner, so one consumer can absorb
                 from SEVERAL sources in one pass. Ruling B could not express
                 that: it had one advance_ref slot and a LIMIT 1.

    Each consumption writes a VECRM Carry Consumption row on the SOURCE, and
    reduces the consumer's net_payable. advance_consumed / advance_ref on the
    consumer are still maintained as the aggregate and primary-source mirror,
    because the payout page and the portal read them.

    dry_run (default 1) returns the full plan and writes NOTHING. Run it, read
    it, then run again with dry_run=0. Every live write is read back and
    verified before the next one (Rule E: never trust the writer's return).

    Idempotent: a (source, consumer) pair that already has a row is skipped,
    and a consumer whose net is already reduced offers nothing to absorb.

    DELIBERATE SCOPE: Travel (petrol) vouchers do not absorb carry. Every
    source is an Expense voucher, the advance was given against expenses, and
    Travel has no net_payable column to reduce. Where an employee's cycle has
    no expense net to absorb against, the carry stays open and is VISIBLE on
    the payout page, so Accounts can act deliberately rather than the system
    guessing. Revisit only if the visible balance shows this biting.
    """
    _require_payout_access()
    if not (from_date and to_date):
        frappe.throw("from_date and to_date are required")
    from_date = getdate(from_date)
    to_date = getdate(to_date)
    if from_date > to_date:
        frappe.throw("from_date cannot be after to_date")
    dry = str(dry_run).strip().lower() not in ("0", "false", "no", "")

    from vecrm.vecrm.doctype.vecrm_expense_voucher.vecrm_expense_voucher import (
        list_outstanding_carry_forward as _outstanding,
    )

    per_emp = _collect_vouchers(from_date, to_date)
    actor = (frappe.session.data or {}).get("vecrm_email") or frappe.session.user
    now = frappe.utils.now_datetime()

    # --- plan (pure; no writes) ------------------------------------------
    plan = []
    for emp in sorted(per_emp.keys()):
        consumers = sorted(
            [
                {"name": v["name"], "remaining": flt(v["net_payable"]), "period": v["period"]}
                for v in per_emp[emp]["vouchers"]
                if v["type"] == "VECRM Expense Voucher" and flt(v["net_payable"]) > 0
            ],
            key=lambda c: c["name"],
        )
        if not consumers:
            continue
        sources = [s for s in _outstanding(emp) if flt(s.get("outstanding")) > 0]
        for src in sources:
            src_left = flt(src["outstanding"])
            for con in consumers:
                if src_left <= 0.005:
                    break
                if con["remaining"] <= 0.005 or con["name"] == src["name"]:
                    continue
                pull = round(min(src_left, con["remaining"]), 2)
                if pull <= 0:
                    continue
                plan.append({
                    "employee": emp,
                    "source": src["name"],
                    "source_date": str(src.get("expense_date") or ""),
                    "source_carry": flt(src.get("carry_forward_amount")),
                    "consumer": con["name"],
                    "consumer_period": con["period"],
                    "amount": pull,
                    "consumer_net_before": round(con["remaining"], 2),
                    "consumer_net_after": round(con["remaining"] - pull, 2),
                })
                src_left = round(src_left - pull, 2)
                con["remaining"] = round(con["remaining"] - pull, 2)

    total = round(sum(p["amount"] for p in plan), 2)
    result = {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "dry_run": dry,
        "employees_in_cycle": len(per_emp),
        "employees_settled": len(set(p["employee"] for p in plan)),
        "consumptions": len(plan),
        "total_recovered": total,
        "plan": plan,
        "applied": [],
        "skipped_existing": [],
    }
    if dry or not plan:
        return result

    # --- apply (writes; one verified step at a time) ----------------------
    for p in plan:
        dup = frappe.db.sql(
            """SELECT name FROM `tabVECRM Carry Consumption`
               WHERE parent = %s AND parenttype = 'VECRM Expense Voucher'
                 AND parentfield = 'carry_consumptions'
                 AND consumer_doctype = 'VECRM Expense Voucher'
                 AND consumer_name = %s""",
            (p["source"], p["consumer"]),
        )
        if dup:
            result["skipped_existing"].append(
                {"source": p["source"], "consumer": p["consumer"]}
            )
            continue

        con = frappe.db.get_value(
            "VECRM Expense Voucher", p["consumer"],
            ["net_payable", "advance_consumed", "advance_ref", "expense_date"],
            as_dict=True,
        )
        net_before = flt(con.net_payable)
        if net_before + 0.005 < p["amount"]:
            frappe.throw(
                f"settle_payout_cycle ABORT on {p['consumer']}: planned pull of "
                f"Rs {p['amount']} exceeds its current net payable of Rs {net_before}. "
                f"The cycle moved under the plan; re-run the dry run."
            )
        new_net = round(net_before - p["amount"], 2)
        new_consumed = round(flt(con.advance_consumed) + p["amount"], 2)
        new_ref = (con.advance_ref or "").strip() or p["source"]

        idx = frappe.db.sql(
            """SELECT IFNULL(MAX(idx), 0) + 1 FROM `tabVECRM Carry Consumption`
               WHERE parent = %s""",
            (p["source"],),
        )[0][0]
        row_name = frappe.generate_hash(length=10)
        frappe.db.sql(
            """
            INSERT INTO `tabVECRM Carry Consumption`
                (name, creation, modified, modified_by, owner, docstatus, idx,
                 parent, parentfield, parenttype,
                 consumer_doctype, consumer_name, amount,
                 settled_at, settled_by, period_key)
            VALUES
                (%(name)s, NOW(), NOW(), %(owner)s, %(owner)s, 1, %(idx)s,
                 %(parent)s, 'carry_consumptions', 'VECRM Expense Voucher',
                 'VECRM Expense Voucher', %(consumer)s, %(amount)s,
                 %(settled_at)s, %(actor)s, %(period_key)s)
            """,
            {
                "name": row_name, "actor": actor, "idx": idx,
                # owner / modified_by are Link to User. `actor` is the portal
                # person's vecrm_email, which is NOT a User on this bench —
                # portal-bff@ is the only one — so passing it would write two
                # dangling links on every settlement row. The human identity
                # belongs in settled_by, which is Data and already carries it.
                "owner": frappe.session.user,
                "parent": p["source"], "consumer": p["consumer"],
                "amount": p["amount"], "settled_at": now,
                "period_key": period_key(con.expense_date) if con.expense_date else None,
            },
        )

        voucher = frappe.get_doc("VECRM Expense Voucher", p["consumer"])
        voucher.db_set("net_payable", new_net, update_modified=False)
        voucher.db_set("advance_consumed", new_consumed, update_modified=False)
        voucher.db_set("advance_ref", new_ref, update_modified=False)

        # Rule E read-back, on BOTH sides of the fact.
        check = frappe.db.get_value(
            "VECRM Expense Voucher", p["consumer"],
            ["net_payable", "advance_consumed", "advance_ref"], as_dict=True,
        )
        row = frappe.db.sql(
            "SELECT amount, consumer_name FROM `tabVECRM Carry Consumption` WHERE name = %s",
            (row_name,), as_dict=True,
        )
        if (
            abs(flt(check.net_payable) - new_net) > 0.0001
            or abs(flt(check.advance_consumed) - new_consumed) > 0.0001
            or (check.advance_ref or "") != new_ref
            or not row
            or abs(flt(row[0]["amount"]) - p["amount"]) > 0.0001
            or row[0]["consumer_name"] != p["consumer"]
        ):
            frappe.throw(
                f"settle_payout_cycle write verification FAILED: source {p['source']} "
                f"-> consumer {p['consumer']} Rs {p['amount']}. Voucher read-back "
                f"{dict(check)}, child row {row}. Nothing further applied."
            )
        result["applied"].append({
            "source": p["source"], "consumer": p["consumer"], "amount": p["amount"],
            "net_before": net_before, "net_after": new_net, "row": row_name,
        })

    # --- invariant, BEFORE the commit so a violation can still roll back ---
    # This ran after the commit as first written. A post-commit assertion can
    # only report a bad state, never undo it. Patch v1_11 already establishes
    # the correct order: assert, then commit. Reading inside the transaction
    # still proves the writes took effect, which is what the Rule E read-backs
    # above are for; durability is not what this check is testing.
    over = frappe.db.sql(
        """
        SELECT src.name, src.carry_forward_amount, SUM(cc.amount) AS consumed
        FROM `tabVECRM Expense Voucher` src
        JOIN `tabVECRM Carry Consumption` cc
          ON cc.parent = src.name AND cc.parentfield = 'carry_consumptions'
        GROUP BY src.name, src.carry_forward_amount
        HAVING SUM(cc.amount) - src.carry_forward_amount > 0.005
        """,
        as_dict=True,
    )
    if over:
        frappe.throw(
            "settle_payout_cycle POST-assert FAILED, consumption exceeds carry on: "
            + ", ".join(f"{r['name']} ({r['consumed']} > {r['carry_forward_amount']})"
                        for r in over)
        )

    frappe.db.commit()
    result["applied_total"] = round(sum(a["amount"] for a in result["applied"]), 2)
    return result
