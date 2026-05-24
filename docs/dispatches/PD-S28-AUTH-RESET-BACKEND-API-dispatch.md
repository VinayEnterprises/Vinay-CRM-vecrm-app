# PD-S28-AUTH-RESET-BACKEND-API — Phase B Dispatch

**Session:** S28 (held in reserve, authored S27 close)
**Phase:** B (Build)
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (IDE)
**Operator:** Ajay Salvi

**Status:** READY when S28 opens. Schema substrate (PD-S28-AUTH-RESET-SCHEMA) shipped in S27 (`6d46b0d`). This dispatch ships the Frappe-side API methods that USE the schema. Portal-side wiring (BFF, UI, email mechanism) ships separately.

**Reference docs (read first):**
- `docs/dispatches/PD-S28-AUTH-RESET-INFRA-recon-findings-ADDENDUM.md` (commit `22bf471`) — architectural decisions, security invariants
- `docs/dispatches/PD-S28-AUTH-RESET-SCHEMA-dispatch.md` (S27, archive) — schema shape

**Scope contract:** Frappe API methods ONLY. NO portal code, NO email sending, NO HTML templates. The methods are pure data + crypto operations; the portal does email delivery.

---

## §0 — Pre-flight

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm
git fetch origin
git checkout main
git pull origin main
git status
```

Confirm: on `main`, clean, HEAD includes commits at least through `6d46b0d` (PR #21).

```bash
git checkout -b feat/s28-auth-reset-backend-api
git push -u origin feat/s28-auth-reset-backend-api
```

---

## §1 — Files to modify

```
M  vecrm/api.py                                       (add 4 new API methods)
M  vecrm/vecrm/doctype/vecrm_auth_reset_token/vecrm_auth_reset_token.py  (add internal-use helper if needed)
A  vecrm/utils/auth_reset.py                          (NEW — pure crypto helpers, no Frappe context)
```

**Files NOT to touch:**
- Schema files (already shipped in PR #21)
- portal code (different repo)
- audit log doctype (vocabulary extension is convention only)

---

## §2 — Module 1: `vecrm/utils/auth_reset.py` (NEW)

Pure-function helpers for token generation and hashing. No Frappe context — easily unit-testable.

```python
# vecrm/utils/auth_reset.py
"""Auth reset token primitives — pure crypto, no Frappe context."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Final

# Token format: 32 random bytes, base64url-encoded → ~43 chars URL-safe
TOKEN_BYTES: Final[int] = 32

# Default lifetime: 30 minutes (matches existing _LOCKOUT_MINUTES shape in api.py)
DEFAULT_TOKEN_TTL_MINUTES: Final[int] = 30

# Rate limit: 3 reset requests per employee per 15-min window
RATE_LIMIT_WINDOW_MINUTES: Final[int] = 15
RATE_LIMIT_MAX_REQUESTS: Final[int] = 3


def generate_token() -> tuple[str, str]:
    """Generate a fresh reset token.

    Returns:
        (raw_token, token_hash) — raw_token goes in the emailed link, token_hash gets stored.
    """
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """sha256 hex digest of the raw token.

    Used both at storage time and at lookup time. Must produce identical
    output for the same input across processes / machines.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison. Prevents timing oracle attacks."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
```

Notes:
- `secrets.token_urlsafe(32)` produces ~43 base64url chars, more than enough entropy for reset tokens (256 bits)
- `hmac.compare_digest` is the canonical constant-time string compare in Python stdlib
- All constants are module-level for easy testing/tuning

---

## §3 — Module 2: `vecrm/api.py` (extend, 4 new methods)

Add 4 type-annotated whitelist methods. All MUST be type-annotated per Frappe v16's `require_type_annotated_api_methods`. Pattern mirrors existing methods (look at `login_with_password` for the canonical shape).

### §3.1 — `request_password_reset(email: str) -> dict[str, Any]`

```python
@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_password_reset(email: str) -> dict[str, Any]:
    """Initiate a password reset flow.

    Always returns success regardless of whether email maps to a real employee
    (no-enumeration invariant). If a real match exists, creates a VECRM Auth
    Reset Token row and returns the raw token in the response so the portal
    BFF can include it in the emailed link.

    Args:
        email: User email to request reset for.

    Returns:
        {
          "success": True,
          "message": "If an account exists for this email, a reset link has been sent.",
          "_internal": { "raw_token": <str or None>, "employee_name": <str or None> }
        }

    The portal MUST NOT pass `_internal` through to the client. It exists so
    the portal BFF can construct the emailed link (which contains raw_token)
    without a second API roundtrip. The public-facing response shape is just
    `success` + `message`.
    """
```

Implementation outline:
1. Normalize email (lower, strip)
2. Rate limit check: count rows in `tabVECRM Auth Reset Token` where employee→user.email matches AND created within last 15 min. If ≥ 3, emit `auth.reset.rate_limited` audit event and return success (no-enumeration: same response as if email matched but rate limit didn't apply — log internally that this was rate-limited).
3. Look up VECRM Employee by `email` (Link to tabUser → user.email). If no match: emit `auth.reset.requested` audit row with `employee=NULL` (no-enumeration) and return success response with `_internal.raw_token=None`.
4. Generate token: `raw_token, token_hash = generate_token()`
5. Create `VECRM Auth Reset Token` row: `token_hash`, `employee=<phone>`, `reset_for="password"`, `expires_at=now() + 30min`, `ip_address=frappe.local.request_ip`
6. Emit `auth.reset.requested` audit row with `employee=<phone>`, `path="password"`
7. `frappe.db.commit()`
8. Return success with `_internal.raw_token=<raw_token>`, `_internal.employee_name=<phone>`

### §3.2 — `request_pin_reset(phone: str) -> dict[str, Any]`

Same structure as §3.1 but:
- Input is `phone` (E.164 `+91-XXXXXXXXXX`)
- Lookup is VECRM Employee by `phone` field directly (no User-email indirection)
- `reset_for="pin"`
- Audit path = `"pin"`
- Email is sent to the email associated with that employee (VECRM Employee → linked User → User.email)

### §3.3 — `complete_password_reset(token: str, new_password: str) -> dict[str, Any]`

```python
@frappe.whitelist(allow_guest=True, methods=["POST"])
def complete_password_reset(token: str, new_password: str) -> dict[str, Any]:
    """Consume a password reset token and set new password.

    Returns:
        Success: { "success": True, "message": "Password updated." }
        Failure: frappe.throw(...) with generic message; specifics in audit log only.

    Generic failure response prevents enumeration of valid/invalid tokens by
    response shape. Specifics (expired/invalid/already-consumed) are written
    to audit log for forensics.
    """
```

Implementation outline:
1. Validate `new_password` against existing password policy in api.py (length, complexity)
2. `token_hash = hash_token(token)`
3. Look up `VECRM Auth Reset Token` by `token_hash`. **MUST use exact match on token_hash, not name** — name is the autoname hash, unrelated.
4. If no row: emit `auth.reset.invalid_token` audit (employee=NULL), throw generic error.
5. If `consumed_at` is not NULL: emit `auth.reset.invalid_token` audit (employee=<phone>), throw generic error.
6. If `expires_at < now()`: emit `auth.reset.expired` audit (employee=<phone>), throw generic error.
7. If `reset_for != "password"`: emit `auth.reset.invalid_token` audit (PIN token used for password reset), throw generic error.
8. Set `consumed_at = now()` on the token row
9. Look up VECRM Employee row, get linked User
10. Update User's password via Frappe's `update_password()` helper (uses bcrypt internally)
11. Clear lockout state: `failed_password_attempts = 0`, `password_locked_until = NULL` on the User custom fields (or wherever lockout is stored — verify against existing api.py)
12. Emit `auth.reset.consumed` audit row with `employee=<phone>`, `path="password"`
13. `frappe.db.commit()` (atomic with token consume + password set + lockout clear)
14. Return success

### §3.4 — `complete_pin_reset(token: str, new_pin: str) -> dict[str, Any]`

Same as §3.3 but:
- Input is `new_pin` (validate format: 4 digits, no repeats per existing policy if any)
- Token's `reset_for` must equal `"pin"`
- Write new PIN to the appropriate hash field (likely `pin_hash` on VECRM Employee — verify against api.py)
- Clear `failed_pin_attempts` and `pin_locked_until`
- Emit `auth.reset.consumed` audit with `path="pin"`

---

## §4 — Module 3: `vecrm/vecrm/doctype/vecrm_auth_reset_token/vecrm_auth_reset_token.py` (extend if needed)

Most likely no changes needed — the controller remains `pass`. All logic is in `api.py`.

**Only extend if:** a Document-lifecycle method (e.g., `validate()`) is needed to enforce that `reset_for` is one of the allowed values, or that `expires_at` is in the future. These are defense-in-depth — the API layer should never write invalid values, but Document-level validation catches manual-edit bugs.

Recommendation: SKIP Document-level validation in this PR. The API layer is the only writer; bench console / desk UI access is locked to System Manager only (per schema permissions). Add validation later only if a real defect demands it.

---

## §5 — Security review checkpoints (executor MUST verify)

Before opening PR, executor verifies each:

- [ ] **No raw token persisted** — search `vecrm/api.py` for any storage of `raw_token` outside the response object. The only persistence is `token_hash`.
- [ ] **Constant-time compare on token lookup** — token hash comparison goes through `hmac.compare_digest` (in our helper or via Frappe's underlying query, which is hash equality).
- [ ] **Single-use enforced** — `consumed_at` check precedes any credential write.
- [ ] **Expiry enforced** — `expires_at < now()` check precedes any credential write.
- [ ] **reset_for discriminator enforced** — password tokens can't be used for PIN reset and vice versa.
- [ ] **No-enumeration response** — `request_*_reset` returns identical shape regardless of match success.
- [ ] **Rate limit applied** — count-based, per-employee, 15-min window.
- [ ] **Audit log emitted on all paths** — request/consume/expired/invalid/rate-limited each have explicit emit.
- [ ] **Lockout cleared on success** — both `failed_*_attempts` and `*_locked_until` reset to defaults.
- [ ] **All 4 methods type-annotated** — Frappe v16 requirement.

---

## §6 — Commit, push, PR

```bash
git add vecrm/api.py vecrm/utils/auth_reset.py
git commit -m "S28 PR #XX: PD-S28-AUTH-RESET-BACKEND-API — token mgmt + credential write

Adds 4 whitelist API methods to vecrm.api:
  - request_password_reset(email) -> creates token, returns raw for portal email
  - request_pin_reset(phone) -> creates token, returns raw for portal email
  - complete_password_reset(token, new_password) -> consumes token, updates password
  - complete_pin_reset(token, new_pin) -> consumes token, updates PIN

Plus pure crypto helpers in vecrm.utils.auth_reset (generate_token, hash_token,
constant_time_equals).

Schema substrate from PR #21. Portal-side email send + Forgot form + accept
pages ship in PD-S28-AUTH-RESET-PORTAL-{BFF,UI,EMAIL-TEMPLATE}.

Security invariants enforced (see code comments):
  - Tokens hashed at rest (sha256)
  - Constant-time hash compare (hmac.compare_digest)
  - Single-use (consumed_at)
  - Time-bounded (30min default)
  - Rate-limited (3 reset requests / employee / 15min)
  - No-enumeration responses
  - Lockout state cleared on successful reset
  - 5 new audit events: auth.reset.{requested,consumed,expired,invalid_token,rate_limited}

All methods type-annotated per Frappe v16 require_type_annotated_api_methods.

Ref: PD-S28-AUTH-RESET-INFRA-recon-findings-ADDENDUM.md (commit 22bf471)"

git push origin feat/s28-auth-reset-backend-api

gh pr create --base main --head feat/s28-auth-reset-backend-api \
  --title "S28 PR #XX: PD-S28-AUTH-RESET-BACKEND-API — token mgmt + credential write" \
  --body "<see commit message above + render security checklist from §5>"
```

---

## §7 — Smoke (after merge + deploy)

No new schema, so no migrate-deploy-cycle needed. Just deploy via PD-S27-DEPLOY-RUNBOOK (build + recreate, no patches to apply).

After deploy:

```bash
# RUN ON VPS — smoke each method end-to-end via curl
# 1. Request password reset (no match → no-enumeration check)
curl -s -X POST https://crm.vinayenterprises.co.in/api/method/vecrm.api.request_password_reset \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=nonexistent@example.com"
# Expected: {"message":{"success":true,"message":"If an account exists..."}}

# 2. Request password reset (real match)
curl -s -X POST https://crm.vinayenterprises.co.in/api/method/vecrm.api.request_password_reset \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=test.salesrep@vinayenterprises.co.in"
# Expected: same success shape

# 3. Check audit log — should see auth.reset.requested rows
docker exec vecrm-backend-1 bash -c '<mysql query SELECT FROM tabVECRM Auth Audit Log ORDER BY creation DESC LIMIT 5>'

# 4. Check tabVECRM Auth Reset Token — should see one row for the real match (not the nonexistent)
docker exec vecrm-backend-1 bash -c '<mysql query SELECT FROM tabVECRM Auth Reset Token>'

# 5. Manually extract raw_token from the response (or audit/log path), then test complete_password_reset
# This is where portal would call complete_password_reset on the user's behalf
```

Full end-to-end (request + receive email + click link + complete) requires portal wiring (PORTAL-BFF + PORTAL-UI + EMAIL-MECHANISM) so won't smoke here. Backend smoke is API-only.

---

## §8 — Effort

| Sub-step | Effort |
|---|---|
| §0-1 branch + file scaffolding | 10 min |
| §2 utils/auth_reset.py | 15 min |
| §3 4 API methods (~50-70 lines each) | 1.5-2 hrs |
| §4 controller (likely no-op) | 0-5 min |
| §5 security checklist verification | 15 min |
| §6 commit + PR | 10 min |
| §7 smoke (operator-run) | 30 min |
| **Total** | **2.5-3 hrs** |

---

## §9 — Layer-transition checkpoints

1. Before file changes: main HEAD is `6d46b0d` (or later) on Mac
2. Before commit: §5 security checklist all checked
3. Before deploy: PR merged, main updated
4. After deploy: §7 smokes all pass

**End of dispatch.**
