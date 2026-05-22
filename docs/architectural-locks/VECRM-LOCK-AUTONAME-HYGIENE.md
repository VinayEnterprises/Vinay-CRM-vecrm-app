# VECRM-LOCK-AUTONAME-HYGIENE

**Status:** ACTIVE (formal lock)
**Earned:** S23
**Promoted from:** OBS-S23-B
**Governs:** All Frappe doctype JSONs with controller-driven autoname()

---

## Lock statement

For any VECRM doctype with a controller-defined `autoname(self)` method, the doctype JSON's `autoname` field MUST be the empty string `""`. It MUST NOT be `"prompt"`, `"Prompt"`, `"uuid"`, or any other case-variant of these reserved values.

## Rationale

Frappe Framework v16.18.2's `frappe/model/naming.py` at line ~158 performs a case-insensitive check:

```python
if autoname and autoname.lower() in ("prompt", "uuid"):
    # ... skip controller autoname() entirely
    return
```

This means `autoname: "prompt"` OR `autoname: "Prompt"` OR `autoname: "PROMPT"` will SILENTLY BYPASS the controller's `autoname()` method. The document's `name` field will instead be populated from user input (Desk's prompt-mode Name field) or hash fallback. The controller's allocator call never runs. The counter never advances. fy_label and other autoname-side-effects are never set.

## Surfacing evidence (S23)

Travel Voucher, Lead, and Inquiry all shipped pre-S23 with `autoname: "prompt"` or `"Prompt"` paired with controller `autoname()` methods. Result:

- Lead and Inquiry counters at 0 since S18 (controller introduced ~S18); zero rows in `tabVECRM Lead` and `tabVECRM Inquiry` despite the counters existing
- Travel Voucher's first Desk-created voucher in S23 Phase B got named "Test Sales Rep" (the submitter's display name leaked in via prompt-mode); audit row had `fy_label=null`
- Only programmatic paths (e.g. `Lead.convert_to_inquiry`) accidentally bypassed the bug because they leave `self.name` empty, hitting the autoname branch instead of the prompt branch

The bug was silent in production because:
- Frappe doesn't log a warning when prompt-mode bypasses controller autoname
- No exception is raised; document creation succeeds with the wrong name
- Audit rows are still written (just with stale/null snapshot fields)
- Counter rows exist (just with last_value=0)

## Canonical fix

In the doctype JSON:
```json
{
  "autoname": "",
  "naming_rule": ""
}
```

`naming_rule: "Set by user"` was paired with prompt mode on Travel Voucher; it has no semantic meaning when autoname is empty. Cleared for consistency.

If a defensive name-prefix guard is added in the controller (recommended for any doctype with allocator-driven naming), the guard belongs in `validate()`, NOT `before_insert()`. See companion lock VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER.

## Enforcement points

1. **JSON authoring discipline** — When creating a new submittable doctype with a counter-allocated name (e.g. future Expense Reimbursement, Asset Voucher, etc.), the JSON template starts with `autoname: ""`. Never `"prompt"`.

2. **Code review** — Any PR that touches a doctype JSON `autoname` field must explicitly justify a non-empty value if used. Most non-empty values are wrong; valid non-empty values are documented Frappe naming rules like `"field:fieldname"`, `"naming_series:"`, `"hash"`, or `"format:..."`.

3. **§6 hard-gate** — Concurrency tests should verify counter advancement matches the number of vouchers created. If counter stays at 0 while vouchers get unique names from a different source, autoname-prompt bypass is the likely cause (re-check the JSON).

4. **Desk smoke** — OBS-S23-F (manual Desk smoke is not skippable) is the empirical detection mechanism. Programmatic insert tests can't reliably catch this — they don't exercise the prompt-mode Name field path.

## Examples

**WRONG (will silently bypass autoname()):**
```json
{
  "doctype": "DocType",
  "autoname": "prompt",
  "naming_rule": "Set by user"
}
```

**WRONG (case-insensitive — still bypasses):**
```json
{
  "doctype": "DocType",
  "autoname": "Prompt"
}
```

**WRONG (also bypasses via L158 check):**
```json
{
  "doctype": "DocType",
  "autoname": "uuid"
}
```

**RIGHT (allows controller autoname() to run):**
```json
{
  "doctype": "DocType",
  "autoname": "",
  "naming_rule": ""
}
```

**ALSO RIGHT (when controller-driven naming isn't needed, use Frappe's built-in patterns):**
```json
{
  "doctype": "DocType",
  "autoname": "field:vecrm_phone"
}
```
(For VECRM Employee — name = phone, no controller logic needed; uses Frappe's built-in field-reference pattern.)

```json
{
  "doctype": "DocType",
  "autoname": "hash"
}
```
(For VECRM Voucher Audit Log — opaque hash ids, no controller logic; Frappe's built-in hash pattern.)

## Related locks

- **VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER** — Name guards in validate() not before_insert() (same surfacing session)
- **VECRM-L8** — Allocator anchor sha (the autoname() method that this lock protects from being skipped)

## Verification

Quick check for any VECRM doctype:

```bash
# In container
docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.get_meta" --kwargs '{"doctype": "VECRM <Doctype Name>"}' 2>&1 | grep autoname
```

Expected: `autoname=''` (or `autoname=None`).

If the result is `autoname='prompt'` or any case variant, the doctype is broken — Desk-driven creation will silently fail to advance counters or run autoname-side-effects.

---

**End of VECRM-LOCK-AUTONAME-HYGIENE**
