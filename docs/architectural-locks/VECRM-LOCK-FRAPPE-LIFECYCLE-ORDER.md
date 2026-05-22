# VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER

**Status:** ACTIVE (formal lock)
**Earned:** S23
**Promoted from:** OBS-S23-C
**Governs:** Placement of defensive name-related guards in Frappe doctype controllers

---

## Lock statement

Defensive name-related validation guards (prefix-pattern checks, allocator-required checks, naming-rule enforcement) MUST be placed in the controller's `validate(self)` method, NOT in `before_insert(self)`.

This is because Frappe Framework v16.18.2 runs `before_insert` BEFORE `set_new_name`, meaning `self.name` is `None` at `before_insert` time. A name guard placed in `before_insert` will fire on every insert with `self.name=None`, blocking all document creation.

## Frappe v16.18.2 insert lifecycle (cited from source)

`frappe/model/document.py`, `_insert()` method (paraphrased order):

```
L441: run_method("before_insert")        ← self.name is None HERE
L442: set_new_name(self)                  ← triggers autoname() if defined; sets self.name
L447: run_before_save_methods()           ← calls validate() and before_save(); self.name is set
L458: db_insert()                         ← row goes to database
```

Key insight: `set_new_name` runs AFTER `before_insert`. The framework gives `before_insert` access to a not-yet-named document so the controller can mutate fields that should be frozen at create (snapshots, lookups). But `self.name` doesn't exist yet.

`validate()` runs via `run_before_save_methods()` AFTER `set_new_name`, so `self.name` is populated and guard-checkable.

## Rationale

Why this is non-obvious:

- Frappe's docs don't explicitly state the order
- The names "before_insert" and "validate" sound like before_insert runs earlier in a way that suggests "earlier in the document's life" — and it does, but it runs BEFORE the name is allocated
- An intuitive (incorrect) assumption is that autoname() runs FIRST (because it produces the name), THEN before_insert runs (because the document is "about to be inserted"), THEN validate runs (final pre-DB check). Source disproves this.

## Surfacing evidence (S23)

S23 PR #11 Phase A.5 initially placed defensive name-prefix guards in `before_insert`:

```python
def before_insert(self) -> None:
    # WRONG — self.name is None here
    if not self.name or not self.name.startswith("VE/TV/"):
        frappe.throw(...)
```

Phase B Desk smoke immediately falsified this — the guard fired on EVERY insert with `self.name=None`, blocking all document creation across Travel Voucher, Lead, and Inquiry simultaneously.

Claude Code (under OBS-S22-F escalation discipline — 4th miss threshold triggers parallel-recon) read `frappe/model/document.py` in full, identified the order, and corrected the guard placement to validate(). PR #11 Phase A.5.11 (the "guard relocation" sub-phase) deployed the fix and Phase B re-ran clean.

## Canonical fix pattern

For doctypes with controller-driven naming:

```python
def autoname(self) -> None:
    """Allocate name via voucher_counter or similar.
    
    Sets self.name. Called by Frappe at insert time after before_insert.
    """
    # ... allocator logic
    self.name = f"VE/<PREFIX>/####/FY"

def before_insert(self) -> None:
    """Snapshot fields. self.name is NOT yet set here.
    
    Per VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER: Frappe v16.18.2 runs this
    BEFORE set_new_name (document.py L441 < L442). Do NOT place
    name-related guards here.
    """
    # ... snapshot logic (submitter_role, base_city, etc.)

def validate(self) -> None:
    """Validation pipeline. self.name IS set here.
    
    1. Defensive name guard (PD-S23-AUTONAME-HYGIENE) — name MUST be
       canonical VE/<PREFIX>/####/FY format, set by autoname(). validate()
       runs via run_before_save_methods (document.py L447) AFTER
       set_new_name has populated self.name, and runs on every save
       thereafter — so a non-canonical name from any source (hash
       fallback, future rename attempt) is caught here.
    """
    if not self.name or not self.name.startswith("VE/<PREFIX>/"):
        frappe.throw(
            f"VECRM <Doctype> name must be allocated via voucher_counter "
            f"(VE/<PREFIX>/####/FY format). Got: {self.name!r}. "
            f"Do not pre-populate name; let autoname() handle allocation.",
            frappe.ValidationError,
        )
    # ... other validations
```

Every controller in VECRM that follows this pattern includes the comment block citing `document.py L441 < L442` for future-reader recognition.

## Why placing in validate() ALSO catches edit-path bypass attempts

`validate()` runs on every save (insert + every subsequent update). This means the guard catches not just initial allocation bypass attempts but also:

- Future code paths that try to rename a document via `db_set` or similar
- Hash-fallback names that slip through some other Frappe path
- Schema migrations that touch the `name` column directly

A `before_insert`-placed guard would only fire on initial creation. validate-placed guards provide defense-in-depth.

## Enforcement points

1. **Controller authoring** — When writing a new controller for a counter-allocated doctype, name guards go in `validate()`. Include the comment block citing document.py L441/L442.

2. **Code review** — Any PR with a name guard in `before_insert` is flagged for relocation. Reviewer comment: "Per VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER, name guards must be in validate() not before_insert(). self.name is None at before_insert time."

3. **AST grep** — Pre-commit (or future CI) can grep for `self.name` references inside `def before_insert` blocks and flag them for review.

4. **Phase B Desk smoke** — Manual create in Desk catches before_insert-placed guards within seconds (the guard fires with self.name=None on every insert attempt). See OBS-S23-F (Desk smoke is not skippable).

## Examples

**WRONG (S23 initial design, falsified):**
```python
def before_insert(self):
    if not self.name or not self.name.startswith("VE/TV/"):
        frappe.throw(...)  # ALWAYS FIRES — self.name is None here
```

**RIGHT (S23 corrected design):**
```python
def before_insert(self):
    # Snapshot logic only; no name-related checks
    self.submitter_role = frappe.get_doc("VECRM Employee", self.submitter).role

def validate(self):
    # Defensive name guard with full lifecycle citation
    if not self.name or not self.name.startswith("VE/TV/"):
        frappe.throw(...)
    # ... other validations
```

## Related locks

- **VECRM-LOCK-AUTONAME-HYGIENE** — autoname='' is the only safe JSON value (same surfacing session)
- **VECRM-L8** — Allocator anchor sha (defines the autoname() method whose output the validate guard checks)

## Verification

For an existing controller, verify guard placement:

```bash
# Grep for self.name references in before_insert
grep -A 20 "def before_insert" vecrm/vecrm/doctype/<doctype>/<doctype>.py | grep "self\.name"
```

Expected output: nothing (no self.name references in before_insert).

If self.name appears inside before_insert in any context other than reading it for logging (which won't be useful since it's None), investigate.

---

**End of VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER**
