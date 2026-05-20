# VECRM-S19-E — Build context "minimum set" derived from every COPY/ADD

**Status:** Active (promoted from candidate to active at S20 Gate 0 adjudication)
**Earned in:** S19
**Date:** 2026-05-20 (S20 promotion)

---

## Statement

Before claiming a "minimum set" for any build context, grep every `COPY` and `ADD` directive in the Dockerfile / Containerfile and verify each referenced path is included in the staged context.

Do NOT infer the minimum set from directory inspection. Do NOT assume "I copied the obvious folders, that should be enough."

## Why it exists

S19's first Path B build attempt missed the `resources/` directory in the build context transfer. The Containerfile had a `COPY resources/ ...` directive that only became apparent when the build failed at that step. The root cause was inferring the minimum set by looking at what folders "seemed relevant" rather than reading what the Containerfile actually demanded.

The fix is mechanical: parse every COPY/ADD directive, derive the path list, and check each path exists in the staged context BEFORE invoking buildx.

## How to apply

From `vecrm-rebuild-pathB.sh` step 2-3:

```bash
# 1. Parse all COPY/ADD source paths from Containerfile
REQUIRED_PATHS="$(grep -E '^\s*(COPY|ADD)\s+' "$CONTAINERFILE" \
    | awk '{
        $1=""                           # strip COPY/ADD directive
        for (i=2; i<NF; i++) {          # skip the destination (last token)
            if ($i ~ /^--/) continue    # skip --flag=value tokens
            print $i
        }
    }' | sort -u)"

# 2. Stage the build context (e.g. via rsync)

# 3. Verify each required path exists post-staging
while IFS= read -r p; do
    test_p="${p%/}"  # strip trailing slash
    if [ ! -e "$VECRM_BUILD_CTX/$test_p" ]; then
        echo "MISSING: $test_p" >&2
        exit 1
    fi
done <<< "$REQUIRED_PATHS"
```

If any required path is missing, the repo itself is incomplete OR the build context staging logic is wrong. Either way, do not proceed.

## Limitations

This parsing logic handles standard COPY/ADD syntax:
- `COPY src dest`
- `COPY src1 src2 dest`
- `COPY --flag=value src dest`
- `ADD src dest`

It does NOT handle:
- Glob patterns in source paths (`COPY *.json /app/`)
- Heredoc syntax (newer Docker feature)
- Multi-stage build context inheritance

If the Containerfile uses any of these, the parser needs extending — and a comment in the Containerfile flagging the parser limitation is appropriate.

## Meta-principle

This is a specific instance of the more general principle that **automation should read what's in the source, not what's in the operator's mental model of the source**. The mental model drifts; the source is the source.

## Related

- [VECRM-S19-F](VECRM-S19-F.md) — Cross-session prose-vs-source corollary (same principle at a different scope)
- [VECRM-S20-A](VECRM-S20-A.md) — Path B operationalizes this lock inside `vecrm-rebuild-pathB.sh`
