import frappe

# Exact mapping from recon audit — VECRM employee name -> VEHRMS data
HRMS_DATA = {
    "Ajay Salvi": {"company": "Vinay Enterprises", "designation": "Founder", "hrms_id": "HR-EMP-00002"},
    "Anil Patel": {"company": "Vinay Enterprises", "designation": "Head of Accounts", "hrms_id": "HR-EMP-00004"},
    "Ashvin Tadvi": {"company": "Vinay Enterprises", "designation": "Head of Store", "hrms_id": "HR-EMP-00005"},
    "Bhavesh Thakor": {"company": "VECS", "designation": "Driver", "hrms_id": "HR-EMP-00008"},
    "Gunjan Pandya": {"company": "Vinay Enterprises", "designation": "Senior Engineer", "hrms_id": "HR-EMP-00011"},
    "Harvik Prajapati": {"company": "VECS", "designation": "Active Engineer", "hrms_id": "HR-EMP-00037"},
    "Jahid Makwana": {"company": "Vinay Enterprises", "designation": "Engineer", "hrms_id": "HR-EMP-00026"},
    "Janak Vasani": {"company": "Vinay Enterprises", "designation": "Business Acceleration Executive", "hrms_id": "HR-EMP-00032"},
    "Jaydeep Desai": {"company": "VECS", "designation": "Active Engineer", "hrms_id": "HR-EMP-00036"},
    "Kamlesh Khuddhara": {"company": "Vinay Enterprises", "designation": "Head of Engineers", "hrms_id": "HR-EMP-00010"},
    "Kavindra Singh": {"company": "Vinay Enterprises", "designation": "Senior Engineer", "hrms_id": "HR-EMP-00016"},
    "Krunal Solanki": {"company": "Vinay Enterprises", "designation": "Engineer", "hrms_id": "HR-EMP-00025"},
    "Mahek Maniar": {"company": "VECS", "designation": "Inside Sales Executive", "hrms_id": "HR-EMP-00033"},
    "Mayur Kaduskar": {"company": "Vinay Enterprises", "designation": "Business Acceleration Executive", "hrms_id": "HR-EMP-00030"},
    "Mohit Sahija": {"company": "Vinay Enterprises", "designation": "Senior Business Acceleration Executive", "hrms_id": "HR-EMP-00015"},
    "Nirali Kasundra": {"company": "Vinay Enterprises", "designation": "HR Executive", "hrms_id": "HR-EMP-00024"},
    "Parth Ravaliya": {"company": "VECS", "designation": "Business Acceleration Executive", "hrms_id": "HR-EMP-00038"},
    "Sagar Thakre": {"company": "Vinay Enterprises", "designation": "Business Acceleration Executive", "hrms_id": "HR-EMP-00040"},
    "Shyam Ratanpara": {"company": "VECS", "designation": "Active Engineer", "hrms_id": "HR-EMP-00035"},
    "Somnath Gunjal": {"company": "Vinay Enterprises", "designation": "Business Acceleration Executive", "hrms_id": "HR-EMP-00029"},
    "Sunil Rami": {"company": "Vinay Enterprises", "designation": "Engineer", "hrms_id": "HR-EMP-00014"},
    "Trishul Patel": {"company": "Vinay Enterprises", "designation": "Senior Engineer", "hrms_id": "HR-EMP-00009"},
    "Tushar Rami": {"company": "Vinay Enterprises", "designation": "Senior Engineer", "hrms_id": "HR-EMP-00012"},
    "Veenas Malik": {"company": "Vinay Enterprises", "designation": "Engineer", "hrms_id": "HR-EMP-00028"},
    "Vishal Maru": {"company": "VECS", "designation": "Store Assistant", "hrms_id": "HR-EMP-00006"},
    "Vivek Desai": {"company": "VECS", "designation": "Active Engineer", "hrms_id": "HR-EMP-00017"},
    "Vivek Goswami": {"company": "Vinay Enterprises", "designation": "Engineer", "hrms_id": "HR-EMP-00013"},
}

# Test accounts — set company to VE, no HRMS link
TEST_ACCOUNTS = ["Smoke Test User", "Test HR Approver", "Test Sales Rep"]


def execute():
    employees = frappe.get_all("VECRM Employee", fields=["name", "employee_name"])
    updated = 0
    skipped = 0

    for emp in employees:
        data = HRMS_DATA.get(emp.employee_name)
        if data:
            frappe.db.set_value("VECRM Employee", emp.name, {
                "company": data["company"],
                "designation": data["designation"],
                "hrms_employee_id": data["hrms_id"]
            }, update_modified=False)
            updated += 1
        elif emp.employee_name in TEST_ACCOUNTS:
            frappe.db.set_value("VECRM Employee", emp.name, {
                "company": "Vinay Enterprises"
            }, update_modified=False)
            skipped += 1
        else:
            print(f"WARNING: No HRMS match for {emp.employee_name}")
            skipped += 1

    frappe.db.commit()
    print(f"Migration complete: {updated} updated, {skipped} skipped")
