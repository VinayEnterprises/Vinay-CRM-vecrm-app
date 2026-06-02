import frappe

TRACKED_DOCTYPES = [
	"VECRM Lead", "VECRM Inquiry",
	"VECRM Petrol Voucher", "VECRM Travel Voucher", "VECRM Expense Voucher"
]

def enqueue_log_doc_event(doc, method=None, **kwargs):
	"""Wrapper to enqueue the audit log off the critical path."""
	if doc.doctype not in TRACKED_DOCTYPES:
		return
	try:
		frappe.enqueue(
			"vecrm.audit.log_doc_event_worker",
			doc_doctype=doc.doctype,
			doc_name=doc.name,
			doc_creation=doc.creation,
			doc_modified=doc.modified,
			# NOT `method=` — frappe.enqueue's own first positional param is
			# named `method` (the job path), so a `method=` kwarg collides:
			# "enqueue() got multiple values for argument 'method'". Forward
			# the doc-event under a distinct name the worker accepts.
			event_method=method,
			user=getattr(frappe.session, "user", "Administrator"),
			queue="short",
			enqueue_after_commit=True
		)
	except Exception as e:
		if hasattr(frappe.local, "message_log"):
			frappe.local.message_log = []
		frappe.log_error(f"Failed to enqueue audit event: {str(e)}", "Audit Enqueue Error")

def log_doc_event_worker(doc_doctype, doc_name, doc_creation, doc_modified, event_method, user):
	"""Auto-log lifecycle events for VECRM doctypes."""
	event_map = {
		"after_insert": "create",
		"on_update": "update",
		"on_submit": "submit",
		"on_cancel": "cancel",
		"on_trash": "delete",
	}
	event_type = event_map.get(event_method, event_method)

	# Skip redundant update events (every insert also triggers on_update)
	if event_type == "update" and doc_creation == doc_modified:
		return

	audit_doc = frappe.get_doc({
		"doctype": "VECRM User Audit Log",
		"event_type": event_type,
		"actor": user,
		"target": doc_name,
		"event_timestamp": frappe.utils.now_datetime(),
		"detail": f"{event_type.title()} {doc_doctype}: {doc_name}"
	})
	try:
		audit_doc.set_new_name()
		audit_doc.db_insert()
	except Exception as e:
		if hasattr(frappe.local, "message_log"):
			frappe.local.message_log = []
		frappe.log_error(f"Failed to insert VECRM User Audit Log: {str(e)}", "Audit Log Error")


@frappe.whitelist()
def log_auth_event(event_type: str, actor: str) -> dict:
	"""Log login/logout events from the portal."""
	if event_type not in ("login", "logout"):
		frappe.throw("Invalid auth event type")

	# SECURITY: bind the actor to the authenticated session identity when
	# present, so a caller can't forge auth-log rows for an arbitrary actor.
	session_email = (frappe.session.data or {}).get("vecrm_email")
	if session_email:
		actor = session_email

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
