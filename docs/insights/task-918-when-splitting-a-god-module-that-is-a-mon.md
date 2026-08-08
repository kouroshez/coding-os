<!-- domain:BOARD_OS | layer:reference | ssot:false | source:outcome_history#987 | updated:2026-08-08 -->
# TASK-918: When splitting a god-module that is a monkeypatch surface: (1) use RELATIVE imports inside the split (dual-instance package loading makes absolute imports cross instances), (2) enumerate monkeypatch targets with re.finditer over setattr(\s*module patterns (multiline), (3) route calls to patched names through `from . import kernel as _kernel; _kernel.name(...)` at call time. Verify with sibling-first import probes for every module.

**Date:** 2026-08-08  
**Domain:** BOARD_OS  
**Source task:** [TASK-918](../tasks/TASK-918-split-board-os-mcp-tools-py-into-kernel-private-mcp-siblings.md)

## Key Insight

When splitting a god-module that is a monkeypatch surface: (1) use RELATIVE imports inside the split (dual-instance package loading makes absolute imports cross instances), (2) enumerate monkeypatch targets with re.finditer over setattr(\s*module patterns (multiline), (3) route calls to patched names through `from . import kernel as _kernel; _kernel.name(...)` at call time. Verify with sibling-first import probes for every module.

## What Failed

Splitting board_os/mcp_tools.py with ABSOLUTE imports (from board_os._mcp_x import ...) broke monkeypatch transparency: the repo loads board_os under two package identities (board_os.* and core.board_os.*), so absolute imports crossed instances — tests patched core.board_os.mcp_tools while the code read board_os.mcp_tools. Also single-line grep for setattr(mcp_tools, ...) missed multiline monkeypatch.setattr calls, hiding _commits_referencing_batch as a patch target.

## What Worked

Relative imports for every split-internal reference (from ._mcp_shared import, from . import mcp_tools as _kernel) keep each package instance self-consistent; monkeypatched helpers are read late-bound through the kernel module at call time. Extract setattr targets with a multiline-safe regex over the test tree before choosing what stays in the kernel.

## Links

- Pattern: `learned_patterns#354` — retrievable via `cos_details`
- History: `outcome_history#987`
