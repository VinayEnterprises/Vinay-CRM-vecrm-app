# VECRM-S20-C — Cross-app hooks affect site-wide enforcement; check ALL installed apps when adding API surfaces

**Status:** Active
**Earned in:** S20 Phase 6 (C2-a HTTP 403 incident; resolved in PR #6)
**Date:** 2026-05-20

---

## Context

S20 added a new whitelisted API method to vecrm: `vecrm.api.convert_lead_to_inquiry`. The original C1 dispatch matched the style of `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.py` — doctype controller methods with no type annotations. First authenticated smoke (C2-a) returned `HTTP 403 PermissionError "Function ... is not whitelisted"` despite the `@frappe.whitelist()` decorator being correctly applied.

Diagnostic recon compared the failing method to a working reference (`apps/crm/crm/api/contact.py`) and surfaced the cause: `apps/crm/crm/hooks.py` sets `require_type_annotated_api_methods = True`. This is a Frappe v16 site-wide enforcement rule — it applies to all whitelisted API methods on the site, regardless of which app they live in. The misleading error text ("not whitelisted") conflated three distinct failure modes: auth failure, decorator-registration failure, and type-annotation-enforcement failure.

The fix (PR #6) added type annotations to all five parameters and the return type. The "match existing style" heuristic from C1 had failed because the reference (`vecrm_lead.py`) is a doctype controller — not subject to the API-method enforcement — while the new code was a whitelisted API method — subject to it.

## Decision

When introducing a new API surface in any Frappe app on a multi-app site, check ALL installed apps' `hooks.py` files for site-wide enforcement rules before drafting. Site-wide hooks set by any app apply to all apps on the site. "Match existing style" is unsafe across Frappe category boundaries — doctype controllers, API methods, server scripts, and background jobs each have different applicable rules.

Concretely, before adding a new `@frappe.whitelist()` function in vecrm or any other app on the crm.vinayenterprises.co.in site:

1. Enumerate all installed apps: `bench --site <site> list-apps`
2. For each app, read `apps/<app>/<app>/hooks.py` and identify any `require_*`, `default_*`, or `*_validators` settings that apply site-wide
3. Confirm the new code's Frappe category (API method, doctype controller, server script, background job) and match it against rules applicable to that category specifically
4. Use a known-working reference from the same Frappe category in the same image as the style precedent (per VECRM-S20-D)

## Operational implications

- New API methods on this site must include type annotations on all parameters and return value (enforced by `crm/hooks.py::require_type_annotated_api_methods = True`).
- The HTTP 403 error text "Function ... is not whitelisted" is misleading on this site. Authenticated retries are required to surface the real failure mode before hypothesizing. Token-auth via API key + secret is the canonical retry pattern.
- Future app installs on this site (e.g. ERPNext, HR, Payments) must include a hooks.py audit step at install gate. New `require_*` rules from a newly-installed app could break working code in already-installed apps without modifying that code.
- Dispatch artifacts for new API surfaces should include the hooks.py audit as an explicit pre-flight step, not assume the absence of site-wide enforcement.

## Reversal conditions

This lock is irreversible in the literal sense — Frappe's design intentionally makes hooks.py settings site-wide. The lock is the discipline of accounting for this; it cannot be relaxed without inviting recurrence of the C2-a incident.

If future Frappe versions remove or change the `require_type_annotated_api_methods` enforcement, the specific operational implication around type annotations would change, but the underlying principle (check all apps' hooks at API-surface introduction) remains.

## Relationships

- **VECRM-S20-D** (compare to known-working reference in same image) — the diagnostic move that surfaced this lock. The two locks are complementary: S20-C is the principle, S20-D is the debugging technique that proves it.
- **VECRM-S19-F** (verify against source not handover prose) — the C1 dispatch's "DO NOT add type hints — match unannotated style of vecrm_lead.py" was a prose-derived instruction that did not account for hooks.py reality. S19-F would have caught it at draft time.

## Verification

S20 Phase 6 surfaced the issue; Phase 7 (PR #6, commit `66118d7`) fixed it with type annotations. C2 smoke verified GREEN at Phase 8 (HTTP 404 `DoesNotExistError` on bad lead_name — proves end-to-end whitelist + type-validation + function-body execution).
