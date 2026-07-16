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


@frappe.whitelist()
def list_prospects(disposition=None, assigned_rep=None, callback_due=None,
                   search=None, limit=50, offset=0):
    actor = _require_transfer_authority()
    limit = min(int(limit or 50), 200)
    offset = max(int(offset or 0), 0)
    conds, args = ["1=1"], {}
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
    rows = frappe.db.sql(
        """SELECT name, first_name, last_name, title, company_name, industry,
                  mobile, city, state, assigned_rep, disposition, callback_on,
                  attempt_count, last_called_at, promoted_lead, modified
           FROM `tabVECRM Prospect`
           WHERE {conds}
           ORDER BY modified DESC
           LIMIT %(limit)s OFFSET %(offset)s""".format(conds=" AND ".join(conds)),
        dict(args, limit=limit, offset=offset), as_dict=True)
    total = frappe.db.sql(
        "SELECT COUNT(*) c FROM `tabVECRM Prospect` WHERE {conds}".format(
            conds=" AND ".join(conds)), args, as_dict=True)[0].c
    return {"prospects": rows, "total": total, "actor": actor}


@frappe.whitelist()
def set_prospect_disposition(prospect=None, disposition=None, note=None,
                             callback_on=None):
    actor = _require_transfer_authority()
    if not prospect or not str(prospect).strip():
        frappe.throw("prospect is required", frappe.ValidationError)
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
    if not frappe.db.exists("VECRM Employee", to_rep):
        frappe.throw("VECRM Employee {0} not found".format(to_rep),
                     frappe.ValidationError)
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
    """
    actor = _require_transfer_authority()
    if not prospect or not str(prospect).strip():
        frappe.throw("prospect is required", frappe.ValidationError)
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
        "lead_owner": doc.assigned_rep,
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
