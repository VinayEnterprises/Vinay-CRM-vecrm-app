"""S143 voucher-due (W2) reminders and voucher mails (VECRM).

Rulings 24 Sep 2026 (Ajay):
- W2 roles: Field Engineer, Network Security Engineer, Store Executive.
- Pop-up days: 16th to 20th (this month's H1) and 1st to 5th (previous
  month's H2). Personal reminders: 15th to 20th and last day to 5th.
- Filed = a submitted Travel Voucher for the period, or a "No petrol claim
  this period" declaration (VECRM Voucher Declaration). A draft is not filed.
- Mail recipients' addresses are VECRM Employee.vecrm_email.
- These voucher mails carry no per-mail audit BCC (bcc_policy="none"); one
  daily summary goes to the audit mailbox instead.
- Submission: the functional head is mailed per submission; Accounts, HR and
  Admin get one daily list.
- Paid: the engineer is told the amount actually paid (net of advance and
  carry-forward, the same arithmetic as the bank file).

Everything here is best-effort except the declaration write: a mail failure
never blocks a voucher action. Dates are site-local (IST).
"""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime, time, timedelta

import frappe
from frappe.utils import flt, getdate

from vecrm.vecrm.utils.voucher_period import (
    on_time_day,
    period_key,
    period_label,
    submit_window,
)

W2_ROLES = ("Field Engineer", "Network Security Engineer", "Store Executive")
HEAD_ROLES = ("Head of Engineers", "Head of Stores", "Sales Head",
              "Senior Business Acceleration Executive")
DAILY_LIST_ROLES = ("Accounts Executive", "HR", "Head of Accounts & HR", "Admin")
AUDIT_MAILBOX = "attach@anusuya.ai"
DECLARATION_DT = "VECRM Voucher Declaration"
PORTAL = "https://app.anusuya.ai"
PETROL_URL = PORTAL + "/petrol-vouchers"
OVERVIEW_URL = PORTAL + "/voucher-overview"


# ── dates ────────────────────────────────────────────────────────────────

def _today() -> date:
    return getdate(frappe.utils.today())


def _last_day(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def window_for(d) -> dict | None:
    """The period a given day serves, or None on a quiet day.

    {"anchor": first day of the period, "remind": bool, "popup": bool}
    """
    d = getdate(d)
    last = _last_day(d.year, d.month)
    if 15 <= d.day <= 20:
        return {"anchor": date(d.year, d.month, 1), "remind": True, "popup": d.day >= 16}
    if d.day == last:
        return {"anchor": date(d.year, d.month, 16), "remind": True, "popup": False}
    if 1 <= d.day <= 5:
        prev = d.replace(day=1) - timedelta(days=1)
        return {"anchor": date(prev.year, prev.month, 16), "remind": True, "popup": True}
    return None


def _bounds(anchor: date) -> tuple[date, date]:
    if anchor.day <= 15:
        return date(anchor.year, anchor.month, 1), date(anchor.year, anchor.month, 15)
    return (date(anchor.year, anchor.month, 16),
            date(anchor.year, anchor.month, _last_day(anchor.year, anchor.month)))


def _deadline(anchor: date) -> datetime:
    return submit_window(anchor)[1]


def _fmt_day(d) -> str:
    return getdate(d).strftime("%d %b %Y")


# ── state ────────────────────────────────────────────────────────────────

def filed_state(employee: str, anchor: date) -> dict:
    """submitted > declared > draft > none for one employee and period."""
    start, end = _bounds(anchor)
    pk = period_key(anchor)
    rows = frappe.get_all(
        "VECRM Travel Voucher",
        filters={"submitter": employee, "business_date": ["between", [start, end]],
                 "docstatus": ["<", 2]},
        fields=["name", "docstatus"],
        ignore_permissions=True,
    )
    submitted = [r.name for r in rows if r.docstatus == 1]
    if submitted:
        return {"state": "submitted", "voucher": submitted[0], "period_key": pk}
    if frappe.db.exists(DECLARATION_DT, {"employee": employee, "period_key": pk}):
        return {"state": "declared", "period_key": pk}
    drafts = [r.name for r in rows if r.docstatus == 0]
    if drafts:
        lines = frappe.db.count("VECRM Visit Line", {"parent": drafts[0]})
        return {"state": "draft", "draft": drafts[0], "lines": int(lines or 0), "period_key": pk}
    return {"state": "none", "period_key": pk}


def _w2_employees() -> list:
    return frappe.get_all(
        "VECRM Employee",
        filters={"role": ["in", list(W2_ROLES)], "vecrm_account_status": "Active"},
        fields=["name", "employee_name", "role", "vecrm_email"],
        order_by="employee_name asc",
        ignore_permissions=True,
    )


def head_roles_for(role: str) -> list:
    """The functional head roles for a submitter role: the leading head
    entries of its VOUCHER_APPROVER_SETS row (routing engineers already see).
    Empty for heads, Admin and anything unmapped."""
    from vecrm.vecrm.utils.roles import VOUCHER_APPROVER_SETS

    out = []
    for r in VOUCHER_APPROVER_SETS.get(role or "", []):
        if r in HEAD_ROLES:
            out.append(r)
        else:
            break
    return out


def _people_in_roles(roles) -> list:
    if not roles:
        return []
    return frappe.get_all(
        "VECRM Employee",
        filters={"role": ["in", list(roles)], "vecrm_account_status": "Active"},
        fields=["name", "employee_name", "role", "vecrm_email"],
        ignore_permissions=True,
    )


# ── mail plumbing ────────────────────────────────────────────────────────

def _esc(v) -> str:
    return frappe.utils.escape_html(str(v if v is not None else ""))


def _inr(amount) -> str:
    """Indian digit grouping, two decimals: 123456.5 -> Rs 1,23,456.50"""
    amount = round(flt(amount), 2)
    neg = amount < 0
    whole, frac = ("%.2f" % abs(amount)).split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + "Rs " + whole + "." + frac


def _p(text_html: str) -> str:
    return '<p style="margin:0 0 14px;font-size:15px;line-height:1.55;color:#0F172A;">%s</p>' % text_html


def _link(url: str, label: str) -> str:
    return '<a href="%s" style="color:#EA580C;font-weight:600;">%s</a>' % (_esc(url), _esc(label))


def _table(headers, rows) -> str:
    th = "".join('<th style="text-align:left;padding:6px 8px;border-bottom:1px solid #E2E8F0;'
                 'font-size:12px;color:#64748B;">%s</th>' % _esc(h) for h in headers)
    body = ""
    for r in rows:
        body += "<tr>" + "".join('<td style="padding:6px 8px;border-bottom:1px solid #F1F5F9;'
                                 'font-size:14px;">%s</td>' % _esc(c) for c in r) + "</tr>"
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%%" '
            'style="border-collapse:collapse;margin:0 0 14px;"><tr>%s</tr>%s</table>' % (th, body))


def _send(to, subject: str, body_html: str, preheader: str, dry_run: bool, log: list) -> bool:
    to = [a for a in ([to] if isinstance(to, str) else list(to or [])) if a]
    log.append({"to": to, "subject": subject})
    if dry_run or not to:
        return False
    try:
        from vecrm.email_utils import send_email
        from vecrm.vecrm.email_templates import render_email_layout

        send_email(to=to, subject=subject,
                   html_body=render_email_layout(preheader=preheader, body_html=body_html),
                   bcc_policy="none")
        return True
    except Exception:
        frappe.log_error(title="S143 voucher mail failed",
                         message="to=%s subject=%s\n%s" % (to, subject, frappe.get_traceback()))
        return False


def _once(key: str) -> bool:
    """True the first time a key is seen today (guards double scheduler fires)."""
    ck = "vecrm_s143_once:%s:%s" % (_today().isoformat(), key)
    if frappe.cache().get_value(ck):
        return False
    frappe.cache().set_value(ck, 1, expires_in_sec=36 * 3600)
    return True


# ── portal read + declaration ────────────────────────────────────────────

def get_due(phone: str, role: str) -> dict:
    """What the portal pop-up needs for the signed-in employee."""
    if role not in W2_ROLES or not phone:
        return {"due": False, "reason": "role"}
    w = window_for(_today())
    if not w or not w["popup"]:
        return {"due": False, "reason": "window"}
    anchor = w["anchor"]
    st = filed_state(phone, anchor)
    base = {
        "period_key": st["period_key"],
        "period_label": period_label(anchor),
        "deadline": _fmt_day(_deadline(anchor)),
        "state": st["state"],
    }
    if st["state"] in ("submitted", "declared"):
        return dict(base, due=False, reason="filed")
    return dict(base, due=True, late=_today() > on_time_day(anchor),
                draft_name=st.get("draft"), draft_lines=st.get("lines", 0))


def declare_no_claim(phone: str, role: str, period: str, source: str = "Portal") -> dict:
    """One-tap "No petrol claim this period". Rule E: self only, current
    period only, refused when a claim exists. Commits and reads back."""
    if role not in W2_ROLES:
        frappe.throw(frappe._("Only field engineers, network security engineers and store "
                              "executives file petrol vouchers."), frappe.PermissionError)
    if not phone:
        frappe.throw(frappe._("No employee on this session."), frappe.PermissionError)
    w = window_for(_today())
    if not w:
        frappe.throw(frappe._("There is no open petrol voucher period to declare for today."),
                     frappe.ValidationError)
    anchor = w["anchor"]
    pk = period_key(anchor)
    if (period or "").strip() != pk:
        frappe.throw(frappe._("You can only declare for the current period ({0}).").format(pk),
                     frappe.ValidationError)
    st = filed_state(phone, anchor)
    if st["state"] == "submitted":
        frappe.throw(frappe._("You have already submitted a petrol voucher for this period ({0}).")
                     .format(st["voucher"]), frappe.ValidationError)
    if st["state"] == "declared":
        frappe.throw(frappe._("You have already declared no petrol claim for this period."),
                     frappe.ValidationError)
    if st["state"] == "draft" and st.get("lines"):
        frappe.throw(frappe._("You have a draft petrol voucher with {0} line(s) for this period "
                              "({1}). Submit it instead.").format(st["lines"], st["draft"]),
                     frappe.ValidationError)

    name = frappe.db.get_value("VECRM Employee", phone, "employee_name") or phone
    doc = frappe.get_doc({
        "doctype": DECLARATION_DT,
        "employee": phone,
        "employee_name": name,
        "period_key": pk,
        "declared_at": frappe.utils.now_datetime(),
        "source": source if source in ("Portal", "App") else "Portal",
    }).insert(ignore_permissions=True)
    frappe.get_doc({
        "doctype": "VECRM Voucher Audit Log",
        "event": "voucher.declaration.created",
        "event_timestamp": frappe.utils.now_datetime(),
        "payload": json.dumps({"declaration": doc.name, "employee": phone,
                               "period_key": pk, "actor_role": role}),
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    back = frappe.db.get_value(DECLARATION_DT, doc.name,
                               ["name", "employee", "period_key", "declared_at"], as_dict=True)
    if not back or back.employee != phone or back.period_key != pk:
        frappe.throw(frappe._("Declaration did not persist."), frappe.ValidationError)
    return {"name": back.name, "employee": back.employee, "period_key": back.period_key,
            "declared_at": str(back.declared_at), "period_label": period_label(anchor)}


# ── daily run (called from notifications.voucher_period_reminder, 10:00) ──

def run_daily(dry_run: bool = False, today=None) -> dict:
    today = getdate(today) if today else _today()
    out = {"date": today.isoformat(), "mails": []}
    if dry_run or _once("submissions"):
        out["submissions"] = _daily_submission_list(today, dry_run, out["mails"])
    w = window_for(today)
    if w and (dry_run or _once("window")):
        out["window"] = _window_day(today, w, dry_run, out["mails"])
    return out


def _window_day(today: date, w: dict, dry_run: bool, log: list) -> dict:
    anchor = w["anchor"]
    label = period_label(anchor)
    deadline = _deadline(anchor)
    otd = on_time_day(anchor)
    rows = []
    for e in _w2_employees():
        st = filed_state(e.name, anchor)
        rows.append((e, st))
    unfiled = [(e, st) for e, st in rows if st["state"] in ("none", "draft")]

    reminded = []
    for e, st in unfiled:
        if not e.vecrm_email:
            continue
        if st["state"] == "draft":
            status = "is still a draft with %d line(s). A draft is not filed until you submit it." % st.get("lines", 0)
        else:
            status = "has not been filed yet."
        if today == otd:
            timing = ("The submission window opens tonight at 9 pm. File tonight to be recorded "
                      "as on time.")
        else:
            timing = "Filing now is recorded as Late."
        body = (
            _p("Hi %s," % _esc(e.employee_name))
            + _p("Your petrol voucher for %s %s" % (_esc(label), _esc(status)))
            + _p("The window closes on %s at 11:59 pm. %s" % (_esc(_fmt_day(deadline)), _esc(timing)))
            + _p("Open it here: %s" % _link(PETROL_URL, "Petrol vouchers"))
            + _p("If you had no petrol spend this period, open the Anusuya app and tap "
                 "\"No petrol claim this period\" so you are not reminded again.")
        )
        if _send(e.vecrm_email, "Petrol voucher due by %s: %s" % (_fmt_day(deadline), label),
                 body, "Petrol voucher due", dry_run, log):
            reminded.append(e.employee_name)
        elif dry_run:
            reminded.append(e.employee_name)

    hod_mails = []
    if w["popup"]:
        by_head_role = {}
        for e, st in unfiled:
            for hr in head_roles_for(e.role):
                by_head_role.setdefault(hr, []).append((e, st))
        for hr, members in by_head_role.items():
            for head in _people_in_roles([hr]):
                if not head.vecrm_email:
                    continue
                table = _table(["Name", "Role", "Status"], [
                    (m.employee_name, m.role,
                     "Draft, %d line(s), not submitted" % s.get("lines", 0) if s["state"] == "draft"
                     else "Not filed")
                    for m, s in members])
                body = (
                    _p("Hi %s," % _esc(head.employee_name))
                    + _p("These people in your team have not filed their petrol voucher for %s. "
                         "The window closes on %s at 11:59 pm." % (_esc(label), _esc(_fmt_day(deadline))))
                    + table
                    + _p(_link(OVERVIEW_URL, "Open the voucher overview"))
                )
                _send(head.vecrm_email, "Petrol vouchers not filed: %s (%d)" % (label, len(members)),
                      body, "Petrol vouchers not filed", dry_run, log)
                hod_mails.append({"to": head.employee_name, "count": len(members)})

    filed = [e.employee_name for e, st in rows if st["state"] == "submitted"]
    declared = [e.employee_name for e, st in rows if st["state"] == "declared"]
    summary = (
        _p("Petrol voucher status for %s on %s." % (_esc(label), _esc(_fmt_day(today))))
        + _table(["Name", "Role", "Status"], [
            (e.employee_name, e.role,
             {"submitted": "Submitted", "declared": "No claim declared",
              "draft": "Draft, not submitted", "none": "Not filed"}[st["state"]])
            for e, st in rows])
        + _p("Reminded today: %s." % _esc(", ".join(reminded) or "nobody"))
        + _p("HOD mails today: %s." % _esc(
            ", ".join("%s (%d)" % (h["to"], h["count"]) for h in hod_mails) or "none"))
    )
    _send(AUDIT_MAILBOX, "Voucher reminder summary %s: %s" % (_fmt_day(today), label),
          summary, "Voucher reminder summary", dry_run, log)
    return {"period": period_key(anchor), "employees": len(rows), "unfiled": len(unfiled),
            "reminded": reminded, "hod_mails": hod_mails, "filed": filed, "declared": declared}


def _daily_submission_list(today: date, dry_run: bool, log: list) -> dict:
    """Yesterday's submissions, one mail to Accounts, HR and Admin."""
    y = today - timedelta(days=1)
    events = frappe.get_all(
        "VECRM Voucher Audit Log",
        filters={"event": ["in", ["voucher.travel.submitted", "voucher.expense.submitted"]],
                 "event_timestamp": ["between", [datetime.combine(y, time(0, 0, 0)),
                                                 datetime.combine(y, time(23, 59, 59))]]},
        fields=["payload", "event_timestamp"],
        order_by="event_timestamp asc",
        ignore_permissions=True,
    )
    rows = []
    for ev in events:
        try:
            p = json.loads(ev.payload or "{}")
        except Exception:
            continue
        dt, vn = p.get("voucher_doctype"), p.get("voucher_name")
        if not dt or not vn or not frappe.db.exists(dt, vn):
            continue
        v = frappe.db.get_value(dt, vn, ["submitter", "total_amount"], as_dict=True) or {}
        who = frappe.db.get_value("VECRM Employee", v.get("submitter"), "employee_name") or v.get("submitter")
        kind = "Petrol" if dt == "VECRM Travel Voucher" else "Expense"
        rows.append((who, kind, vn, _inr(v.get("total_amount")),
                     ev.event_timestamp.strftime("%H:%M") if ev.event_timestamp else ""))
    if not rows:
        return {"date": y.isoformat(), "count": 0}
    body = (_p("Vouchers submitted on %s:" % _esc(_fmt_day(y)))
            + _table(["Name", "Type", "Voucher", "Amount", "Time"], rows)
            + _p(_link(OVERVIEW_URL, "Open the voucher overview")))
    to = [p.vecrm_email for p in _people_in_roles(DAILY_LIST_ROLES) if p.vecrm_email]
    _send(to, "Vouchers submitted on %s (%d)" % (_fmt_day(y), len(rows)), body,
          "Vouchers submitted", dry_run, log)
    return {"date": y.isoformat(), "count": len(rows), "to": to}


# ── per-event mails ──────────────────────────────────────────────────────

def send_submission_hod_mail(doc, dry_run: bool = False) -> list:
    """On submit: mail the submitter's functional head (none for heads/Admin)."""
    log = []
    submitter = getattr(doc, "submitter", None)
    role = getattr(doc, "submitter_role", None) or frappe.db.get_value("VECRM Employee", submitter, "role")
    heads = [h for h in _people_in_roles(head_roles_for(role)) if h.name != submitter]
    if not heads:
        return log
    who = frappe.db.get_value("VECRM Employee", submitter, "employee_name") or submitter
    kind = "petrol" if doc.doctype == "VECRM Travel Voucher" else "expense"
    for h in heads:
        if not h.vecrm_email:
            continue
        body = (_p("Hi %s," % _esc(h.employee_name))
                + _p("%s has submitted %s voucher %s for %s." % (
                    _esc(who), kind, _esc(doc.name), _esc(_inr(doc.total_amount))))
                + _p(_link(OVERVIEW_URL, "Review it in the voucher overview")))
        _send(h.vecrm_email, "%s submitted a %s voucher: %s" % (who, kind, doc.name), body,
              "Voucher submitted", dry_run, log)
    return log


def _paid_row(doctype: str, name: str) -> dict | None:
    """Same arithmetic as voucher_cms._collect_vouchers (what the bank file paid)."""
    if doctype == "VECRM Travel Voucher":
        v = frappe.db.get_value(doctype, name, ["submitter", "total_amount"], as_dict=True)
        if not v:
            return None
        total = flt(v.total_amount)
        return {"submitter": v.submitter, "name": name, "kind": "Petrol",
                "approved": total, "deducted": 0.0, "paid": total}
    v = frappe.db.get_value(doctype, name, ["submitter", "total_amount", "advance_received",
                                            "advance_amount", "advance_consumed"], as_dict=True)
    if not v:
        return None
    total = flt(v.total_amount)
    adv = flt(v.advance_amount) if v.advance_received else 0.0
    net = max(0.0, total - adv - flt(v.advance_consumed))
    return {"submitter": v.submitter, "name": name, "kind": "Expense",
            "approved": total, "deducted": round(total - net, 2), "paid": net}


def _paid_mail(submitter: str, items: list, dry_run: bool, log: list) -> None:
    email = frappe.db.get_value("VECRM Employee", submitter, "vecrm_email")
    if not email or not items:
        return
    who = frappe.db.get_value("VECRM Employee", submitter, "employee_name") or submitter
    total_paid = sum(i["paid"] for i in items)
    rows = [(i["name"], i["kind"], _inr(i["approved"]),
             _inr(i["deducted"]) if i["deducted"] else "-", _inr(i["paid"])) for i in items]
    body = (_p("Hi %s," % _esc(who))
            + _p("%s has been paid to your bank account for the voucher(s) below." % _esc(_inr(total_paid)))
            + _table(["Voucher", "Type", "Approved", "Advance deducted", "Paid"], rows))
    if any(i["deducted"] for i in items):
        body += _p("Advance deducted is the advance you had already received against that "
                   "voucher, including any balance carried forward from an earlier trip.")
    body += _p(_link(PETROL_URL, "See your vouchers"))
    _send(email, "Voucher payment: %s paid" % _inr(total_paid), body, "Voucher payment",
          dry_run, log)


def send_paid_mail_single(doc, dry_run: bool = False) -> list:
    """Per-voucher mark-paid path. Silent inside a bulk payout run, which
    sends one grouped mail per employee instead."""
    log = []
    if frappe.flags.get("vecrm_bulk_paid"):
        return log
    row = _paid_row(doc.doctype, doc.name)
    if row:
        _paid_mail(row["submitter"], [row], dry_run, log)
    return log


def send_paid_mail_bulk(marked: list, dry_run: bool = False) -> list:
    """marked: [{"type": doctype, "name": voucher}, ...] from mark_voucher_targets_paid."""
    log = []
    per = {}
    for m in marked or []:
        row = _paid_row(m.get("type"), m.get("name"))
        if row:
            per.setdefault(row["submitter"], []).append(row)
    for submitter, items in per.items():
        _paid_mail(submitter, items, dry_run, log)
    return log
