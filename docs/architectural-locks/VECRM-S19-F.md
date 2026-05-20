# VECRM-S19-F — Cross-session prose-vs-source corollary to L1

**Status:** Active (promoted from candidate to active at S20 Gate 0 adjudication)
**Earned in:** S19
**Date:** 2026-05-20 (S20 promotion)

---

## Statement

The prose-vs-source discipline extends across sessions. Before halting on a finding that contradicts a known-working baseline, search prior conversation history of the session that established that baseline. Do not assume your current understanding is the most current understanding.

## Why it exists

S19 nearly flagged `apps.json` as broken before learning that the "COPY-not-clone" mechanism for app source acquisition had already been locked in S12. The handover prose for S19 did not mention the S12 mechanism. The S19 operator's mental model assumed a `git clone`-based flow that didn't exist in this codebase.

The fix is to actively check session history when a finding contradicts a baseline, rather than trusting the contradiction at face value. "X looks broken" is a hypothesis, not a fact. "I searched S12-S18 for prior context on X" is the verification step.

## How to apply

When a session is about to declare a finding "FAIL" or "BROKEN":

1. **State the finding explicitly.** "apps.json looks malformed because it references URLs not git repos."
2. **Identify what baseline the finding contradicts.** "But the system has been building successfully for 8 sessions."
3. **Search prior session history for that baseline.** Look in handovers, session-close documents, and chat transcripts for the session(s) that established the current behavior.
4. **Adjudicate.** If prior context explains the apparent contradiction, the finding is not a finding — it's a knowledge gap. If prior context cannot explain it, escalate to a real investigation.

## In practice

S20 hit this lock multiple times in flight:

- **`~/GitHub/vecrm` vs `~/Documents/GitHub/vecrm`** — appeared to be one path; turned out to be two. Prose-vs-source check on the filesystem (`ls -la`) caught it.
- **`vecrm-src` repo name** — propagated as a repo name; was always just a VPS-side directory name. Reading the actual `git remote -v` caught it.
- **Mac local `main` stale at `779caa1`** — local branch lagged origin by one PR. `git fetch && git log origin/main` caught it.

In each case, the prose (handover language, mental model from prior sessions, inherited assumptions) disagreed with the source (actual filesystem, actual git state). The source won.

## Meta-principle

L1 says "verify the artifact, never the exit code." This lock says "verify the artifact, never the prose."

Prose includes: prior handovers, session-close documents, your own mental model, this lock file itself. All are subject to verification against actual source state. None is exempt.

## Related

- L1 (operating-model lock) — Verify the artifact, never the exit code
- L27 (operating-model lock) — Verify history/inventory at every layer-transition checkpoint
- [VECRM-S19-E](VECRM-S19-E.md) — Build context minimum set from source, not mental model (same principle, narrower scope)
