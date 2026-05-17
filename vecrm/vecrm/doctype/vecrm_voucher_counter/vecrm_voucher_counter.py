# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VECRMVoucherCounter(Document):
	"""Machine-maintained per-(series, FY) monotonic counter.

	Defense-in-depth lockdown:
	  * Permission layer denies create/write/delete to all roles (read-only).
	  * Controller layer blocks every save path that didn't go through the
	    allocator in ``vecrm.voucher_counter.next_number`` — the allocator
	    sets ``flags.vecrm_counter_alloc = True`` before invoking ``save()``.
	  * ``on_trash`` is unconditionally blocked: counter rows are permanent
	    accounting infrastructure.

	The allocator gate is keyed on the per-save flag — NOT on ``is_new()``.
	S6 §2.1: ``is_new()`` returns False on the post-insert ``on_update`` hook
	path, so an ``if self.is_new(): return`` short-circuit would let the
	insert through and then block every subsequent allocator save. The flag
	is the only correct gate.
	"""

	def on_update(self):
		if not getattr(self.flags, "vecrm_counter_alloc", False):
			frappe.throw(
				_(
					"VECRM Voucher Counter is machine-maintained. "
					"Direct modification is not permitted."
				),
				frappe.PermissionError,
			)

	def on_trash(self):
		frappe.throw(
			_(
				"VECRM Voucher Counter rows are permanent accounting "
				"infrastructure and cannot be deleted."
			),
			frappe.PermissionError,
		)
