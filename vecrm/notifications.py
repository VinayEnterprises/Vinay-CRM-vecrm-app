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

	# Persist a readable in-app bell row per recipient. Previously this wrote
	# core "Notification Log" gated on frappe.db.exists("User", ...), but portal
	# users share ONE Frappe user and aren't User records, so that guard never
	# matched and the bell stayed empty forever. We now write VECRM Notification
	# keyed by the device token's user_email, which the portal reads via the
	# whitelisted get_my_notifications.
	try:
		users_to_notify = set()
		for t in tokens:
			rows = frappe.get_all("VECRM Device Token", filters={"fcm_token": t}, fields=["user_email"])
			for r in rows:
				if r.user_email:
					users_to_notify.add(r.user_email)
		for user in users_to_notify:
			_log_notification(user, title, body, data)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.send_push.log")

	return {"sent": response.success_count, "failed": response.failure_count}


def _log_notification(email, title, body, data=None):
	"""Persist one VECRM Notification row — the readable in-app bell store.

	Keyed by plain email: portal sessions share one Frappe user and employees
	are not User records, so core Notification Log (for_user -> User) is
	unusable. Best-effort; never raises into the caller."""
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


def notify_voucher_outcome(doc, status_word):
	"""Notify a voucher's submitter that it was Approved / Rejected / Paid.

	Called DIRECTLY from approve/reject/mark-paid, which mutate via db_set() and
	so never fire on_update_after_submit -> notify_voucher_status can't fire for
	them, so there is no duplicate. If the submitter has device tokens, send_push
	handles both the push and the bell row; otherwise we log the bell row
	directly (web-only users). Best-effort; never raises into the caller."""
	try:
		submitter_email = _employee_email(getattr(doc, "submitter", None))
		if not submitter_email:
			return
		title = f"Voucher {status_word}"
		body = f"Your voucher {doc.name} was {status_word.lower()}"
		payload = {"screen": "vouchers", "voucher": doc.name, "doctype": doc.doctype}
		tokens = _tokens_for_user(submitter_email)
		if tokens:
			send_push(tokens, title, body, payload)
		else:
			_log_notification(submitter_email, title, body, payload)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.notify_voucher_outcome")


def cleanup_old_notifications():
	"""Prune VECRM Notification (scheduler, daily). send_push writes one row per
	recipient per fire, so the table grows steadily; delete read rows older than
	30 days and any row older than 90 days. Best-effort; never raises."""
	try:
		read_cutoff = frappe.utils.add_days(frappe.utils.today(), -30)
		hard_cutoff = frappe.utils.add_days(frappe.utils.today(), -90)
		frappe.db.delete("VECRM Notification", {"is_read": 1, "creation": ["<", read_cutoff]})
		frappe.db.delete("VECRM Notification", {"creation": ["<", hard_cutoff]})
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications.cleanup_old_notifications")


def _all_active_tokens():
	rows = frappe.get_all("VECRM Device Token", fields=["fcm_token"], ignore_permissions=True)
	return [r.fcm_token for r in rows if r.fcm_token]


# Lead/inquiry broadcasts go ONLY to sales-side roles. Field Engineer and
# Head of Engineers are voucher-only and must NOT receive lead/inquiry nudges.
LEAD_AUDIENCE_ROLES = ("Sales Rep", "Sales Head", "Admin")


def _tokens_for_lead_audience():
	"""Device tokens for active users in lead-relevant roles, excluding the
	voucher-only engineering roles. Used for lead/inquiry broadcasts so
	field engineers don't get lead notifications."""
	emps = frappe.get_all(
		"VECRM Employee",
		filters={"role": ["in", LEAD_AUDIENCE_ROLES], "vecrm_account_status": "Active"},
		fields=["vecrm_email"],
	)
	emails = [e.vecrm_email for e in emps if e.vecrm_email]
	if not emails:
		return []
	rows = frappe.get_all(
		"VECRM Device Token",
		filters={"user_email": ["in", emails]},
		fields=["fcm_token"],
		ignore_permissions=True,
	)
	return [r.fcm_token for r in rows if r.fcm_token]


def daily_lead_reminder():
	"""Daily nudge to log leads/meeting notes (sales-side roles only)."""
	tokens = _tokens_for_lead_audience()
	send_push(
		tokens,
		"Log today's meetings",
		"Don't forget to add any leads or meeting notes in Anusuya Workspace.",
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
		f"Reminder: please submit your {period} petrol/travel/expense vouchers in Anusuya Workspace.",
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


def _employee_name(email):
	"""Resolve a login email to the employee's display name for human-
	readable notifications. Falls back to the email itself when no matching
	VECRM Employee exists (e.g. the portal service account)."""
	if not email:
		return "Unknown"
	name = frappe.db.get_value("VECRM Employee", {"vecrm_email": email}, "employee_name")
	return name or email


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
		# 1. Notify Lead Owner via Push
		tokens = _tokens_for_user(doc.lead_owner)
		if tokens:
			send_push(
				tokens,
				f"Lead status: {doc.company_name}",
				f"{doc.company_name}: {old_status or '-'} → {new_status or '-'}",
				{"screen": "leads", "lead": doc.name},
			)
			
		# 2. If status is Closed-Won or Closed-Lost, notify Sales Head and Admin
		# via Push + Email. (Was checking "Won"/"Lost" which never matched the
		# actual VECRM Lead status values, so this email never fired.)
		if new_status in ("Closed-Won", "Closed-Lost"):
			sales_heads = frappe.get_all("VECRM Employee", filters={"role": "Sales Head"}, fields=["vecrm_email"])
			admins = frappe.get_all("VECRM Employee", filters={"role": "Admin"}, fields=["vecrm_email"])

			recipients = [e.vecrm_email for e in sales_heads + admins if e.vecrm_email]

			subject = f"Lead {new_status}: {doc.company_name}"
			# Branded Vinay Enterprises layout (render_lead_status_email ->
			# render_email_layout) so won/lost alerts carry company branding.
			from vecrm.vecrm.email_templates import render_lead_status_email
			message = render_lead_status_email(
				doc, old_status or "-", new_status, _employee_name(doc.lead_owner)
			)
			
			for email in recipients:
				head_tokens = _tokens_for_user(email)
				if head_tokens:
					send_push(
						head_tokens,
						subject,
						f"Lead marked as {new_status} by {_employee_name(doc.lead_owner)}",
						{"screen": "leads", "lead": doc.name},
					)
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
		# Lead-conversion is a lead/inquiry event — sales-side roles only,
		# not field engineers.
		tokens = _tokens_for_lead_audience()
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
			creator = _employee_name(doc.lead_owner or doc.owner)
			send_push(
				tokens=tokens,
				title="New Lead Created",
				body=f"Lead: {company} - created by {creator}",
				data={"screen": "leads", "lead": doc.name}
			)
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

		# Recipients = the roles eligible to approve this submitter's voucher
		# (their functional head + HR + Admin), from the single source of
		# truth shared with the voucher controllers. Covers all roles incl.
		# Network Security Engineer -> Head of Engineers, Store Executive ->
		# Head of Stores. Falls back to Admin/HR for any unmapped role.
		from vecrm.vecrm.utils.roles import VOUCHER_APPROVER_SETS

		target_roles = VOUCHER_APPROVER_SETS.get(submitter_role, ["Admin", "HR"])

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
					f"New {doc.doctype.replace('VECRM ', '')} submitted by {_employee_name(submitter_email)}",
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
			filters={"role": ["in", ["Admin", "HR", "Sales Head", "Head of Engineers", "Head of Stores"]]},
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


def _notify_employee(submitter_phone, title, body):
	"""Best-effort FCM push to a submitter (by VECRM Employee phone-id)."""
	try:
		email = _employee_email(submitter_phone)
		if not email:
			return
		tokens = _tokens_for_user(email)
		if tokens:
			send_push(tokens, title, body, {"screen": "vouchers"})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "notifications._notify_employee")


def auto_submit_closed_period_vouchers():
	"""Scheduled 18th & 3rd at 00:05 IST. Auto-submit the consolidated TRAVEL
	draft for the period whose grace window just closed; stamp Auto-Submitted
	and notify the rep. Empty drafts are skipped with a 'no voucher filed'
	notice (an empty voucher is never pushed through)."""
	from datetime import date, timedelta
	from vecrm.vecrm.utils.voucher_period import period_key

	today = frappe.utils.getdate(frappe.utils.today())
	if today.day == 18:
		anchor = date(today.year, today.month, 1)            # H1 this month
	elif today.day == 3:
		prev_last = today.replace(day=1) - timedelta(days=1)
		anchor = date(prev_last.year, prev_last.month, 16)   # H2 previous month
	else:
		return
	target = period_key(anchor)

	for row in frappe.get_all(
		"VECRM Travel Voucher",
		filters={"docstatus": 0},
		fields=["name", "submitter", "business_date"],
	):
		if not row.business_date or period_key(row.business_date) != target:
			continue
		try:
			doc = frappe.get_doc("VECRM Travel Voucher", row.name)
			if not doc.visit_lines:
				_notify_employee(
					doc.submitter,
					"No voucher filed",
					f"No travel voucher was filed for {target}. Nothing was submitted.",
				)
				continue
			doc.submitted_at = frappe.utils.now_datetime()
			doc.submission_timeliness = "Auto-Submitted"
			doc.submit()
			frappe.db.commit()
			_notify_employee(
				doc.submitter,
				"Voucher auto-submitted",
				f"Your {target} travel voucher {doc.name} was auto-submitted for approval.",
			)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), "auto_submit_closed_period_vouchers")


def relock_expired_reopened_vouchers():
	"""Scheduled daily. A voucher reopened by a manager but not resubmitted
	within its 24h window is returned to the approval queue (Pending) so it is
	never stranded in the editable 'Rejected' state."""
	now = frappe.utils.now_datetime()
	for row in frappe.get_all(
		"VECRM Travel Voucher",
		filters={"reopened": 1, "docstatus": 1, "approval_status": "Rejected"},
		fields=["name", "submitter", "reopened_until"],
	):
		if not row.reopened_until or frappe.utils.get_datetime(row.reopened_until) >= now:
			continue
		try:
			doc = frappe.get_doc("VECRM Travel Voucher", row.name)
			doc.db_set("approval_status", "Pending", update_modified=False)
			doc.db_set("rejected_by_employee", None, update_modified=False)
			doc.db_set("rejected_by_role", None, update_modified=False)
			doc.db_set("rejected_at", None, update_modified=False)
			doc.db_set("rejection_reason", None, update_modified=False)
			# S41: clear ALL reopen stamps (incl. reopened_by) so the voucher
			# returns to a clean state and an admin can reopen it again later.
			doc.db_set("reopened", 0, update_modified=False)
			doc.db_set("reopened_by", None, update_modified=False)
			doc.db_set("reopened_until", None, update_modified=False)
			frappe.db.commit()
			_notify_employee(
				doc.submitter,
				"Reopen window closed",
				f"The 24-hour edit window for {doc.name} closed; it's back in the approval queue.",
			)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), "relock_expired_reopened_vouchers")


def notify_intent_pending(doc, method):
	"""On a Call Log with NO disposition set, push to the CALLER (the rep)."""
	if getattr(doc.flags, "skip_notification", False):
		return
	if doc.get("disposition"):
		return
	try:
		email = _employee_email(doc.caller)
		tokens = _tokens_for_user(email)
		if tokens:
			send_push(
				tokens,
				"Set call intent",
				f"Update the intent for your call to {doc.get('contact_number') or 'a lead'}",
				data={"screen": "lead", "lead": doc.get("lead") or "", "call": doc.name},
			)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Push Notification Error")
