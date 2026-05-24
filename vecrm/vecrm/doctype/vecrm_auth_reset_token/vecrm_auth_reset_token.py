# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class VECRMAuthResetToken(Document):
    """Auth reset token storage.

    Rows in this doctype are written by `vecrm.api` API methods only.
    Direct portal access is not exposed; portal interacts via:
      - vecrm.api.request_password_reset / request_pin_reset (creates row)
      - vecrm.api.complete_password_reset / complete_pin_reset (consumes row)

    Security invariants (enforced by API layer, not by DB):
      - token_hash stores sha256 of raw token; raw token never persisted
      - Token comparison must use hmac.compare_digest (constant-time)
      - Single-use: consumed_at is set on first successful use
      - Time-bounded: expires_at enforced by API on consume
      - Rate-limited: 3 reset requests per employee per 15-min window (API-enforced)
      - No-enumeration: request_*_reset always returns success regardless of match
    """

    pass
