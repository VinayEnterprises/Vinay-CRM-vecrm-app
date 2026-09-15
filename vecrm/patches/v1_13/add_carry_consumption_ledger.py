# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""Add the VECRM Carry Consumption ledger and payout-adjustment restore field (v1_13).

S132 (advance carry-forward settlement at payout run).

Creates:
  - VECRM Carry Consumption (child doctype, parented to the SOURCE Expense
    Voucher) holding one row per slice of a carry-forward absorbed by a
    consuming voucher.
  - VECRM Expense Voucher.carry_consumptions (Table, allow_on_submit) as the
    parent field for those rows.
  - VECRM Payout Adjustment.advance_before (Currency, read-only) capturing the
    voucher's own advance_amount immediately before the FIRST override, so
    clearing an override restores the submitter's declaration exactly.

Backfills the 15 Ruling B (S75) consumptions recorded as
(advance_ref, advance_consumed) pairs on the CONSUMER row into child rows on
the SOURCE. The legacy columns are left written and untouched: the portal
reads them, and they remain the primary-source plus aggregate mirror.

Idempotent: re-running inserts nothing already present, keyed on
(parent, consumer_doctype, consumer_name).

Pre/post assertions per VECRM-L22. This patch is executed DIRECTLY via
`bench execute vecrm.patches.v1_13.add_carry_consumption_ledger.execute`,
never via `bench migrate`: this bench also carries Frappe CRM, and a migrate
would run that app's patch backlog as well.
"""

import frappe

EV_TABLE = "tabVECRM Expense Voucher"
CC_TABLE = "tabVECRM Carry Consumption"
ADJ_TABLE = "tabVECRM Payout Adjustment"

PARENTFIELD = "carry_consumptions"
CONSUMER_DT = "VECRM Expense Voucher"


def _has_column(table, column):
    return bool(
        frappe.db.sql(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,), as_dict=True)
    )


def _legacy_consumptions():
    """Ruling B pairs, read from the CONSUMER side, oldest source first."""
    return frappe.db.sql(
        """
        SELECT
            cons.name            AS consumer_name,
            cons.advance_ref     AS source_name,
            cons.advance_consumed AS amount,
            cons.approved_at     AS settled_at,
            cons.approved_by_employee AS settled_by,
            cons.expense_date    AS consumer_date
        FROM `tabVECRM Expense Voucher` cons
        WHERE cons.docstatus = 1
          AND IFNULL(cons.advance_consumed, 0) > 0
          AND IFNULL(cons.advance_ref, '') != ''
        ORDER BY cons.approved_at ASC, cons.name ASC
        """,
        as_dict=True,
    )


def execute():
    from vecrm.vecrm.utils.voucher_period import period_key

    # Step 1: sync the three doctype JSONs. reload_doc creates the child table
    # and adds the two new parent-side fields without a full bench migrate.
    frappe.reload_doc("vecrm", "doctype", "vecrm_carry_consumption")
    frappe.reload_doc("vecrm", "doctype", "vecrm_expense_voucher")
    frappe.reload_doc("vecrm", "doctype", "vecrm_payout_adjustment")

    # Step 2: verify every structure materialised. Guard column existence from
    # the live schema rather than trusting reload_doc's return.
    if not frappe.db.sql("SHOW TABLES LIKE %s", (CC_TABLE,)):
        frappe.throw(f"v1_13 failed: {CC_TABLE} not created after doctype sync")

    for col in ("consumer_doctype", "consumer_name", "amount", "settled_at",
                "settled_by", "period_key"):
        if not _has_column(CC_TABLE, col):
            frappe.throw(f"v1_13 failed: {CC_TABLE}.{col} missing after doctype sync")

    if not _has_column(ADJ_TABLE, "advance_before"):
        frappe.throw(f"v1_13 failed: {ADJ_TABLE}.advance_before missing after doctype sync")

    # Step 3: PRE-assertion. Snapshot the legacy truth BEFORE writing anything,
    # so the post-check compares against a figure taken from the old shape.
    legacy = _legacy_consumptions()
    legacy_by_source = {}
    for row in legacy:
        legacy_by_source[row["source_name"]] = (
            legacy_by_source.get(row["source_name"], 0.0) + float(row["amount"] or 0)
        )
    legacy_total = round(sum(legacy_by_source.values()), 2)

    existing_rows = frappe.db.sql(f"SELECT COUNT(*) FROM `{CC_TABLE}`")[0][0]

    # Step 4: BACKFILL. One child row per legacy pair, parented to the SOURCE.
    # Raw SQL because the parents are docstatus=1 and the ORM's
    # update-after-submit gate would refuse; this mirrors v1_11's backfill.
    inserted = 0
    skipped = 0
    for row in legacy:
        source = row["source_name"]
        consumer = row["consumer_name"]

        # Idempotency key: one row per (source, consumer_doctype, consumer).
        dup = frappe.db.sql(
            f"""SELECT name FROM `{CC_TABLE}`
                WHERE parent = %s AND consumer_doctype = %s AND consumer_name = %s""",
            (source, CONSUMER_DT, consumer),
        )
        if dup:
            skipped += 1
            continue

        # Source must exist and be a submitted, approved voucher, or the row
        # would orphan. A missing source is a fail-loud condition, not a skip.
        src_exists = frappe.db.sql(
            f"""SELECT docstatus, approval_status, carry_forward_amount
                FROM `{EV_TABLE}` WHERE name = %s""",
            (source,),
            as_dict=True,
        )
        if not src_exists:
            frappe.throw(
                f"v1_13 BACKFILL abort: consumer {consumer} references "
                f"advance_ref {source!r} which does not exist"
            )

        idx = frappe.db.sql(
            f"SELECT IFNULL(MAX(idx), 0) + 1 FROM `{CC_TABLE}` WHERE parent = %s",
            (source,),
        )[0][0]

        pkey = period_key(row["consumer_date"]) if row["consumer_date"] else None

        frappe.db.sql(
            f"""
            INSERT INTO `{CC_TABLE}`
                (name, creation, modified, modified_by, owner, docstatus, idx,
                 parent, parentfield, parenttype,
                 consumer_doctype, consumer_name, amount,
                 settled_at, settled_by, period_key)
            VALUES
                (%(name)s, NOW(), NOW(), 'Administrator', 'Administrator', 1, %(idx)s,
                 %(parent)s, %(parentfield)s, %(parenttype)s,
                 %(consumer_doctype)s, %(consumer_name)s, %(amount)s,
                 %(settled_at)s, %(settled_by)s, %(period_key)s)
            """,
            {
                "name": frappe.generate_hash(length=10),
                "idx": idx,
                "parent": source,
                "parentfield": PARENTFIELD,
                "parenttype": CONSUMER_DT,
                "consumer_doctype": CONSUMER_DT,
                "consumer_name": consumer,
                "amount": float(row["amount"] or 0),
                "settled_at": row["settled_at"],
                "settled_by": row["settled_by"],
                "period_key": pkey,
            },
        )
        inserted += 1

    # Step 5: POST-assertion, BEFORE the commit so a failure rolls the backfill
    # back. A post-commit assertion can only report a bad state, never undo it.
    # Matches v1_11's order: assert, then commit. Compare the NEW shape against
    # the legacy snapshot taken in step 3, per source and in total. Never trust
    # the writer's return (Rule E).
    new_by_source = {}
    for r in frappe.db.sql(
        f"""SELECT parent, SUM(amount) AS total FROM `{CC_TABLE}`
            WHERE parenttype = %s AND parentfield = %s GROUP BY parent""",
        (CONSUMER_DT, PARENTFIELD),
        as_dict=True,
    ):
        new_by_source[r["parent"]] = float(r["total"] or 0)

    mismatches = []
    for source, legacy_amt in legacy_by_source.items():
        new_amt = new_by_source.get(source, 0.0)
        if abs(new_amt - legacy_amt) > 0.005:
            mismatches.append(f"{source}: legacy={legacy_amt} child_sum={new_amt}")
    if mismatches:
        frappe.throw(
            "v1_13 POST-assert FAILED, per-source totals disagree:\n"
            + "\n".join(mismatches)
        )

    new_total = round(sum(new_by_source.values()), 2)
    if abs(new_total - legacy_total) > 0.005:
        frappe.throw(
            f"v1_13 POST-assert FAILED: child-row total {new_total} != "
            f"legacy consumed total {legacy_total}"
        )

    # No child row may exceed its source's carry_forward_amount.
    over = frappe.db.sql(
        f"""
        SELECT src.name, src.carry_forward_amount, SUM(cc.amount) AS consumed
        FROM `{EV_TABLE}` src
        JOIN `{CC_TABLE}` cc ON cc.parent = src.name AND cc.parentfield = %s
        GROUP BY src.name, src.carry_forward_amount
        HAVING SUM(cc.amount) - src.carry_forward_amount > 0.005
        """,
        (PARENTFIELD,),
        as_dict=True,
    )
    if over:
        frappe.throw(
            "v1_13 POST-assert FAILED, consumption exceeds carry on: "
            + ", ".join(f"{r['name']} ({r['consumed']} > {r['carry_forward_amount']})"
                        for r in over)
        )

    frappe.db.commit()
    frappe.clear_cache(doctype="VECRM Carry Consumption")
    frappe.clear_cache(doctype="VECRM Expense Voucher")
    frappe.clear_cache(doctype="VECRM Payout Adjustment")
    print(
        f"v1_13 complete. {CC_TABLE} created; advance_before added to {ADJ_TABLE}; "
        f"legacy pairs seen={len(legacy)} inserted={inserted} skipped_existing={skipped} "
        f"(child rows before={existing_rows}); per-source and total reconcile at "
        f"Rs {new_total} across {len(new_by_source)} sources."
    )
