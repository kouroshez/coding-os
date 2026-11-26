Load and summarize the task specified by $ARGUMENTS.

Steps:
1. Run `cos task-show $ARGUMENTS` (or read the task detail file directly from docs/tasks/)
2. Read the full task detail file — including Notes and Session Checkpoint sections
3. Classify the task domain and identify which playbook applies
4. Present a summary:
   - **Goal:** why this task exists (1-2 sentences)
   - **Domain:** which playbook route
   - **Scope:** Small / Medium / Large (based on file count and complexity)
   - **Requirements:** the Given/When/Then acceptance criteria
   - **Dependencies:** any prerequisite tasks and their status
   - **Verification:** what commands to run when done
   - **Session Checkpoint:** any previous progress (if exists)
5. Ask: "What would you like to do? (a) Start — run Classify → Orient → Plan → Execute, (b) Investigate first, (c) Mark as blocked"

If no task number is provided, run `cos task-pick` to suggest the next task.
