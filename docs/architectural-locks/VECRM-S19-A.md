# VECRM-S19-A — Verify remote-tracking ref exists after `git fetch`

**Status:** Active (promoted from candidate to active at S20 Gate 0 adjudication)
**Earned in:** S19
**Date:** 2026-05-20 (S20 promotion)

---

## Statement

After every `git fetch`, assert that the expected remote-tracking ref exists via `git rev-parse --verify` BEFORE relying on it.

A `git fetch` that silently fails to populate a remote-tracking ref will leave the local repo with a stale or absent `origin/<branch>` reference. Any subsequent `git reset --hard origin/<branch>` or `git rebase origin/<branch>` will then operate on the wrong target.

## Why it exists

S19's `vecrm-src` vendor remote was configured with a tag-only refspec. A bare `git fetch origin` populated tags but not branches. The expected `origin/main` ref never materialized locally, even though the command exited 0. A subsequent operation that assumed `origin/main` was current produced the wrong result.

The fix is two-fold:
1. Use `git fetch origin main` (explicit branch fetch) rather than bare `git fetch origin`.
2. After the fetch, `git rev-parse --verify origin/main` to confirm the ref exists.

If `--verify` fails, the refspec is wrong and must be corrected before proceeding.

## How to apply

```bash
git fetch origin main
if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "ERROR: origin/main ref does not exist after fetch — check refspec"
    exit 1
fi
REMOTE_SHA="$(git rev-parse origin/main)"
echo "origin/main = $REMOTE_SHA"
```

This pattern is baked into `vecrm-rebuild-pathB.sh` step 1.

## Related findings

The Mac/VPS sync incident at S20 Gate 4 was a related but different failure mode — the Mac's `origin/main` ref WAS valid but STALE (last fetched before PR #3 landed). The lesson there: don't trust a remote-tracking ref's age either; check the actual remote at session start.

## When to apply

- At the start of any session that touches git state
- Before any `git reset --hard origin/<branch>` operation
- Inside any automation script that depends on a remote-tracking ref
- Whenever switching between machines that may have different fetch histories
