# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class VECRMExpenseLine(Document):
    """Child doctype rows for VECRM Expense Voucher.

    No controller-level logic; validation happens at the parent
    voucher's validate() (amount > 0, total computation, reqd fields).
    Frappe's reqd: 1 on category/amount/description enforces field-level
    reqd at insert time.
    """
    pass
