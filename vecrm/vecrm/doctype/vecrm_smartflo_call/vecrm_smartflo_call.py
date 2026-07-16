# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""VECRM Smartflo Call — raw telephony event log (S85 spec P2).

Insert-only from the webhook receiver; idempotent on call_id (UNIQUE).
Device-sourced portal call history stays in VECRM Call Log — separate
surfaces by design (S85 ruling; merge option noted for later).
"""
from frappe.model.document import Document


class VECRMSmartfloCall(Document):
    pass
