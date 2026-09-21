---
name: test-patches-hide-in-suite-helper-packages
description: "Before a refactor, grep for monkeypatch targets in tests/_cli_suite/ and similar helper packages, not just the test file that names the class."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-21T02:36:43.322Z
---

`tests/test_cli.py` contains almost no pr-mode test bodies — they live in `tests/_cli_suite/pr_*.py` and are mixed into the classes by inheritance. A grep for `setattr(pr_commands` across `tests/` returned **0**, so I concluded the split was safe. It was not: 64 tests failed, all patching via an alias (`prc`) inside that helper package.

**Why:** two things defeated the grep at once — the patch target was an alias, not the module name, and the file lived one directory deeper than I looked. Either alone is enough to turn a refactor's risk assessment upside down.

**How to apply:** before splitting a module, find its patch surface by **module object**, not by name:

```bash
grep -rn "import .*<module> as \([a-z]*\)" tests/    # find every alias
grep -rn "setattr(\s*\(prc\|pc\|m\)\s*," tests/       # then the patches
```

and run the suite on the pure move *before* deciding no retargeting is needed. A loud failure is the good case; the dangerous one is a patch that still applies to a name nobody reads any more. When several modules read the same helper, retargeting each test is fragile — route the callers through the module object (`_shared.helper()`) so there is one patch point, and commit that body edit separately from the move so `check_split_parity` stays meaningful. Related: [[splitting-a-facade-needs-a-runtime-surface-diff]], [[verification-matrix-must-match-ci]].
