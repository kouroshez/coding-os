export interface ContentBlock {
  type: string;
  text?: string;
  name?: string;
  input?: unknown;
  content?: unknown;
  is_error?: boolean;
  id?: string;
  tool_use_id?: string;
}

export interface ChatMessage {
  uuid?: string;
  type?: string;
  role?: string;
  model?: string | null;
  stop_reason?: string | null;
  blocks: ContentBlock[];
  parent_tool_use_id?: string | null;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  } | null;
}

export interface SessionMeta {
  session_id: string;
  summary?: string | null;
  custom_title?: string | null;
  first_prompt?: string | null;
  last_modified?: number | null;
  file_size?: number | null;
  git_branch?: string | null;
  cwd?: string | null;
}

export interface ChatPayload {
  session: SessionMeta;
  messages: ChatMessage[];
  count: number;
}

export interface LiveEvent {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  ts: number;
}

// Logical turn — what the human actually sees as a single "exchange".
// Folds in:
//   - assistant text + thinking + tool_use blocks
//   - the tool_result echoes that follow as `role:user` messages
// Real human prompts (role:user with text/image blocks, no tool_result) are
// their own turn.
export type Turn =
  | { kind: 'human'; uuid: string; blocks: ContentBlock[] }
  | {
      kind: 'assistant';
      uuid: string;
      messages: ChatMessage[];           // possibly multiple SDK messages
      toolResults: Map<string, ContentBlock>;  // keyed by tool_use_id
    };

// A resumed terminal session bakes the transparency banner (the `🔔 ses=…`
// line) into its transcript, and the model echoes it on resume despite the
// Hub system prompt asking it not to (the few-shot history outweighs the
// instruction). Strip a leading banner line from assistant prose so the Hub
// chat stays clean (TASK-283). Assistant-scoped — human messages are untouched.
export function stripLeadingBanner(text: string): string {
  return text.replace(/^\s*🔔[^\n]*\n+/, '');
}

export function isToolResultOnly(m: ChatMessage): boolean {
  return (
    m.role === 'user' &&
    m.blocks.length > 0 &&
    m.blocks.every((b) => b.type === 'tool_result')
  );
}

export function buildTurns(messages: ChatMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (const m of messages) {
    if (m.role === 'user' && !isToolResultOnly(m)) {
      turns.push({ kind: 'human', uuid: m.uuid ?? `h-${turns.length}`, blocks: m.blocks });
      continue;
    }
    if (isToolResultOnly(m)) {
      // Attach to the last assistant turn (or create one if none).
      let last = turns[turns.length - 1];
      if (!last || last.kind !== 'assistant') {
        last = { kind: 'assistant', uuid: m.uuid ?? `a-${turns.length}`, messages: [], toolResults: new Map() };
        turns.push(last);
      }
      for (const b of m.blocks) {
        if (b.type === 'tool_result' && b.tool_use_id) {
          last.toolResults.set(b.tool_use_id, b);
        }
      }
      continue;
    }
    if (m.role === 'assistant' || m.type === 'assistant') {
      // Coalesce consecutive assistant messages into one turn so the
      // bubble doesn't fragment around thinking → text → tool_use → text.
      const last = turns[turns.length - 1];
      if (last && last.kind === 'assistant') {
        last.messages.push(m);
      } else {
        turns.push({
          kind: 'assistant',
          uuid: m.uuid ?? `a-${turns.length}`,
          messages: [m],
          toolResults: new Map(),
        });
      }
      continue;
    }
    // Unknown role with no renderable blocks — system/result transcript
    // entries that would otherwise render as an empty assistant bubble
    // (TASK-283). Skip them; keep any that DO carry content for visibility.
    if (!m.blocks || m.blocks.length === 0) continue;
    turns.push({
      kind: 'assistant',
      uuid: m.uuid ?? `u-${turns.length}`,
      messages: [m],
      toolResults: new Map(),
    });
  }
  return turns;
}

