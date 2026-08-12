# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""VECRM Prospecting + Smartflo integration backend (S85 spec sections 2, 3, 5).

Deliberately a NEW module (vecrm.prospecting) rather than edits to vecrm.api:
zero blind edits to existing files. Auth guard is imported from vecrm.api
(_require_transfer_authority, shipped S84 lead-transfer, commit 7686eb0).

Methods:
  list_prospects            read, rep-scoped by default
  set_prospect_disposition  R-P2 conditional write, attempt_count++, re-SELECT
  assign_prospects          bulk cap 500, skip-and-report
  promote_prospect          Rule-E-adjacent: creates a real VECRM Lead
  import_prospects_batch    one-time import path (batch <= 500)
  smartflo_webhook          allow_guest POST receiver, shared-secret gated,
                            DARK until smartflo_webhook_secret is set in
                            site_config (unset => refuses everything)
"""
import json
import re

import frappe
from frappe.utils import now_datetime, today

from vecrm.api import _require_transfer_authority
from vecrm.vecrm.doctype.vecrm_prospect.vecrm_prospect import normalize_mobile

BULK_CAP = 500
DISPOSITIONS = (
    "Fresh", "No answer", "Not interested", "Callback",
    "Wrong number", "Interested", "Other", "Promoted",
)


def _names_arg(raw):
    """Normalize a JSON-string or list argument into a python list (cap 500)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        frappe.throw("Expected a list of prospect names", frappe.ValidationError)
    if len(raw) > BULK_CAP:
        frappe.throw(
            "At most {0} prospects per call (got {1})".format(BULK_CAP, len(raw)),
            frappe.ValidationError,
        )
    return [str(x).strip() for x in raw if str(x).strip()]


_PROSPECTING_ADMIN_ROLES = (
    "Senior Business Acceleration Executive",
    "HR",
    "Head of Accounts & HR",
    "Admin",
)
_PROSPECTING_REP_ROLES = ("Sales Rep",)


def _require_prospecting_access():
    """Gate for the prospecting surface (S87 rider 1, ruling (a)).

    Returns (actor_email, scope, rep_key):
      scope "all" -> admin set; sees every prospect.
      scope "own" -> Sales Rep; scoped to prospects whose assigned_rep is the
                     caller's own VECRM Employee name (the phone_key).
    rep_key is resolved server-side from the session email, never taken from
    the portal. Unassigned prospects are invisible to reps by ruling (a):
    assign_prospects (admin-only) is the control point.
    """
    session_data = frappe.session.data or {}
    role = session_data.get("vecrm_employee_role")
    vecrm_email = session_data.get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("Session does not include employee linkage. "
                     "Please log in again."),
            frappe.PermissionError,
        )
    if role in _PROSPECTING_ADMIN_ROLES:
        scope = "all"
    elif role in _PROSPECTING_REP_ROLES:
        scope = "own"
    else:
        frappe.throw(
            frappe._("You are not authorized for the prospecting queue."),
            frappe.PermissionError,
        )
    emp = frappe.db.get_value(
        "VECRM Employee", {"vecrm_email": vecrm_email},
        ["name", "vecrm_account_status"], as_dict=True,
    )
    if not emp or emp.vecrm_account_status != "Active":
        frappe.throw(
            frappe._("Your account is not Active."),
            frappe.PermissionError,
        )
    return vecrm_email, scope, emp.name


def _assert_owns(prospect_name, scope, rep_key):
    """Ownership check for rep-scoped single-record operations (S87)."""
    if scope == "all":
        return
    owner = frappe.db.get_value("VECRM Prospect", prospect_name, "assigned_rep")
    if owner != rep_key:
        frappe.throw(
            frappe._("This prospect is not in your queue."),
            frappe.PermissionError,
        )


def _rep_email(rep_name):
    """Resolve a VECRM Employee's vecrm_email for lead_owner (S89/B30).

    VECRM Lead.lead_owner carries an EMAIL (2820/2821 rows; lib/owner-names.ts
    joins on vecrm_email). VECRM Employee.name is a phone key. promote_prospect
    wrote the phone key, mis-keying the one lead it created. Throws rather than
    writing a blank: lead_owner is reqd.
    """
    em = frappe.db.get_value("VECRM Employee", rep_name, "vecrm_email")
    if not em:
        frappe.throw(
            "VECRM Employee {0} has no vecrm_email; cannot set lead_owner"
            .format(rep_name), frappe.ValidationError)
    return em


def _validate_rep_target(rep_name):
    """Validate a VECRM Employee may hold a prospect queue.

    Shared by create_prospect (S88) and assign_prospects (S89/B29). Returns the
    row so callers use the canonical .name. Extracted verbatim from
    create_prospect; the create path's behaviour is unchanged.
    """
    rep_row = frappe.db.get_value(
        "VECRM Employee", rep_name,
        ["name", "vecrm_account_status", "role"], as_dict=True,
    )
    if not rep_row:
        frappe.throw("VECRM Employee {0} not found".format(rep_name),
                     frappe.ValidationError)
    if rep_row.vecrm_account_status != "Active":
        frappe.throw("VECRM Employee {0} is not Active".format(rep_name),
                     frappe.ValidationError)
    if rep_row.role not in (_PROSPECTING_ADMIN_ROLES
                            + _PROSPECTING_REP_ROLES):
        frappe.throw(
            "VECRM Employee {0} (role {1}) cannot hold a prospect "
            "queue".format(rep_name, rep_row.role),
            frappe.ValidationError,
        )
    return rep_row


@frappe.whitelist()
def list_prospects(disposition=None, assigned_rep=None, callback_due=None,
                   search=None, city=None, industry=None, limit=50, offset=0,
                   sort_by=None, sort_dir=None):
    actor, scope, rep_key = _require_prospecting_access()
    limit = min(int(limit or 50), 500)
    offset = max(int(offset or 0), 0)

    # --- Sort whitelist: UI key -> real column. Raw input NEVER reaches ORDER BY. ---
    _SORT_COLUMNS = {
        "name": "first_name",
        "company": "company_name",
        "city": "city",
        "industry": "industry",
        "assigned_rep": "assigned_rep",
        "disposition": "disposition",
        "callback": "callback_on",
        "attempts": "attempt_count",
        "last_called": "last_called_at",
        "modified": "modified",
    }
    sort_col = _SORT_COLUMNS.get((sort_by or "").strip().lower(), "modified")
    sort_dir = "ASC" if str(sort_dir or "").strip().lower() == "asc" else "DESC"
    # Deterministic tiebreaker on unique name -> stable pagination.
    order_by = "{col} {dir}, name ASC".format(col=sort_col, dir=sort_dir)

    conds, args = ["1=1"], {}
    if scope == "own":
        # Ruling (a): reps see only their own queue. A caller-supplied
        # assigned_rep is ignored for reps -- never trust the portal.
        assigned_rep = rep_key
    if disposition:
        conds.append("disposition = %(disposition)s")
        args["disposition"] = disposition
    if assigned_rep:
        conds.append("assigned_rep = %(assigned_rep)s")
        args["assigned_rep"] = assigned_rep
    if callback_due:
        conds.append("disposition = 'Callback' AND callback_on <= %(today)s")
        args["today"] = today()
    if search:
        conds.append(
            "(first_name LIKE %(q)s OR last_name LIKE %(q)s "
            "OR company_name LIKE %(q)s OR mobile LIKE %(q)s)"
        )
        args["q"] = "%" + str(search).strip() + "%"
    if city:
        conds.append("city = %(city)s")
        args["city"] = city
    if industry:
        conds.append("industry = %(industry)s")
        args["industry"] = industry
    rows = frappe.db.sql(
        """SELECT name, first_name, last_name, title, company_name, industry,
                  mobile, city, state, assigned_rep, disposition, disposition_note, callback_on,
                  attempt_count, last_called_at, promoted_lead, modified
           FROM `tabVECRM Prospect`
           WHERE {conds}
           ORDER BY {order_by}
           LIMIT %(limit)s OFFSET %(offset)s""".format(
            conds=" AND ".join(conds), order_by=order_by),
        dict(args, limit=limit, offset=offset), as_dict=True)
    total = frappe.db.sql(
        "SELECT COUNT(*) c FROM `tabVECRM Prospect` WHERE {conds}".format(
            conds=" AND ".join(conds)), args, as_dict=True)[0].c
    return {"prospects": rows, "total": total, "actor": actor}


@frappe.whitelist()
def set_prospect_disposition(prospect=None, disposition=None, note=None,
                             callback_on=None):
    actor, scope, rep_key = _require_prospecting_access()
    if not prospect or not str(prospect).strip():
        frappe.throw("prospect is required", frappe.ValidationError)
    _assert_owns(str(prospect).strip(), scope, rep_key)
    if disposition not in DISPOSITIONS:
        frappe.throw(
            "disposition must be one of: {0}".format(", ".join(DISPOSITIONS)),
            frappe.ValidationError)
    if disposition == "Promoted":
        frappe.throw("Use promote_prospect to promote", frappe.ValidationError)
    doc = frappe.get_doc("VECRM Prospect", str(prospect).strip())
    if doc.disposition == "Promoted":
        frappe.throw(
            "Prospect {0} is already Promoted (lead {1})".format(
                doc.name, doc.promoted_lead), frappe.ValidationError)
    doc.disposition = disposition
    doc.disposition_note = note or ""
    doc.callback_on = callback_on if disposition == "Callback" else None
    doc.attempt_count = int(doc.attempt_count or 0) + 1
    doc.last_called_at = now_datetime()
    doc.add_comment("Info", "Disposition '{0}' by {1}".format(disposition, actor))
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    fresh = frappe.db.get_value(
        "VECRM Prospect", doc.name,
        ["disposition", "attempt_count"], as_dict=True)
    if not fresh or fresh.disposition != disposition:
        frappe.throw("Post-write verification failed for {0}".format(doc.name))
    return {"prospect": doc.name, "disposition": fresh.disposition,
            "attempt_count": fresh.attempt_count}


@frappe.whitelist()
def assign_prospects(prospect_names=None, to_rep=None):
    actor = _require_transfer_authority()
    if not to_rep or not str(to_rep).strip():
        frappe.throw("to_rep is required", frappe.ValidationError)
    to_rep = str(to_rep).strip()
    to_rep = _validate_rep_target(to_rep).name
    names = _names_arg(prospect_names)
    if not names:
        frappe.throw("prospect_names is required", frappe.ValidationError)
    assigned, skipped = [], []
    for name in names:
        row = frappe.db.get_value(
            "VECRM Prospect", name, ["name", "disposition"], as_dict=True)
        if not row:
            skipped.append({"name": name, "reason": "not found"})
            continue
        if row.disposition == "Promoted":
            skipped.append({"name": name, "reason": "already promoted"})
            continue
        frappe.db.set_value("VECRM Prospect", name, "assigned_rep", to_rep)
        assigned.append(name)
    frappe.db.commit()
    check = frappe.db.sql(
        """SELECT COUNT(*) c FROM `tabVECRM Prospect`
           WHERE name IN %(names)s AND assigned_rep = %(rep)s""",
        {"names": assigned or ["__none__"], "rep": to_rep}, as_dict=True)[0].c
    if check != len(assigned):
        frappe.throw("Post-write verification failed: expected {0}, found {1}"
                     .format(len(assigned), check))
    return {"assigned": len(assigned), "skipped": skipped,
            "to_rep": to_rep, "actor": actor}


@frappe.whitelist()
def promote_prospect(prospect=None, territory=None, priority=3):
    """Create a real VECRM Lead from an Interested prospect.

    Rule-E-adjacent: single Lead insert; normal push/ledger side effects are
    INTENTIONALLY not suppressed (it is a real new lead - S85 spec section 2).
    Field map covers the six documented-required Lead fields (OBS-S84-D):
    territory, priority, contact_date, lead_owner, company_name, status.

    S88: gate widened from _require_transfer_authority (admin-only) to
    _require_prospecting_access + _assert_owns, so a Sales Rep may promote a
    prospect that is in their OWN queue. Admin/SBAE scope "all" -> _assert_owns
    is a no-op. `actor` keeps its binding; the add_comment and return dict are
    unchanged.
    """
    actor, _pp_scope, _pp_rep_key = _require_prospecting_access()
    if not prospect or not str(prospect).strip():
        frappe.throw("prospect is required", frappe.ValidationError)
    _assert_owns(str(prospect).strip(), _pp_scope, _pp_rep_key)
    if not territory or not str(territory).strip():
        frappe.throw("territory is required to create the lead",
                     frappe.ValidationError)
    doc = frappe.get_doc("VECRM Prospect", str(prospect).strip())
    if doc.disposition == "Promoted":
        frappe.throw("Prospect {0} already promoted (lead {1})".format(
            doc.name, doc.promoted_lead), frappe.ValidationError)
    if not doc.assigned_rep:
        frappe.throw("Prospect {0} has no assigned rep; assign before promoting"
                     .format(doc.name), frappe.ValidationError)
    dup = frappe.db.get_value(
        "VECRM Lead", {"contact_number": doc.mobile}, "name")
    if dup:
        frappe.throw(
            "A lead with mobile {0} already exists: {1}".format(doc.mobile, dup),
            frappe.ValidationError)

    lead = frappe.get_doc({
        "doctype": "VECRM Lead",
        "company_name": doc.company_name,
        "contact_person_name": " ".join(
            p for p in (doc.first_name, doc.last_name) if p),
        "contact_number": doc.mobile,
        "contact_email": doc.business_email or "",
        "territory": str(territory).strip(),
        "priority": int(priority or 3),
        "contact_date": today(),
        "lead_owner": _rep_email(doc.assigned_rep),
        "status": "Open",
    })
    lead.insert(ignore_permissions=True)

    doc.disposition = "Promoted"
    doc.promoted_lead = lead.name
    doc.add_comment("Info", "Promoted to lead {0} by {1}".format(lead.name, actor))
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    fresh = frappe.db.get_value(
        "VECRM Lead", lead.name, ["name", "lead_owner"], as_dict=True)
    if not fresh:
        frappe.throw("Post-write verification failed: lead {0} not readable"
                     .format(lead.name))
    return {"prospect": doc.name, "lead": lead.name,
            "lead_owner": fresh.lead_owner, "actor": actor}


@frappe.whitelist()
def import_prospects_batch(rows_json=None, batch_tag=None):
    """One-time bulk import path (S85 spec section 3). Batch <= 500 rows.

    Dedupe inside: skips mobiles already present in Prospect or Lead tables.
    Returns inserted/skipped detail; caller (the transform module) asserts
    inserted + skipped == source rows per batch.
    """
    actor = _require_transfer_authority()
    if isinstance(rows_json, str):
        rows = json.loads(rows_json)
    else:
        rows = rows_json
    if not isinstance(rows, list) or not rows:
        frappe.throw("rows_json must be a non-empty list", frappe.ValidationError)
    if len(rows) > BULK_CAP:
        frappe.throw("At most {0} rows per batch".format(BULK_CAP),
                     frappe.ValidationError)
    inserted, skipped = [], []
    for i, row in enumerate(rows):
        mob = normalize_mobile(row.get("mobile"))
        if not mob or len(mob) != 10:
            skipped.append({"i": i, "mobile": row.get("mobile"),
                            "reason": "invalid mobile"})
            continue
        if frappe.db.exists("VECRM Prospect", {"mobile": mob}):
            skipped.append({"i": i, "mobile": mob, "reason": "prospect exists"})
            continue
        lead_dup = frappe.db.get_value(
            "VECRM Lead", {"contact_number": mob}, "name")
        if lead_dup:
            skipped.append({"i": i, "mobile": mob,
                            "reason": "lead exists: {0}".format(lead_dup)})
            continue
        doc = frappe.get_doc({
            "doctype": "VECRM Prospect",
            "first_name": row.get("first_name") or "(unknown)",
            "last_name": row.get("last_name") or "",
            "title": row.get("title") or "",
            "company_name": row.get("company_name") or "(unknown)",
            "industry": row.get("industry") or "",
            "mobile": mob,
            "alternate_mobile": row.get("alternate_mobile") or "",
            "business_email": row.get("business_email") or "",
            "city": row.get("city") or "",
            "state": row.get("state") or "",
            "region": row.get("region") or "",
            "company_size": row.get("company_size") or "",
            "website": row.get("website") or "",
            "linkedin": row.get("linkedin") or "",
            "company_details": row.get("company_details") or "",
            "source": row.get("source") or (batch_tag or "Purchased"),
            "assigned_rep": row.get("assigned_rep") or None,
            "disposition": row.get("disposition") or "Fresh",
            "disposition_note": row.get("disposition_note") or "",
            "notes": row.get("notes") or "",
        })
        doc.insert(ignore_permissions=True)
        inserted.append(doc.name)
    frappe.db.commit()
    count = frappe.db.sql(
        "SELECT COUNT(*) c FROM `tabVECRM Prospect`", as_dict=True)[0].c
    return {"inserted": len(inserted), "skipped": skipped,
            "table_total_after": count, "actor": actor}


@frappe.whitelist()
def create_prospect(payload_json=None):
    """Single-record prospect creation from the portal (S88).

    Guard: admin set (scope "all") + Sales Rep (scope "own").
      scope "own" -> assigned_rep is FORCED to the caller's own phone_key;
                     any client-supplied assigned_rep is ignored.
      scope "all" -> a supplied assigned_rep is honoured, validated Active and
                     role-in-set (R1-ii, deliberately stricter than
                     assign_prospects, which checks existence only);
                     omitted -> None (unassigned).
    `source` is stamped server-side as manual:<actor_email>; the payload's own
    `source` is explicitly discarded. The doctype's read_only:1 on `source` is
    a FORM flag only and does NOT block server-side dict construction.
    Dedupe: identical predicates to import_prospects_batch (Prospect + Lead),
    plus a DuplicateEntryError catch for the pre-check/insert race (`mobile` is
    unique:1 at the DB level).
    """
    actor, scope, rep_key = _require_prospecting_access()

    if isinstance(payload_json, str):
        payload = json.loads(payload_json)
    else:
        payload = payload_json
    if not isinstance(payload, dict) or not payload:
        frappe.throw("payload_json must be a non-empty object",
                     frappe.ValidationError)

    mob = normalize_mobile(payload.get("mobile"))
    if not mob or len(mob) != 10:
        frappe.throw(
            "Mobile must contain a valid 10-digit number (got: {0})".format(
                payload.get("mobile")),
            frappe.ValidationError,
        )

    first_name = (payload.get("first_name") or "").strip()
    company_name = (payload.get("company_name") or "").strip()
    if not first_name:
        frappe.throw("first_name is required", frappe.ValidationError)
    if not company_name:
        frappe.throw("company_name is required", frappe.ValidationError)

    if frappe.db.exists("VECRM Prospect", {"mobile": mob}):
        existing = frappe.db.get_value("VECRM Prospect", {"mobile": mob}, "name")
        frappe.throw(
            "A prospect with mobile {0} already exists: {1}".format(
                mob, existing),
            frappe.ValidationError,
        )
    lead_dup = frappe.db.get_value("VECRM Lead", {"contact_number": mob}, "name")
    if lead_dup:
        frappe.throw(
            "A lead with mobile {0} already exists: {1}".format(mob, lead_dup),
            frappe.ValidationError,
        )

    if scope == "own":
        assigned_rep = rep_key
    else:
        raw_rep = (payload.get("assigned_rep") or "").strip()
        if raw_rep:
            assigned_rep = _validate_rep_target(raw_rep).name
        else:
            assigned_rep = None

    doc = frappe.get_doc({
        "doctype": "VECRM Prospect",
        "first_name": first_name,
        "last_name": (payload.get("last_name") or "").strip(),
        "title": (payload.get("title") or "").strip(),
        "company_name": company_name,
        "industry": (payload.get("industry") or "").strip(),
        "mobile": mob,
        "alternate_mobile": (payload.get("alternate_mobile") or "").strip(),
        "business_email": (payload.get("business_email") or "").strip(),
        "city": (payload.get("city") or "").strip(),
        "state": (payload.get("state") or "").strip(),
        "region": (payload.get("region") or "").strip(),
        "company_size": (payload.get("company_size") or "").strip(),
        "website": (payload.get("website") or "").strip(),
        "linkedin": (payload.get("linkedin") or "").strip(),
        "company_details": payload.get("company_details") or "",
        "source": "manual:{0}".format(actor),
        "assigned_rep": assigned_rep,
        "disposition": "Fresh",
        "disposition_note": "",
        "notes": payload.get("notes") or "",
    })
    try:
        doc.insert(ignore_permissions=True)
    except frappe.exceptions.DuplicateEntryError:
        frappe.throw(
            "A prospect with mobile {0} already exists".format(mob),
            frappe.ValidationError,
        )
    frappe.db.commit()

    fresh = frappe.db.get_value(
        "VECRM Prospect", doc.name,
        ["name", "assigned_rep", "source", "mobile"], as_dict=True,
    )
    if not fresh:
        frappe.throw(
            "Post-write verification failed: prospect {0} not readable".format(
                doc.name))
    if fresh.mobile != mob or fresh.source != "manual:{0}".format(actor):
        frappe.throw(
            "Post-write verification failed: prospect {0} stored "
            "mobile={1} source={2}".format(doc.name, fresh.mobile, fresh.source)
        )
    return {"prospect": fresh.name, "assigned_rep": fresh.assigned_rep}


# ---------------------------------------------------------------------------
# Smartflo webhook receiver (P2) - DARK until secret is configured
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True, methods=["POST"])
def smartflo_webhook():
    """Receive Smartflo call-event webhooks. Idempotent on call_id.

    Guard: shared secret in header X-Anusuya-Secret must equal
    site_config `smartflo_webhook_secret`. Secret unset => hard refuse
    (ships dark, S85 spec section 7 gate 1).
    """
    secret = frappe.conf.get("smartflo_webhook_secret")
    if not secret:
        frappe.throw("Receiver not configured", frappe.PermissionError)
    provided = frappe.get_request_header("X-Anusuya-Secret") or ""
    if provided != secret:
        frappe.throw("Forbidden", frappe.PermissionError)

    try:
        payload = frappe.request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    if not payload:
        payload = {k: v for k, v in (frappe.form_dict or {}).items()
                   if not k.startswith("cmd")}

    call_id = str(payload.get("call_id") or payload.get("uuid") or "").strip()
    if not call_id:
        frappe.throw("call_id missing in payload", frappe.ValidationError)
    if frappe.db.exists("VECRM Smartflo Call", {"call_id": call_id}):
        return {"status": "duplicate", "call_id": call_id}

    customer_raw = (payload.get("customer_no_with_prefix")
                    or payload.get("call_to_number")
                    or payload.get("caller_id_number") or "")
    customer10 = normalize_mobile(customer_raw)
    direction = "Inbound" if str(
        payload.get("direction", "")).lower().startswith("in") else "Outbound"

    matched_doctype, matched_name = None, None
    if customer10 and len(customer10) == 10:
        matched_name = frappe.db.get_value(
            "VECRM Prospect", {"mobile": customer10}, "name")
        if matched_name:
            matched_doctype = "VECRM Prospect"
        else:
            matched_name = frappe.db.get_value(
                "VECRM Lead", {"contact_number": customer10}, "name")
            if matched_name:
                matched_doctype = "VECRM Lead"

    rec = frappe.get_doc({
        "doctype": "VECRM Smartflo Call",
        "call_id": call_id,
        "direction": direction,
        "customer_number": customer10 or str(customer_raw)[:20],
        "agent_number": str(payload.get("agent_number")
                            or payload.get("answered_agent_number") or "")[:20],
        "matched_doctype": matched_doctype,
        "matched_name": matched_name,
        "start_stamp": payload.get("start_stamp") or None,
        "duration_seconds": int(payload.get("duration")
                                or payload.get("call_duration") or 0),
        "recording_url": str(payload.get("recording_url") or "")[:500],
        "raw_payload": json.dumps(payload, default=str)[:20000],
    })
    rec.insert(ignore_permissions=True)
    if matched_doctype == "VECRM Prospect":
        frappe.db.set_value("VECRM Prospect", matched_name,
                            "last_called_at", now_datetime(),
                            update_modified=False)
    frappe.db.commit()
    return {"status": "ok", "call_id": call_id,
            "matched": matched_doctype, "record": rec.name}


# ---------------------------------------------------------------------------
# Smartflo P1 - click to call (S86). Write-free: call lifecycle is logged by
# the P2 webhook receiver above; this method only originates the call.
# ---------------------------------------------------------------------------

SMARTFLO_C2C_URL = "https://api-smartflo.tatateleservices.com/v1/click_to_call"


def _require_mapped_caller():
    """Caller must be an Active VECRM Employee (session vecrm_email) with an
    entry in site_config smartflo_agent_map. Returns (email, map_entry)."""
    vecrm_email = (frappe.session.data or {}).get("vecrm_email")
    if not vecrm_email:
        frappe.throw(
            frappe._("Session does not include employee linkage. "
                     "Please log in again."),
            frappe.PermissionError,
        )
    status = frappe.db.get_value(
        "VECRM Employee", {"vecrm_email": vecrm_email},
        "vecrm_account_status",
    )
    if status != "Active":
        frappe.throw(
            frappe._("Your account is not active for calling."),
            frappe.PermissionError,
        )
    agent_map = frappe.conf.get("smartflo_agent_map") or {}
    entry = agent_map.get(vecrm_email)
    if not entry or not entry.get("agent_number") or not entry.get("caller_id"):
        frappe.throw(
            frappe._("No Smartflo agent mapping for your account. "
                     "Contact the administrator."),
            frappe.PermissionError,
        )
    return vecrm_email, entry


@frappe.whitelist()
def click_to_call(prospect=None, lead=None):
    """Originate a Smartflo click-to-call from the caller's mapped agent
    number to the record's mobile. Exactly one of prospect/lead required."""
    import requests

    token = frappe.conf.get("smartflo_api_token")
    if not token:
        frappe.throw("Calling is not configured", frappe.PermissionError)
    if bool(prospect) == bool(lead):
        frappe.throw("Pass exactly one of prospect or lead",
                     frappe.ValidationError)
    vecrm_email, entry = _require_mapped_caller()

    if prospect:
        destination = frappe.db.get_value("VECRM Prospect", prospect, "mobile")
        record = prospect
    else:
        destination = frappe.db.get_value("VECRM Lead", lead, "contact_number")
        record = lead
    if destination is None:
        frappe.throw("Record not found: {0}".format(record),
                     frappe.ValidationError)
    destination = normalize_mobile(destination)
    if not destination or len(destination) != 10:
        frappe.throw("Record has no valid 10-digit mobile",
                     frappe.ValidationError)

    if prospect:
        # S87: reps may only originate to prospects in their own queue.
        # The lead branch keeps its own lead_owner model (out of scope).
        _p_actor, _p_scope, _p_rep_key = _require_prospecting_access()
        _assert_owns(str(prospect).strip(), _p_scope, _p_rep_key)
    payload = {
        "agent_number": entry["agent_number"],
        "destination_number": destination,
        "caller_id": entry["caller_id"],
        "async": 1,
        "custom_identifier": record,
    }
    try:
        resp = requests.post(
            SMARTFLO_C2C_URL,
            json=payload,
            headers={"Authorization": token,
                     "content-type": "application/json",
                     "accept": "application/json"},
            timeout=10,
        )
    except requests.RequestException as e:
        frappe.throw("Smartflo unreachable: {0}".format(type(e).__name__))
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After") or ""
        frappe.throw("Smartflo rate limit hit. Retry after: {0}s".format(
            retry_after or "a few"))
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": (resp.text or "")[:200]}
    if resp.status_code != 200 or not body.get("success", True):
        frappe.throw("Smartflo refused ({0}): {1}".format(
            resp.status_code, body.get("message") or body))
    return {"success": True, "message": body.get("message") or "originated",
            "record": record, "destination": destination,
            "actor": vecrm_email}


@frappe.whitelist()
def get_prospect(prospect=None):
    """Full single-record detail for the drawer (S86). Rep-scoped by
    _require_prospecting_access (S87); list rows stay lean, drawer fetches
    this."""
    actor, scope, rep_key = _require_prospecting_access()
    if not prospect:
        frappe.throw("prospect is required", frappe.ValidationError)
    _assert_owns(str(prospect).strip(), scope, rep_key)
    row = frappe.db.sql(
        """SELECT name, first_name, last_name, title, company_name, industry,
                  mobile, alternate_mobile, business_email, city, state,
                  region, company_size, website, linkedin, company_details,
                  source, assigned_rep, disposition, disposition_note,
                  callback_on, attempt_count, last_called_at, promoted_lead,
                  notes, creation, modified
           FROM `tabVECRM Prospect` WHERE name = %(name)s""",
        {"name": prospect}, as_dict=True)
    if not row:
        frappe.throw("Record not found: {0}".format(prospect),
                     frappe.ValidationError)
    return {"prospect": row[0], "actor": actor}


# ---------------------------------------------------------------------------
# SMARTFLO-PANEL-BE (S92) - read-only caller-ID panel feed.
# Matched-ownership scope on the _require_prospecting_access rail; Call Log
# history folded by normalized last-10 phone key. No writes.
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_recent_inbound_calls(limit=20, since=None):
    """Recent INBOUND Smartflo calls the caller may see, each hydrated with
    matched-record context and recent manual/device call history.

    Scope (S92, matched-ownership):
      "all" (admin / Sales Head) -> every inbound call, matched or not.
      "own" (Sales Rep)          -> inbound calls whose matched Prospect's
                                     assigned_rep == caller's rep_key.
    Read-only. Session-derived role; never trusts a client-supplied scope.
    """
    actor, scope, rep_key = _require_prospecting_access()

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    args = {"limit": limit}
    conds = ["sc.direction = 'Inbound'"]
    if scope == "own":
        conds.append("sc.matched_doctype = 'VECRM Prospect'")
        conds.append("p.assigned_rep = %(rep_key)s")
        args["rep_key"] = rep_key
    if since:
        conds.append("COALESCE(sc.start_stamp, sc.creation) >= %(since)s")
        args["since"] = since
    where = " AND ".join(conds)

    rows = frappe.db.sql(
        """SELECT sc.call_id, sc.customer_number, sc.agent_number,
                  sc.start_stamp, sc.creation, sc.duration_seconds,
                  sc.recording_url, sc.matched_doctype, sc.matched_name
           FROM `tabVECRM Smartflo Call` sc
           LEFT JOIN `tabVECRM Prospect` p
                  ON sc.matched_doctype = 'VECRM Prospect'
                 AND sc.matched_name = p.name
           WHERE {where}
           ORDER BY COALESCE(sc.start_stamp, sc.creation) DESC
           LIMIT %(limit)s""".format(where=where),
        args, as_dict=True,
    )

    out = []
    for r in rows:
        out.append({
            "call_id": r.call_id,
            "customer_number": r.customer_number,
            "agent_number": r.agent_number,
            "start_stamp": r.start_stamp or r.creation,
            "duration_seconds": r.duration_seconds,
            "recording_url": r.recording_url,
            "matched": _hydrate_match(r.matched_doctype, r.matched_name),
            "call_history": _recent_call_log(r.customer_number),
        })
    return {"scope": scope, "calls": out}


def _hydrate_match(matched_doctype, matched_name):
    """Resolve display + context for a matched Prospect or Lead; None if unmatched."""
    if not matched_doctype or not matched_name:
        return None
    if matched_doctype == "VECRM Prospect":
        p = frappe.db.get_value(
            "VECRM Prospect", matched_name,
            ["name", "first_name", "last_name", "company_name", "mobile",
             "city", "state", "assigned_rep", "disposition", "callback_on",
             "attempt_count", "last_called_at"], as_dict=True,
        )
        if not p:
            return None
        display = " ".join(x for x in (p.first_name, p.last_name) if x) \
            or p.company_name or p.name
        return {
            "doctype": "VECRM Prospect", "name": p.name,
            "display_name": display, "company": p.company_name,
            "city": p.city, "state": p.state, "assigned_rep": p.assigned_rep,
            "disposition": p.disposition, "attempt_count": p.attempt_count,
            "last_called_at": p.last_called_at, "callback_on": p.callback_on,
        }
    if matched_doctype == "VECRM Lead":
        lead = frappe.db.get_value(
            "VECRM Lead", matched_name,
            ["name", "company_name", "contact_person_name", "lead_owner",
             "status", "territory"], as_dict=True,
        )
        if not lead:
            return None
        return {
            "doctype": "VECRM Lead", "name": lead.name,
            "display_name": lead.contact_person_name or lead.company_name
            or lead.name,
            "company": lead.company_name, "city": None, "state": None,
            "assigned_rep": lead.lead_owner, "disposition": lead.status,
            "attempt_count": None, "last_called_at": None, "callback_on": None,
        }
    return None


def _recent_call_log(number, limit=5):
    """Recent VECRM Call Log rows for a phone number, matched on normalized
    last-10 digits (Call Log stores mixed +91 / bare forms)."""
    if not number:
        return []
    num10 = normalize_mobile(number) or ""
    if len(num10) != 10:
        return []
    return frappe.db.sql(
        """SELECT call_datetime, direction, disposition, notes,
                  next_followup_date, duration_seconds, source
           FROM `tabVECRM Call Log`
           WHERE RIGHT(REGEXP_REPLACE(contact_number, '[^0-9]', ''), 10)
                 = %(num)s
           ORDER BY call_datetime DESC
           LIMIT %(lim)s""",
        {"num": num10, "lim": limit}, as_dict=True,
    )


# ─────────────────────────────────────────────────────────────
# S120 — call history + notes for the prospect drawer
# Sales-team requirement, 12 Aug 2026. Sourced from VECRM Smartflo
# Call, NOT VECRM Call Log: Call Log holds 14 rows, all lead-keyed,
# zero prospect matches (measured 2026-08-12). Smartflo carries 945
# prospect-matched rows, matched_name integrity 945/945 with zero
# dangling and zero number disagreement.
# duration_seconds and recording_url are 0/empty on all 1908 rows;
# they are returned as null, never 0, so the FE cannot render an
# absent measurement as a real one. The CDR reconciler is the route
# to real durations and is a separate build.
# ─────────────────────────────────────────────────────────────

CALL_HISTORY_CAP = 200
CALL_COVERAGE_FROM = "2026-07-17"


def _call_history_rows(prospect_name, limit):
	"""Smartflo events for one prospect, newest first. Joined on
	matched_name, which the receive-time matcher sets and which was
	verified to agree with the phone key on every matched row."""
	return frappe.db.sql(
		"""SELECT sc.call_id, sc.direction, sc.customer_number,
		          COALESCE(sc.start_stamp, sc.creation) AS when_at,
		          sc.duration_seconds, sc.recording_url
		     FROM `tabVECRM Smartflo Call` sc
		    WHERE sc.matched_doctype = 'VECRM Prospect'
		      AND sc.matched_name = %(name)s
		 ORDER BY COALESCE(sc.start_stamp, sc.creation) DESC
		    LIMIT %(lim)s""",
		{"name": prospect_name, "lim": limit}, as_dict=True)


@frappe.whitelist()
def get_call_history(prospect=None, limit=50):
	"""Call count, per-day breakdown and recent calls for one prospect.
	Rep-scoped by _require_prospecting_access + _assert_owns."""
	actor, scope, rep_key = _require_prospecting_access()
	if not prospect or not str(prospect).strip():
		frappe.throw("prospect is required", frappe.ValidationError)
	prospect = str(prospect).strip()
	_assert_owns(prospect, scope, rep_key)
	if not frappe.db.exists("VECRM Prospect", prospect):
		frappe.throw("Record not found: {0}".format(prospect),
		             frappe.ValidationError)
	try:
		limit = int(limit)
	except (TypeError, ValueError):
		limit = 50
	limit = max(1, min(limit, CALL_HISTORY_CAP))

	agg = frappe.db.sql(
		"""SELECT COUNT(*) AS total,
		          MIN(COALESCE(start_stamp, creation)) AS first_call,
		          MAX(COALESCE(start_stamp, creation)) AS last_call,
		          SUM(CASE WHEN direction = 'Inbound' THEN 1 ELSE 0 END)
		            AS inbound,
		          SUM(CASE WHEN direction = 'Outbound' THEN 1 ELSE 0 END)
		            AS outbound
		     FROM `tabVECRM Smartflo Call`
		    WHERE matched_doctype = 'VECRM Prospect'
		      AND matched_name = %(name)s""",
		{"name": prospect}, as_dict=True)[0]

	by_date_raw = frappe.db.sql(
		"""SELECT DATE(COALESCE(start_stamp, creation)) AS on_date,
		          COUNT(*) AS calls,
		          SUM(CASE WHEN direction = 'Inbound' THEN 1 ELSE 0 END)
		            AS inbound,
		          SUM(CASE WHEN direction = 'Outbound' THEN 1 ELSE 0 END)
		            AS outbound
		     FROM `tabVECRM Smartflo Call`
		    WHERE matched_doctype = 'VECRM Prospect'
		      AND matched_name = %(name)s
		 GROUP BY on_date
		 ORDER BY on_date DESC""",
		{"name": prospect}, as_dict=True)

	# MySQL SUM() returns Decimal; cast so the wire contract is integers
	# throughout and the FE never sees 1.0 where it expects 1.
	by_date = [{
		"on_date": r.get("on_date"),
		"calls": int(r.get("calls") or 0),
		"inbound": int(r.get("inbound") or 0),
		"outbound": int(r.get("outbound") or 0),
	} for r in by_date_raw]

	calls = []
	for r in _call_history_rows(prospect, limit):
		dur = r.get("duration_seconds")
		rec = r.get("recording_url")
		calls.append({
			"call_id": r.get("call_id"),
			"direction": r.get("direction"),
			"number": r.get("customer_number"),
			"when": r.get("when_at"),
			"duration_seconds": int(dur) if dur else None,
			"recording_url": rec or None,
		})

	return {
		"prospect": prospect,
		"total_calls": int(agg.get("total") or 0),
		"inbound": int(agg.get("inbound") or 0),
		"outbound": int(agg.get("outbound") or 0),
		"first_call": agg.get("first_call"),
		"last_call": agg.get("last_call"),
		"by_date": by_date,
		"calls": calls,
		"returned": len(calls),
		"truncated": len(calls) >= limit,
		"coverage_from": CALL_COVERAGE_FROM,
		"duration_available": False,
	}


@frappe.whitelist()
def save_notes(prospect=None, notes=None, modified=None):
	"""Autosave the prospect notes field.

	notes MUST be sent. An empty string clears the field deliberately;
	an ABSENT notes argument is refused, because autosave makes a
	dropped payload indistinguishable from an intentional clear.

	modified is the timestamp the client last read (get_prospect
	returns it). If it no longer matches, the write is refused and the
	current value is returned so the caller can surface the conflict
	rather than silently overwriting a colleague.
	"""
	actor, scope, rep_key = _require_prospecting_access()
	if not prospect or not str(prospect).strip():
		frappe.throw("prospect is required", frappe.ValidationError)
	prospect = str(prospect).strip()
	_assert_owns(prospect, scope, rep_key)
	if notes is None:
		frappe.throw("notes is required (send an empty string to clear)",
		             frappe.ValidationError)
	notes = str(notes)
	if len(notes) > 20000:
		frappe.throw("notes exceeds 20000 characters", frappe.ValidationError)

	cur = frappe.db.get_value(
		"VECRM Prospect", prospect, ["notes", "modified"], as_dict=True)
	if not cur:
		frappe.throw("Record not found: {0}".format(prospect),
		             frappe.ValidationError)

	if modified is not None and str(modified).strip():
		if str(cur.modified) != str(modified).strip():
			return {"ok": False, "conflict": True, "prospect": prospect,
			        "notes": cur.notes or "", "modified": str(cur.modified),
			        "message": ("These notes were changed elsewhere since you "
			                    "opened them. Your text was not saved.")}

	if (cur.notes or "") == notes:
		return {"ok": True, "conflict": False, "changed": False,
		        "prospect": prospect, "notes": cur.notes or "",
		        "modified": str(cur.modified)}

	frappe.db.set_value("VECRM Prospect", prospect, "notes", notes)
	frappe.db.commit()
	fresh = frappe.db.get_value(
		"VECRM Prospect", prospect, ["notes", "modified"], as_dict=True)
	if not fresh or (fresh.notes or "") != notes:
		frappe.throw("Post-write verification failed for {0}".format(prospect))
	return {"ok": True, "conflict": False, "changed": True,
	        "prospect": prospect, "notes": fresh.notes or "",
	        "modified": str(fresh.modified)}


@frappe.whitelist()
def get_call_counts(prospect_names=None):
	"""Smartflo call counts for a page of prospects (S120).

	Bulk companion to get_call_history: a 50-row list costs two queries,
	never one per row. Every requested name comes back with an explicit
	integer including 0, so the FE renders a real zero rather than a blank
	where the map has no key.

	Rep scope filters the INPUT list: a rep asking about a prospect outside
	their queue gets silence, not a count. Ownership is resolved in one
	query, not per name.
	"""
	actor, scope, rep_key = _require_prospecting_access()
	names = _names_arg(prospect_names)
	if not names:
		return {"counts": {}, "coverage_from": CALL_COVERAGE_FROM}
	names = list(dict.fromkeys(names))
	ph = ", ".join(["%s"] * len(names))
	if scope == "own":
		owned = frappe.db.sql(
			"SELECT name FROM `tabVECRM Prospect`"
			" WHERE name IN (" + ph + ") AND assigned_rep = %s",
			tuple(names) + (rep_key,))
		names = [r[0] for r in owned]
		if not names:
			return {"counts": {}, "coverage_from": CALL_COVERAGE_FROM}
		ph = ", ".join(["%s"] * len(names))
	rows = frappe.db.sql(
		"""SELECT matched_name AS name, COUNT(*) AS calls
		     FROM `tabVECRM Smartflo Call`
		    WHERE matched_doctype = 'VECRM Prospect'
		      AND matched_name IN (""" + ph + """)
		 GROUP BY matched_name""",
		tuple(names), as_dict=True)
	found = {r["name"]: int(r["calls"]) for r in rows}
	return {"counts": {n: found.get(n, 0) for n in names},
	        "coverage_from": CALL_COVERAGE_FROM}
