# VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY

**Earned:** S28 (PR #14 PORTAL-UI; audited + cited as PASS basis in PR #25 §1.13)
**Status:** ACTIVE
**Severity:** High (auth-trust boundary defect potential)

## Statement

Public-auth paths (paths a logged-out portal user must reach without being short-circuited to LoginForm) MUST be declared as a hardcoded `string[]` at module top-level, with an explicit `Array.includes(pathname)` membership check in the boundary component. NOT `startsWith`. NOT regex. NOT computed from any other source.

## Rule

| Declaration form | Allowed? |
|---|---|
| `const PUBLIC_AUTH_PATHS = ["/set-password", "/set-pin"];` + `.includes(pathname)` | ✅ Required form |
| `PUBLIC_AUTH_PATHS.some(p => pathname.startsWith(p))` | ❌ Forbidden — scoping bug surface |
| `/^\/set-(password|pin)/.test(pathname)` | ❌ Forbidden — regex makes review harder |
| `PUBLIC_AUTH_PATHS` imported from a remote config / env var | ❌ Forbidden — defeats compile-time auditability |
| `PUBLIC_AUTH_PATHS` derived from a route-collection introspection | ❌ Forbidden — same as above |
| Trailing slash, query strings, or hash fragments in path values | ❌ Forbidden — `usePathname()` returns the canonical pathname, no trailing slash |

## Why permanent

Public-auth paths sit on the auth-trust boundary — the difference between "renders the login screen" and "renders an unauthenticated page that can mutate credentials." The `includes()` check makes the membership decision auditable in one glance:

```tsx
const PUBLIC_AUTH_PATHS = ["/set-password", "/set-pin"];

if (!user) {
  if (PUBLIC_AUTH_PATHS.includes(pathname)) {
    return <>{children}</>;  // unauthenticated page rendered as-is
  }
  return <LoginForm onLogin={login} />;  // everything else short-circuits to login
}
```

`startsWith` and regex introduce subtle scoping bugs:

- `pathname.startsWith("/set-password")` matches `/set-password-evil`, `/set-password/anything`, `/set-passwordattack`. Any of these could be a real route added later (intentionally or by mistake) that inherits the public-auth bypass.
- Regex compiled at module load means the *intent* of which paths are public lives in pattern syntax rather than literal strings. Reviewing whether a new path is correctly public/private requires regex-evaluating in your head — slower and error-prone.

The hardcoded array + `includes()` forces every public-auth path to appear by exact string in source, where:
- A `grep -r PUBLIC_AUTH_PATHS` shows every declaration site
- A `grep -r "set-password"` finds all references to the literal path
- Code review can verify the exact set in one glance

## Pattern (correct)

```tsx
// app/components/AppShell.tsx (or equivalent boundary component)
"use client";

import { usePathname } from "next/navigation";

// Paths that must render to a LOGGED-OUT user (not get short-circuited
// to the LoginForm). The password/PIN reset accept pages are the only
// such surfaces: by definition the user clicking a reset link in their
// email is not logged in. Hardcoded list — explicit includes() check
// (not startsWith, not regex) keeps the security boundary auditable.
const PUBLIC_AUTH_PATHS = ["/set-password", "/set-pin"];

export default function AppShell({ user, children }) {
  const pathname = usePathname();
  if (!user) {
    if (PUBLIC_AUTH_PATHS.includes(pathname)) {
      return <>{children}</>;
    }
    return <LoginForm onLogin={login} />;
  }
  // ... authenticated render path
}
```

## Anti-pattern (WRONG — would invalidate the auth-trust audit)

```tsx
// ❌ startsWith: matches /set-password-evil, /set-passwordattack, etc.
if (PUBLIC_AUTH_PATHS.some(p => pathname.startsWith(p))) {

// ❌ regex: harder to audit
if (/^\/set-(password|pin)$/.test(pathname)) {

// ❌ remote config: defeats compile-time auditability
const PUBLIC_AUTH_PATHS = await loadPublicPathsFromAPI();
```

## Application sites (S28 close)

- `vecrm-portal/app/components/AppShell.tsx:24` — the only current application; introduced PR #14, audited PR #25 §1.13.

## Audit basis

PR #25 audit (PD-S28-AUTH-RESET-SECURITY-REVIEW) §1.13 cited this pattern explicitly as the basis for its PASS verdict:

> AppShell `PUBLIC_AUTH_PATHS` whitelist is hardcoded + `includes()` (not startsWith/regex) — ✅ PASS — `vecrm-portal/app/components/AppShell.tsx:24` — `const PUBLIC_AUTH_PATHS = ["/set-password", "/set-pin"];` followed by `PUBLIC_AUTH_PATHS.includes(pathname)` check. Exact spec compliance. No other route in `app/` bypasses the user-required boundary (verified by grep of `usePathname` users — only TopBar + MobileNav, both nav-only, not auth-gating).

## Adding a new public-auth path

When a new public-auth route is genuinely needed (e.g. a future "/email-verify" flow):

1. Add the literal path string to `PUBLIC_AUTH_PATHS` in `AppShell.tsx`
2. The PR adding the path MUST include a security note in the commit message explaining why this new path is safe to render to unauthenticated users
3. The PR MUST be reviewed by the operator (not just merged by Claude Code) — adding a public-auth path is an auth-trust-boundary change
4. The next session's security audit (or a one-off mini-audit) should verify the new path doesn't unintentionally enable an attack vector

## When this lock can be relaxed

NEVER for the auth-trust boundary in AppShell or any equivalent root-level component. If a future architecture moves the auth-gate to a different layer (e.g., Next.js middleware, an edge function), the lock applies at that new layer with the same form.

## Related observations / locks

- VECRM-LOCK-PORTAL-SHARED-PRINCIPAL (S27) — establishes that auth principal is the shared portal user; this lock governs which paths bypass that gate
- VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE (pre-S27) — adding a public-auth path is a verification-gated change; this lock specifies the *form* of the gate
- PD-S28-AUTH-RESET-SECURITY-REVIEW (PR #25) — audit basis

## Application to non-VECRM contexts

The pattern generalises: any auth-trust boundary in a Next.js / React Router / similar SPA framework should use the same hardcoded-array + `.includes()` form for public-path whitelists. Vemio's dashboard does not currently have a public-path whitelist (no equivalent flows) but should adopt this lock if it grows one.
