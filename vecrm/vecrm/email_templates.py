# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

import frappe
from typing import Any

def render_email_layout(preheader: str, body_html: str) -> str:
    """Renders the Vinay Enterprises branded email layout.
    Mirrors the logic from vecrm-portal's lib/email-templates/shared.ts.
    """
    logo_src = "data:image/png;base64,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"
    
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
