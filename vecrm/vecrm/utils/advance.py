"""S144 expense advances tied to expense vouchers (VECRM).

Spec: claude/ANUSUYA-S144-EXPENSE-ADVANCE-SPEC.md. Rulings (Ajay, 24 Sep 2026):
- One approval: the requester's functional head OR Admin. Nobody approves or
  pays their own request. A head (or Admin) filing on an employee's behalf
  counts as the approval.
- Payers: every holder of Admin and Head of Accounts & HR. Anil pays over UPI
  outside the system, then marks the advance Paid (amount, optional UPI ref).
- Marking Paid creates the trip's Expense Voucher draft carrying the advance,
  site, location and trip start date. A paid top-up joins the same draft while
  it is still a draft; otherwise it opens a new draft.
- The voucher's linked_advance_amount is server-computed and locked. The
  engineer's own "Advance payment received?" stays, meaning "other advance
  received outside the app", and adds on top: advance_amount =
  linked + other, never below linked (controller validate + voucher_cms guard).
- Mail buttons only open the portal page; nothing is ever marked from a mail.
- Engineer mails carry no per-mail BCC (voucher ruling); advance events go into
  one daily summary to the audit mailbox.

Money writes (pay, voucher attach) are Rule E: guarded, committed in-module and
re-SELECTed. Mails and pushes are dispatched after commit on the short queue and
are best-effort: a mail failure never undoes a recorded payment.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import flt, getdate

from vecrm.vecrm.utils.voucher_due import (
    AUDIT_MAILBOX,
    DAILY_LIST_ROLES,
    PORTAL,
    W2_ROLES,
    _esc,
    _fmt_day,
    _inr,
    _link,
    _once,
    _p,
    _people_in_roles,
    _send,
    _table,
    _today,
    head_roles_for,
)

ADV_DT = "VECRM Advance Request"
EV_DT = "VECRM Expense Voucher"
AUDIT_DT = "VECRM Voucher Audit Log"
PAYER_ROLES = ("Admin", "Head of Accounts & HR")
ADV_URL = PORTAL + "/expense-advances"
OPEN_STATUSES = ("Pending Approval", "Approved")
OVERDUE_DAYS = 7


# ── identity ─────────────────────────────────────────────────────────────

EMP_FIELDS = ["name", "employee_name", "role", "vecrm_account_status", "vecrm_email"]


def _emp(phone: str):
    if not phone:
        return None
    return frappe.db.get_value("VECRM Employee", phone, EMP_FIELDS, as_dict=True)


def _caller():
    """The signed-in employee, with the LIVE role and status from the DB."""
    phone = (frappe.session.data or {}).get("vecrm_employee_phone")
    emp = _emp(phone)
    if not emp or emp.vecrm_account_status != "Active":
        frappe.throw(_("Please sign in again."), frappe.PermissionError)
    return emp


def approver_roles(employee_role: str) -> list:
    out = list(head_roles_for(employee_role))
    if "Admin" not in out:
        out.append("Admin")
    return out


def _is_head_of(caller_role: str, employee_role: str) -> bool:
    return caller_role in head_roles_for(employee_role)


def _can_approve(caller, doc) -> bool:
    return caller.name != doc.employee and caller.role in approver_roles(doc.employee_role)


def _can_pay(caller, doc) -> bool:
    return caller.name != doc.employee and caller.role in PAYER_ROLES


def _can_view(caller, doc) -> bool:
    return (caller.name in (doc.employee, doc.requested_by)
            or caller.role in approver_roles(doc.employee_role)
            or caller.role in PAYER_ROLES
            or caller.role in ("HR", "Accounts Executive"))


# ── small helpers ────────────────────────────────────────────────────────

def _url(name: str) -> str:
    return ADV_URL + "/" + quote(name or "", safe="")


def _ev_url(name: str) -> str:
    return PORTAL + "/expense-vouchers/" + quote(name or "", safe="")


def _now():
    return frappe.utils.now_datetime()


def _get(name: str, for_update: bool = False):
    if not name or not frappe.db.exists(ADV_DT, name):
        frappe.throw(_("Advance request {0} was not found.").format(name), frappe.DoesNotExistError)
    return frappe.get_doc(ADV_DT, name, for_update=for_update)


def _write(doc, insert: bool = False):
    doc.flags.vecrm_advance_write = True
    doc.flags.ignore_permissions = True
    if insert:
        doc.insert()
    else:
        doc.save()
    return doc


def _audit(doc, event: str, actor, extra: dict | None = None) -> None:
    payload = {
        "voucher_doctype": ADV_DT,
        "voucher_name": doc.name,
        "actor_employee": actor.name if actor else None,
        "actor_role": actor.role if actor else None,
        "actor_user": (frappe.session.data or {}).get("vecrm_email") or frappe.session.user,
        "employee": doc.employee,
        "amount": flt(doc.amount),
        "status": doc.status,
    }
    if extra:
        payload.update(extra)
    frappe.get_doc({
        "doctype": AUDIT_DT,
        "event": event,
        "event_timestamp": _now(),
        "payload": json.dumps(payload, default=str),
    }).insert(ignore_permissions=True)


def _enqueue(name: str, kind: str, prior: str = "") -> None:
    # frappe.enqueue reserves "event" and "job_name"; the job kwargs are adv/kind/prior.
    try:
        frappe.enqueue("vecrm.vecrm.utils.advance.dispatch_event", queue="short",
                       enqueue_after_commit=True, adv=name, kind=kind, prior=prior)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "S144 advance enqueue")


def linked_total(voucher_name: str) -> float:
    """Sum of PAID app advances linked to a voucher. 0 before S144 is installed."""
    if not voucher_name or not frappe.db.table_exists(ADV_DT):
        return 0.0
    row = frappe.db.sql(
        "SELECT COALESCE(SUM(paid_amount), 0) FROM `tabVECRM Advance Request` "
        "WHERE voucher = %s AND status = 'Paid'", (voucher_name,))
    return flt(row[0][0]) if row else 0.0


def has_links(voucher_name: str) -> bool:
    if not voucher_name or not frappe.db.table_exists(ADV_DT):
        return False
    return bool(frappe.db.exists(ADV_DT, {"voucher": voucher_name}))


# ── shaping ──────────────────────────────────────────────────────────────

FIELDS = ["name", "employee", "employee_name", "employee_role", "status", "trip_type",
          "parent_advance", "site", "location", "purpose", "travel_from", "travel_to",
          "amount", "requested_by", "requested_by_role", "requested_at", "decided_by",
          "decided_by_role", "decided_at", "decision_notes", "paid_amount", "payment_ref",
          "paid_by", "paid_by_role", "paid_at", "decline_reason", "voucher", "creation"]


def _voucher_state(voucher: str) -> str | None:
    if not voucher:
        return None
    v = frappe.db.get_value(EV_DT, voucher, ["docstatus", "approval_status", "payment_status"],
                            as_dict=True)
    if not v:
        return None
    if v.docstatus == 0:
        return "Draft"
    if v.payment_status == "Paid":
        return "Settled"
    return {"Approved": "Approved", "Rejected": "Rejected"}.get(v.approval_status, "Submitted")


def _names(phones) -> dict:
    phones = [p for p in set(phones) if p]
    if not phones:
        return {}
    rows = frappe.get_all("VECRM Employee", filters={"name": ["in", phones]},
                          fields=["name", "employee_name"], ignore_permissions=True)
    return {r.name: r.employee_name for r in rows}


def _shape(row, caller=None) -> dict:
    d = {f: row.get(f) for f in FIELDS}
    for f in ("amount", "paid_amount"):
        d[f] = flt(d.get(f))
    for f in ("travel_from", "travel_to"):
        d[f] = str(d[f]) if d.get(f) else None
    for f in ("requested_at", "decided_at", "paid_at", "creation"):
        d[f] = str(d[f]) if d.get(f) else None
    names = _names([d.get("requested_by"), d.get("decided_by"), d.get("paid_by")])
    d["requested_by_name"] = names.get(d.get("requested_by"))
    d["decided_by_name"] = names.get(d.get("decided_by"))
    d["paid_by_name"] = names.get(d.get("paid_by"))
    d["voucher_state"] = _voucher_state(d.get("voucher"))
    d["settled"] = d["voucher_state"] == "Settled"
    d["on_behalf"] = bool(d.get("requested_by") and d.get("requested_by") != d.get("employee"))
    if caller is not None:
        doc = frappe._dict(row)
        d["can_approve"] = doc.status == "Pending Approval" and _can_approve(caller, doc)
        d["can_pay"] = doc.status == "Approved" and _can_pay(caller, doc)
        d["can_cancel"] = doc.status in OPEN_STATUSES and (
            caller.name in (doc.employee, doc.requested_by) or caller.role == "Admin")
    return d


# ── actions ──────────────────────────────────────────────────────────────

def request_advance(amount, purpose, site, location, travel_from, travel_to,
                    employee: str = "", parent_advance: str = "") -> dict:
    caller = _caller()
    target = _emp(employee or caller.name)
    if not target or target.vecrm_account_status != "Active":
        frappe.throw(_("That employee is not active."), frappe.ValidationError)
    if target.role not in W2_ROLES:
        frappe.throw(_("Expense advances are for field, store and sales roles ({0}).").format(
            ", ".join(W2_ROLES)), frappe.ValidationError)
    on_behalf = target.name != caller.name
    if on_behalf and not (caller.role == "Admin" or _is_head_of(caller.role, target.role)):
        frappe.throw(_("Only the employee's head or Admin can request an advance on their behalf."),
                     frappe.PermissionError)

    doc = frappe.new_doc(ADV_DT)
    doc.employee = target.name
    doc.employee_name = target.employee_name
    doc.employee_role = target.role
    doc.amount = flt(amount)
    doc.purpose = (purpose or "").strip()
    doc.travel_from = travel_from
    doc.travel_to = travel_to
    if parent_advance:
        parent = _get(parent_advance)
        if parent.employee != target.name or parent.status != "Paid":
            frappe.throw(_("A top-up must follow a paid advance of the same employee."),
                         frappe.ValidationError)
        doc.trip_type = "Top-up"
        doc.parent_advance = parent.name
        doc.site, doc.location = parent.site, parent.location
    else:
        doc.trip_type = "New trip"
        doc.site = (site or "").strip()
        doc.location = (location or "").strip()
    doc.requested_by = caller.name
    doc.requested_by_role = caller.role
    doc.requested_at = _now()
    if on_behalf:
        doc.status = "Approved"
        doc.decided_by = caller.name
        doc.decided_by_role = caller.role
        doc.decided_at = doc.requested_at
        doc.decision_notes = "Requested on the employee's behalf (counts as approval)."
    else:
        doc.status = "Pending Approval"
    _write(doc, insert=True)
    _audit(doc, "advance.requested", caller, {"on_behalf": on_behalf, "trip_type": doc.trip_type,
                                               "parent_advance": doc.parent_advance})
    if on_behalf:
        _audit(doc, "advance.approved", caller, {"on_behalf": True})
    _enqueue(doc.name, "requested_on_behalf" if on_behalf else "requested")
    return _shape(doc.as_dict(), caller)


def decide_advance(name: str, action: str, notes: str = "") -> dict:
    caller = _caller()
    doc = _get(name, for_update=True)
    if doc.status != "Pending Approval":
        frappe.throw(_("This request is {0}, not awaiting approval.").format(doc.status),
                     frappe.ValidationError)
    if doc.employee == caller.name:
        frappe.throw(_("You cannot approve your own advance request."), frappe.PermissionError)
    if caller.role not in approver_roles(doc.employee_role):
        frappe.throw(_("Only {0} can decide this request.").format(
            " or ".join(approver_roles(doc.employee_role))), frappe.PermissionError)
    notes = (notes or "").strip()
    if action == "approve":
        doc.status = "Approved"
    elif action == "reject":
        if not notes:
            frappe.throw(_("Please give a reason for rejecting."), frappe.ValidationError)
        doc.status = "Rejected"
    else:
        frappe.throw(_("Unknown action."), frappe.ValidationError)
    doc.decided_by, doc.decided_by_role, doc.decided_at = caller.name, caller.role, _now()
    doc.decision_notes = notes
    _write(doc)
    _audit(doc, "advance.%s" % ("approved" if action == "approve" else "rejected"), caller,
           {"notes": notes})
    _enqueue(doc.name, "approved" if action == "approve" else "rejected")
    return _shape(doc.as_dict(), caller)


def pay_advance(name: str, paid_amount=None, payment_ref: str = "") -> dict:
    """Record that the payer has sent the money, and attach it to the voucher draft."""
    caller = _caller()
    doc = _get(name, for_update=True)
    if doc.status == "Paid":
        frappe.throw(_("This advance is already marked paid ({0}).").format(_inr(doc.paid_amount)),
                     frappe.ValidationError)
    if doc.status != "Approved":
        frappe.throw(_("Only an approved advance can be marked paid (this one is {0}).").format(
            doc.status), frappe.ValidationError)
    if not _can_pay(caller, doc):
        frappe.throw(_("Only Admin or Head of Accounts & HR can mark an advance paid, and not "
                       "their own."), frappe.PermissionError)
    amt = flt(doc.amount) if paid_amount in (None, "") else flt(paid_amount)
    if amt <= 0 or amt > flt(doc.amount) + 0.005:
        frappe.throw(_("The paid amount must be more than zero and not more than {0}.").format(
            _inr(doc.amount)), frappe.ValidationError)
    ref = (payment_ref or "").strip()[:64]

    doc.status = "Paid"
    doc.paid_amount = amt
    doc.payment_ref = ref
    doc.paid_by, doc.paid_by_role, doc.paid_at = caller.name, caller.role, _now()
    _write(doc)
    voucher = attach_to_voucher(doc)
    _audit(doc, "advance.paid", caller, {"paid_amount": amt, "payment_ref": ref, "voucher": voucher})

    # Rule E read-back, inside the transaction, then commit, then again.
    def _check(stage):
        a = frappe.db.get_value(ADV_DT, doc.name, ["status", "paid_amount", "voucher"], as_dict=True)
        v = frappe.db.get_value(EV_DT, voucher, ["docstatus", "advance_received", "advance_amount",
                                                  "linked_advance_amount"], as_dict=True)
        lt = linked_total(voucher)
        ok = (a and a.status == "Paid" and abs(flt(a.paid_amount) - amt) < 0.005
              and a.voucher == voucher and v and int(v.advance_received or 0) == 1
              and abs(flt(v.linked_advance_amount) - lt) < 0.005
              and flt(v.advance_amount) + 0.005 >= lt)
        if not ok:
            frappe.throw("Advance payment verification FAILED at %s on %s: advance=%s voucher=%s "
                         "linked_total=%s" % (stage, doc.name, a, v, lt))
    _check("pre-commit")
    frappe.db.commit()
    _check("post-commit")
    _enqueue(doc.name, "paid")
    return _shape(frappe.get_doc(ADV_DT, doc.name).as_dict(), caller)


def decline_payment(name: str, reason: str) -> dict:
    caller = _caller()
    doc = _get(name, for_update=True)
    if doc.status != "Approved":
        frappe.throw(_("Only an approved advance awaiting payment can be declined (this one is "
                       "{0}).").format(doc.status), frappe.ValidationError)
    if not _can_pay(caller, doc):
        frappe.throw(_("Only Admin or Head of Accounts & HR can decline payment."),
                     frappe.PermissionError)
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Please give a reason for declining."), frappe.ValidationError)
    doc.status = "Payment Declined"
    doc.decline_reason = reason
    _write(doc)
    _audit(doc, "advance.payment_declined", caller, {"reason": reason})
    _enqueue(doc.name, "declined")
    return _shape(doc.as_dict(), caller)


def cancel_advance(name: str) -> dict:
    caller = _caller()
    doc = _get(name, for_update=True)
    if doc.status not in OPEN_STATUSES:
        frappe.throw(_("Only a request that is not yet paid can be cancelled (this one is {0}).")
                     .format(doc.status), frappe.ValidationError)
    if caller.name not in (doc.employee, doc.requested_by) and caller.role != "Admin":
        frappe.throw(_("Only the employee, whoever filed it, or Admin can cancel this request."),
                     frappe.PermissionError)
    prior = doc.status
    doc.status = "Cancelled"
    doc.cancelled_by, doc.cancelled_at = caller.name, _now()
    _write(doc)
    _audit(doc, "advance.cancelled", caller, {"prior_status": prior})
    _enqueue(doc.name, "cancelled", prior=prior)
    return _shape(doc.as_dict(), caller)


# ── voucher link ─────────────────────────────────────────────────────────

def attach_to_voucher(doc) -> str:
    """Put a just-paid advance on its trip's draft voucher (created if needed)."""
    target = None
    if doc.trip_type == "Top-up" and doc.parent_advance:
        pv = frappe.db.get_value(ADV_DT, doc.parent_advance, "voucher")
        if pv and frappe.db.get_value(EV_DT, pv, "docstatus") == 0:
            target = pv
    if not target:
        ev = frappe.new_doc(EV_DT)
        ev.submitter = doc.employee
        ev.expense_date = doc.travel_from
        ev.site = doc.site
        ev.location = doc.location
        ev.advance_received = 0
        ev.advance_amount = 0
        ev.flags.vecrm_advance_draft = True
        ev.flags.ignore_permissions = True
        ev.insert()
        target = ev.name
    doc.db_set("voucher", target, update_modified=False)
    refresh_voucher_advance(target)
    return target


def refresh_voucher_advance(voucher_name: str) -> dict:
    """Recompute a draft's app-advance total, keeping the engineer's 'other' advance."""
    ev = frappe.get_doc(EV_DT, voucher_name, for_update=True)
    if ev.docstatus != 0:
        frappe.throw("App advances attach only to a draft voucher; %s is not a draft." % voucher_name)
    old_linked = flt(ev.get("linked_advance_amount"))
    old_adv = flt(ev.advance_amount) if ev.advance_received else 0.0
    other = max(0.0, old_adv - old_linked)
    new_linked = linked_total(voucher_name)
    ev.advance_received = 1 if (new_linked + other) > 0 else 0
    ev.advance_amount = new_linked + other
    ev.flags.vecrm_advance_draft = True
    ev.flags.ignore_permissions = True
    ev.save()
    return {"voucher": voucher_name, "linked": new_linked, "other": other}


# ── reads ────────────────────────────────────────────────────────────────

def list_mine() -> list:
    caller = _caller()
    rows = frappe.get_all(ADV_DT, filters={"employee": caller.name}, fields=FIELDS,
                          order_by="creation desc", limit_page_length=200, ignore_permissions=True)
    return [_shape(r, caller) for r in rows]


def list_queue() -> dict:
    """What the caller has to act on, plus the last 60 days of team history."""
    caller = _caller()
    out = {"to_approve": [], "to_pay": [], "recent": []}
    pend = frappe.get_all(ADV_DT, filters={"status": "Pending Approval"}, fields=FIELDS,
                          order_by="creation asc", ignore_permissions=True)
    out["to_approve"] = [_shape(r, caller) for r in pend if _can_approve(caller, frappe._dict(r))]
    if caller.role in PAYER_ROLES:
        appr = frappe.get_all(ADV_DT, filters={"status": "Approved"}, fields=FIELDS,
                              order_by="decided_at asc", ignore_permissions=True)
        out["to_pay"] = [_shape(r, caller) for r in appr if r.employee != caller.name]
    since = frappe.utils.add_days(_today(), -60)
    recent = frappe.get_all(ADV_DT, filters={"creation": [">=", since],
                                             "employee": ["!=", caller.name]},
                            fields=FIELDS, order_by="creation desc", limit_page_length=300,
                            ignore_permissions=True)
    out["recent"] = [_shape(r, caller) for r in recent if _can_view(caller, frappe._dict(r))]
    return out


def get_one(name: str) -> dict:
    caller = _caller()
    doc = _get(name)
    if not _can_view(caller, doc):
        frappe.throw(_("You cannot view this advance request."), frappe.PermissionError)
    d = _shape(doc.as_dict(), caller)
    events = frappe.db.sql(
        """SELECT event, event_timestamp, payload FROM `tabVECRM Voucher Audit Log`
           WHERE event LIKE 'advance.%%' AND payload LIKE %s ORDER BY event_timestamp ASC""",
        ('%%"voucher_name": "%s"%%' % doc.name.replace("%", ""),), as_dict=True)
    trail = []
    for e in events:
        try:
            p = json.loads(e.payload or "{}")
        except Exception:
            p = {}
        if p.get("voucher_name") != doc.name:
            continue
        trail.append({"event": e.event, "at": str(e.event_timestamp),
                      "by": p.get("actor_employee"), "role": p.get("actor_role")})
    names = _names([t["by"] for t in trail])
    for t in trail:
        t["by_name"] = names.get(t["by"])
    d["trail"] = trail
    if doc.trip_type == "New trip":
        tops = frappe.get_all(ADV_DT, filters={"parent_advance": doc.name}, fields=FIELDS,
                              order_by="creation asc", ignore_permissions=True)
        d["top_ups"] = [_shape(r, caller) for r in tops]
    return d


def open_trips(employee: str = "") -> list:
    """Paid new-trip advances (last 90 days) that a top-up can follow."""
    caller = _caller()
    target = _emp(employee or caller.name)
    if not target:
        frappe.throw(_("Employee not found."), frappe.ValidationError)
    if target.name != caller.name and not (caller.role == "Admin"
                                           or _is_head_of(caller.role, target.role)):
        frappe.throw(_("You cannot see this employee's trips."), frappe.PermissionError)
    since = frappe.utils.add_days(_today(), -90)
    rows = frappe.get_all(ADV_DT, filters={"employee": target.name, "status": "Paid",
                                           "trip_type": "New trip", "travel_from": [">=", since]},
                          fields=FIELDS, order_by="travel_from desc", ignore_permissions=True)
    return [_shape(r, caller) for r in rows]


def voucher_advances(voucher_name: str) -> dict:
    """App advances on a voucher, for the voucher form's locked rows."""
    caller = _caller()
    sub = frappe.db.get_value(EV_DT, voucher_name, ["submitter", "submitter_role"], as_dict=True)
    if not sub:
        frappe.throw(_("Voucher not found."), frappe.DoesNotExistError)
    if not (caller.name == sub.submitter or caller.role in approver_roles(sub.submitter_role)
            or caller.role in PAYER_ROLES or caller.role in ("HR", "Accounts Executive")):
        frappe.throw(_("You cannot view this voucher."), frappe.PermissionError)
    rows = frappe.get_all(ADV_DT, filters={"voucher": voucher_name, "status": "Paid"},
                          fields=FIELDS, order_by="paid_at asc", ignore_permissions=True)
    return {"voucher": voucher_name, "linked_total": linked_total(voucher_name),
            "advances": [_shape(r) for r in rows]}


# ── mails and pushes ─────────────────────────────────────────────────────

def _push(emp, title: str, body: str, name: str) -> None:
    if not emp or not emp.get("vecrm_email"):
        return
    try:
        from vecrm.notifications import _log_notification, _tokens_for_user, send_push

        payload = {"screen": "advances", "advance": name, "doctype": ADV_DT}
        tokens = _tokens_for_user(emp.vecrm_email)
        if tokens:
            send_push(tokens, title, body, payload)
        else:
            _log_notification(emp.vecrm_email, title, body, payload)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "S144 advance push")


def _heads(doc) -> list:
    people = _people_in_roles(head_roles_for(doc.employee_role))
    people = [p for p in people if p.name != doc.employee]
    return people or [p for p in _people_in_roles(["Admin"]) if p.name != doc.employee]


def _payers(doc) -> list:
    return [p for p in _people_in_roles(PAYER_ROLES) if p.name != doc.employee]


def _facts(doc, paid: bool = False) -> str:
    rows = [("Advance", doc.name), ("Employee", "%s (%s)" % (doc.employee_name, doc.employee)),
            ("Amount requested", _inr(doc.amount))]
    if paid:
        rows.append(("Amount paid", _inr(doc.paid_amount)))
        if doc.payment_ref:
            rows.append(("UPI / payment ref", doc.payment_ref))
    rows += [("Site", doc.site), ("Location", doc.location),
             ("Travel", "%s to %s" % (_fmt_day(doc.travel_from), _fmt_day(doc.travel_to))),
             ("Purpose", doc.purpose)]
    if doc.trip_type == "Top-up":
        rows.append(("Top-up of", doc.parent_advance))
    return _table(["", ""], rows)


def _other_open(doc) -> str:
    rows = frappe.get_all(ADV_DT, filters={"employee": doc.employee, "status": "Paid",
                                           "name": ["!=", doc.name]},
                          fields=["name", "paid_amount", "voucher", "site"],
                          order_by="paid_at desc", limit_page_length=20, ignore_permissions=True)
    rows = [r for r in rows if _voucher_state(r.voucher) != "Settled"]
    if not rows:
        return _p("No other advance of %s is still open." % _esc(doc.employee_name))
    return (_p("%s also holds these advances, not yet settled by a paid voucher:"
               % _esc(doc.employee_name))
            + _table(["Advance", "Paid", "Site", "Voucher"],
                     [(r.name, _inr(r.paid_amount), r.site or "",
                       "%s (%s)" % (r.voucher or "", _voucher_state(r.voucher) or "")) for r in rows]))


def dispatch_event(adv: str, kind: str, prior: str = "", dry_run: bool = False) -> list:
    """Compose and send the mails and pushes for one advance event. Best-effort."""
    log = []
    name, event = adv, kind
    try:
        doc = frappe.get_doc(ADV_DT, name)
        emp = _emp(doc.employee)
        who = _emp(doc.decided_by) if doc.decided_by else None
        who_name = who.employee_name if who else "Admin"
        link = _p(_link(_url(doc.name), "Open the advance"))

        def mail(person, subject, body, pre):
            if person and person.get("vecrm_email"):
                _send(person.vecrm_email, subject, _p("Hi %s," % _esc(person.employee_name)) + body,
                      pre, dry_run, log)

        def push(person, title, body):
            if not dry_run:
                _push(person, title, body, doc.name)

        amt = _inr(doc.amount)
        if event in ("requested", "requested_on_behalf"):
            if event == "requested":
                mail(emp, "Advance request received: %s, %s" % (amt, doc.site),
                     _p("Your advance request %s for %s is with %s for approval."
                        % (_esc(doc.name), _esc(amt), _esc(" or ".join(approver_roles(doc.employee_role)))))
                     + _facts(doc) + link, "Advance request received")
                push(emp, "Advance requested", "%s for %s sent for approval" % (amt, doc.site))
                for h in _heads(doc):
                    mail(h, "Advance to approve: %s, %s, %s" % (doc.employee_name, amt, doc.site),
                         _p("%s has requested an expense advance. Please approve or reject it."
                            % _esc(doc.employee_name)) + _facts(doc)
                         + _p(_link(_url(doc.name), "Open to approve or reject")),
                         "Advance to approve")
                    push(h, "Advance to approve", "%s: %s for %s" % (doc.employee_name, amt, doc.site))
            else:
                req = _emp(doc.requested_by)
                mail(emp, "Advance raised for you: %s, %s" % (amt, doc.site),
                     _p("%s raised advance %s for you and it counts as approved. It now goes to "
                        "Accounts for payment." % (_esc(req.employee_name if req else "Your head"),
                                                    _esc(doc.name))) + _facts(doc) + link,
                     "Advance raised for you")
                push(emp, "Advance raised for you", "%s for %s, approved" % (amt, doc.site))
                _payment_request(doc, mail, push)
        elif event == "approved":
            mail(emp, "Advance approved: %s, %s" % (amt, doc.site),
                 _p("%s approved your advance %s. It now goes to Accounts for payment."
                    % (_esc(who_name), _esc(doc.name))) + _facts(doc) + link, "Advance approved")
            push(emp, "Advance approved", "%s for %s approved, awaiting payment" % (amt, doc.site))
            _payment_request(doc, mail, push)
        elif event == "rejected":
            mail(emp, "Advance not approved: %s, %s" % (amt, doc.site),
                 _p("%s did not approve your advance %s." % (_esc(who_name), _esc(doc.name)))
                 + _p("Reason: %s" % _esc(doc.decision_notes)) + _facts(doc) + link,
                 "Advance not approved")
            push(emp, "Advance not approved", "%s for %s: %s" % (amt, doc.site, doc.decision_notes))
        elif event == "paid":
            ev_link = _p("Your expense voucher %s is ready with this advance on it. Add your "
                         "expense lines and submit it after the trip: %s"
                         % (_esc(doc.voucher), _link(_ev_url(doc.voucher), "Open the voucher")))
            mail(emp, "Advance paid: %s, %s" % (_inr(doc.paid_amount), doc.site),
                 _p("Your advance %s has been paid: %s."
                    % (_esc(doc.name), _esc(_inr(doc.paid_amount))))
                 + _facts(doc, paid=True) + ev_link, "Advance paid")
            push(emp, "Advance paid", "%s paid for %s. Voucher %s is ready."
                 % (_inr(doc.paid_amount), doc.site, doc.voucher))
        elif event == "declined":
            mail(emp, "Advance payment declined: %s, %s" % (amt, doc.site),
                 _p("Accounts declined payment of your advance %s." % _esc(doc.name))
                 + _p("Reason: %s" % _esc(doc.decline_reason)) + _facts(doc) + link,
                 "Advance payment declined")
            push(emp, "Advance payment declined", "%s for %s: %s" % (amt, doc.site, doc.decline_reason))
            if who:
                mail(who, "Advance payment declined: %s, %s" % (doc.employee_name, amt),
                     _p("Accounts declined payment of advance %s, which you approved."
                        % _esc(doc.name)) + _p("Reason: %s" % _esc(doc.decline_reason))
                     + _facts(doc) + link, "Advance payment declined")
        elif event == "cancelled":
            for h in (_heads(doc) if prior == "Pending Approval" else []):
                mail(h, "Advance request cancelled: %s, %s" % (doc.employee_name, amt),
                     _p("Advance %s was cancelled before approval." % _esc(doc.name))
                     + _facts(doc), "Advance cancelled")
            if prior == "Approved":
                for pz in _payers(doc):
                    mail(pz, "Advance cancelled, do not pay: %s, %s" % (doc.employee_name, amt),
                         _p("Advance %s was cancelled before payment. Do not pay it."
                            % _esc(doc.name)) + _facts(doc), "Advance cancelled")
                    push(pz, "Advance cancelled", "Do not pay %s to %s" % (amt, doc.employee_name))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "S144 advance dispatch %s %s" % (name, event))
    return log


def _payment_request(doc, mail, push) -> None:
    for pz in _payers(doc):
        mail(pz, "Advance to pay: %s, %s, %s" % (doc.employee_name, _inr(doc.amount), doc.site),
             _p("Advance %s is approved and waiting for payment. Pay it over UPI to %s (%s), "
                "then open it and mark it paid." % (_esc(doc.name), _esc(doc.employee_name),
                                                     _esc(doc.employee)))
             + _facts(doc) + _other_open(doc)
             + _p(_link(_url(doc.name), "Open to mark paid")),
             "Advance to pay")
        push(pz, "Advance to pay", "%s: %s for %s" % (doc.employee_name, _inr(doc.amount), doc.site))


# ── daily (called from notifications.voucher_period_reminder, 10:00) ─────

def _period_close(d) -> date:
    from vecrm.vecrm.utils.voucher_period import submit_window
    return submit_window(d)[1].date()


def run_daily(dry_run: bool = False, today=None) -> dict:
    today = getdate(today) if today else _today()
    out = {"date": today.isoformat(), "mails": []}
    if not frappe.db.table_exists(ADV_DT):
        out["skipped"] = "table missing"
        return out
    if dry_run or _once("adv_chase"):
        out["chase"] = _chase(today, dry_run, out["mails"])
    if dry_run or _once("adv_accounts"):
        out["accounts"] = _accounts_list(today, dry_run, out["mails"])
    if dry_run or _once("adv_audit"):
        out["audit"] = _audit_summary(today, dry_run, out["mails"])
    return out


def _open_drafts() -> list:
    """Paid app advances whose voucher is still a draft, grouped by voucher."""
    rows = frappe.db.sql(
        """SELECT a.voucher, a.employee, MAX(a.travel_to) AS trip_end,
                  SUM(a.paid_amount) AS paid, GROUP_CONCAT(a.name ORDER BY a.name) AS advances,
                  MAX(a.site) AS site
           FROM `tabVECRM Advance Request` a
           JOIN `tabVECRM Expense Voucher` v ON v.name = a.voucher
           WHERE a.status = 'Paid' AND v.docstatus = 0
           GROUP BY a.voucher, a.employee""", as_dict=True)
    return rows


def _chase(today: date, dry_run: bool, log: list) -> list:
    """Remind the engineer the day after the trip ends, then every 3 days."""
    sent = []
    for r in _open_drafts():
        days = (today - getdate(r.trip_end)).days
        if days < 1 or (days - 1) % 3:
            continue
        emp = _emp(r.employee)
        if not emp or emp.vecrm_account_status != "Active":
            continue
        close = _period_close(r.trip_end)
        body = (_p("Hi %s," % _esc(emp.employee_name))
                + _p("Your trip to %s ended on %s. You hold %s in advances (%s) and voucher %s is "
                     "still a draft." % (_esc(r.site), _esc(_fmt_day(r.trip_end)), _esc(_inr(r.paid)),
                                         _esc(r.advances), _esc(r.voucher)))
                + _p("Add your expense lines and submit it. Expenses from %s must be submitted by "
                     "%s." % (_esc(_fmt_day(r.trip_end)), _esc(_fmt_day(close))))
                + _p(_link(_ev_url(r.voucher), "Open the voucher")))
        _send(emp.vecrm_email, "Submit your trip voucher: %s, %s advance" % (r.site, _inr(r.paid)),
              body, "Trip voucher pending", dry_run, log)
        if not dry_run:
            _push(emp, "Trip voucher pending", "Add lines to %s and submit it" % r.voucher,
                  r.advances.split(",")[0])
        sent.append({"employee": emp.employee_name, "voucher": r.voucher, "days": days})
    return sent


def _accounts_list(today: date, dry_run: bool, log: list) -> dict:
    overdue = []
    for r in _open_drafts():
        days = (today - getdate(r.trip_end)).days
        if days >= OVERDUE_DAYS:
            name = frappe.db.get_value("VECRM Employee", r.employee, "employee_name") or r.employee
            overdue.append((name, r.advances, _inr(r.paid), r.site or "", r.voucher,
                            "%d days" % days))
    waiting = []
    for a in frappe.get_all(ADV_DT, filters={"status": "Approved"},
                            fields=["name", "employee_name", "amount", "site", "decided_at"],
                            order_by="decided_at asc", ignore_permissions=True):
        if a.decided_at and (datetime.combine(today, time(10, 0)) - a.decided_at).days >= 1:
            waiting.append((a.employee_name, a.name, _inr(a.amount), a.site or "",
                            _fmt_day(a.decided_at)))
    if not overdue and not waiting:
        return {"overdue": 0, "waiting": 0}
    body = ""
    if waiting:
        body += (_p("Approved advances still waiting for payment:")
                 + _table(["Name", "Advance", "Amount", "Site", "Approved"], waiting))
    if overdue:
        body += (_p("Paid advances whose trip ended %d or more days ago and whose voucher is "
                    "still a draft:" % OVERDUE_DAYS)
                 + _table(["Name", "Advances", "Paid", "Site", "Voucher", "Since trip end"], overdue))
    body += _p(_link(ADV_URL, "Open expense advances"))
    to = [p.vecrm_email for p in _people_in_roles(DAILY_LIST_ROLES) if p.vecrm_email]
    _send(to, "Expense advances needing attention (%d)" % (len(overdue) + len(waiting)), body,
          "Expense advances needing attention", dry_run, log)
    return {"overdue": len(overdue), "waiting": len(waiting), "to": to}


def _audit_summary(today: date, dry_run: bool, log: list) -> dict:
    y = today - timedelta(days=1)
    events = frappe.get_all(
        AUDIT_DT,
        filters={"event": ["like", "advance.%"],
                 "event_timestamp": ["between", [datetime.combine(y, time(0, 0, 0)),
                                                 datetime.combine(y, time(23, 59, 59))]]},
        fields=["event", "event_timestamp", "payload"], order_by="event_timestamp asc",
        ignore_permissions=True)
    rows = []
    for e in events:
        try:
            p = json.loads(e.payload or "{}")
        except Exception:
            p = {}
        emp = frappe.db.get_value("VECRM Employee", p.get("employee"), "employee_name") or p.get("employee")
        actor = frappe.db.get_value("VECRM Employee", p.get("actor_employee"), "employee_name") \
            or p.get("actor_employee")
        amt = p.get("paid_amount") if e.event == "advance.paid" else p.get("amount")
        rows.append((e.event_timestamp.strftime("%H:%M") if e.event_timestamp else "",
                     e.event.replace("advance.", ""), p.get("voucher_name"), emp or "",
                     _inr(amt), actor or ""))
    if not rows:
        return {"date": y.isoformat(), "count": 0}
    body = (_p("Expense advance activity on %s." % _esc(_fmt_day(y)))
            + _table(["Time", "Event", "Advance", "Employee", "Amount", "By"], rows))
    _send(AUDIT_MAILBOX, "Expense advance summary %s (%d)" % (_fmt_day(y), len(rows)), body,
          "Expense advance summary", dry_run, log)
    return {"date": y.isoformat(), "count": len(rows)}
