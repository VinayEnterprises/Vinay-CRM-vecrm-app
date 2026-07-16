# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt
"""S85 Bake N -- verify VECRM Prospect + VECRM Smartflo Call materialized.

Follows the v1_7 pattern exactly: the doctype JSONs under
vecrm/vecrm/doctype/{vecrm_prospect,vecrm_smartflo_call}/ are the source of
truth; Frappe's doctype-sync (pre-patch phase of migrate) creates the tables.
This patch is a no-op-then-assert verifier. No DDL here.
"""
import frappe

TABLES = ("VECRM Prospect", "VECRM Smartflo Call")
DOCS = (("vecrm", "doctype", "vecrm_prospect"),
        ("vecrm", "doctype", "vecrm_smartflo_call"))


def execute():
    for args in DOCS:
        frappe.reload_doc(*args)
    for table in TABLES:
        if not frappe.db.table_exists(table):
            frappe.throw(
                "v1_12 patch: tab{0} did not materialize after doctype "
                "sync. Investigate the doctype JSON validity and the "
                "migrate output.".format(table)
            )
        frappe.clear_cache(doctype=table)
