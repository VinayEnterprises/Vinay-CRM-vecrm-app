# VECRM-LOCK-NEXTJS-NAME-PARAM-DECODE

**Status:** ACTIVE
**Earned in:** S24 (DISPATCH-S24-A2 Phase 5 smoke + DISPATCH-S24-B1 extended scope)
**Related OBS:** OBS-S24-L, OBS-S24-N, OBS-S24-P
**Affects:** Every `app/<resource>/[name]/...` and `app/api/<resource>/[name]/...` route in `vecrm-portal`

---

## Statement

Next.js `[name]` dynamic-segment route parameters arrive **URL-encoded by default**. Next.js does NOT decode `%2F` substrings in the `name` param because decoded slashes would change the route's segment structure. Any downstream code that calls `encodeURIComponent` on the already-encoded param value produces double-encoded URLs (`%2F` → `%252F`) that downstream systems (Frappe, custom backends) correctly reject as 404.

**Required pattern:** decode at entry, immediately after `use(params)` (client component) or `await params` (server route handler).

```typescript
// Client component:
const { name: rawName } = use(params);
const name = decodeURIComponent(rawName);

// Server route handler:
const { name: rawName } = await params;
const name = decodeURIComponent(rawName);
```

All downstream code uses `name` (the decoded value). Existing `encodeURIComponent(name)` calls for outbound URL construction then produce correct single-encoded URLs.

---

## Empirical proof (S24 Phase 5 smoke)

```javascript
encodeURIComponent("%2F") === "%252F"  // true, deterministic
```

The Phase 5 smoke's DevTools showed a failing request URL of `/api/travel-vouchers/VE%252FTV%252F00094%252F26-27`. The detail page's fetch was `fetch(/api/travel-vouchers/${encodeURIComponent(name)})`. For the output to contain `%252F`, the input `name` must have already contained `%2F` substrings. Therefore `params.name` arrived URL-encoded.

This holds regardless of context (client `use(params)` or server `await params`) and regardless of Next.js version (verified on 16.2.6).

---

## Round-1 fix that did NOT work (history for learning)

The first fix attempt (commit `8f623ff` on the Sub-A portal branch) prescribed: "raw space in doctype path segment `VECRM Travel Voucher` triggers a URL-parser re-encode pass; encode the doctype segment too." This addressed one encoding-related concern but NOT the actual root cause (which is the `params.name` value being encoded).

Re-smoke after `8f623ff` STILL produced double-encoded URLs. The doctype-encoding patch landed; the symptom persisted.

**The lesson** (OBS-S24-L updated reading): "working precedent" must mean "verified-against-input-shape," not "exists and is deployed." Both `leads/[name]` and `app/api/leads/[name]/route.ts` looked like working precedents because they shipped in S23 — but they had never been exercised on slash-format names (which only existed post-S23 PR #11 autoname). Both carried the identical latent bug.

---

## Affected surfaces (S24 close)

| Route | Decode-at-entry? | Earned via |
|---|---|---|
| `app/travel-vouchers/[name]/page.tsx` | ✅ | S24 PR #5 commit `f65f184` |
| `app/api/travel-vouchers/[name]/route.ts` | ✅ | S24 PR #5 commit `f65f184` |
| `app/api/travel-vouchers/[name]/submit/route.ts` | ✅ | S24 PR #5 commit `f65f184` |
| `app/leads/[name]/page.tsx` | ✅ | S24 PR #6 commit `db0d3a0` |
| `app/api/leads/[name]/route.ts` | ✅ | S24 PR #6 commit `db0d3a0` |
| `app/api/leads/[name]/convert/route.ts` | ✅ | S24 PR #6 commit `db0d3a0` |
| `app/inquiries/[name]/page.tsx` | ✅ | S24 PR #6 commit `acced72` |
| `app/api/inquiries/[name]/route.ts` | ✅ | S24 PR #6 commit `acced72` |

Future routes (`expense-vouchers/[name]`, `approver/queue/[name]` if applicable, etc.) MUST adopt this pattern at first commit, not retroactively after a 404 surfaces in smoke.

---

## Why `decodeURIComponent` is safe (idempotency)

Voucher and slash-format entity names contain no literal `%` characters. Therefore:

- If Next.js delivers the param URL-encoded (current behavior): `decodeURIComponent("VE%2FTV%2F00094%2F26-27")` → `"VE/TV/00094/26-27"` (correct).
- If Next.js ever changes to deliver the param URL-decoded (future): `decodeURIComponent("VE/TV/00094/26-27")` → `"VE/TV/00094/26-27"` (unchanged; no-op).

The pattern is robust across Next.js version changes.

---

## Required testing for new [name] routes

Smoke flow that exercises the bug class:

1. Create or use an existing entity with slash-format name (e.g., `VE/<TYPE>/00001/26-27`)
2. Navigate to `localhost:3000/<resource>/VE%2F<TYPE>%2F00001%2F26-27` in browser
3. Open DevTools → Network tab
4. Confirm the BFF request URL shows single-encoded `%2F`, NOT double-encoded `%252F`
5. Confirm the page renders correctly, NOT a 404

A curl-driven test of the BFF route alone is NOT sufficient — the bug manifests through Next.js's `params` decoding behavior, which `curl` does not exercise.

---

## Related discipline

This lock pairs with:

- **OBS-S22-B** — handover prose must be re-verified at session-open (this lock's existence is the literal embodiment of that principle for `[name]` routes)
- **VECRM-L13** — squash-merge + branch delete (the S24 PRs that earned this lock all followed L13)
- **`docs/portal-conventions.md` Section 1** — codifies this pattern as the portal-wide resource-route shape

---

## Versioning

Banked at S24 close. Review at S25 close: confirm any new `[name]` routes added in S25 (e.g., from Sub-B Expense Voucher portal, or Approver portal) carry the pattern from first commit.

If Next.js's `params` decoding behavior changes in a future version, update this lock to reflect the new contract while preserving the idempotent-decode pattern.
