import frappe
import os

_firebase_app = None


def _get_firebase_app():
	global _firebase_app
	if _firebase_app is None:
		import firebase_admin
		from firebase_admin import credentials
		key_path = "/home/frappe/frappe-bench/sites/firebase-service-account.json"
		cred = credentials.Certificate(key_path)
		_firebase_app = firebase_admin.initialize_app(cred)
	return _firebase_app


def send_push(tokens: list, title: str, body: str, data: dict = None):
	"""Send FCM push to a list of device tokens."""
	if not tokens:
		return {"sent": 0}
	from firebase_admin import messaging
	_get_firebase_app()
	message = messaging.MulticastMessage(
		notification=messaging.Notification(title=title, body=body),
		data=data or {},
		tokens=tokens,
	)
	response = messaging.send_each_for_multicast(message)
	return {"sent": response.success_count, "failed": response.failure_count}


def _all_active_tokens():
	rows = frappe.get_all("VECRM Device Token", fields=["fcm_token"], ignore_permissions=True)
	return [r.fcm_token for r in rows if r.fcm_token]


def daily_lead_reminder():
	"""Daily nudge to log leads/meeting notes."""
	tokens = _all_active_tokens()
	send_push(
		tokens,
		"Log today's meetings",
		"Don't forget to add any leads or meeting notes in VECRM.",
		{"screen": "leads"},
	)


def voucher_period_reminder():
	"""Voucher fill reminder — only fires on specific dates."""
	from datetime import date
	day = date.today().day
	# H1 period (1-15) reminder window: 13,14,15,16,17
	# H2 period (16-end) reminder window: 28,29,30,1,2
	if day in (13, 14, 15, 16, 17):
		period = "first-half (1st-15th)"
	elif day in (28, 29, 30, 1, 2):
		period = "second-half (16th-end)"
	else:
		return  # not a reminder day
	tokens = _all_active_tokens()
	send_push(
		tokens,
		"Fill your vouchers",
		f"Reminder: please submit your {period} petrol/travel/expense vouchers in VECRM.",
		{"screen": "vouchers"},
	)


# ── Targeted notifications ──────────────────────────────────────────────────
#
# Field-name reminders (verified against doctype JSONs):
#   VECRM Lead     : lead_owner (email Data), status, company_name,
#                    next_followup_date
#   VECRM Inquiry  : source_lead (Link → VECRM Lead), company_name,
#                    inquiry_owner (email Data)
#   VECRM Travel/Expense Voucher: submitter (Link → VECRM Employee — the
#                    Employee.name is the phone, so we look up vecrm_email
#                    before token lookup), approval_status (Pending/Approved/
#                    Rejected), payment_status (Unpaid/Paid)
#
# Every doc-event handler is wrapped in try/except + frappe.log_error: a
# notification failure must never propagate out and block the document save.

MANAGER_EMAIL = "ajay@vinayenterprises.co.in"


def _tokens_for_user(email):
	if not email:
		return []
	rows = frappe.get_all(
		"VECRM Device Token",
		filters={"user_email": email},
		fields=["fcm_token"],
		ignore_permissions=True,
	)
	return [r.fcm_token for r in rows if r.fcm_token]


def _employee_email(employee_name):
	"""VECRM Employee.name is the phone; vecrm_email is the address we
	register device tokens against. Returns None for unknown / missing."""
	if not employee_name:
		return None
	return frappe.db.get_value("VECRM Employee", employee_name, "vecrm_email")


def notify_lead_assigned(doc, method):
	"""On Lead update: push to new owner when lead_owner is (re)assigned."""
	try:
		before = doc.get_doc_before_save()
		if before is None:
			return  # insert path; ignored here
		old_owner = getattr(before, "lead_owner", None)
		new_owner = doc.lead_owner
		if not new_owner or new_owner == old_owner:
			return
		tokens = _tokens_for_user(new_owner)
		if not tokens:
			return
		send_push(
			tokens,
			"New lead assigned",
			f"New lead: {doc.company_name} assigned to you",
			{"screen": "leads", "lead": doc.name},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_lead_assigned")


def notify_lead_status(doc, method):
	"""On Lead update: push to lead_owner when status changes."""
	try:
		before = doc.get_doc_before_save()
		if before is None:
			return
		old_status = getattr(before, "status", None)
		new_status = doc.status
		if new_status == old_status:
			return
		tokens = _tokens_for_user(doc.lead_owner)
		if not tokens:
			return
		send_push(
			tokens,
			f"Lead status: {doc.company_name}",
			f"{doc.company_name}: {old_status or '—'} → {new_status or '—'}",
			{"screen": "leads", "lead": doc.name},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_lead_status")


def notify_voucher_status(doc, method):
	"""On voucher update: push to submitter when approval_status moves to
	Approved/Rejected or payment_status moves to Paid."""
	try:
		before = doc.get_doc_before_save()
		if before is None:
			return
		transitions = []
		old_approval = getattr(before, "approval_status", None)
		new_approval = getattr(doc, "approval_status", None)
		if new_approval != old_approval and new_approval in ("Approved", "Rejected"):
			transitions.append(new_approval)

		old_payment = getattr(before, "payment_status", None)
		new_payment = getattr(doc, "payment_status", None)
		if new_payment != old_payment and new_payment == "Paid":
			transitions.append("Paid")

		if not transitions:
			return

		submitter_email = _employee_email(getattr(doc, "submitter", None))
		tokens = _tokens_for_user(submitter_email)
		if not tokens:
			return
		for status_word in transitions:
			send_push(
				tokens,
				f"Voucher {status_word}",
				f"Your voucher {doc.name} was {status_word}",
				{"screen": "vouchers", "voucher": doc.name, "doctype": doc.doctype},
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_voucher_status")


def notify_lead_converted(doc, method):
	"""On Inquiry after_insert: if it was created via lead conversion
	(source_lead is set), broadcast to all active tokens."""
	try:
		if not getattr(doc, "source_lead", None):
			return
		tokens = _all_active_tokens()
		if not tokens:
			return
		send_push(
			tokens,
			"Lead converted",
			f"Lead converted: {doc.company_name} → new inquiry {doc.name}",
			{"screen": "inquiries", "inquiry": doc.name},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_lead_converted")


# ── Scheduler-driven reminders ──────────────────────────────────────────────


def follow_up_due_reminder():
	"""Fire each lead's owner: 'Follow-up due today for {company}'."""
	try:
		today = frappe.utils.today()
		rows = frappe.get_all(
			"VECRM Lead",
			filters={"next_followup_date": today, "status": "Open"},
			fields=["name", "company_name", "lead_owner"],
			ignore_permissions=True,
		)
		for r in rows:
			tokens = _tokens_for_user(r.lead_owner)
			if not tokens:
				continue
			send_push(
				tokens,
				"Follow-up due today",
				f"Follow-up due today for {r.company_name}",
				{"screen": "leads", "lead": r.name},
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.follow_up_due_reminder")


def manager_overdue_alert():
	"""If any open leads are past their follow-up date, alert the manager."""
	try:
		today = frappe.utils.today()
		count = frappe.db.count(
			"VECRM Lead",
			filters={"next_followup_date": ["<", today], "status": "Open"},
		)
		if not count:
			return
		tokens = _tokens_for_user(MANAGER_EMAIL)
		if not tokens:
			return
		send_push(
			tokens,
			"Overdue follow-ups",
			f"{count} leads overdue for follow-up",
			{"screen": "leads", "filter": "overdue"},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.manager_overdue_alert")
