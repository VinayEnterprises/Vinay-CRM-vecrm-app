# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""
VECRM Lead Touchpoint — append-only touchpoint log per PD-S30-LEAD-FOLLOWUP Phase 2.

This controller is intentionally minimal. The doctype is append-only by design
(see PD-S30-LEAD-FOLLOWUP-LOCK Phase 2 spec + Q-LEAD-FOLLOWUP-PHASE-2-ADDENDUM
Q-LFL-P2-8: no delete endpoint, touchpoints are immutable).

All business logic — auth gates, terminal-state behavior (allowed on all
statuses), session-derived actor_employee — lives in
vecrm.api.create_touchpoint. The controller exists primarily to:

  1. Provide a Document subclass for Frappe's ORM hooks.
  2. Be the file Frappe expects in this doctype directory.

If future requirements introduce server-side touchpoint validation
(e.g. forbid touchpoint_date in future, deduplicate same-day same-type
touchpoints), the validate() / before_save() hooks land here.
"""

import frappe
from frappe.model.document import Document


class VECRMLeadTouchpoint(Document):
    pass
