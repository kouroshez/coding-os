Show the current Scrumban board state, grouped by swimlane × status.

Steps:
1. Call `cos_task_board` (no args → entire board; with `$ARGUMENTS` interpreted as swimlane → filter).
2. Group cards by `swimlane` then by `status` (`backlog | in_progress | testing | blocked | complete`).
3. Render the table below. Cap displayed cards per cell at 5 — link to `cos_task_search` for more.
4. Surface WIP cap violations at the top (red flag).
5. Surface tasks that have been in `in_progress` > 3 days at the bottom (stale alert per [task-driver](../skills/task-driver/SKILL.md) escalation ladder).

Template:
```markdown
## Board — YYYY-MM-DD

### WIP status
| Lane | in_progress | testing | violations |
|---|---|---|---|

### {swimlane}
| in_progress | testing | blocked | backlog |
|---|---|---|---|
| [TASK-NNN] title | ... | ... | ... |

### Stale (in_progress > 3 days)
- [TASK-NNN] {title} — in_progress since {date} ({N} days)
```

For interactive browsing the human can run `cos board --web` (opens Hub UI at http://127.0.0.1:9188). Mention this as the visual alternative if the user is exploring a complex state.
