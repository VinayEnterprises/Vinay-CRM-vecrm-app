# PD-S28-AUTH-RESET-SECURITY-REVIEW + SMOKE — Phase B Dispatch

**Session:** S28
**Phase:** B (Build, but really audit/gate)
**Status:** READY when S28 opens. **Final gate. Depends on ALL prior S28 reset-flow sub-PDs merged + deployed.** Not optional — security review is mandatory for any auth-related shipment.

**Scope contract:** Pre-merge audit of all auth-reset code + end-to-end smoke + sign-off. NO new code. NO new features. If issues are found, file follow-up PRs; do not merge unaudited code.

---

## §0 — Pre-conditions

All of these must be true before this dispatch begins:

- ✅ PD-S28-AUTH-RESET-SCHEMA shipped (S27 — already done)
- ✅ PD-S28-AUTH-RESET-BACKEND-API merged + deployed
- ✅ PD-S28-AUTH-RESET-EMAIL-MECHANISM merged + deployed
- ✅ PD-S28-AUTH-RESET-PORTAL-BFF merged + deployed
- ✅ PD-S28-AUTH-RESET-PORTAL-UI merged + deployed
- ✅ PD-S28-AUTH-RESET-EMAIL-TEMPLATE merged + deployed

Verify by:
```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm && git log --oneline -10
cd ~/Documents/GitHub/vecrm-portal && git log --oneline -10
```

All 6 PR squash-merges should be in the recent log.

---

## §1 — Security review checklist (audit BEFORE smoke)

Walk through each item. For each, either ✅ verified or 🔍 needs investigation. Investigation results documented in findings; CANNOT skip to smoke until all are ✅.

### §1.1 — Token entropy + storage

- [ ] Raw token uses `secrets.token_urlsafe(32)` (256 bits) — verified by reading `vecrm/utils/auth_reset.py`
- [ ] Raw token NEVER persisted: search `vecrm/api.py` for `raw_token`; should only appear in response `_internal` (in-memory) and in audit log message if at all (it should NOT be in audit messages — verify)
- [ ] Token hash uses `hashlib.sha256` (not md5, not sha1, not unsalted weakness)
- [ ] DB stores `token_hash`, never raw — verified by `SELECT token_hash FROM tabVECRM Auth Reset Token LIMIT 5` showing 64-char hex values, no raw tokens
- [ ] Email link contains raw token in URL parameter (necessary for the flow); the link is one-time and short-lived

### §1.2 — Token comparison

- [ ] All token comparisons use `hmac.compare_digest` (constant-time) OR go through DB equality (which is also constant-time within a single column index lookup)
- [ ] Frappe's `frappe.db.get_value(token_hash=X)` is acceptable — DB equality on indexed column

### §1.3 — Single-use enforcement

- [ ] `consumed_at` is checked BEFORE any credential write in `complete_*_reset`
- [ ] `consumed_at` is set in the SAME transaction as the credential write (atomic — token marked consumed regardless of credential-write success/failure)
- [ ] Reusing a consumed token returns generic error (audit log records `auth.reset.invalid_token`)

### §1.4 — Time-bound enforcement

- [ ] `expires_at` is checked BEFORE any credential write
- [ ] Comparison uses `frappe.utils.now_datetime()` (timezone-aware) not `datetime.now()` (naive)
- [ ] Default TTL is 30 min (constant in `vecrm/utils/auth_reset.py`)
- [ ] Expired token returns generic error (audit log records `auth.reset.expired`)

### §1.5 — Rate limiting

- [ ] Reset request limit: 3 per employee per 15-min window
- [ ] Rate-limited request still emits an audit row (`auth.reset.rate_limited`)
- [ ] Rate-limited response is identical-shape to success (no-enumeration via rate limit)
- [ ] Rate limit counts BOTH password and PIN reset requests (sharing the budget) — prevents an attacker from spamming reset requests via both paths

### §1.6 — No-enumeration responses

- [ ] `request_password_reset` returns same JSON shape for: success / nonexistent email / rate-limited / internal error
- [ ] `request_pin_reset` same — for phone path
- [ ] `complete_*_reset` failure modes (invalid/expired/consumed/wrong type) all return identical error shape; specifics go to audit log only
- [ ] Email send failures inside BFF routes are caught and logged; do NOT propagate to client response

### §1.7 — Reset_for discriminator

- [ ] `complete_password_reset` rejects tokens with `reset_for != "password"`
- [ ] `complete_pin_reset` rejects tokens with `reset_for != "pin"`
- [ ] Cross-type abuse logged as `auth.reset.invalid_token` with note in audit log

### §1.8 — Lockout interaction

- [ ] Successful password reset clears `failed_password_attempts` and `password_locked_until` on the user record
- [ ] Successful PIN reset clears `failed_pin_attempts` and `pin_locked_until`
- [ ] Failed reset attempts do NOT increment login-failure counters (they're separate from login)

### §1.9 — PIN-via-email trust boundary

- [ ] PIN reset email is sent to the user's EMAIL (linked via VECRM Employee → User)
- [ ] V1 trade-off documented: PIN can be reset via email-only (no SMS OTP infrastructure yet)
- [ ] Future: PIN reset SHOULD require SMS OTP for stronger second-factor; banked as P2 for post-V1 hardening

### §1.10 — Audit log coverage

- [ ] All 5 events emit correctly: `auth.reset.requested`, `auth.reset.consumed`, `auth.reset.expired`, `auth.reset.invalid_token`, `auth.reset.rate_limited`
- [ ] Audit rows include `employee` field (NULL for non-enumeration cases is acceptable)
- [ ] Audit rows include `path` field (password/pin)
- [ ] Audit rows include `ip_address` field for forensic capability

### §1.11 — Email security (DNS auth)

- [ ] Reset emails arrive in Outlook (not spam) — confirms SPF/DKIM/DMARC align for `DoNotReply@vinayenterprises.co.in`
- [ ] Check email headers: `Authentication-Results` should show `spf=pass`, `dkim=pass`, `dmarc=pass`
- [ ] Sender shown to user as `DoNotReply@vinayenterprises.co.in` (not as `<user>@vemio.io` from a Graph misconfig)

### §1.12 — TypeScript / Python type safety

- [ ] All 4 Frappe API methods have full type annotations (per Frappe v16 `require_type_annotated_api_methods`)
- [ ] All BFF routes use TypeScript with proper types (no `any` slop except at JSON.parse boundary)
- [ ] BFF routes catch typed errors not `any`

### §1.13 — Secret hygiene

- [ ] `GRAPH_CLIENT_SECRET` is NEVER logged anywhere in code (search `console.log`, `print`, `logger.*` for any GRAPH_* references)
- [ ] `.env.local` is in `.gitignore` on vecrm-portal
- [ ] No client secrets committed to either repo (history scan)

---

## §2 — End-to-end smoke (after security review passes)

Complete user-journey test, both paths.

### §2.1 — Password reset path

```
Step 1: Open https://app.vinayenterprises.co.in in incognito window
Step 2: Click "Forgot your password?" on Email tab
Step 3: Enter test.salesrep@vinayenterprises.co.in
Step 4: Click "Send reset link"
Step 5: Observe "Check your email" confirmation
Step 6: Open <test rep's email inbox> (operator-managed)
Step 7: Verify email arrived from DoNotReply@vinayenterprises.co.in within 60s
Step 8: Verify email subject: "Reset your VECRM password"
Step 9: Verify HTML renders correctly (button styled, branding present)
Step 10: Click "Reset password" button in email
Step 11: Land on https://app.vinayenterprises.co.in/set-password?token=<32-char>
Step 12: Enter new password "newpass123!" twice (matching)
Step 13: Click submit
Step 14: Redirected to /login with success message
Step 15: Sign in with test.salesrep@vinayenterprises.co.in / newpass123!
Step 16: Login succeeds, lands on /dashboard
Step 17: Confirm in audit log: rows for auth.reset.requested, auth.reset.consumed, auth.login.success — in chronological order
```

### §2.2 — PIN reset path

Repeat §2.1 but starting with Phone tab, phone `+91-9999900001`, PIN reset link, new PIN "5678".

### §2.3 — Error path smokes

For each, observe behavior and check audit log:

- [ ] **Expired token**: wait 31 minutes after requesting a reset, then click the link. Expect generic error message, audit row `auth.reset.expired`.
- [ ] **Reused token**: complete a reset successfully, then click the same link again. Expect generic error, audit row `auth.reset.invalid_token`.
- [ ] **Wrong type**: request password reset, manually swap URL to `/set-pin?token=<password-token>`. Expect generic error, audit row `auth.reset.invalid_token`.
- [ ] **Rate limit**: request 4 password resets within 15 min. Verify 4th is rate-limited. All 4 requests return identical-looking response (no-enumeration). 4th audit row is `auth.reset.rate_limited`.
- [ ] **Nonexistent email**: request reset for `nope@example.com`. Get success-shape response. No email sent. Audit row `auth.reset.requested` with `employee=NULL`.
- [ ] **Backend down**: stop vecrm-backend-1 momentarily, request reset, verify portal still returns success-shape (no-enumeration via backend failure). Restart backend.

### §2.4 — Reset clears lockout state

```
Step 1: Lock the test rep account by failing login 5 times with wrong password
Step 2: Confirm User.failed_password_attempts = 5 and password_locked_until is set in the future
Step 3: Run password reset flow successfully (§2.1)
Step 4: Probe DB: failed_password_attempts should be 0, password_locked_until should be NULL
Step 5: Test rep can sign in immediately (no waiting for lockout expiry)
```

Repeat for PIN path.

---

## §3 — Findings document

Author findings doc:
```
~/Documents/GitHub/vecrm/docs/dispatches/PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md
```

Structure:
- §1 audit results (1.1 through 1.13 — each item ✅ or 🔍 with notes)
- §2 smoke results (each path's exit state)
- §3 deviations / hotfix follow-ups (if any audit item or smoke step failed)
- §4 sign-off (operator: yes/no for shipping V1)

Commit on branch `audit/s28-auth-reset-security-review` (don't merge — the doc is the artifact, no code change).

---

## §4 — Sign-off criteria

**SHIP V1** if and only if:
- All §1 audit items checked ✅
- All §2.1 + §2.2 happy-path smokes pass
- §2.3 error-path smokes all show correct behavior
- §2.4 lockout-clearing works
- DNS auth headers show pass/pass/pass

**DO NOT SHIP** if any of:
- Token entropy or storage issue found
- Constant-time compare missing anywhere
- No-enumeration violated (different response shapes for different failure modes)
- Email delivery fails to real inbox
- Audit log missing events
- Lockout not cleared on successful reset

If anything blocks: hotfix PR(s), redeploy, re-audit affected items, re-smoke affected paths.

---

## §5 — Effort

| Sub-step | Effort |
|---|---|
| §1 security review (13 audit items) | 1-1.5 hrs |
| §2.1 password happy-path smoke | 15 min |
| §2.2 PIN happy-path smoke | 15 min |
| §2.3 error-path smokes (5 cases) | 45 min |
| §2.4 lockout clearing (2 paths) | 30 min |
| §3 findings doc | 30 min |
| §4 sign-off | 5 min |
| **Total** | **3.5-4 hrs** |

---

## §6 — Post-sign-off

When V1 ships:

1. Author S28 close handover documenting the full reset-flow shipment
2. Bank any new observations or locks discovered during audit/smoke
3. Promote any draft locks to permanent (e.g., VECRM-LOCK-VEMIO-EMAIL-PATTERN was draft; promote at S28 close if held up)
4. Update VECRM dependency map with new reset-flow modules
5. PD-S28-AUTH-RESET-FLOW (the parent PD spanning all 6 sub-PDs) is officially closed in the pendency

---

**End of dispatch.**

This is the final dispatch in the S28 reset-flow series. Total S28 effort across all 6 sub-PDs: 9-11 hours.
