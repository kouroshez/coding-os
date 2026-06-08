// Single source of truth for the cognition Server-Sent-Events protocol.
//
// Every chat surface (NewChatForm's first turn, ChatView's follow-up turn, the
// board's "draft with AI" modal) POSTs a prompt to a /api/cognition/* endpoint
// and reads back an event-stream of `event:`/`data:` frames. The fetch + reader
// + `\n\n`-frame-split + line-parse loop used to be copy-pasted in all three;
// drift between them caused subtle bugs. consumeSse owns that loop once. Each
// caller keeps ONLY its own per-frame interpretation in `onFrame` — they
// genuinely differ (text extraction vs raw-event accumulation), so that part
// stays local.

import { csrfHeader, resolveApiUrl } from './api-client';

export interface SseBlock {
  type?: string;
  text?: string;
  name?: string;
}

export interface SseUsage {
  input_tokens?: number;
  output_tokens?: number;
}

// One parsed SSE frame's JSON payload. Named fields cover everything the chat
// surfaces read; the index signature keeps arbitrary extra keys (ChatView
// stores the whole payload for its raw-event viewer).
export interface SseFramePayload {
  session_id?: string;
  content?: SseBlock[];
  blocks?: SseBlock[];
  model?: string;
  // assistant frames carry a message object; error frames carry a string.
  message?: string | { model?: string; usage?: SseUsage };
  usage?: SseUsage;
  message_text?: string;
  // StreamEvent frames (include_partial_messages) carry the raw Anthropic
  // streaming event — content_block_delta (text/thinking), content_block_start
  // (tool_use), message_start/stop, etc.
  event?: {
    type?: string;
    delta?: { type?: string; text?: string; thinking?: string };
    content_block?: { type?: string; name?: string };
  };
  raw?: string;
  parse_error?: string;
  [key: string]: unknown;
}

/** The assistant answer TEXT delta from a `streamevent` frame, or '' (thinking
 *  and tool-input deltas are not user-visible answer text). */
export function streamDeltaText(payload: SseFramePayload): string {
  const e = payload.event;
  if (e?.type === 'content_block_delta' && e.delta?.type === 'text_delta') {
    return e.delta.text ?? '';
  }
  return '';
}

/** The tool name when a `streamevent` opens a tool_use block, or ''. */
export function streamToolName(payload: SseFramePayload): string {
  const e = payload.event;
  if (e?.type === 'content_block_start' && e.content_block?.type === 'tool_use') {
    return e.content_block.name ?? '';
  }
  return '';
}

export type SseFrameHandler = (event: string, payload: SseFramePayload) => void;

// Stream one cognition turn. Throws on a non-OK response (message lifted from
// the JSON error envelope when present) or a network/abort error — the caller's
// own try/catch/finally handles error state and cleanup, exactly as before.
export async function consumeSse(
  endpoint: string,
  body: Record<string, unknown>,
  onFrame: SseFrameHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(resolveApiUrl(endpoint), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...csrfHeader() },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '');
    let msg = `HTTP ${res.status}`;
    try {
      msg = JSON.parse(t)?.error?.message ?? msg;
    } catch {
      msg = t.slice(0, 160) || msg;
    }
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx = buffer.indexOf('\n\n');
    while (idx >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = 'event';
      let data = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (data) {
        try {
          onFrame(event, JSON.parse(data) as SseFramePayload);
        } catch (parseErr) {
          // Surface unparseable frames the way ChatView's raw viewer expects,
          // instead of silently dropping them.
          onFrame(event, { raw: data.slice(0, 500), parse_error: String(parseErr) });
        }
      }
      idx = buffer.indexOf('\n\n');
    }
  }
}
