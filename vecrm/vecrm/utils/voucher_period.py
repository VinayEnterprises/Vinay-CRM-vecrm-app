"""VECRM half-month period + submission-window helpers (TRAVEL vouchers).

The site timezone is Asia/Kolkata (see hooks.py), so frappe.utils.now_datetime()
and getdate() already return IST — no explicit tz conversion is needed here.

Periods (a payment cycle splits each month in two):
  H1 = days 1-15
  H2 = days 16-last day of month

Submit window — when a rep may submit that period's single consolidated
voucher. Opens once the period is essentially over (9pm on the last day of
the period) and closes at the existing backfill deadline:
  H1: 15th 21:00:00          ->  17th 23:59:59
  H2: last-day 21:00:00       ->  2nd of next month 23:59:59

On-time boundary (drives the late stamp):
  submitted ON the on-time day (H1: 15th; H2: last day)  => On Time
  submitted after it, inside the grace window            => Late
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time

import frappe

# Roles that bypass the petrol/travel submit-window gate entirely. Per policy
# (Jun 2026): ONLY Admin may submit outside the window; Sales Head and HR are
# held to the period window like every other role. (Distinct from
# _check_voucher_date_cutoff's deadline/backfill bypass, which is unchanged and
# still applies to expense vouchers too — expense submission is adhoc.)
WINDOW_BYPASS_ROLES = ("Admin",)


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def period_of(d) -> tuple[int, int, str]:
    """(year, month, 'H1'|'H2') for the half-month containing date d."""
    d = frappe.utils.getdate(d)
    return (d.year, d.month, "H1" if d.day <= 15 else "H2")


def period_key(d) -> str:
    """Stable string key for a half-month, e.g. '2026-06-H1'. Used for the
    single-draft-per-period dedup."""
    y, m, half = period_of(d)
    return f"{y:04d}-{m:02d}-{half}"


def period_label(d) -> str:
    """Human-facing half-month label, e.g. '1-15 Jun 2026' / '16-30 Jun 2026'.

    Derived from period_of() so a Travel (petrol) voucher dated by
    business_date and an Expense voucher dated by expense_date that fall in
    the SAME half-month render an identical label — which is what lets the
    payout page group the two voucher types under one period (S42)."""
    y, m, half = period_of(d)
    mon = calendar.month_abbr[m]  # e.g. 'Jun'
    if half == "H1":
        return f"1-15 {mon} {y}"
    return f"16-{_last_day(y, m)} {mon} {y}"


def on_time_day(d) -> date:
    """The last 'on-time' calendar day of d's period (15th, or last day)."""
    d = frappe.utils.getdate(d)
    if d.day <= 15:
        return date(d.year, d.month, 15)
    return date(d.year, d.month, _last_day(d.year, d.month))


def submit_window(d) -> tuple[datetime, datetime]:
    """(open_dt, close_dt) in IST for the period containing date d."""
    d = frappe.utils.getdate(d)
    open_dt = datetime.combine(on_time_day(d), time(21, 0, 0))
    if d.day <= 15:
        close_day = date(d.year, d.month, 17)
    elif d.month == 12:
        close_day = date(d.year + 1, 1, 2)
    else:
        close_day = date(d.year, d.month + 1, 2)
    close_dt = datetime.combine(close_day, time(23, 59, 59))
    return (open_dt, close_dt)


def is_submit_window_open(d, now=None) -> bool:
    """True iff `now` (default: IST now) is inside d's period submit window."""
    now_dt = frappe.utils.get_datetime(now) if now is not None else frappe.utils.now_datetime()
    open_dt, close_dt = submit_window(d)
    return open_dt <= now_dt <= close_dt


def lateness(d, submitted_at=None) -> str:
    """'On Time' or 'Late', by submission date vs d's on-time day."""
    sub = frappe.utils.get_datetime(submitted_at) if submitted_at is not None else frappe.utils.now_datetime()
    return "On Time" if sub.date() <= on_time_day(d) else "Late"
