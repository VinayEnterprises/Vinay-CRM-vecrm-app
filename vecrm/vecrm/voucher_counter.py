# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""Strict gap-free voucher counter allocator (VECRM L10).

Per (series, FY) monotonic counter with row-level locking. The allocator runs
inside the caller's transaction; the FOR UPDATE row lock held by
``next_number`` is released only when the caller's enclosing voucher
transaction commits or rolls back. This is what makes allocation gap-free:
a rollback returns the counter to its pre-allocation value because the
UPDATE on ``last_value`` is part of the same transaction.

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


def _lock_counter_row(counter_key: str) -> str | None:
	"""Acquire an InnoDB row-level lock on the counter row, returning its name.

	Returns ``None`` if no row exists for ``counter_key``. The lock is held
	until the surrounding transaction commits or rolls back — there is no
	standalone commit in this module.
	"""
	rows = frappe.db.sql(
		"""
		SELECT name
		FROM `tabVECRM Voucher Counter`
		WHERE counter_key = %s
		FOR UPDATE
		""",
		(counter_key,),
		as_dict=True,
	)
	return rows[0]["name"] if rows else None


def next_number(series: str, fy: str) -> int:
	"""Allocate the next integer for ``(series, fy)`` — strict gap-free.

	Algorithm (per L10 §3):
	  1. Compute ``counter_key = f"{series}-{fy}"``.
	  2. ``SELECT ... FOR UPDATE`` the matching row via :func:`_lock_counter_row`.
	  3. If absent, perform a single atomic ``INSERT ... ON DUPLICATE KEY
	     UPDATE counter_key = counter_key`` upsert that seeds the row at
	     ``last_value = 0`` if it does not yet exist and is a no-op
	     self-assignment otherwise. No ORM ``Document`` is constructed,
	     no ``on_update`` hook fires, and no integrity exception is
	     ever raised to the caller — so the duplicate-loser ORM-state-
	     coherence problem is structurally absent (no ORM state exists
	     to be incoherent).
	  4. UNCONDITIONALLY re-run ``SELECT ... FOR UPDATE``. The
	     create-winner and the no-op-loser converge on this single
	     explicit-locked-row code path. If the re-lock still returns
	     ``None``, that is the genuinely unreachable case (the upsert
	     guaranteed the row exists) and the function surfaces a hard
	     error.
	  5. ``new_value = last_value + 1``. Refuse > 99999 (five-digit overflow).
	  6. Persist ``last_value = new_value`` via ``doc.save()`` with the
	     ``vecrm_counter_alloc`` flag set so the controller guard lets
	     the write through.
	  7. Return ``new_value``. The row lock is released by the caller's
	     transaction boundary — no standalone commit here.

	INVARIANT (CR-3): every return path from :func:`next_number` performs
	its increment on a row acquired via explicit ``SELECT ... FOR UPDATE``
	(:func:`_lock_counter_row`). No path relies on InnoDB's implicit
	insert-intention lock or on the ``ON DUPLICATE KEY UPDATE`` upsert's
	transient X-lock as the synchronisation primitive.

	ON DUPLICATE clause invariant (CR-4 critical): the upsert's
	``ON DUPLICATE KEY UPDATE`` clause MUST remain the no-op
	self-assignment ``counter_key = counter_key``. It must NEVER write
	``last_value`` or any other business column. The counter value is
	owned solely by the explicit-FOR-UPDATE-locked increment path
	below; modifying the ON DUPLICATE clause to write any business
	column silently destroys strict gap-free numbering — every
	post-first voucher in an FY would collide/reset to 1. This is the
	single line whose accidental future edit is catastrophic; do not
	touch it without re-deriving the algorithm.

	Controller-guard bypass note: the raw upsert deliberately bypasses
	the :class:`VECRMVoucherCounter.on_update` controller guard at
	create time. This is intended — the guard exists to block
	out-of-band UI/Desk/script mutation of counter rows, and
	:func:`next_number` is the sole sanctioned create path. The
	increment tail (``doc.save(ignore_permissions=True)`` with
	``flags.vecrm_counter_alloc=True``) still goes through the
	controller, so the guard remains in force for every value-mutating
	save.

	Column set + defaults derived from Frappe v16.18.2
	``frappe/model/base_document.py::db_insert``: 7 bookkeeping columns
	(``name, creation, modified, modified_by, owner, docstatus, idx``)
	+ 4 business columns (``counter_key, series, fy, last_value``).
	``name`` equals ``counter_key`` per the ``field:counter_key``
	autoname semantics in ``frappe/model/naming.py::_field_autoname``
	(``cstr(doc.counter_key).strip()`` — our counter_key has no
	whitespace, so the values are byte-identical). All values are
	bound parameters; no user data is interpolated into the SQL
	string.
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

	name = _lock_counter_row(counter_key)
	if name is None:
		# ── Atomic upsert: create-if-absent, no-op-if-exists ─────────────
		# A single INSERT ... ON DUPLICATE KEY UPDATE seeds the row at
		# last_value = 0 if it does not yet exist, or self-assigns
		# counter_key = counter_key (no-op) if a concurrent allocator
		# already won the create race. Constructs no ORM Document,
		# fires no on_update hook, raises no integrity exception. The
		# row is then re-locked unconditionally below via explicit
		# SELECT ... FOR UPDATE — that is the synchronisation primitive,
		# not the upsert's transient X-lock.
		#
		# Column set + defaults derived from Frappe v16.18.2
		# base_document.py::db_insert (see docstring).
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
			-- This clause MUST NEVER write last_value or any other
			-- business column. The counter value is owned solely by the
			-- explicit FOR-UPDATE-locked increment path below; writing
			-- a business column here silently destroys strict gap-free
			-- numbering (every post-first voucher in an FY would
			-- collide/reset to 1).
			ON DUPLICATE KEY UPDATE `counter_key` = `counter_key`
			""",
			(
				counter_key,  # name  (field:counter_key autoname → name == counter_key)
				ts,           # creation
				ts,           # modified  (same instant as creation)
				usr,          # modified_by
				usr,          # owner     (identical to modified_by on insert)
				0,            # docstatus = DocStatus.DRAFT
				0,            # idx
				counter_key,  # business: counter_key
				series,       # business: series
				fy,           # business: fy
				0,            # business: last_value seed
			),
		)

		# ── Convergence point: explicit FOR UPDATE on the now-existing row ──
		# The upsert above guaranteed the row exists. Re-lock it via
		# SELECT ... FOR UPDATE before incrementing — this is the
		# CR-3 invariant: every return path holds an explicit
		# FOR-UPDATE lock on the row it increments.
		name = _lock_counter_row(counter_key)
		if name is None:
			# Genuinely unreachable. The atomic upsert above guarantees
			# the row exists; FOR UPDATE will find it (blocking until
			# a concurrent winner commits if necessary). Surface loudly
			# rather than silently double-allocate.
			frappe.throw(
				_(
					"VECRM Voucher Counter: race resolution failed for "
					"counter_key '{0}'."
				).format(counter_key),
				frappe.ValidationError,
			)

	doc = frappe.get_doc(DOCTYPE, name)
	new_value = (doc.last_value or 0) + 1
	if new_value > MAX_VALUE:
		frappe.throw(
			_("VECRM Voucher Counter overflow: series {0} FY {1} exhausted").format(
				series, fy
			),
			frappe.ValidationError,
		)

	doc.last_value = new_value
	doc.flags.vecrm_counter_alloc = True
	doc.save(ignore_permissions=True)

	return new_value


def seed_probe() -> str:
	"""L10 reachability sentinel (S7 pattern).

	The harness invokes this via ``bench execute vecrm.voucher_counter.seed_probe``
	to confirm the module is importable before running concurrency tests against
	:func:`next_number`. The return value is a fixed string and carries no state.
	"""
	return "vecrm.voucher_counter:ok"
