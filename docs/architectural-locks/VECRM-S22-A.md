# VECRM-S22-A — Counter allocator: read value INSIDE the locking statement

**Status:** Active (earned S22 §6 hard-gate)
**Earned in:** S22 §6 concurrency hard-gate investigation
**Date:** 2026-05-21

---

## Statement

Any allocator that uses `SELECT ... FOR UPDATE` to serialize access to a counter row MUST read the counter's current value WITHIN THE SAME LOCKING STATEMENT.

Splitting the lock acquisition from the value read across two statements (e.g. `SELECT name FOR UPDATE` followed by a separate `SELECT last_value`) silently breaks gap-free numbering under concurrent load, even though the row lock itself serializes correctly.

## Why it exists

Under MariaDB/InnoDB REPEATABLE-READ isolation (Frappe's default), a non-locking SELECT returns the value as of the transaction's MVCC read view. The read view is established at the FIRST consistent read in the transaction.

In a Frappe controller path, the read view is typically established by some early-lifecycle read (`check_permission`, `_validate_links`, an in-controller `frappe.get_doc("VECRM Employee", ...)`, etc.) — all of which run BEFORE the allocator gets called from `autoname`.

The allocator's `SELECT ... FOR UPDATE` is a locking read — it correctly serializes threads on the row lock and reads the current committed row. But a SUBSEQUENT plain `SELECT last_value WHERE name = %s` is a non-locking read — it returns the transaction's stale snapshot view, not the current committed value.

Under contention, every thread:
1. Acquires the FOR UPDATE row lock (serialized — correct)
2. Reads `last_value` via the plain SELECT (returns stale snapshot — bug)
3. Computes `new_value = stale_last_value + 1` (every thread gets same number)
4. Raw UPDATE succeeds (no version check)
5. Insert of the dependent row fails with DuplicateEntryError because every thread allocated the same number

This is a textbook split lock-and-read antipattern. It was latent in the VECRM voucher allocator from the first commit (a990fa8, sha 7ad2b3a3) until S22 §6 surfaced it.

## How to verify

Inspect any allocator's `next_number`-style function. The locking statement should return both the row identifier AND the value being read:

```sql
SELECT name, last_value
FROM `tabVECRM Voucher Counter`
WHERE counter_key = %s
FOR UPDATE
```

NOT:

```sql
SELECT name FROM `tabVECRM Voucher Counter` WHERE counter_key = %s FOR UPDATE;
-- ... later ...
SELECT last_value FROM `tabVECRM Voucher Counter` WHERE name = %s;
```

The two-statement form is broken under concurrent load even if it works under single-thread testing.

## Diagnostic signature

The bug presents as: under N concurrent inserts, ~1 succeeds and N-1 fail with `DuplicateEntryError 1062`, all colliding on the SAME allocated voucher number. Elapsed time matches what would be expected if threads ARE serializing on the lock (~0.6s for 10 threads), because they ARE serializing — they're just all reading the wrong value during their critical section.

## Banked test

S22 §6 hard-gate test in `vecrm._smoke6.run_all` exercises this pattern. After the fix, 10 concurrent same-FY submits return 10 unique, gap-free sequence numbers. Before the fix, 9/10 fail with DuplicateEntryError.

## Related locks

- **VECRM-L8** — allocator dual-surface sha verification (catches code drift but not behavioral correctness)
- **VECRM-L10** — strict gap-free invariant (this lock describes the IMPLEMENTATION requirement for L10 to actually hold under concurrent load)
