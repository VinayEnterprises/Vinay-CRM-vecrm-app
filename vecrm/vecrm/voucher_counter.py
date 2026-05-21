# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""Strict gap-free voucher counter allocator (VECRM L10).

Per (series, FY) monotonic counter with row-level locking. The allocator runs
inside the caller's transaction; the FOR UPDATE row lock held by
``next_number`` is released only when the caller's enclosing voucher
transaction commits or rolls back. This is what makes allocation gap-free:
a rollback returns the counter to its pre-allocation value because the
UPDATE on ``last_value`` is part of the same transaction.

S22 §6 hard-gate fix (the real one)
====================================

The previous versions of this allocator had a latent stale-read bug present
since the very first commit:

  1. ``SELECT name ... FOR UPDATE`` acquired the row lock
  2. ``frappe.get_doc(DOCTYPE, name).last_value`` (original) OR a separate
     ``SELECT last_value ... WHERE name = %s`` (S22 first-attempt fix) read
     the counter value via a NON-LOCKING consistent read

A non-locking SELECT under REPEATABLE-READ honors the transaction's MVCC
read view, which is established at the FIRST consistent read in the
transaction — long BEFORE next_number is called (typically by
``check_permission``, ``_validate_links``, or our own ``before_insert``'s
Employee/Rate-Card reads). After a concurrent transaction commits a new
``last_value``, the snapshot-bound read still returns the OLD value. Every
serialized thread therefore computes the same new_value, and 9-of-10 collide
with DuplicateEntryError on the voucher INSERT.

The fix: read ``last_value`` INSIDE the same locking statement that acquires
the FOR UPDATE row lock. A locking read returns the current committed row,
not a snapshot view. This is what every concurrency diagnostic that PASSED
in the S22 hard-gate investigation actually does — including the diagnostics
we wrote tonight that achieved 10/10 success under contention.

Why this latent bug was never caught: this allocator was NEVER concurrency-
tested before S22 §6. Earlier sessions (S19/S20) verified its sha (L8) and
its single-threaded correctness, but never ran it under load. S22 §6 is the
first time the bug had a chance to surface.

Public surface (L10-invocable as ``vecrm.voucher_counter.*``):
  * :func:`fy_label` — Indian FY label for a business date.
  * :func:`next_number` — allocate the next integer for a (series, FY) pair.
  * :func:`seed_probe` — reachability sentinel (S7 L10 pattern).
"""

import frappe
from frappe import _
from frappe.utils import getdate, now

DOCTYPE = "VECRM Voucher Counter"
MAX_VALUE = 99999


def fy_label(business_date) -> str:
	"""Return the Indian financial-year label ``"YY-YY"`` for ``business_date``.

	Month >= 4 ⇒ ``f"{yy}-{yy+1}"``; month <= 3 ⇒ ``f"{yy-1}-{yy}"``. Years are
	the two-digit, zero-padded calendar-year modulo 100, so the century edge
	is handled explicitly: e.g. 2000-04-01 ⇒ ``"00-01"`` and 2000-03-31 ⇒
	``"99-00"``.

	Fails loud — every voucher MUST have a date that determines its FY, and a
	silent default would corrupt the counter partitioning.
	"""
	if business_date is None or business_date == "":
		frappe.throw(
			_("Voucher business_date is required to derive the FY label."),
			frappe.ValidationError,
		)

	try:
		dt = getdate(business_date)
	except Exception:
		dt = None

	if dt is None:
		frappe.throw(
			_("Voucher business_date '{0}' is not a parseable date.").format(business_date),
			frappe.ValidationError,
		)

	if dt.month >= 4:
		start_year = dt.year
		end_year = dt.year + 1
	else:
		start_year = dt.year - 1
		end_year = dt.year

	yy_start = start_year % 100
	yy_end = end_year % 100
	return f"{yy_start:02d}-{yy_end:02d}"


def _lock_counter_row(counter_key: str) -> tuple[str | None, int]:
	"""Acquire an InnoDB row-level lock on the counter row, returning (name, last_value).

	Reads BOTH ``name`` and ``last_value`` in the SAME locking statement.
	This is the S22 §6 fix: under REPEATABLE-READ MVCC, a separate
	non-locking SELECT after the FOR UPDATE would return the transaction's
	stale snapshot view of ``last_value``, not the current committed value.
	Reading both columns in the FOR UPDATE statement guarantees we see the
	row's latest committed state.

	Returns ``(None, 0)`` if no row exists for ``counter_key``. The lock is
	held until the surrounding transaction commits or rolls back — there is
	no standalone commit in this module.
	"""
	rows = frappe.db.sql(
		"""
		SELECT name, last_value
		FROM `tabVECRM Voucher Counter`
		WHERE counter_key = %s
		FOR UPDATE
		""",
		(counter_key,),
		as_dict=True,
	)
	if not rows:
		return (None, 0)
	return (rows[0]["name"], rows[0]["last_value"] or 0)


def next_number(series: str, fy: str) -> int:
	"""Allocate the next integer for ``(series, fy)`` — strict gap-free.

	Algorithm (per L10 §3, S22 §6 corrected):
	  1. Compute ``counter_key = f"{series}-{fy}"``.
	  2. ``SELECT name, last_value ... FOR UPDATE`` the matching row via
	     :func:`_lock_counter_row`. Both columns read in ONE locking
	     statement — this is the S22 §6 fix.
	  3. If absent, perform a single atomic ``INSERT ... ON DUPLICATE KEY
	     UPDATE counter_key = counter_key`` upsert (CR-4 no-op clause).
	  4. UNCONDITIONALLY re-run ``SELECT name, last_value ... FOR UPDATE``
	     (CR-3 invariant). Both columns again returned by the locking read.
	  5. ``new_value = last_value + 1``. Refuse > 99999.
	  6. Persist via raw SQL ``UPDATE ... SET last_value = %s, modified = %s
	     WHERE name = %s``.
	  7. Return ``new_value``. Row lock released by caller's transaction.

	INVARIANT (CR-3): every return path performs its increment on a row
	acquired via explicit ``SELECT ... FOR UPDATE``. The locking read now
	also returns the row's current ``last_value`` — eliminating the
	stale-snapshot read that defeated this invariant in practice under
	concurrent load.

	ON DUPLICATE clause invariant (CR-4 critical): the upsert's
	``ON DUPLICATE KEY UPDATE`` clause MUST remain the no-op
	self-assignment ``counter_key = counter_key``. UNCHANGED.

	Controller-guard note: the controller's ``on_update`` guard (which
	gates on ``flags.vecrm_counter_alloc``) is NOT REACHED — allocator
	writes go through raw SQL UPDATE, not the ORM. The guard remains in
	force for any other code path (UI, Desk, scripts) that tries to
	``doc.save()`` a counter row.

	HISTORICAL NOTE: prior versions of this allocator (commit a990fa8 sha
	7ad2b3a3 onward) read ``last_value`` via a SEPARATE statement from the
	FOR UPDATE lock — either ``frappe.get_doc(DOCTYPE, name).last_value``
	or a plain ``SELECT last_value WHERE name = %s``. Both are
	non-locking consistent reads, which under REPEATABLE-READ return the
	transaction's stale snapshot rather than the current committed value.
	This is a textbook split lock-and-read antipattern. It was latent for
	the allocator's entire history; S22 §6 is the first concurrency
	exercise that surfaced it.
	"""
	if not series:
		frappe.throw(
			_("VECRM Voucher Counter: series is required."), frappe.ValidationError
		)
	if not fy:
		frappe.throw(
			_("VECRM Voucher Counter: fy is required."), frappe.ValidationError
		)

	counter_key = f"{series}-{fy}"

	name, current_value = _lock_counter_row(counter_key)
	if name is None:
		# ── Atomic upsert: create-if-absent, no-op-if-exists ─────────────
		ts = now()
		usr = frappe.session.user
		frappe.db.sql(
			"""
			INSERT INTO `tabVECRM Voucher Counter`
			  (`name`, `creation`, `modified`, `modified_by`, `owner`,
			   `docstatus`, `idx`,
			   `counter_key`, `series`, `fy`, `last_value`)
			VALUES
			  (%s, %s, %s, %s, %s,
			   %s, %s,
			   %s, %s, %s, %s)
			-- CR-4 INVARIANT (DO NOT EDIT): no-op self-assignment ONLY.
			ON DUPLICATE KEY UPDATE `counter_key` = `counter_key`
			""",
			(
				counter_key,  # name (field:counter_key autoname → name == counter_key)
				ts,           # creation
				ts,           # modified
				usr,          # modified_by
				usr,          # owner
				0,            # docstatus
				0,            # idx
				counter_key,  # business: counter_key
				series,       # business: series
				fy,           # business: fy
				0,            # business: last_value seed
			),
		)

		# CR-3 convergence point: re-lock and read value in same statement.
		name, current_value = _lock_counter_row(counter_key)
		if name is None:
			# Genuinely unreachable post-upsert.
			frappe.throw(
				_(
					"VECRM Voucher Counter: race resolution failed for "
					"counter_key '{0}'."
				).format(counter_key),
				frappe.ValidationError,
			)

	# ── Increment using value read from locking statement ───────────────
	# current_value came from the FOR UPDATE — it IS the latest committed
	# value, not a snapshot. Safe to increment.
	new_value = current_value + 1

	if new_value > MAX_VALUE:
		frappe.throw(
			_("VECRM Voucher Counter overflow: series {0} FY {1} exhausted").format(
				series, fy
			),
			frappe.ValidationError,
		)

	# Raw UPDATE under held FOR UPDATE lock. Concurrent threads serialize
	# on the row lock and each see the post-commit value when they acquire.
	frappe.db.sql(
		"""
		UPDATE `tabVECRM Voucher Counter`
		SET `last_value` = %s, `modified` = %s, `modified_by` = %s
		WHERE `name` = %s
		""",
		(new_value, now(), frappe.session.user, name),
	)

	return new_value


def seed_probe() -> str:
	"""L10 reachability sentinel (S7 pattern).

	The harness invokes this via ``bench execute vecrm.voucher_counter.seed_probe``
	to confirm the module is importable before running concurrency tests against
	:func:`next_number`. The return value is a fixed string and carries no state.
	"""
	return "vecrm.voucher_counter:ok"
