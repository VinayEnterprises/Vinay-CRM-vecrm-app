# PD-S28-AUTH-RESET-PORTAL-UI — Phase B Dispatch

**Session:** S28
**Phase:** B (Build)
**Status:** READY when S28 opens. **Depends on PD-S28-AUTH-RESET-PORTAL-BFF merged & deployed.**

**Scope contract:** Portal UI pages + forms ONLY. BFF routes already exist (PORTAL-BFF). Email mechanism already exists (EMAIL-MECHANISM). Email templates already exist (EMAIL-TEMPLATE).

---

## §0 — Pre-flight

```bash
cd ~/Documents/GitHub/vecrm-portal
git fetch origin && git checkout main && git pull origin main && git status

# Confirm BFF routes deployed
curl -sI https://app.vinayenterprises.co.in/api/auth/forgot-password | head -3
# Expected: HTTP/2 405 (Method Not Allowed for GET) — route exists

git checkout -b feat/s28-auth-reset-portal-ui
```

---

## §1 — Files to add/modify

```
M  components/auth/LoginForm.tsx                # extend Forgot toggle (S27 placeholder → real form)
A  components/auth/ForgotPasswordForm.tsx       # NEW — email input + submit + post-submit state
A  components/auth/ForgotPinForm.tsx            # NEW — phone input + submit + post-submit state
A  app/(auth)/set-password/page.tsx             # NEW — token+new-password accept page
A  app/(auth)/set-pin/page.tsx                  # NEW — token+new-pin accept page
A  components/auth/SetPasswordForm.tsx          # NEW — password input + confirm + submit
A  components/auth/SetPinForm.tsx               # NEW — 4-digit PIN input + confirm + submit
```

**Pattern reference:** Existing `components/auth/LoginForm.tsx` (S26/S27 code) for form patterns, validation, error display. Mirror its styling, button shapes, and error toast pattern.

---

## §2 — LoginForm.tsx — wire the Forgot link

S27's PR #10 added a Forgot placeholder. Replace it with a working toggle that swaps the form to ForgotPasswordForm (if email mode) or ForgotPinForm (if phone mode).

State machine:
- `mode = "login" | "forgot"` (in addition to existing `authMethod = "email" | "phone"`)
- When `mode == "forgot"`: render `<ForgotPasswordForm />` (if `authMethod == "email"`) or `<ForgotPinForm />` (if `authMethod == "phone"`)
- A "Back to sign in" link sets `mode = "login"`

---

## §3 — ForgotPasswordForm.tsx

```tsx
"use client";
import { useState } from "react";
import { Mail } from "lucide-react";

export function ForgotPasswordForm({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
    } catch {
      // Network errors: still show success per no-enumeration
    } finally {
      setSubmitted(true);
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="space-y-4 text-center">
        <h2 className="text-xl font-semibold">Check your email</h2>
        <p className="text-sm text-gray-600">
          If an account exists for <strong>{email}</strong>, a reset link has been sent.
          The link expires in 30 minutes.
        </p>
        <button onClick={onBack} className="text-orange-600 hover:underline">
          Back to sign in
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h2 className="text-xl font-semibold">Forgot your password?</h2>
      <p className="text-sm text-gray-600">
        Enter your email; we'll send a reset link.
      </p>
      <div>
        <label className="text-sm">Email</label>
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@vinayenterprises.co.in"
          className="<existing-input-classes>"
        />
      </div>
      <button type="submit" disabled={submitting} className="<existing-primary-button>">
        {submitting ? "Sending..." : "Send reset link"}
      </button>
      <button type="button" onClick={onBack} className="text-orange-600 hover:underline text-sm">
        Back to sign in
      </button>
    </form>
  );
}
```

---

## §4 — ForgotPinForm.tsx

Same structure as §3 but:
- Input is `phone` with placeholder `"+91-9999900001"` and `inputMode="tel"`
- POSTs to `/api/auth/forgot-pin`
- Success message says "PIN reset link" instead of "password reset link"

---

## §5 — set-password/page.tsx + SetPasswordForm.tsx

**Page (server component):**
```tsx
// app/(auth)/set-password/page.tsx
import { SetPasswordForm } from "@/components/auth/SetPasswordForm";

export default function SetPasswordPage({
  searchParams,
}: {
  searchParams: { token?: string };
}) {
  const token = searchParams.token || "";

  if (!token) {
    return (
      <div className="text-center">
        <h2>Invalid link</h2>
        <p>This link is missing required information. Please request a new reset link.</p>
      </div>
    );
  }

  return <SetPasswordForm token={token} />;
}
```

**Form (client component):**
- Two inputs: `new_password`, `confirm_password` (must match)
- Show password requirements visibly (min length, etc — match existing api.py policy)
- Submit POSTs to `/api/auth/complete-reset` with `{token, reset_for: "password", new_secret: new_password}`
- On success: redirect to `/login?message=password-reset-success`
- On error: show generic error from response, with link to request a new reset link

---

## §6 — set-pin/page.tsx + SetPinForm.tsx

Same as §5 but:
- 4-digit PIN inputs (use the same PIN input pattern as login PIN entry)
- POST `reset_for: "pin"`

---

## §7 — Smoke (end-to-end)

After all merges + Vercel deploy, full E2E:

```
1. Open https://app.vinayenterprises.co.in
2. Click "Forgot your password?"
3. Enter test.salesrep@vinayenterprises.co.in, click "Send reset link"
4. See "Check your email" confirmation
5. Open ajay@vinayenterprises.co.in inbox (or whatever email test rep is linked to)
6. Receive email from DoNotReply@vinayenterprises.co.in
7. Click reset link in email
8. Lands on /set-password?token=...
9. Enter new password, confirm
10. Click submit
11. Redirected to /login with "Password reset successful" message
12. Sign in with new password — succeeds
```

Then repeat for PIN flow (steps 1-12 with phone path).

Pass criteria: all 12 steps complete cleanly, both paths.

---

## §8 — Commit, push, PR

```
S28 PR #XX: PD-S28-AUTH-RESET-PORTAL-UI — Forgot forms + /set-password + /set-pin pages
```

---

## §9 — Effort

| Sub-step | Effort |
|---|---|
| §2 LoginForm extension | 20 min |
| §3 ForgotPasswordForm | 30 min |
| §4 ForgotPinForm | 20 min |
| §5 set-password page + form | 30 min |
| §6 set-pin page + form | 20 min |
| §7 E2E smoke | 30 min |
| §8 commit + PR | 10 min |
| **Total** | **2-2.5 hrs** |

**End of dispatch.**
