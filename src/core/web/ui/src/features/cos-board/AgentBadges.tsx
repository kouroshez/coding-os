import { useContext } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { visualFor } from './agentPresenceVisuals';
import { LiveSessionsContext, useAgentCatalog, type AgentState } from './board-shared';

export function AgentBadge({
  agentId,
  state,
  sessionCount,
}: {
  agentId: string;
  state: AgentState;
  sessionCount?: number;
}) {
  const catalog = useAgentCatalog();
  const a = catalog.find((x) => x.id === agentId);
  if (!a) return null;
  const dot = visualFor(state);
  const live = state !== 'offline';
  // Border = STATE color (not brand) so the pill itself signals presence.
  // Brand color survives in the faint background tint + label color, so
  // adapter identity stays readable without competing with state.
  // Fixes the regression where Claude's amber brand made every Claude
  // pill look like it was in `present` (also amber) regardless of state.
  const borderColor = live ? dot.color : 'var(--col-border)';
  return (
    <div
      title={`${a.label} — ${dot.label}${sessionCount && sessionCount > 1 ? ` (${sessionCount} sessions)` : ''}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        padding: '3px 8px 3px 6px',
        borderRadius: 999,
        background: live ? `${a.color}12` : 'var(--board-grain)',
        border: `1.5px solid ${borderColor}`,
        color: live ? a.color : 'var(--ink-faint)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
        fontWeight: 600,
        transition: 'all 0.2s',
      }}
    >
      <span
        style={{
          width: 9,
          height: 9,
          borderRadius: '50%',
          background: dot.color,
          boxShadow: `0 0 0 2px ${dot.ring}`,
          animation: dot.pulse ? 'cos-agent-pulse 1.4s ease-in-out infinite' : undefined,
        }}
      />
      {a.label}
      {sessionCount && sessionCount > 1 ? (
        <span style={{ opacity: 0.85, fontWeight: 700 }}>·{sessionCount}</span>
      ) : null}
    </div>
  );
}

export function AgentPip({ agentId, title, size = 18 }: { agentId?: string | null; title?: string; size?: number }) {
  // Hook must run unconditionally — call before the early return (rules-of-hooks).
  const catalog = useAgentCatalog();
  if (!agentId) return null;
  const a = catalog.find((x) => x.id === agentId);
  if (!a) return null;
  // Two-letter glyphs need a tighter font to fit inside the pip cleanly.
  const glyphRatio = a.glyph.length > 1 ? 0.44 : 0.58;
  return (
    <span
      title={title || `${a.label} (${a.session})`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        borderRadius: '50%',
        background: a.color,
        color: 'white',
        fontSize: Math.round(size * glyphRatio),
        fontWeight: 700,
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: a.glyph.length > 1 ? '-0.5px' : undefined,
        boxShadow: '0 2px 4px rgba(0,0,0,.15)',
        border: '2px solid rgba(255,255,255,0.85)',
      }}
    >
      {a.glyph}
    </span>
  );
}

/** Card corner pip that pulses while the bound session is live and
 *  deep-links to that session's chat. Falls back to the static pip when
 *  the session is not in the live inventory. */
export function LiveAgentPip({
  agentId,
  session,
}: {
  agentId: string;
  session: string | null | undefined;
}) {
  const liveSessions = useContext(LiveSessionsContext);
  const navigate = useNavigate();
  const { slug } = useParams<{ slug?: string }>();
  const live = session ? liveSessions.get(session) : undefined;
  if (!live) return <AgentPip agentId={agentId} />;
  const v = visualFor(live.state);
  const hint = `${agentId} ${v.label} — open live chat`;
  return (
    <button
      type="button"
      // The card is `draggable`; a cancelled dragstart here keeps an
      // imprecise pip click from starting a card drag (and an accidental
      // column drop / status transition).
      draggable
      onDragStart={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (slug) {
          navigate(
            `/p/${encodeURIComponent(slug)}/workspace/chat/${encodeURIComponent(live.chatId)}`,
          );
        }
      }}
      aria-label={`Open live chat for the ${agentId} session on this task`}
      className="focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
      style={{
        display: 'inline-flex',
        padding: 0,
        border: 'none',
        background: 'transparent',
        borderRadius: '50%',
        cursor: 'pointer',
        boxShadow: `0 0 0 3px ${v.ring}`,
        animation: 'cos-agent-pulse 1.4s ease-in-out infinite',
      }}
    >
      <AgentPip agentId={agentId} title={hint} />
    </button>
  );
}
