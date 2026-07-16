# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""VECRM Prospect — pre-lead tier for purchased/cold databases (S85 spec R-P1).

Ruled dispositions (R-P2): Fresh / No answer / Not interested / Callback /
Wrong number / Interested / Other / Promoted. `Other` requires a note;
`Callback` requires callback_on. Mobile is the normalized 10-digit dedupe key.
"""
import re

import frappe
from frappe.model.document import Document

NOTE_REQUIRED = ("Other",)
CALLBACK = "Callback"


def normalize_mobile(raw):
    """Digits-only, last 10. Returns None when nothing usable remains."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) >= 10:
        return digits[-10:]
    return digits or None


class VECRMProspect(Document):
    def validate(self):
        self._normalize_numbers()
        self._validate_disposition_conditionals()

    def _normalize_numbers(self):
        mob = normalize_mobile(self.mobile)
        if not mob or len(mob) != 10:
            frappe.throw(
                "Mobile must contain a valid 10-digit number "
                "(got: {0})".format(self.mobile),
                frappe.ValidationError,
            )
        self.mobile = mob
        if self.alternate_mobile:
            self.alternate_mobile = normalize_mobile(self.alternate_mobile) or ""

    def _validate_disposition_conditionals(self):
        if self.disposition in NOTE_REQUIRED and not (self.disposition_note or "").strip():
            frappe.throw(
                "Disposition '{0}' requires a disposition note".format(self.disposition),
                frappe.ValidationError,
            )
        if self.disposition == CALLBACK and not self.callback_on:
            frappe.throw(
                "Disposition 'Callback' requires a callback date",
                frappe.ValidationError,
            )
