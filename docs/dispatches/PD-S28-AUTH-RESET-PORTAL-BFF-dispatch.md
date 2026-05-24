# PD-S28-AUTH-RESET-PORTAL-BFF — Phase B Dispatch

**Session:** S28 (held in reserve, authored S27 close)
**Phase:** B (Build)
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (IDE)

**Status:** READY when S28 opens. **Depends on PD-S28-AUTH-RESET-BACKEND-API + PD-S28-AUTH-RESET-EMAIL-MECHANISM both merged & deployed.**

**Scope contract:** Next.js App Router BFF routes ONLY. NO UI pages (PORTAL-UI). NO email templates (EMAIL-TEMPLATE — though we'll import the template module).

---

## §0 — Pre-flight

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm-portal
git fetch origin
git checkout main
git pull origin main
git status

# Confirm dependencies are deployed
curl -sI https://crm.vinayenterprises.co.in/api/method/vecrm.api.request_password_reset | head -3
# Expected: HTTP/2 405 (Method Not Allowed for GET) — endpoint exists
```

```bash
git checkout -b feat/s28-auth-reset-portal-bff
git push -u origin feat/s28-auth-reset-portal-bff
```

---

## §1 — Files to add

```
A  app/api/auth/forgot-password/route.ts
A  app/api/auth/forgot-pin/route.ts
A  app/api/auth/complete-reset/route.ts
M  lib/frappe.ts                                # if helper for api.method calls needs extension
```

Pattern mirrors existing auth BFF routes — look at `app/api/auth/login/route.ts` for canonical shape (Frappe API call via existing helper, response shape, error handling).

---

## §2 — Route 1: `app/api/auth/forgot-password/route.ts`

```typescript
import { NextRequest, NextResponse } from "next/server";
import { sendMailNoreply } from "@/lib/email";
import { callFrappeAPI } from "@/lib/frappe"; // existing helper, exact name may vary
import { renderPasswordResetEmail } from "@/lib/email-templates/password-reset";

export async function POST(request: NextRequest) {
  let email: string;
  try {
    const body = await request.json();
    email = String(body.email || "").trim().toLowerCase();
  } catch {
    return NextResponse.json(
      { success: false, message: "Invalid request" },
      { status: 400 }
    );
  }

  if (!email) {
    return NextResponse.json(
      { success: true, message: "If an account exists for this email, a reset link has been sent." }
    );
  }

  try {
    // Call backend API
    const result = await callFrappeAPI(
      "vecrm.api.request_password_reset",
      { email },
      { method: "POST" }
    );

    // Backend returns {success, message, _internal: {raw_token, employee_name}}
    // _internal is BFF-only; never pass to client.
    const internal = result?.message?._internal;

    if (internal?.raw_token) {
      const resetUrl = new URL(
        `/set-password?token=${encodeURIComponent(internal.raw_token)}`,
        request.nextUrl.origin
      ).toString();

      const html = renderPasswordResetEmail({
        recipientName: internal.employee_name || "User",
        resetUrl,
        expiryMinutes: 30,
      });

      // Send email; if delivery fails, swallow error (no-enumeration: client
      // sees same response). Log to console for ops visibility.
      try {
        await sendMailNoreply({
          toAddresses: [email],
          subject: "Reset your VECRM password",
          html,
        });
      } catch (err) {
        console.error("[forgot-password] email send failed:", err.message);
        // Continue — return success to client regardless
      }
    }

    // Always return same shape (no-enumeration)
    return NextResponse.json({
      success: true,
      message: "If an account exists for this email, a reset link has been sent.",
    });
  } catch (err) {
    console.error("[forgot-password] backend error:", err);
    // Even on backend error, return success shape (no-enumeration)
    return NextResponse.json({
      success: true,
      message: "If an account exists for this email, a reset link has been sent.",
    });
  }
}
```

---

## §3 — Route 2: `app/api/auth/forgot-pin/route.ts`

Same structure as §2 but:
- Input is `phone` not `email`
- Calls `vecrm.api.request_pin_reset`
- Email template: `renderPinResetEmail` (similar to password but says "PIN")
- Reset URL: `/set-pin?token=...`
- Subject: "Reset your VECRM PIN"

Note: The email STILL goes to the user's email address (associated with their phone in VECRM Employee). The user provides their phone number, backend looks up the linked User's email, the email is sent there. This is the V1 trade-off documented in the addendum security invariants.

---

## §4 — Route 3: `app/api/auth/complete-reset/route.ts`

Single route handling both password and PIN completion. Decided by `reset_for` param.

```typescript
import { NextRequest, NextResponse } from "next/server";
import { callFrappeAPI } from "@/lib/frappe";

export async function POST(request: NextRequest) {
  let body: any;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, message: "Invalid request" },
      { status: 400 }
    );
  }

  const token = String(body.token || "");
  const resetFor = String(body.reset_for || ""); // "password" or "pin"
  const newSecret = String(body.new_secret || "");

  if (!token || !resetFor || !newSecret) {
    return NextResponse.json(
      { success: false, message: "Missing required fields" },
      { status: 400 }
    );
  }

  const method = resetFor === "password"
    ? "vecrm.api.complete_password_reset"
    : resetFor === "pin"
    ? "vecrm.api.complete_pin_reset"
    : null;

  if (!method) {
    return NextResponse.json(
      { success: false, message: "Invalid reset type" },
      { status: 400 }
    );
  }

  const paramName = resetFor === "password" ? "new_password" : "new_pin";

  try {
    const result = await callFrappeAPI(
      method,
      { token, [paramName]: newSecret },
      { method: "POST" }
    );

    // Backend throws on invalid/expired/consumed; if we get here, success.
    return NextResponse.json({
      success: true,
      message: result?.message?.message || `${resetFor === "password" ? "Password" : "PIN"} updated. You may now sign in.`,
    });
  } catch (err: any) {
    // Backend throws generic "Invalid or expired link"; surface that.
    return NextResponse.json(
      {
        success: false,
        message: err?.message || "Invalid or expired link. Request a new reset link.",
      },
      { status: 400 }
    );
  }
}
```

---

## §5 — Local smoke (operator + executor)

Before merging, smoke locally via `vercel dev`:

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm-portal
vercel env pull .env.local
vercel dev  # spins up on localhost:3000
```

Then in another terminal:

```bash
# RUN FROM MAC
# Smoke 1: forgot-password with real email
curl -X POST http://localhost:3000/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "test.salesrep@vinayenterprises.co.in"}'

# Smoke 2: forgot-password with nonexistent email (no-enumeration check)
curl -X POST http://localhost:3000/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "nope@example.com"}'

# Smoke 3: forgot-pin with real phone
curl -X POST http://localhost:3000/api/auth/forgot-pin \
  -H "Content-Type: application/json" \
  -d '{"phone": "+91-9999900001"}'
```

**Pass criteria:**
- All three return `{success: true, message: "If an account exists..."}`
- Smoke 1 and 3 result in email arriving at the real user's inbox
- Smoke 2 doesn't send any email (no-enumeration: client can't tell from response, but no email is sent)
- Backend audit log shows `auth.reset.requested` for all three (Smoke 2 with `employee=NULL`)

---

## §6 — Commit, push, PR

```bash
git add app/api/auth/forgot-password/route.ts \
        app/api/auth/forgot-pin/route.ts \
        app/api/auth/complete-reset/route.ts
git commit -m "S28 PR #XX: PD-S28-AUTH-RESET-PORTAL-BFF — reset flow BFF routes

Three new Next.js App Router routes:
  - POST /api/auth/forgot-password (email -> token + email send)
  - POST /api/auth/forgot-pin (phone -> token + email send)
  - POST /api/auth/complete-reset (token + new secret -> credential update)

forgot-* routes:
  1. Validate input
  2. Call vecrm.api.request_*_reset (returns raw_token in _internal)
  3. If _internal.raw_token, send email via sendMailNoreply
  4. Return generic success (no-enumeration: same shape regardless of match)

complete-reset:
  1. Validate input
  2. Dispatch by reset_for to vecrm.api.complete_password_reset or complete_pin_reset
  3. Backend throws on invalid/expired/consumed -> surface generic error
  4. Success -> {success: true, message}

Email send failures are caught and logged (no-enumeration: client sees same
response). Backend errors are also masked. The user-visible signal is purely
'we may have sent you an email; check your inbox'.

Local smoke (vercel dev): 3 paths verified — real email, nonexistent email
(no-enumeration), real phone.

Depends on:
  - PD-S28-AUTH-RESET-BACKEND-API (backend methods)
  - PD-S28-AUTH-RESET-EMAIL-MECHANISM (sendMailNoreply)
  - PD-S28-AUTH-RESET-EMAIL-TEMPLATE (renderPasswordResetEmail, renderPinResetEmail)

Ref: PD-S28-AUTH-RESET-INFRA-recon-findings-ADDENDUM.md"

git push origin feat/s28-auth-reset-portal-bff

gh pr create --base main --head feat/s28-auth-reset-portal-bff \
  --title "S28 PR #XX: PD-S28-AUTH-RESET-PORTAL-BFF — reset flow BFF routes" \
  --body "<rendered from commit message>"
```

---

## §7 — Effort

| Sub-step | Effort |
|---|---|
| §0 pre-flight | 5 min |
| §2 forgot-password route | 30 min |
| §3 forgot-pin route | 20 min |
| §4 complete-reset route | 30 min |
| §5 local smoke (3 paths) | 30 min |
| §6 commit + PR | 10 min |
| **Total** | **2 hrs** |

---

## §8 — Layer-transition checkpoints

1. Before §2: BACKEND-API and EMAIL-MECHANISM both merged + deployed
2. Before commit: §5 all 3 smokes pass locally
3. Before deploy: PR merged; Vercel auto-deploys
4. Post-deploy: PORTAL-UI uses these routes (next dispatch)

**End of dispatch.**
