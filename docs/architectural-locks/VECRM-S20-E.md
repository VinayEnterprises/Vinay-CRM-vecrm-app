# VECRM-S20-E — Own-session output is subject to VECRM-S19-F: documents drafted within a session can themselves drift from production reality

**Status:** Active
**Earned in:** S20 PR #4 (Path B runbook drift), S21 PD-S20-DOCS-DRIFT (formalized after multiple confirming instances)
**Date:** 2026-05-20

---

## Context

VECRM-S19-F established that handover prose is not source — verify against current production state (filesystem, git, docker, DESCRIBE), not against narrative descriptions in close handovers from prior sessions. The principle was scoped to *cross-session* drift: prose written in a previous session that no longer matches current reality.

S20 surfaced that the principle applies equally to documents drafted *within* the same session:

1. **VECRM-S20-A original drafting** described "Path B (Mac amd64 buildx) is the permanent vecrm rebuild path." The S20 production builds (PR #5, PR #6) were VPS-side `docker build`, not Mac buildx. The lock contradicted what the session itself was doing. Drafted from memory of S19's narrative rather than from current `/opt/vecrm/` shell-history verification.

2. **PR #4 Path B runbook and scripts** (`docs/runbooks/rebuild-pathB/README.md` + 2 shell scripts) described a Mac-buildx workflow that does not match VPS-side reality. 787 lines of fictional procedure, shipped as authoritative documentation.

3. **S20-close-handover §3 "DB interaction discipline"** documented MariaDB probes via `MYSQL_PWD=$(cat /run/secrets/db_root_password ...)`. The S20 session scripts have the correct fallback to `$MYSQL_ROOT_PASSWORD`; the handover prose dropped the fallback. The handover drifted from its own scripts.

4. **S21 Gate 0 cold-check** (cited in S21-open-handover §3) inherited the drifted MariaDB pattern AND introduced a new anchored grep error (`^helpdesk` missing `frappe-helpdesk-*`). Three separate documentation drift bugs surfaced in 30 minutes of running it.

These are not cross-session drift in S19-F's original sense — these are documents drifting from the production reality of *the same session that produced them*.

## Decision

VECRM-S19-F applies to documents drafted within the current session. Before committing any operational document that describes "how something works in production" — runbook, lock, script, handover prose, dispatch artifact — verify against current production state, not against narrative reconstruction from earlier in the same session.

Concretely:

1. When drafting a runbook or operational document, the procedure described must be verified against current filesystem/shell-history/docker state at draft time.
2. When drafting a lock that documents a decision, the decision must reflect what is actually happening in production, not what was planned or what was done in a contingency earlier in the session.
3. When distilling a pattern from a working script into prose (e.g. for a handover §3 reference), preserve the script's full conditional logic. Trimming fallbacks or anchoring patterns that the script intentionally left unanchored is drift.
4. When inheriting a pattern from a prior session's handover, treat the handover prose as untrusted input. Re-verify against the current source (script, file, container state) before using it in a new artifact.
5. When time pressure or session fatigue makes verification feel skippable, that is the strongest signal NOT to skip it. The S20 PR #4 drift was drafted in a 12-hour session around hour 6-7, when narrative reconstruction felt faster than verification.

## Operational implications

- Dispatch artifacts that document "how to do X in production" include an explicit recon step that reads from source, not from prior dispatches or handover prose.
- Locks that document decisions are drafted AFTER the decision has been executed and verified, not before. (S20-A was drafted at Gate 3 before the actual Gate 5 build; the build went a different way than the lock predicted.)
- Handover §3 reference patterns that distill scripts into one-liners must be verified to actually execute correctly, not just to read correctly.
- When a session produces both a script and a prose distillation of the same procedure, the script is canonical. If they conflict, the prose is wrong.
- The strongest defense against own-session drift is mandatory re-verification at each gate boundary. The dispatch artifact pattern (S20-formalized) supports this by requiring recon as a separate phase from drafting.

## Reversal conditions

Not reversible — this is a discipline principle, not a constraint. The lock formalizes the priority ("apply S19-F intra-session too") rather than introducing the discipline.

If future tooling makes drift detection automatic (e.g. CI that compares runbook procedures against canonical scripts), the manual discipline becomes less load-bearing but remains valid as a fallback.

## Relationships

- **VECRM-S19-F** (verify against source not handover prose) — VECRM-S20-E is the intra-session extension. S19-F was scoped to cross-session; S20-E removes that scope restriction.
- **VECRM-S20-A** (VPS-side build path) — the lock whose original drafting earned this principle. The S21 revision of S20-A applies S20-E retroactively.
- **VECRM-S20-D** (compare to known-working reference in same image) — the diagnostic move that surfaces own-session drift. When a runbook describes a procedure, the working reference is the actual shell history / Containerfile / compose chain.
- **VECRM-S20-B** (carry-forward content audit gate) — sibling principle for the carry-forward case. S20-B audits whether old carry-forward content is still real; S20-E audits whether new own-session content is real to begin with.

## Verification

Earned from four confirming instances: VECRM-S20-A original drafting drift, PR #4 runbook drift, S20-close-handover §3 DB pattern drift, S21 Gate 0 cold-check pattern bugs. All four corrected in PR #8.
