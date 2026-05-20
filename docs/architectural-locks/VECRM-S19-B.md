# VECRM-S19-B — Positive verification of build manifest before rebuild

**Status:** Active (promoted from candidate to active at S20 Gate 0 adjudication)
**Earned in:** S19
**Date:** 2026-05-20 (S20 promotion)

---

## Statement

The pre-rebuild baseline must POSITIVELY verify that the build manifest (`apps.json` for vecrm) references every app the new image must contain.

Do not assume the manifest is correct. Do not infer correctness from "the build worked last time." Read the manifest, assert each required app is named, and abort if any are missing.

## Why it exists

S19 nearly attempted a rebuild against a build context where `apps.json` was incomplete. A negative-checking approach ("the build will fail if apps.json is wrong") wastes the full ~5 minute build before the error surfaces. A positive check ("apps.json references both `frappe` and `vecrm`") catches it in seconds, before any docker/buildx invocation.

More fundamentally: silent-absence in manifests is the same class of bug as silent-absence in remote-tracking refs (see VECRM-S19-A). The pattern across both is "verify what you depend on, do not infer it from non-failure."

## How to apply

For `apps.json`, the required apps for vecrm are at minimum:

```
frappe
vecrm
```

Verification (from `vecrm-rebuild-pathB.sh` step 4):

```bash
REQUIRED_APPS="frappe vecrm"
for app in $REQUIRED_APPS; do
    if grep -q "\"$app\"" "$APPS_JSON" || grep -qE "/${app}\\.git" "$APPS_JSON" || grep -qE "/${app}(\"|/)" "$APPS_JSON"; then
        echo "  apps.json references: $app  ✓"
    else
        echo "ERROR: manifest does not reference required app $app"
        exit 1
    fi
done
```

If new apps are added to the build (e.g. helpdesk-as-vecrm-app integration, additional custom apps), update `REQUIRED_APPS` AND the runbook AND this lock simultaneously.

## When to apply

- Inside any vecrm rebuild script
- During any "did the manifest get corrupted" investigation
- When adding a new app to the vecrm image — update the verification list

## Limitations

This lock only verifies that named apps are *referenced* in the manifest. It does NOT verify that the URLs resolve, that the versions specified exist, or that the apps are clonable. Those failures happen at build time. The positive check catches the most common silent failure (forgot to add the app), not all manifest pathologies.
