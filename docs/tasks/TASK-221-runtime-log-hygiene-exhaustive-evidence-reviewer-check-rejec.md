---
id: TASK-221
title: "Runtime log hygiene: exhaustive_evidence reviewer_check rejects free-text (add reviewer_notes) + embeddings phone-home to HF Hub at runtime (offline-by-default)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [cognition, embeddings, enterprise, offline, privacy, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-07
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-221: Runtime log hygiene: exhaustive_evidence reviewer_check rejects free-text (add reviewer_notes) + embeddings phone-home to HF Hub at runtime (offline-by-default)

**Outcome (one sentence):** Two runtime log defects are fixed: (1) ExhaustiveEvidence gains a reviewer_notes free-text field and cos_supervise_record_output gives a clear error (not a silent drop) when reviewer_check isn't the pending/pass/fail literal — the board hint is clarified to match; (2) the embedding model never makes unauthenticated HuggingFace Hub requests at runtime — embeddings.py defaults to offline (HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE) and a first-time vendoring download requires explicit COS_ALLOW_MODEL_DOWNLOAD=1, with lexical fallback when the model is absent. Verified by thinking_os tests + a clear log path.

## Read First
- src/core/thinking_os/cognition_schemas.py
- src/core/thinking_os/tools/cognition.py
- src/core/thinking_os/embeddings.py

## Repro Steps
1. Call cos_supervise_record_output(formula_id='exhaustive_evidence', output_json={... reviewer_check: 'batch commits spot-verified ...'}) → log: `Failed to parse exhaustive evidence: reviewer_check Input should be 'pending','pass' or 'fail'`; the whole bundle field is silently dropped.
2. Run any session that triggers semantic search/doc-index → log: `huggingface_hub: You are sending unauthenticated requests to the HF Hub` + an HTTP HEAD to huggingface.co for all-MiniLM-L6-v2.
Expected: (1) a clear actionable error + a place for free-text notes; (2) no runtime network call to HF without explicit consent.
Actual: (1) silent bundle drop on a Literal mismatch; (2) the agent runtime phones home to HuggingFace unauthenticated on a hot path.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a caller passes free-text in reviewer_check, or a session that would load the embedding model.
- **When** cos_supervise_record_output validates the bundle / embeddings._get_model_by_name loads the model.
- **Then** (1) ExhaustiveEvidence has a reviewer_notes field, the error names reviewer_notes + the literal set (no silent drop), and the board hint matches; (2) the embedding load defaults to offline (no HF network) and only downloads when COS_ALLOW_MODEL_DOWNLOAD=1, else lexical fallback — verified by thinking_os tests passing.

## Work Log
- 2026-06-07 [claude]: Both fixes shipped + 190 thinking_os tests pass. (1) ExhaustiveEvidence gained reviewer_notes (str); cos_supervise_recor
- 2026-06-07 [claude]: committed d46f45a3: src/core/board_os/mcp_tools.py, src/core/thinking_os/cognition_schemas.py, src/core/thinking_os/embe
