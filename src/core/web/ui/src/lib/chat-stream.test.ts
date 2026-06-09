import { describe, expect, it } from 'vitest';
import { streamDeltaText, streamToolName } from './chat-stream';

// These guard the exact StreamEvent shape captured live from the Claude Agent
// SDK (include_partial_messages). If the SDK delta shape drifts or the extractor
// regresses, token-by-token streaming breaks silently — these fail first.

describe('streamDeltaText', () => {
  it('returns the text of a content_block_delta text_delta', () => {
    expect(
      streamDeltaText({ event: { type: 'content_block_delta', delta: { type: 'text_delta', text: 'hi ' } } }),
    ).toBe('hi ');
  });

  it('ignores thinking_delta — it is not user-visible answer text', () => {
    expect(
      streamDeltaText({
        event: { type: 'content_block_delta', delta: { type: 'thinking_delta', thinking: 'hmm' } },
      }),
    ).toBe('');
  });

  it('returns empty for control frames and non-stream payloads', () => {
    expect(streamDeltaText({ event: { type: 'message_start' } })).toBe('');
    expect(streamDeltaText({ event: { type: 'content_block_start', content_block: { type: 'text' } } })).toBe('');
    expect(streamDeltaText({})).toBe('');
  });
});

describe('streamToolName', () => {
  it('returns the tool name when a content_block_start opens a tool_use', () => {
    expect(
      streamToolName({ event: { type: 'content_block_start', content_block: { type: 'tool_use', name: 'Read' } } }),
    ).toBe('Read');
  });

  it('returns empty for a text block start or a delta frame', () => {
    expect(streamToolName({ event: { type: 'content_block_start', content_block: { type: 'text' } } })).toBe('');
    expect(
      streamToolName({ event: { type: 'content_block_delta', delta: { type: 'text_delta', text: 'x' } } }),
    ).toBe('');
    expect(streamToolName({})).toBe('');
  });
});
