# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class VECRMNotification(Document):
	"""In-app notification for a VECRM portal user.

	Keyed by plain `for_email` rather than a Link-to-User because all portal
	sessions share one Frappe user; individual employees are not User records,
	so core "Notification Log" (for_user → User) cannot represent them. Reads
	are served by the whitelisted vecrm.api.get_my_notifications, scoped to the
	session's vecrm_email.
	"""

	pass
