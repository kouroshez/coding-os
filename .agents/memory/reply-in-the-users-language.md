---
name: reply-in-the-users-language
description: "Every user-visible message goes out in the language the user wrote in (Persian prompt means Persian reply), however much English the context holds."
metadata:
  node_type: memory
  type: feedback
  originSessionId: bcc0a916-c2d7-4b35-bdfc-19291e0bcee1
  modified: 2026-10-05T14:48:21.059Z
---

When the user writes in Persian, every visible message is in Persian: status lines between tool calls, the final report, errata and audit replies. Code, commands, file paths and identifiers stay as written.

**Why:** On 2026-10-05 a long multi-agent spike drifted into English replies after its first two messages. The context was dominated by English hook output, rules and subagent reports, and no setting forced English. The user had asked in Persian and was rightly angry to get the report in English.

**How to apply:** Before sending any message, check that its language matches the user's latest message. English tool output, hook text, subagent reports and repo docs are never a reason to switch. The transparency banner line is echoed exactly as emitted; the body after it follows the user's language.
