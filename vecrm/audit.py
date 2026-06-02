import frappe

TRACKED_DOCTYPES = [
	"VECRM Lead", "VECRM Inquiry",
	"VECRM Petrol Voucher", "VECRM Travel Voucher", "VECRM Expense Voucher"
]


def log_doc_event(doc, method):
	"""Auto-log lifecycle events for VECRM doctypes."""
	if doc.doctype not in TRACKED_DOCTYPES:
		return

	event_map = {
		"after_insert": "create",
		"on_update": "update",
		"on_submit": "submit",
		"on_cancel": "cancel",
		"on_trash": "delete",
	}
	event_type = event_map.get(method, method)

	# Skip redundant update events (every insert also triggers on_update)
	if event_type == "update" and doc.creation == doc.modified:
		return

	audit_doc = frappe.get_doc({
		"doctype": "VECRM User Audit Log",
		"event_type": event_type,
		"actor": frappe.session.user,
		"target": doc.name,
		"event_timestamp": frappe.utils.now_datetime(),
		"detail": f"{event_type.title()} {doc.doctype}: {doc.name}"
	})
	audit_doc.flags.ignore_links = True
	audit_doc.insert(ignore_permissions=True)


@frappe.whitelist()
def log_auth_event(event_type: str, actor: str) -> dict:
	"""Log login/logout events from the portal."""
	if event_type not in ("login", "logout"):
		frappe.throw("Invalid auth event type")

	audit_doc = frappe.get_doc({
		"doctype": "VECRM User Audit Log",
		"event_type": event_type,
		"actor": actor,
		"target": actor,
		"event_timestamp": frappe.utils.now_datetime(),
		"detail": f"{event_type.title()}: {actor}"
	})
	audit_doc.flags.ignore_links = True
	audit_doc.insert(ignore_permissions=True)

	return {"success": True}
