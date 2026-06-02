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
	
	try:
		users_to_notify = set()
		for t in tokens:
			rows = frappe.get_all("VECRM Device Token", filters={"fcm_token": t}, fields=["user_email"])
			for r in rows:
				if r.user_email:
					users_to_notify.add(r.user_email)
					
		for user in users_to_notify:
			doc_type = data.get("doctype") if data else None
			doc_name = (data.get("voucher") or data.get("lead") or data.get("inquiry")) if data else None
			notif_log = frappe.get_doc({
				"doctype": "Notification Log",
				"subject": title,
				"email_content": body,
				"for_user": user,
				"type": "Alert",
				"document_type": doc_type,
				"document_name": doc_name
			})
			notif_log.flags.ignore_links = True
			notif_log.insert(ignore_permissions=True)
	except Exception as e:
		frappe.log_error(f"Error logging notification: {e}", "Notification Log Error")

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
			f"{doc.company_name}: {old_status or '-'} → {new_status or '-'}",
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


def follow_up_upcoming_reminder():
	"""Fire each lead's owner: 'Follow-up due tomorrow for {company}'."""
	try:
		tomorrow = frappe.utils.add_days(frappe.utils.today(), 1)
		rows = frappe.get_all(
			"VECRM Lead",
			filters={"next_followup_date": tomorrow, "status": "Open"},
			fields=["name", "company_name", "lead_owner"],
			ignore_permissions=True,
		)
		for r in rows:
			tokens = _tokens_for_user(r.lead_owner)
			if not tokens:
				continue
			send_push(
				tokens,
				"Follow-up due tomorrow",
				f"Upcoming follow-up tomorrow for {r.company_name}",
				{"screen": "leads", "lead": r.name},
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.follow_up_upcoming_reminder")


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


def notify_admin_lead_created(doc, method):
	"""Push notification to admin when any lead is created."""
	if getattr(doc.flags, 'skip_notification', False):
		return
	try:
		admin_email = "ajay@vinayenterprises.co.in"
		tokens = _tokens_for_user(admin_email)
		if tokens:
			company = doc.get("company_name", "Unknown")
			creator = doc.lead_owner or doc.owner
			res = send_push(
				tokens=tokens,
				title="New Lead Created",
				body=f"Lead: {company} - created by {creator}",
				data={"screen": "leads", "lead": doc.name}
			)
			frappe.log_error(f"Tokens: {len(tokens)}, Result: {res}", "Push Notification Debug")
		else:
			frappe.log_error(f"No tokens found for {admin_email}", "Push Notification Debug")
	except Exception as e:
		frappe.log_error(f"notify_admin_lead_created failed: {str(e)}", "Push Notification Error")


def notify_voucher_submitted(doc, method):
	"""Ping approvers when a new voucher is submitted."""
	try:
		submitter_email = _employee_email(getattr(doc, "submitter", None))
		if not submitter_email:
			return
		
		submitter_employee = frappe.get_all(
			"VECRM Employee", 
			filters={"vecrm_email": submitter_email}, 
			fields=["role"], 
			limit=1
		)
		submitter_role = submitter_employee[0].role if submitter_employee else None

		target_roles = ["Admin", "HR"]
		if submitter_role == "Field Engineer":
			target_roles.append("Head of Engineers")
		elif submitter_role == "Sales Rep":
			target_roles.append("Sales Head")

		approver_employees = frappe.get_all(
			"VECRM Employee",
			filters={"role": ["in", target_roles]},
			fields=["vecrm_email"],
			ignore_permissions=True
		)

		approver_emails = [e.vecrm_email for e in approver_employees if e.vecrm_email]
		
		for email in approver_emails:
			tokens = _tokens_for_user(email)
			if tokens:
				send_push(
					tokens,
					"New Voucher Submitted",
					f"New {doc.doctype.replace('VECRM ', '')} submitted by {submitter_email}",
					{"screen": "vouchers", "voucher": doc.name, "doctype": doc.doctype}
				)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_voucher_submitted")


def stale_inquiry_reminder():
	"""Find inquiries with status Open that haven't been modified in 3 days."""
	try:
		three_days_ago = frappe.utils.add_days(frappe.utils.today(), -3)
		stale_inquiries = frappe.get_all(
			"VECRM Inquiry",
			filters={
				"status": "Open",
				"modified": ["<", three_days_ago]
			},
			fields=["name", "company_name", "inquiry_owner"]
		)

		for r in stale_inquiries:
			tokens = _tokens_for_user(r.inquiry_owner)
			if tokens:
				send_push(
					tokens,
					"Stale Inquiry",
					f"Your inquiry for {r.company_name} hasn't been updated recently. Give them a call?",
					{"screen": "inquiries", "inquiry": r.name}
				)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.stale_inquiry_reminder")


def manager_daily_digest():
	"""Send a daily digest to the manager summarizing today's activity."""
	try:
		today = frappe.utils.today()
		
		leads_created = frappe.db.count("VECRM Lead", {"creation": ["like", f"{today}%"]})
		
		tv_submitted = frappe.db.count("VECRM Travel Voucher", {"docstatus": 1, "modified": ["like", f"{today}%"]})
		ev_submitted = frappe.db.count("VECRM Expense Voucher", {"docstatus": 1, "modified": ["like", f"{today}%"]})
		pv_submitted = frappe.db.count("VECRM Petrol Voucher", {"docstatus": 1, "modified": ["like", f"{today}%"]})
		vouchers_submitted = tv_submitted + ev_submitted + pv_submitted

		if leads_created == 0 and vouchers_submitted == 0:
			return

		tokens = _tokens_for_user(MANAGER_EMAIL)
		if tokens:
			send_push(
				tokens,
				"Daily Digest",
				f"Your team added {leads_created} leads and submitted {vouchers_submitted} vouchers today.",
				{"screen": "dashboard"}
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.manager_daily_digest")


def voucher_approver_payment_reminder():
	"""Cron job that runs daily at 10 AM to remind Approvers about Vouchers."""
	try:
		from datetime import date
		day = date.today().day
		
		messages = []
		if day in (15, 16, 17):
			messages.append("Please approve pending vouchers for the 1st-15th period.")
		elif day in (1, 2, 3):
			messages.append("Please approve pending vouchers for the preceding month.")
			
		if day == 20:
			messages.append("Voucher payments for the 1st-15th period are due today.")
		elif day == 5:
			messages.append("Voucher payments for the preceding month are due today.")
			
		if not messages:
			return
			
		approver_employees = frappe.get_all(
			"VECRM Employee",
			filters={"role": ["in", ["Admin", "HR", "Sales Head", "Head of Engineers"]]},
			fields=["vecrm_email"],
			ignore_permissions=True
		)
		
		approver_emails = [e.vecrm_email for e in approver_employees if e.vecrm_email]
		
		for email in approver_emails:
			tokens = _tokens_for_user(email)
			if tokens:
				for msg in messages:
					send_push(
						tokens,
						"Voucher Action Required",
						msg,
						{"screen": "vouchers"}
					)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.voucher_approver_payment_reminder")
