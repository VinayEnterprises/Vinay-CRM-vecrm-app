# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""Add advance-payment fields to VECRM Expense Voucher + backfill net_payable,
and add the VECRM Payout Adjustment composite unique index (v1_11).

S42 (Expense Voucher advance payment + bi-monthly payout split).

Adds three fields to VECRM Expense Voucher:
  - advance_received (Check, default 0)
  - advance_amount   (Currency, default 0)
  - net_payable      (Currency, read-only) = total_amount - advance_amount

The controller only computes net_payable on save, so without a backfill every
PRE-EXISTING expense voucher would land with net_payable = 0/NULL and pay out
as ₹0 in the new payout breakdown. Historical vouchers have no advance, so
their net_payable IS their total_amount. This patch sets that for any row where
net_payable is still NULL or 0 (idempotent / re-runnable).

Also adds a composite UNIQUE index on VECRM Payout Adjustment
(voucher_doctype, voucher_name) — the authoritative DB-level guarantee that an
override is single-row-per-voucher (the controller validate() is the friendly
application-level mirror).

Pre/post assertions per VECRM-L22.
"""

import frappe

TABLE = "tabVECRM Expense Voucher"
NEW_COLS = ["advance_received", "advance_amount", "net_payable"]

ADJ_TABLE = "tabVECRM Payout Adjustment"
ADJ_INDEX = "unique_voucher_doctype_name"
ADJ_INDEX_COLS = ["voucher_doctype", "voucher_name"]


def _add_unique_index(table, index_name, columns):
	"""Idempotently add a composite UNIQUE index (skip if it already exists)."""
	if frappe.db.sql(f"SHOW INDEX FROM `{table}` WHERE Key_name=%s", (index_name,)):
		return False
	cols = ", ".join(f"`{c}`" for c in columns)
	frappe.db.sql(f"ALTER TABLE `{table}` ADD UNIQUE INDEX `{index_name}` ({cols})")
	return True


def execute():
	# Step 1: reload the doctype JSON → Frappe auto-adds the new columns.
	frappe.reload_doc("vecrm", "doctype", "vecrm_expense_voucher")

	# Step 2: verify every new column materialized.
	for col in NEW_COLS:
		if not frappe.db.sql(f"SHOW COLUMNS FROM `{TABLE}` LIKE %s", (col,), as_dict=True):
			frappe.throw(f"v1_11 failed: {TABLE}.{col} not created after doctype sync")

	# Step 3: PRE-assertion — count rows needing the net_payable backfill.
	to_backfill = frappe.db.sql(
		f"SELECT COUNT(*) FROM `{TABLE}` "
		f"WHERE net_payable IS NULL OR net_payable = 0"
	)[0][0]

	# Step 4: BACKFILL — historical vouchers have no advance, so net == total.
	# Idempotent: re-running only touches rows still at NULL/0.
	frappe.db.sql(
		f"""UPDATE `{TABLE}`
			SET net_payable = total_amount
			WHERE net_payable IS NULL OR net_payable = 0"""
	)

	# Step 5: POST-assertion — no submitted/draft voucher with a positive total
	# may be left at net_payable 0 unless it genuinely has a full advance.
	stragglers = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `{TABLE}`
			WHERE (net_payable IS NULL OR net_payable = 0)
			  AND total_amount > 0
			  AND NOT (advance_received = 1 AND advance_amount = total_amount)"""
	)[0][0]
	if stragglers:
		frappe.throw(
			f"v1_11 POST-assert failed: {TABLE} still has {stragglers} rows "
			f"with net_payable 0 and a positive total but no full advance"
		)

	# Step 6: sync the new VECRM Payout Adjustment doctype + add its composite
	# UNIQUE index. post_model_sync already created the table; reload_doc is a
	# safe explicit re-sync, then we add the index idempotently.
	frappe.reload_doc("vecrm", "doctype", "vecrm_payout_adjustment")
	if not frappe.db.sql(f"SHOW TABLES LIKE %s", (ADJ_TABLE,)):
		frappe.throw(f"v1_11 failed: {ADJ_TABLE} not created after doctype sync")
	index_added = _add_unique_index(ADJ_TABLE, ADJ_INDEX, ADJ_INDEX_COLS)

	frappe.db.commit()
	frappe.clear_cache(doctype="VECRM Expense Voucher")
	frappe.clear_cache(doctype="VECRM Payout Adjustment")
	print(
		f"v1_11 complete. 3 advance fields added to {TABLE}; "
		f"net_payable backfilled for {to_backfill} rows; "
		f"{ADJ_TABLE} composite unique index "
		f"{'added' if index_added else 'already present'}."
	)
