# PD-S28-AUTH-RESET-EMAIL-MECHANISM — Phase B Dispatch

**Session:** S28 (held in reserve, authored S27 close)
**Phase:** B (Build)
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (IDE)
**Operator:** Ajay Salvi

**Status:** READY when S28 opens. **Can run in parallel with PD-S28-AUTH-RESET-BACKEND-API** — they touch different repos (this is vecrm-portal, BACKEND-API is vecrm). Either order works, but EMAIL-MECHANISM merging first lets PORTAL-BFF (which depends on both) start immediately.

**Reference docs:**
- `docs/dispatches/PD-S28-AUTH-RESET-INFRA-recon-findings-ADDENDUM.md` (commit `22bf471`) — §1 Graph implementation pattern from Vemio
- Vemio code reference: `~/Documents/GitHub/vemio-dashboard/lib/email.js` (PROVEN canonical pattern, mirror this)

**Scope contract:** vecrm-portal `lib/email.js` module ONLY. NO BFF routes (those are PORTAL-BFF). NO HTML templates (EMAIL-TEMPLATE). NO UI (PORTAL-UI). Just the Graph send mechanism + token cache + sender configuration.

---

## §0 — Pre-flight

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm-portal
git fetch origin
git checkout main
git pull origin main
git status

# Cross-reference: confirm Vemio's email.js exists for mirroring
ls -la ~/Documents/GitHub/vemio-dashboard/lib/email.js
```

---

## §1 — Vercel env var prep (operator-action, BEFORE merge)

Before this PR ships, add these env vars to vecrm-portal's Vercel project (Settings → Environment Variables):

| Variable | Value | Notes |
|---|---|---|
| `GRAPH_TENANT_ID` | (copy from vemio-dashboard Vercel env vars) | Same Azure AD tenant |
| `GRAPH_CLIENT_ID` | (copy from vemio-dashboard) | Same vemio-email-sender app reg |
| `GRAPH_CLIENT_SECRET` | (copy from vemio-dashboard) | SECRET — operator copies directly, never via chat |
| `GRAPH_SENDER_NOREPLY_VECRM` | `DoNotReply@vinayenterprises.co.in` | NEW — VECRM-specific sender |

**Critical:** Use vecrm-specific sender env var name (`GRAPH_SENDER_NOREPLY_VECRM`) rather than reusing Vemio's `GRAPH_SENDER_NOREPLY` value, even though the Graph tenant/client/secret are shared. This makes it explicit that VECRM portal sends from VECRM's sender mailbox, not Vemio's.

**Operator confirms:** all 4 vars set in Vercel for Production environment (Preview/Development optional). Without this step, the deploy will fail with token-fetch errors.

---

## §2 — File: `vecrm-portal/lib/email.js` (NEW)

Mirror Vemio's pattern. ~80-100 lines. Direct `fetch` to Graph; no `msal` library, no `@azure/communication-email`.

```javascript
// vecrm-portal/lib/email.js
/**
 * Microsoft Graph email sender for VECRM portal.
 *
 * Pattern mirrored from vemio-dashboard/lib/email.js (proven in production
 * since mid-April 2026). Same Azure AD app registration, same Graph
 * client_credentials flow, different sender mailbox.
 *
 * Used by /api/auth/forgot-password and /api/auth/forgot-pin BFF routes
 * to deliver password/PIN reset links to user inboxes.
 *
 * Security:
 * - Token cached in module scope with expiry check (Vercel functions are
 *   short-lived, but caching avoids rate-limit issues during burst traffic).
 * - Client secret never logged.
 * - Send failures throw; BFF routes must catch and respond generically
 *   (no-enumeration even for delivery failures).
 *
 * Env vars (Vercel):
 *   GRAPH_TENANT_ID
 *   GRAPH_CLIENT_ID
 *   GRAPH_CLIENT_SECRET
 *   GRAPH_SENDER_NOREPLY_VECRM  ("DoNotReply@vinayenterprises.co.in")
 */

const GRAPH_TENANT_ID = process.env.GRAPH_TENANT_ID;
const GRAPH_CLIENT_ID = process.env.GRAPH_CLIENT_ID;
const GRAPH_CLIENT_SECRET = process.env.GRAPH_CLIENT_SECRET;
const GRAPH_SENDER_NOREPLY_VECRM = process.env.GRAPH_SENDER_NOREPLY_VECRM
  || "DoNotReply@vinayenterprises.co.in";

let graphTokenCache = null; // { token, expiresAtMs }

async function getGraphToken() {
  const now = Date.now();
  if (graphTokenCache && graphTokenCache.expiresAtMs > now + 60_000) {
    return graphTokenCache.token;
  }
  if (!GRAPH_TENANT_ID || !GRAPH_CLIENT_ID || !GRAPH_CLIENT_SECRET) {
    throw new Error(
      "Graph credentials missing — set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET in Vercel env vars."
    );
  }
  const url = `https://login.microsoftonline.com/${encodeURIComponent(GRAPH_TENANT_ID)}/oauth2/v2.0/token`;
  const body = new URLSearchParams({
    grant_type: "client_credentials",
    client_id: GRAPH_CLIENT_ID,
    client_secret: GRAPH_CLIENT_SECRET,
    scope: "https://graph.microsoft.com/.default",
  });
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.access_token) {
    throw new Error(
      `Graph token fetch failed: HTTP ${res.status}`
    );
  }
  const expiresInMs = (Number(data.expires_in) || 3600) * 1000;
  graphTokenCache = { token: data.access_token, expiresAtMs: now + expiresInMs };
  return graphTokenCache.token;
}

/**
 * Send an email via Microsoft Graph from the VECRM no-reply mailbox.
 *
 * @param {Object} params
 * @param {string[]} params.toAddresses - Recipient email addresses
 * @param {string} params.subject - Email subject line
 * @param {string} params.html - HTML body (use lib/email-templates/*)
 * @param {string} [params.replyTo] - Optional Reply-To address
 * @returns {Promise<void>} - Resolves on successful Graph API call
 * @throws {Error} - On token fetch failure or Graph send failure
 */
export async function sendMailNoreply({ toAddresses, subject, html, replyTo }) {
  const token = await getGraphToken();
  const message = {
    message: {
      subject,
      body: { contentType: "HTML", content: html },
      toRecipients: toAddresses.map(addr => ({ emailAddress: { address: addr } })),
      ...(replyTo && { replyTo: [{ emailAddress: { address: replyTo } }] }),
    },
    saveToSentItems: false,
  };
  const res = await fetch(
    `https://graph.microsoft.com/v1.0/users/${encodeURIComponent(GRAPH_SENDER_NOREPLY_VECRM)}/sendMail`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message),
    }
  );
  if (!res.ok) {
    const errBody = await res.text().catch(() => "");
    throw new Error(`Graph sendMail failed: HTTP ${res.status} ${errBody.slice(0, 200)}`);
  }
}
```

---

## §3 — Diff vs Vemio's email.js (executor confirms these)

Before committing, run `diff` against Vemio's:

```bash
diff ~/Documents/GitHub/vemio-dashboard/lib/email.js ./lib/email.js
```

Expected differences:
1. **Env var names** — `GRAPH_SENDER_NOREPLY_VECRM` vs Vemio's `GRAPH_SENDER_NOREPLY`
2. **Default sender** — `DoNotReply@vinayenterprises.co.in` vs `DoNotReply@vemio.io`
3. **Function name** — `sendMailNoreply` (we use a simple name; if Vemio uses `sendInviteEmail` or similar, we don't need that name)
4. **Comment headers** — VECRM-specific docstrings

Expected SAMENESS:
- `getGraphToken()` logic — identical
- Token cache logic — identical
- Graph API URL pattern — identical
- Error handling shape — identical

If Vemio's file has additional helpers (e.g., `sendInviteEmail`, `sendMagicLink`), DO NOT mirror those — VECRM only needs the reset flow's `sendMailNoreply`. PORTAL-BFF will call this directly.

---

## §4 — Smoke test (BEFORE merge — local dev with prod env vars)

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm-portal

# Pull prod env vars locally (vercel CLI)
vercel env pull .env.local

# Quick smoke script
cat > /tmp/test-email.mjs <<'EOF'
import { sendMailNoreply } from "./lib/email.js";

await sendMailNoreply({
  toAddresses: ["ajay@vinayenterprises.co.in"],
  subject: "[VECRM] Email mechanism smoke test (PD-S28-AUTH-RESET-EMAIL-MECHANISM)",
  html: `
    <h2 style="color:#FF8C00">VECRM email mechanism smoke</h2>
    <p>If you are reading this, the new vecrm-portal lib/email.js works.</p>
    <p>Sent: ${new Date().toISOString()}</p>
    <p>Ref: PD-S28-AUTH-RESET-EMAIL-MECHANISM</p>
  `,
});
console.log("sendMailNoreply returned without exception");
EOF

# Run with prod env vars
node --env-file=.env.local /tmp/test-email.mjs
```

**Pass criteria:**
- Script exits without exception
- Operator receives email in ajay@vinayenterprises.co.in within 30 seconds
- Email subject + body render correctly
- Sender shows as `DoNotReply@vinayenterprises.co.in`

If email lands in spam: SPF/DKIM/DMARC drift; halt and fix DNS. (Per recon §R5, this should already be configured.)

---

## §5 — Commit, push, PR

```bash
git checkout -b feat/s28-auth-reset-email-mechanism
git add lib/email.js
git commit -m "S28 PR #XX: PD-S28-AUTH-RESET-EMAIL-MECHANISM — portal-side Graph email send

New lib/email.js mirroring Vemio's portal-side Graph fetch pattern (proven
in production since April 2026 in vemio-dashboard).

Exports sendMailNoreply({ toAddresses, subject, html, replyTo }) — direct
Microsoft Graph API call via fetch, no msal or ACS dependencies. Token
cache in module scope with expiry check.

Sender: DoNotReply@vinayenterprises.co.in (existing M365 mailbox).
Reuses vemio-email-sender app reg (same GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET).

Used by PD-S28-AUTH-RESET-PORTAL-BFF routes /api/auth/forgot-password and
/api/auth/forgot-pin to deliver reset links.

Env vars (Vercel):
  GRAPH_TENANT_ID (reuse from vemio-dashboard)
  GRAPH_CLIENT_ID (reuse)
  GRAPH_CLIENT_SECRET (reuse)
  GRAPH_SENDER_NOREPLY_VECRM=DoNotReply@vinayenterprises.co.in (NEW)

Operator-side smoke (sent test email to ajay@) verified before merge.

Ref: PD-S28-AUTH-RESET-INFRA-recon-findings-ADDENDUM.md (commit 22bf471) §1"

git push origin feat/s28-auth-reset-email-mechanism

gh pr create --base main --head feat/s28-auth-reset-email-mechanism \
  --title "S28 PR #XX: PD-S28-AUTH-RESET-EMAIL-MECHANISM — portal-side Graph email send" \
  --body "<rendered from commit message>"
```

---

## §6 — Effort

| Sub-step | Effort |
|---|---|
| §1 Vercel env vars (operator) | 5-10 min |
| §2 lib/email.js creation | 30 min |
| §3 diff verification | 10 min |
| §4 smoke (test email) | 15 min |
| §5 commit + PR | 10 min |
| **Total** | **1.5 hrs** |

---

## §7 — Layer-transition checkpoints

1. Before §2: Vercel env vars confirmed set (§1)
2. Before commit: smoke test email received in Outlook (§4)
3. Before deploy: PR merged
4. Post-deploy: Vercel auto-deploys to app.vinayenterprises.co.in; no manual smoke (PORTAL-BFF exercises this code path)

**End of dispatch.**
