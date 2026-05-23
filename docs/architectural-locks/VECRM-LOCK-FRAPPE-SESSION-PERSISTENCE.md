# VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE

**Earned:** S25 (Phase 4.6, OBS-S25-AL)
**Status:** ACTIVE
**Severity:** Critical (silent session-data loss)

## Statement

Custom session-data writes in VECRM API endpoints MUST mutate `frappe.session.data.*` directly AND persist the change via `frappe.local.session_obj.update(force=True)`.

NEVER use `frappe.cache.hset("session", sid, ...)` directly to write session data. The cache slot stores the OUTER `{user, sid, data}` shape; manual hset of inner-payload shape poisons the slot and breaks `Session.resume()` on subsequent requests.

`force=True` is required: Session.update()'s default time-threshold gate no-ops on a fresh session where `last_updated` was just set by `Session.start()`.

## Pattern (correct)

```python
def _issue_session(employee_doc):
    frappe.local.login_manager.login_as(_VECRM_PORTAL_USER)
    # Mutate the inner payload directly:
    frappe.session.data.vecrm_employee_phone = employee_doc.vecrm_phone
    frappe.session.data.vecrm_employee_name = employee_doc.employee_name
    frappe.session.data.vecrm_employee_role = employee_doc.role
    frappe.session.data.vecrm_login_path = "password"
    # Persist via Frappe's canonical Session.update — force=True bypasses
    # the time-threshold gate that no-ops on fresh sessions.
    frappe.local.session_obj.update(force=True)
```

## Anti-pattern (WRONG — this caused OBS-S25-AL)

```python
def _issue_session(employee_doc):
    frappe.local.login_manager.login_as(_VECRM_PORTAL_USER)
    frappe.session.data.vecrm_employee_phone = employee_doc.vecrm_phone
    # ❌ WRONG: writes inner payload into outer-shape slot
    frappe.cache.hset("session", frappe.session.sid, frappe.session.data)
```

## Mechanism (verified via Frappe v16.18.2 source-read in S25 Phase 4.6 probe)

- `Session.__init__`: assigns `frappe.local.session = self.data` (the dict, not the Session instance)
- `Session.update(force=False)`: persists `self.data["data"]` (inner payload) to `Sessions.sessiondata` DB column AND caches `self.data` (outer `{user, sid, data}`) via `frappe.cache.hset("session", sid, self.data)`
- `Session.insert_session_record()`: same — caches `self.data` (outer)
- `Session.resume()`: loads from cache slot expecting outer shape; if poisoned with inner shape, the load fails silently and session data is lost

## Why force=True

`Session.update()`'s default behavior:

```python
threshold = min(get_expiry_in_seconds() / 2, 600) or 600
if (force or (time_diff is None) or (time_diff > threshold) or self._update_in_cache):
    # persist...
```

On a fresh session (just started via `login_as`), `last_updated` was milliseconds ago, so `time_diff` is well under the threshold (10 minutes). Without `force=True`, the persist is skipped — meaning the custom keys we just added stay only in memory and never reach the DB/cache.

## Handle availability

`frappe.local.session_obj` exists during HTTP request contexts. It does NOT exist in `bench console` (where `frappe.local.session` is None or just the data dict, not the Session instance). Any probe testing session persistence must run via HTTP (Frappe `requests`-based test or curl), not console.

## Where this is enforced

- `vecrm/api.py::_issue_session` (Phase 4.6 fix)
- Any future custom auth endpoint that issues sessions

## Related observations

- OBS-S25-AL — the root cause (manual cache.hset poison)
- OBS-S25-AH — earlier-iteration workaround that was reverted in Phase 4.7
- OBS-S25-AM — dispatcher state-tracking failure on the 4.6 source-read

## Notes

This lock is Frappe-version-specific. If Frappe upgrades and the Session class internals change, re-verify via source-read before assuming this pattern still holds.
