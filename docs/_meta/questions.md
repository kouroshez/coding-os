<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-07 -->
# Open Questions

Purpose: Running log of questions raised during task execution that need external resolution before the blocked task can move forward.
Read when: Investigating why a task is blocked, or clearing up resolved questions.
Skip when: You're not handling a blocked task.
Read next: The blocked task file referenced in each question.

> Nav: [Docs Index](../00-index.md)

<!-- Blocker questions are logged here automatically by `cos task-block`.
     Format: each question is `Q-NNN: <question>` followed by context lines.
     Resolve a question by removing it and adding the answer to the related task or ADR. -->

## Open

Q-SESSIONSTART-EMIT: Does Claude Code hide SessionStart `{hookSpecificOutput:{additionalContext}}` as a `<system-reminder>` on the `compact` source the same way it hides the UserPromptSubmit `additionalContext` branch of session-context.sh? Prior art (transparency-banner.md, state-files.md §S5, adapter-parity.md `extract_additional_context.py`) establishes the JSON-additionalContext envelope as the correct emission mechanism for SessionStart cognitive cards (session-skill-primer.sh + rules-primer.sh already emit it), but no spec/ADR explicitly documents that SessionStart-source additionalContext is UI-hidden on auto-compact. The plain-stdout SessionStart emitters (session-context.sh digest/MCP-prime/state-snapshot blocks, remind-daily.sh, warn-mcp-down.sh) are the confirmed offenders that auto-compact re-dumps into the visible chat; whether converting them to the JSON envelope fully hides them on the compact path (vs the operator "SessionStart:startup hook success:" stdout line) needs runtime confirmation before the fix lands. Context: SessionStart emission cleanup task.
