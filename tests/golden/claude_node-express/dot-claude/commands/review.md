Review the current changes against project coding standards.

Steps:
1. Run `git diff --name-only` to see which files changed
2. For each changed file, check against the relevant engineering rules
3. Run the appropriate verification commands
4. Report findings in this format:

```
file:line — severity (critical/warning/info) — issue — suggested fix
```

Focus on: bugs, security issues, missing error handling, missing tests.
Skip: style preferences, minor formatting, local patterns that work.
