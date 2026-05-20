# VECRM-S20-D — Compare to known-working reference in same image: the most reliable Frappe debugging move

**Status:** Active
**Earned in:** S20 Phase 6 (C2-a HTTP 403 diagnostic)
**Date:** 2026-05-20

---

## Context

When the C2-a smoke returned `HTTP 403 PermissionError "Function ... is not whitelisted"`, the initial diagnostic posture was hypothesis-driven: read the error text, propose causes (hooks.py needs api_methods registration; decorator wrong; whitelist registry stale), test each hypothesis. This produced no progress for some time. The decorator was correctly applied; api_methods registration was not actually required in Frappe v16; the whitelist registry showed nothing anomalous.

The diagnostic move that solved the problem in minutes: find a working whitelisted API method elsewhere on the same site image, read it, compare pattern. `apps/crm/crm/api/contact.py` was the chosen reference (CRM app, same image, same site, same Frappe version, known-good behavior). Comparison immediately surfaced the structural difference: working method had type annotations on parameters and return value; failing method had bare params. From there, finding `require_type_annotated_api_methods = True` in `crm/hooks.py` took one grep.

## Decision

When Frappe behavior is unclear or unexpected, the first diagnostic move is to find a known-working reference in the same image/site and compare patterns. Pattern comparison beats hypothesis-driven debugging on Frappe behavior questions because Frappe's behavior is largely emergent from many configuration knobs (hooks, fixtures, custom fields, role permissions, doctype-level controls) — and a working reference embodies all of them implicitly, while a hypothesis embodies one explicitly.

Concretely:

1. When a Frappe behavior fails or behaves unexpectedly, before generating hypotheses, identify a working counterpart that does the equivalent thing successfully in the same image/site.
2. Read the working counterpart's source. Compare structurally (signatures, decorators, type annotations, return shapes) and contextually (which app, which directory, which doctype category).
3. Run pattern diff against the failing code. Identify the differences.
4. Test the smallest delta-elimination first (e.g. add type annotations) before more speculative changes (e.g. modify hooks.py).

This applies to: API method behavior, doctype controller behavior, role/permission behavior, fixture loading, scheduler events, background job dispatch, hooks.py effects.

## Operational implications

- Bench-installed apps are themselves a body of working reference code. `apps/crm/`, `apps/helpdesk/`, `apps/erpnext/` (when installed), `apps/frappe/` core all provide reference implementations to compare against.
- The reference and the failing code must be in the same image/site to control for environment differences. A working reference in a different bench is not equivalent — different installed apps, different hooks.py, different fixture state.
- The pattern-comparison move is fast: typically 5-15 minutes from "stuck on hypotheses" to "found the structural difference". If pattern comparison itself doesn't surface a difference within ~15 minutes, that's a signal the issue is not structural — pivot to environment (cache, build, container state) or fixture/data state.
- When writing dispatch artifacts for new Frappe code, include the reference implementation explicitly: "match the pattern of `apps/X/X/Y.py::function_name` which is known-working on this site." This pre-empts the pattern-match-failure class of bugs.

## Reversal conditions

Not reversible in any meaningful sense — pattern comparison against known-working references is a debugging technique, not a constraint. The lock formalizes the priority ("first move, not last resort") rather than introducing the technique itself.

If future Frappe versions introduce strong type-checking or schema enforcement that surfaces these issues at compile/load time rather than at request time, the technique becomes less load-bearing but remains valid.

## Relationships

- **VECRM-S20-C** (cross-app hooks affect site-wide enforcement) — sibling lock. S20-C is the principle (hooks are site-wide); S20-D is the debugging technique that exposes when site-wide hooks are biting. The two locks earned in the same incident.
- **VECRM-S19-F** (verify against source not prose) — S20-D applies S19-F to debugging specifically: when stuck, read the source of a working analog, not the documentation describing how it should work.

## Verification

S20 Phase 6 diagnostic — pattern comparison with `apps/crm/crm/api/contact.py` surfaced the type-annotation requirement in minutes after hypothesis-driven debugging had been spinning. Fix (PR #6) verified GREEN at Phase 8 C2 smoke.
