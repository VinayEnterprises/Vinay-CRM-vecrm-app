# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from typing import Any

def render_email_layout(preheader: str, body_html: str) -> str:
    """Renders the Vinay Enterprises branded email layout.
    Mirrors the logic from vecrm-portal's lib/email-templates/shared.ts.
    """
    logo_src = "cid:logo"
    
    preheader_html = f'<div style="display:none;max-height:0;overflow:hidden;color:transparent;">{frappe.utils.escape_html(preheader)}</div>' if preheader else ""

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vinay Enterprises CRM</title>
</head>
<body style="margin:0;padding:0;background:#F5F1EB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#3A2E2A;">
  {preheader_html}
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#F5F1EB;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06);">
          <tr>
            <td style="padding:32px 40px 16px;text-align:center;border-bottom:3px solid #FF8C00;">
              <img src="{logo_src}" alt="Vinay Enterprises" width="300" style="display:block;margin:0 auto;max-width:300px;height:auto;border:0;outline:none;text-decoration:none;" />
              <p style="margin:12px 0 0;font-size:12px;color:#9C8074;letter-spacing:1.5px;">CRM</p>
            </td>
          </tr>
          <tr>
            <td style="padding:40px;">
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="padding:24px 40px;background:#F5F1EB;text-align:center;color:#9C8074;font-size:12px;">
              <p style="margin:0 0 4px;">This is an automated message. Do not reply.</p>
              <p style="margin:0;">Vinay Enterprises · Est. 1993 · Ahmedabad, India</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
""".strip()

def render_lead_status_email(lead_doc: Any, old_status: str, new_status: str, actor_name: str) -> str:
    """Render the email body for a lead status change."""
    esc_lead = frappe.utils.escape_html(lead_doc.name)
    esc_company = frappe.utils.escape_html(lead_doc.company_name or "")
    esc_old = frappe.utils.escape_html(old_status)
    esc_new = frappe.utils.escape_html(new_status)
    esc_actor = frappe.utils.escape_html(actor_name)
    
    body = f"""
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:600;color:#3A2E2A;">Lead Status Updated</h2>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#5D4037;">
      The status for Lead <strong>{esc_lead} ({esc_company})</strong> was changed from <strong>{esc_old}</strong> to <strong>{esc_new}</strong> by {esc_actor}.
    </p>
    """
    return render_email_layout(
        preheader=f"Lead {esc_company} was updated to {esc_new}",
        body_html=body.strip()
    )

def render_touchpoint_email(lead_doc: Any, touchpoint_date: str, touchpoint_type: str, actor_name: str, notes: str = "") -> str:
    """Render the email body for a new touchpoint logged."""
    esc_lead = frappe.utils.escape_html(lead_doc.name)
    esc_company = frappe.utils.escape_html(lead_doc.company_name or "")
    esc_date = frappe.utils.escape_html(touchpoint_date)
    esc_type = frappe.utils.escape_html(touchpoint_type)
    esc_actor = frappe.utils.escape_html(actor_name)
    esc_notes = frappe.utils.escape_html(notes or "")
    
    body = f"""
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:600;color:#3A2E2A;">New Touchpoint Logged</h2>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#5D4037;">
      A new touchpoint was logged for Lead <strong>{esc_lead} ({esc_company})</strong> by {esc_actor}.
    </p>
    <ul style="margin:0 0 16px;padding-left:20px;font-size:15px;line-height:1.6;color:#5D4037;">
      <li><strong>Date:</strong> {esc_date}</li>
      <li><strong>Type:</strong> {esc_type}</li>
    </ul>
    """
    if esc_notes:
        body += f"""
        <div style="margin:16px 0;padding:16px;background:#F9F9F9;border-left:4px solid #FF8C00;font-size:14px;color:#5D4037;line-height:1.5;">
          {esc_notes}
        </div>
        """
        
    return render_email_layout(
        preheader=f"New {esc_type} touchpoint logged for {esc_company}",
        body_html=body.strip()
    )
