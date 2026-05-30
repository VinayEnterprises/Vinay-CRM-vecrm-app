app_name = "vecrm"
app_title = "VECRM"
app_publisher = "Vinay Enterprises"
app_description = "Vinay Enterprises CRM - Lead/Inquiry pipeline and field-staff travel reimbursement"
app_email = "info@vinayenterprises.co.in"
app_license = "mit"

# Fixtures
# ------------------
# Frappe Roles created/synced on migrate (Desk-side access discipline).
# The actual approval-set logic in controllers is data-driven from
# VECRM Employee.role — these Roles exist purely for Desk access, NOT as
# the source of truth for who may approve a voucher.
fixtures = [
	{
		"doctype": "Role",
		"filters": [
			[
				"role_name",
				"in",
				["VECRM Submitter", "VECRM Approver", "VECRM Admin"],
			]
		],
	}
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "vecrm",
# 		"logo": "/assets/vecrm/logo.png",
# 		"title": "VECRM",
# 		"route": "/vecrm",
# 		"has_permission": "vecrm.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/vecrm/css/vecrm.css"
# app_include_js = "/assets/vecrm/js/vecrm.js"

# include js, css files in header of web template
# web_include_css = "/assets/vecrm/css/vecrm.css"
# web_include_js = "/assets/vecrm/js/vecrm.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "vecrm/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "vecrm/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "vecrm.utils.jinja_methods",
# 	"filters": "vecrm.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "vecrm.install.before_install"
# after_install = "vecrm.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "vecrm.uninstall.before_uninstall"
# after_uninstall = "vecrm.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "vecrm.utils.before_app_install"
# after_app_install = "vecrm.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "vecrm.utils.before_app_uninstall"
# after_app_uninstall = "vecrm.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "vecrm.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "vecrm.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------
# OBS-S34-M: this is the FIRST active scheduler registration for the
# VECRM app. Adding this turns the Frappe worker on for VECRM background
# jobs; there were no others before. doc_events above remain commented
# out intentionally — do NOT activate them as part of this hook.
#
# PD-S29 weekly meeting report: Friday 18:00 IST. The VPS site timezone
# is Asia/Kolkata, so the cron expression is plain "0 18 * * 5"
# (5 = Friday). Aggregates the current Mon 00:00 → now() window.

scheduler_events = {
	"cron": {
		# PD-S29 weekly meeting report — Fri 18:00 IST.
		"0 18 * * 5": [
			"vecrm.api.generate_weekly_meeting_report",
		],
		# PD-S33-PIPELINE-DECAY daily follow-up reminders — Mon-Sat 09:00 IST
		# (working days in India; Sun excluded so reps don't get a Monday
		# inbox flooded with Sunday's "everything is overdue" backlog).
		"0 9 * * 1-6": [
			"vecrm.api.send_followup_reminders",
		],
	},
}

# Testing
# -------

# before_tests = "vecrm.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "vecrm.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "vecrm.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "vecrm.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["vecrm.utils.before_request"]
# after_request = ["vecrm.utils.after_request"]

# Job Events
# ----------
# before_job = ["vecrm.utils.before_job"]
# after_job = ["vecrm.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"vecrm.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

