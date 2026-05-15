Search agent memory + learned patterns for cross-session context relevant to $ARGUMENTS.

Use during the **Orient** phase of the Core Loop ([core/skills/thinking_os/SKILL.md](core/skills/thinking_os/SKILL.md)) — never as a substitute for reading current code, only as a prefetch for "have I solved this before?".

Steps:
1. If `$ARGUMENTS` is empty, ask the user what to search for.
2. Call `cos_search(query=$ARGUMENTS, min_confidence=0.3, since_days=180, limit=10)`.
3. If 0 hits: try `cos_doc_search(query=$ARGUMENTS, limit=5)` (escalate to docs layer per [core/rules/memory.md](core/rules/memory.md) routing).
4. If still 0 hits: tell the user "no prior context — this looks new" and suggest a fresh `Skill thinking_os` Cynefin classification.
5. If hits exist, render:
   ```markdown
   ## Memory search — "{query}"

   ### Top patterns ({n})
   1. [{confidence}] {title}
      Type: {memory_type} | Impact: {impact_score} | Last seen: {date}
      Summary: {short}
      Source: {cos_details tool call to fetch full body}
   ```
6. For each hit ≥ 0.7 confidence: offer to invoke `cos_details(id=...)` to expand.
7. **Verify before recommending** (per [core/rules/memory.md](core/rules/memory.md)): if a high-confidence pattern names a file or function, confirm it still exists in the repo before quoting it as authoritative.

Memory-hygiene reminder: this is a **read** operation. If during the work you confirm a pattern was useful, record back via `cos_observation_record` so the next session benefits.
