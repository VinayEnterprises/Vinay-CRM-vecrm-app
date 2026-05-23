# VECRM-LOCK-FILE-DELIVERY-NOT-PASTE

**Earned:** S25 (mid-session structural fix, OBS-S25-AP after AM/AN/AO recurrences)
**Status:** ACTIVE
**Severity:** High (cross-turn workflow defect)

## Statement

Source artifacts > ~30 lines (Python modules, JSON files, SQL schemas, config files, shell scripts) MUST be delivered to the executor (Claude Code, operator) via `present_files` (file download) — NEVER via inline chat code blocks.

Paste fidelity for large source through chat is unreliable. Markdown rendering, heredoc transformations, quote escaping, and copy-paste truncation produce silent corruption. The corruption may not even be visible — a file may py_compile successfully because the wrong content happens to be syntactically valid Python.

## Rule

| Artifact size | Delivery mechanism |
|---|---|
| ≤ 30 lines | Inline code block in chat is acceptable |
| > 30 lines | `present_files` only; recipient downloads the file |
| Any size | Files containing secrets/passwords: ALWAYS `present_files` |
| Any size | Migration patches: ALWAYS `present_files` |

## Pattern (correct)

Dispatcher in chat:

> Here is the Phase 4.7 migration patch.

```
[dispatcher writes to /mnt/user-data/outputs/<file>.py]
[dispatcher calls present_files with the path]
```

Operator: clicks Download, moves file into the right location in the repo.

Executor: reads from disk via `view` or `cat`, applies as-is.

## Anti-pattern (WRONG — this caused OBS-S25-AM/AN/AO)

Dispatcher in chat:

> Here is the Phase 4.7 migration patch:
>
> ```python
> """Docstring..."""
> import frappe
> # ... 50 lines of code ...
> def execute() -> None:
>     ...
> ```

The chat-rendered code block may:
- Get truncated by chat-display limits
- Have markdown autoformatting strip blank lines or normalize whitespace
- Have triple-quote conflicts with surrounding markdown
- Be partially scrolled off-screen when the operator copies the visible portion
- Be misread by the recipient as part of a different code block in the same reply

Empirical S25 result: FOUR iterations of "the patch source is wrong" before the dispatcher switched to file delivery.

## Why this is structural, not behavioral

"Just be more careful with copy-paste" is the kind of advice that doesn't survive contact with a 14-hour session, 47 OBS observations, and tired operators. File delivery is a mechanical rule that doesn't require vigilance to follow.

The pattern is identical to VECRM-LOCK-VPS-DESTRUCTIVE-OPS: don't trust ad-hoc command construction for destructive ops; require dispatcher authorization. Same logic: don't trust copy-paste fidelity for source artifacts; require file delivery.

## What "delivery" looks like in practice

Dispatcher's responsibility:
1. Write source to `/mnt/user-data/outputs/<descriptive-name>.<ext>`
2. Verify with `py_compile` or equivalent
3. Call `present_files` with the path
4. State in chat: "Download the file from above. Move to `<exact path in repo>`."

Operator's responsibility:
1. Click the download link in the chat UI
2. Move the file (`mv ~/Downloads/<name> <repo path>`)
3. Verify in terminal that the file landed where expected
4. Run any verification commands the dispatcher specified (`grep`, `head`, `py_compile`)

Executor's responsibility:
1. Read the file from its final repo location, not from chat
2. Never reconstruct file content from descriptions in chat

## Why ~30 lines as the threshold

Below 30 lines, chat code blocks render reliably in most chat UIs and survive copy-paste cleanly. The threshold is empirical, not theoretical. Adjust if a smaller threshold proves needed (e.g., for languages with strict whitespace semantics).

## Where this is enforced

- All future VECRM dispatch documents must follow this rule
- S25 close handover and all related docs are themselves delivered via `present_files`
- Migration patches in `vecrm/patches/v1_1/` all came through file delivery (post-AO)

## Related observations

- OBS-S25-AM — dispatcher state-tracking failure on cross-turn source
- OBS-S25-AN — dispatcher referenced source as "in previous turn" when only described
- OBS-S25-AO — third recurrence; pattern confirmed structural
- OBS-S25-AP — promoted to this lock

## When this lock can be relaxed

NEVER for source artifacts > 30 lines. For diffs displayed for review (where the diff is the artifact, not the source), inline display is fine and expected.

## Application to non-VECRM contexts

This pattern generalizes. Operators running large dispatch-based work across any project (VEMIO, future projects) should adopt the same rule: large source artifacts via file delivery, not chat paste.
