# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VECRMAuthAuditLog(Document):
    """Append-only audit log for VECRM portal auth events.

    Created only via vecrm.api.* code paths. Never edited or deleted after creation.
    """
    pass
