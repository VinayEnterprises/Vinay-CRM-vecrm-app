# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""Two-tier voucher-validation bypass (S41).

A controlled escape hatch for data-correction work where the normal
voucher business rules (duplicate-per-period, visit-date period, bi-monthly
submission window) would block a legitimate fix.

Tier 1 — Global bypass: a single site-wide flag in frappe.cache
(`vecrm_global_bypass`). When truthy, ALL voucher validations are skipped
for ALL users. No schema change; toggles instantly; cleared on cache flush.
Admin-only to set (vecrm.api.set_global_bypass).

Tier 2 — User-level bypass: the `validation_bypass` Check field on a
VECRM Employee. When set, that employee's vouchers skip validations. Admin
sets it per employee; persists across restarts.

Both tiers skip ONLY the custom business rules — duplicate check, visit-date
period check, submission-window cutoff. Structural integrity (Frappe
required fields, snapshot setup, total recomputation) is NEVER skipped, so
a bypassed voucher is still internally consistent.

Single source of truth: TV/EV controllers and api.py's cutoff all import
`validations_bypassed` from here so the two tiers cannot drift apart.
"""
from __future__ import annotations

import frappe

# Cache key for the Tier-1 global flag. Stored as 1/0 (int) per the S41
# contract; any truthy value enables the bypass.
GLOBAL_BYPASS_KEY = "vecrm_global_bypass"


def global_bypass_active() -> bool:
    """True if the site-wide Tier-1 global bypass flag is set."""
    return bool(frappe.cache().get_value(GLOBAL_BYPASS_KEY))


def employee_bypass_active(submitter: str | None) -> bool:
    """True if the Tier-2 user-level bypass is set for `submitter`.

    Args:
      submitter: VECRM Employee name (phone PK). None/empty → False.
    """
    if not submitter:
        return False
    return bool(
        frappe.db.get_value("VECRM Employee", submitter, "validation_bypass")
    )


def validations_bypassed(submitter: str | None) -> bool:
    """True if EITHER tier authorizes skipping voucher business rules.

    Global (Tier 1) is checked first (cache hit, no submitter needed);
    then the submitter's user-level (Tier 2) flag.
    """
    return global_bypass_active() or employee_bypass_active(submitter)
