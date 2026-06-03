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
	"""Send an FCM push to a list of device tokens.

	Push ONLY. The in-app bell entry is created separately by
	`_log_notification` / `_notify` so that web users without a registered
	device token still get a notification they can read. (Previously this
	function also wrote the bell row, gated on `frappe.db.exists("User", ...)`
	— which never matched, because portal users are not Frappe User records.)
	"""
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


def _log_notification(email: str, title: str, body: str, data: dict = None):
	"""Persist a single in-app notification row (VECRM Notification).

	Keyed by plain `email` (the employee's vecrm_email) because all portal
	sessions share one Frappe user and individual employees are not User
	records — so core Notification Log (for_user → User) is unusable here.
	Best-effort: a logging failure must never propagate into the caller.
	"""
	if not email:
		return
	try:
		doc_type = data.get("doctype") if data else None
		doc_name = (
			(data.get("voucher") or data.get("lead") or data.get("inquiry"))
			if data
			else None
		)
		frappe.get_doc({
			"doctype": "VECRM Notification",
			"for_email": email,
			"subject": title,
			"body": body,
			"is_read": 0,
			"document_type": doc_type,
			"document_name": doc_name,
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications._log_notification")


def _notify(emails, title: str, body: str, data: dict = None):
	"""Single entry point for a TARGETED notification: write a bell row for
	each recipient email AND push to whatever devices they have registered.

	Logging is unconditional (works for web-only users); the push is
	best-effort. Deduplicates emails so a recipient never gets two bell rows
	for one event."""
	seen = set()
	all_tokens = []
	for email in emails or []:
		if not email or email in seen:
			continue
		seen.add(email)
		_log_notification(email, title, body, data)
		all_tokens.extend(_tokens_for_user(email))
	if all_tokens:
		send_push(all_tokens, title, body, data)


def cleanup_old_notifications():
	"""Prune the VECRM Notification table (scheduler, daily).

	Reminders write one bell row per user per fire, so the table grows
	steadily. Delete read rows older than 30 days and ANY row older than 90
	days. Best-effort; never raises."""
	try:
		read_cutoff = frappe.utils.add_days(frappe.utils.today(), -30)
		hard_cutoff = frappe.utils.add_days(frappe.utils.today(), -90)
		frappe.db.delete(
			"VECRM Notification",
			{"is_read": 1, "creation": ["<", read_cutoff]},
		)
		frappe.db.delete(
			"VECRM Notification",
			{"creation": ["<", hard_cutoff]},
		)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.cleanup_old_notifications")


def _all_token_emails():
	"""Distinct user_emails across all registered devices — the audience for
	broadcast reminders (was: every active token)."""
	rows = frappe.get_all(
		"VECRM Device Token", fields=["user_email"], ignore_permissions=True
	)
	return list({r.user_email for r in rows if r.user_email})


def notify_voucher_outcome(doc, status_word: str):
	"""Notify a voucher's submitter that it was Approved / Rejected / Paid.

	Called DIRECTLY from approve/reject/mark-paid, which mutate via db_set()
	and therefore never fire the on_update_after_submit hook — so
	notify_voucher_status cannot fire for these transitions and there is no
	duplicate-notification risk. Best-effort; never raises into the caller."""
	try:
		submitter_email = _employee_email(getattr(doc, "submitter", None))
		if not submitter_email:
			return
		_notify(
			[submitter_email],
			f"Voucher {status_word}",
			f"Your voucher {doc.name} was {status_word.lower()}",
			{"screen": "vouchers", "voucher": doc.name, "doctype": doc.doctype},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_voucher_outcome")


def _all_active_tokens():
	rows = frappe.get_all("VECRM Device Token", fields=["fcm_token"], ignore_permissions=True)
	return [r.fcm_token for r in rows if r.fcm_token]


def daily_lead_reminder():
	"""Daily nudge to log leads/meeting notes."""
	_notify(
		_all_token_emails(),
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
	_notify(
		_all_token_emails(),
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
		_notify(
			[new_owner],
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
		# 1. Notify Lead Owner (bell + push)
		_notify(
			[doc.lead_owner],
			f"Lead status: {doc.company_name}",
			f"{doc.company_name}: {old_status or '-'} → {new_status or '-'}",
			{"screen": "leads", "lead": doc.name},
		)

		# 2. If status is Won or Lost, notify Sales Head and Admin via Push + Email
		if new_status in ("Won", "Lost"):
			sales_heads = frappe.get_all("VECRM Employee", filters={"role": "Sales Head"}, fields=["vecrm_email"])
			admins = frappe.get_all("VECRM Employee", filters={"role": "Admin"}, fields=["vecrm_email"])
			
			recipients = [e.vecrm_email for e in sales_heads + admins if e.vecrm_email]
			
			subject = f"Lead {new_status}: {doc.company_name}"
			message = f"""
				<p>Hello,</p>
				<p>The lead <strong>{doc.company_name}</strong> was marked as <strong>{new_status}</strong> by {doc.lead_owner}.</p>
				<p>Previous Status: {old_status or '-'}</p>
				<p>Regards,<br>VECRM System</p>
			"""
			
			# Bell + push to Sales Head / Admin recipients
			_notify(
				recipients,
				subject,
				f"Lead marked as {new_status} by {doc.lead_owner}",
				{"screen": "leads", "lead": doc.name},
			)
			# Plus an email to each
			for email in recipients:
				try:
					frappe.sendmail(
						recipients=email,
						subject=subject,
						message=message,
						delayed=False
					)
				except Exception:
					pass
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
		if not submitter_email:
			return
		for status_word in transitions:
			_notify(
				[submitter_email],
				f"Voucher {status_word}",
				f"Your voucher {doc.name} was {status_word.lower()}",
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
		_notify(
			_all_token_emails(),
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
			_notify(
				[r.lead_owner],
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
			_notify(
				[r.lead_owner],
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
		_notify(
			[MANAGER_EMAIL],
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
		company = doc.get("company_name", "Unknown")
		creator = doc.lead_owner or doc.owner
		_notify(
			[admin_email],
			"New Lead Created",
			f"Lead: {company} - created by {creator}",
			{"screen": "leads", "lead": doc.name},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_admin_lead_created")


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

		_notify(
			approver_emails,
			"New Voucher Submitted",
			f"New {doc.doctype.replace('VECRM ', '')} submitted by {submitter_email}",
			{"screen": "vouchers", "voucher": doc.name, "doctype": doc.doctype},
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
			_notify(
				[r.inquiry_owner],
				"Stale Inquiry",
				f"Your inquiry for {r.company_name} hasn't been updated recently. Give them a call?",
				{"screen": "inquiries", "inquiry": r.name},
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

		_notify(
			[MANAGER_EMAIL],
			"Daily Digest",
			f"Your team added {leads_created} leads and submitted {vouchers_submitted} vouchers today.",
			{"screen": "dashboard"},
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

		for msg in messages:
			_notify(
				approver_emails,
				"Voucher Action Required",
				msg,
				{"screen": "vouchers"},
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.voucher_approver_payment_reminder")
