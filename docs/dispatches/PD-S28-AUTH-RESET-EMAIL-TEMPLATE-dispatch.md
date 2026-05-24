# PD-S28-AUTH-RESET-EMAIL-TEMPLATE — Phase B Dispatch

**Session:** S28
**Phase:** B (Build)
**Status:** READY when S28 opens. **Can run in parallel with PORTAL-UI** (different files). **Depends on EMAIL-MECHANISM merged.**

**Scope contract:** HTML email template modules ONLY. Plain TypeScript functions that return HTML strings. NO React, NO MJML, NO external templating libraries — keep it simple.

---

## §0 — Pre-flight

```bash
cd ~/Documents/GitHub/vecrm-portal
git fetch origin && git checkout main && git pull origin main && git status
git checkout -b feat/s28-auth-reset-email-template
```

---

## §1 — Files to add

```
A  lib/email-templates/password-reset.ts
A  lib/email-templates/pin-reset.ts
A  lib/email-templates/shared.ts                # shared layout components (header, footer, button)
```

---

## §2 — shared.ts

Shared HTML helpers — branding header, footer, primary button styling. Mirrors Vinay Enterprises brand (orange accent `#FF8C00`, brown `#5D4037`, "Vinay Enterprises CRM" wordmark).

```typescript
// lib/email-templates/shared.ts
export interface EmailLayoutParams {
  preheader?: string;  // Hidden preview text shown in inbox list
  bodyHtml: string;
}

export function renderEmailLayout({ preheader, bodyHtml }: EmailLayoutParams): string {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vinay Enterprises CRM</title>
</head>
<body style="margin:0;padding:0;background:#F5F1EB;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#3A2E2A;">
  ${preheader ? `<div style="display:none;max-height:0;overflow:hidden;color:transparent;">${escapeHtml(preheader)}</div>` : ""}
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#F5F1EB;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06);">
          <tr>
            <td style="padding:32px 40px 16px;text-align:center;border-bottom:3px solid #FF8C00;">
              <h1 style="margin:0;font-size:22px;font-weight:600;color:#5D4037;letter-spacing:0.5px;">VINAY ENTERPRISES</h1>
              <p style="margin:4px 0 0;font-size:12px;color:#9C8074;letter-spacing:1.5px;">CRM</p>
            </td>
          </tr>
          <tr>
            <td style="padding:40px;">
              ${bodyHtml}
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
  `.trim();
}

export function renderPrimaryButton({ href, label }: { href: string; label: string }): string {
  return `
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">
  <tr>
    <td>
      <a href="${escapeAttr(href)}" style="display:inline-block;background:#FF8C00;color:#FFFFFF;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:600;font-size:15px;">${escapeHtml(label)}</a>
    </td>
  </tr>
</table>
  `.trim();
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function escapeAttr(s: string): string {
  return escapeHtml(s);
}
```

---

## §3 — password-reset.ts

```typescript
// lib/email-templates/password-reset.ts
import { renderEmailLayout, renderPrimaryButton, escapeHtml } from "./shared";

export interface PasswordResetEmailParams {
  recipientName: string;     // From VECRM Employee, e.g., "Test Sales Rep"
  resetUrl: string;          // /set-password?token=<raw_token>
  expiryMinutes: number;     // 30
}

export function renderPasswordResetEmail(params: PasswordResetEmailParams): string {
  const { recipientName, resetUrl, expiryMinutes } = params;

  const bodyHtml = `
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:600;color:#3A2E2A;">Reset your VECRM password</h2>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#5D4037;">
      Hi ${escapeHtml(recipientName)},
    </p>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#5D4037;">
      We received a request to reset the password on your Vinay Enterprises CRM account.
      Click the button below to set a new password. This link expires in ${expiryMinutes} minutes.
    </p>
    ${renderPrimaryButton({ href: resetUrl, label: "Reset password" })}
    <p style="margin:24px 0 8px;font-size:13px;color:#9C8074;">
      Or paste this link in your browser:
    </p>
    <p style="margin:0 0 16px;font-size:12px;color:#9C8074;word-break:break-all;">
      ${escapeHtml(resetUrl)}
    </p>
    <hr style="border:0;border-top:1px solid #E5DDD3;margin:32px 0;" />
    <p style="margin:0 0 12px;font-size:13px;color:#9C8074;line-height:1.6;">
      <strong style="color:#5D4037;">Didn't request this?</strong> You can safely ignore this email.
      Your password will not change unless you click the link above and complete the reset.
    </p>
    <p style="margin:0;font-size:13px;color:#9C8074;line-height:1.6;">
      For security, this link can only be used once and expires after ${expiryMinutes} minutes.
    </p>
  `;

  return renderEmailLayout({
    preheader: `Reset your VECRM password. Link expires in ${expiryMinutes} minutes.`,
    bodyHtml,
  });
}
```

---

## §4 — pin-reset.ts

Same as §3 but:
- Title: "Reset your VECRM PIN"
- Body text replaces "password" with "PIN" throughout
- Button label: "Reset PIN"
- Reset URL goes to `/set-pin?token=...`
- Closing copy emphasizes PIN context: "Your PIN is used for mobile sign-in only."

```typescript
// lib/email-templates/pin-reset.ts
import { renderEmailLayout, renderPrimaryButton, escapeHtml } from "./shared";

export interface PinResetEmailParams {
  recipientName: string;
  resetUrl: string;
  expiryMinutes: number;
}

export function renderPinResetEmail(params: PinResetEmailParams): string {
  const { recipientName, resetUrl, expiryMinutes } = params;

  const bodyHtml = `
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:600;color:#3A2E2A;">Reset your VECRM PIN</h2>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#5D4037;">
      Hi ${escapeHtml(recipientName)},
    </p>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#5D4037;">
      We received a request to reset the PIN on your Vinay Enterprises CRM account.
      Click the button below to set a new PIN. This link expires in ${expiryMinutes} minutes.
    </p>
    ${renderPrimaryButton({ href: resetUrl, label: "Reset PIN" })}
    <p style="margin:24px 0 8px;font-size:13px;color:#9C8074;">
      Or paste this link in your browser:
    </p>
    <p style="margin:0 0 16px;font-size:12px;color:#9C8074;word-break:break-all;">
      ${escapeHtml(resetUrl)}
    </p>
    <hr style="border:0;border-top:1px solid #E5DDD3;margin:32px 0;" />
    <p style="margin:0 0 12px;font-size:13px;color:#9C8074;line-height:1.6;">
      <strong style="color:#5D4037;">Didn't request this?</strong> You can safely ignore this email.
      Your PIN will not change unless you click the link above and complete the reset.
    </p>
    <p style="margin:0 0 12px;font-size:13px;color:#9C8074;line-height:1.6;">
      Your PIN is used for sign-in from your mobile device.
    </p>
    <p style="margin:0;font-size:13px;color:#9C8074;line-height:1.6;">
      For security, this link can only be used once and expires after ${expiryMinutes} minutes.
    </p>
  `;

  return renderEmailLayout({
    preheader: `Reset your VECRM PIN. Link expires in ${expiryMinutes} minutes.`,
    bodyHtml,
  });
}
```

---

## §5 — Smoke (visual rendering)

Render both templates locally and inspect:

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm-portal

cat > /tmp/render-templates.mjs <<'EOF'
import { renderPasswordResetEmail } from "./lib/email-templates/password-reset.js";
import { renderPinResetEmail } from "./lib/email-templates/pin-reset.js";

const passwordHtml = renderPasswordResetEmail({
  recipientName: "Test Sales Rep",
  resetUrl: "https://app.vinayenterprises.co.in/set-password?token=demo-token-here",
  expiryMinutes: 30,
});
const pinHtml = renderPinResetEmail({
  recipientName: "Test Sales Rep",
  resetUrl: "https://app.vinayenterprises.co.in/set-pin?token=demo-token-here",
  expiryMinutes: 30,
});

import { writeFileSync } from "fs";
writeFileSync("/tmp/password-reset.html", passwordHtml);
writeFileSync("/tmp/pin-reset.html", pinHtml);
console.log("Wrote /tmp/password-reset.html and /tmp/pin-reset.html");
EOF

node /tmp/render-templates.mjs
open /tmp/password-reset.html
open /tmp/pin-reset.html
```

Then send a test via the EMAIL-MECHANISM smoke script (modified to use the template):

```javascript
import { sendMailNoreply } from "./lib/email.js";
import { renderPasswordResetEmail } from "./lib/email-templates/password-reset.js";

const html = renderPasswordResetEmail({
  recipientName: "Ajay",
  resetUrl: "https://example.com/set-password?token=template-smoke",
  expiryMinutes: 30,
});

await sendMailNoreply({
  toAddresses: ["ajay@vinayenterprises.co.in"],
  subject: "[VECRM] Email template smoke test",
  html,
});
```

**Pass criteria:**
- Visual inspection in browser: layout renders cleanly, branding correct, button styled correctly
- Email arrives in Outlook with proper rendering (Outlook renders HTML emails restrictively — confirm button + layout still look right)

---

## §6 — Commit, push, PR

```
S28 PR #XX: PD-S28-AUTH-RESET-EMAIL-TEMPLATE — HTML email templates for reset flow
```

---

## §7 — Effort

| Sub-step | Effort |
|---|---|
| §2 shared.ts (layout + button + escape) | 20 min |
| §3 password-reset.ts | 15 min |
| §4 pin-reset.ts | 10 min |
| §5 smoke (render + send + inspect) | 20 min |
| §6 commit + PR | 5 min |
| **Total** | **45 min - 1 hr** |

**End of dispatch.**
