# VECRM-LOCK-FRAPPE-FILTER-PATTERNS

### Purpose
Lock document. Canonical reference for Frappe v15 filter syntax in VECRM. Consult before writing any new filtered query.

### Filter shapes

**a. Equality**
- Python: `["status", "=", "Open"]`
- REST JSON: `["status", "=", "Open"]`

**b. Inequality**
- Python: `["status", "!=", "Draft"]`
- REST JSON: `["status", "!=", "Draft"]`

**c. Like with wildcard**
- Python: `["company_name", "like", "%value%"]`
- REST JSON: `["company_name", "like", "%value%"]`
- *Gotcha:* Frappe uses `%` for wildcards, not `*`.

**d. In list**
- Python: `["status", "in", ["Draft", "Pending"]]`
- REST JSON: `["status", "in", ["Draft", "Pending"]]`

**e. Not in list**
- Python: `["status", "not in", ["Converted", "Closed-Won", "Closed-Lost"]]`
- REST JSON: `["status", "not in", ["Converted", "Closed-Won", "Closed-Lost"]]`
- *Usage:* Common in lead scoping (see `app/api/leads/route.ts`).

**f. Between (dates)**
- Python: `["next_followup_date", "between", ["2026-01-01", "2026-01-31"]]`
- REST JSON: `["next_followup_date", "between", ["2026-01-01", "2026-01-31"]]`
- *Gotcha:* Always pass exactly two elements in the array. Inclusive bounds.

**g. Greater/less than**
- Python: `["next_followup_date", "<", "2026-05-30"]`
- REST JSON: `["next_followup_date", "<", "2026-05-30"]`

**h. Is set (not null)**
- Python: `["next_followup_date", "is", "set"]`
- REST JSON: `["next_followup_date", "is", "set"]`

**i. Is not set (null)**
- Python: `["next_followup_date", "is", "not set"]`
- REST JSON: `["next_followup_date", "is", "not set"]`

### Nullable date gotcha
Frappe treats empty date fields as `None` in Python but stores them as `0000-00-00` or `NULL` at the DB layer. Filtering with `between` or `<`, `>` on a nullable date field can silently include or exclude rows with no date. 
**Lock:** Always pair date range filters with an explicit `is set` check if the field is optional (e.g., `["next_followup_date", "is", "set"]`).

### OBS-S34-A: Frappe v16 aggregate syntax change
**Forward-compat risk:** In Frappe v15, `frappe.db.count("DocType", filters={...})` works, as used currently in `vecrm/api.py`.
However, Frappe v16 overhauls ORM aggregate syntax. Passing kwargs to count/sum methods may break or change shape. Be aware of this migration risk when updating Frappe versions.

### or_filters
If you use `or_filters`, all conditions inside `or_filters` are joined with `OR`, but the resulting clause is joined with `AND` to the main `filters` list.
- Python:
  ```python
  frappe.get_all("Lead",
      filters=[["status", "=", "Open"]],
      or_filters=[["territory", "=", "North"], ["territory", "=", "South"]]
  )
  ```
- Resulting logic: `(status = 'Open') AND (territory = 'North' OR territory = 'South')`.
