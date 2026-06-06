# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""
VECRM Call Log — per-call activity log for inside-sales call tracking.

A "conversation" is a connected call lasting >= CONVERSATION_MIN seconds.
Duration arrives from the device call log (or manual entry); validate()
derives the read-only is_conversation flag from disposition + duration.

All identity/auth (caller = session employee, never client-supplied) lives
in vecrm.api.log_call — this controller only computes the conversation flag.
"""

import frappe
from frappe.model.document import Document

# A connected call lasting >= this many seconds counts as a conversation.
CONVERSATION_MIN = 30

# Dispositions that mean the call never connected — never a conversation,
# regardless of recorded duration.
NON_CONNECT_DISPOSITIONS = ("No Answer", "Busy", "Switched Off", "Wrong Number")


class VECRMCallLog(Document):
    def validate(self):
        connected = self.disposition not in NON_CONNECT_DISPOSITIONS
        duration = int(self.duration_seconds or 0)
        self.is_conversation = 1 if (connected and duration >= CONVERSATION_MIN) else 0
