import frappe
def run():
    doc = frappe.get_doc({
        "doctype": "VECRM Lead",
        "company_name": "CLI Demo Corp 3",
        "territory": "Ahmedabad",
        "contact_date": frappe.utils.today(),
        "priority": 3,
        "contact_number": "+91-7777777777",
        "contact_email": "demo3@clidemo.com",
        "meeting_brief": "CLI Demo 3",
        "status": "Open",
        "lead_owner": "test.salesrep@vinayenterprises.co.in"
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Lead created: {doc.name}")
