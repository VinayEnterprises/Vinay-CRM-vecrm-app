"""
VECRM Email Pipeline — Microsoft Graph API
Credentials stored in site_config.json:
  graph_tenant_id, graph_client_id, graph_client_secret, graph_sender_email
"""
import requests
import frappe


def _get_graph_token():
    config = frappe.get_site_config()
    tenant_id = config.get("graph_tenant_id")
    client_id = config.get("graph_client_id")
    client_secret = config.get("graph_client_secret")

    if not all([tenant_id, client_id, client_secret]):
        frappe.throw("Graph API credentials not configured in site_config.json")

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        frappe.throw(f"Graph token request failed: {resp.status_code}")
    return resp.json()["access_token"]


def send_email(to, subject, html_body, sender=None):
    """Send email via Microsoft Graph API.

    Args:
        to: single email string or list of email strings
        subject: email subject line
        html_body: HTML content
        sender: override sender (defaults to graph_sender_email in site_config)
    """
    config = frappe.get_site_config()
    sender = sender or config.get("graph_sender_email")
    if not sender:
        frappe.throw("graph_sender_email not configured in site_config.json")

    if isinstance(to, str):
        to = [to]

    token = _get_graph_token()
    resp = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html_body},
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            },
            "saveToSentItems": False,
        },
        timeout=15,
    )
    if resp.status_code not in (200, 202):
        frappe.throw(f"Graph sendMail failed: {resp.status_code} — {resp.text[:200]}")
    return True
