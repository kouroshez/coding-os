import { ChevronRight, FolderTree } from 'lucide-react';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { TypeDot } from './MemorySidebar';
import {
  VERIFY_MAX_AGE_DAYS,
  groupAnchor,
  verifiedAgeDays,
  type MemoryFile,
  type MemoryGroup,
  type MemoryRow,
} from './memory-view';

function InlineCode({ text }: { text: string }) {
  return (
    <>
      {text.split(/`([^`]+)`/).map((part, i) =>
        i % 2 ? (
          <code key={i} className="rounded bg-[var(--cos-panel)] px-1 font-mono text-[0.95em]">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}

function Verified({ memory }: { memory: MemoryFile }) {
  const age = verifiedAgeDays(memory.verified);
  if (age === null) return null;
  const stale = age > VERIFY_MAX_AGE_DAYS;
  return (
    <span
      title={`verified ${memory.verified}`}
      className={`font-mono text-[10px] ${stale ? 'text-[var(--cos-warn)]' : 'text-[var(--cos-muted)]'}`}
    >
      {stale ? `verified ${age}d ago` : `verified ${memory.verified}`}
    </span>
  );
}

function TypePill({ type }: { type: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--cos-border)] px-2 py-0.5 text-[10px] capitalize text-[var(--cos-muted)]">
      <TypeDot type={type} />
      {type ?? 'untyped'}
    </span>
  );
}

function SubIndexRow({ row, onJump }: { row: MemoryRow; onJump: (name: string) => void }) {
  const sub = row.subIndex;
  if (!sub) return null;
  return (
    <li>
      <button
        type="button"
        onClick={() => onJump(sub.name)}
        className="flex w-full items-center gap-3 px-4 py-3 text-start transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]"
      >
        <FolderTree size={14} aria-hidden className="shrink-0 text-[var(--accent)]" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-[var(--cos-text)]">
            {row.entry.title}
          </span>
          <span className="block truncate text-xs text-[var(--cos-muted)]">
            Open when: <InlineCode text={row.entry.rule} />
          </span>
        </span>
        <span className="shrink-0 rounded-full bg-[var(--cos-panel)] px-2 py-0.5 font-mono text-[10px] text-[var(--cos-muted)]">
          {sub.entries.length} in {sub.file}
        </span>
      </button>
    </li>
  );
}

function EntryRow({
  row,
  open,
  onToggle,
  onOpenLink,
}: {
  row: MemoryRow;
  open: boolean;
  onToggle: (slug: string) => void;
  onOpenLink: (slug: string) => void;
}) {
  const { entry, memory } = row;
  const slug = entry.slug ?? `line-${entry.line}`;
  const panelId = `memory-body-${slug}`;
  return (
    <li id={`memory-${slug}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => onToggle(slug)}
        className="flex w-full items-center gap-3 px-4 py-3 text-start transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]"
      >
        <ChevronRight
          size={14}
          aria-hidden
          className={`shrink-0 text-[var(--cos-muted)] transition-transform ${open ? 'rotate-90' : ''}`}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-[var(--cos-text)]">
            {entry.title}
          </span>
          <span className="block truncate text-xs text-[var(--cos-muted)]">
            <InlineCode text={entry.rule} />
          </span>
        </span>
        <span className="hidden shrink-0 items-center gap-3 sm:flex">
          {memory && <Verified memory={memory} />}
          {memory ? (
            <TypePill type={memory.type} />
          ) : (
            <span className="rounded-full bg-[var(--cos-err-tint)] px-2 py-0.5 text-[10px] text-[var(--cos-err)]">
              missing file
            </span>
          )}
        </span>
      </button>
      {open && (
        <div
          id={panelId}
          className="border-t border-[var(--cos-border)]/60 bg-black/10 px-4 py-4 sm:ps-11"
        >
          {memory ? (
            <>
              {memory.description && (
                <p className="mb-3 text-xs italic text-[var(--cos-muted)]">{memory.description}</p>
              )}
              <MarkdownBlock source={memory.body} className="text-[13px]" />
              <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
                <code className="rounded bg-[var(--cos-panel)] px-1.5 py-0.5 font-mono text-[var(--cos-muted)]">
                  {memory.slug}.md
                </code>
                {memory.links.map((link) => (
                  <button
                    key={link}
                    type="button"
                    onClick={() => onOpenLink(link)}
                    className="rounded-full border border-[var(--cos-border)] px-2 py-0.5 font-mono text-[var(--accent)] hover:border-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                  >
                    [[{link}]]
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-[var(--cos-err)]">
              Line {entry.line} links a file that does not exist. <code>make memory-lint</code>{' '}
              reports it.
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export function MemoryGroupSection({
  group,
  isRoot,
  expanded,
  onToggle,
  onOpenLink,
  onJump,
}: {
  group: MemoryGroup;
  isRoot: boolean;
  expanded: ReadonlySet<string>;
  onToggle: (slug: string) => void;
  onOpenLink: (slug: string) => void;
  onJump: (name: string) => void;
}) {
  const { index, rows } = group;
  return (
    <section
      id={groupAnchor(index.name)}
      aria-labelledby={`${groupAnchor(index.name)}-title`}
      className="scroll-mt-4"
    >
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 px-1">
        <h3
          id={`${groupAnchor(index.name)}-title`}
          className="text-sm font-semibold text-[var(--cos-text)]"
        >
          {isRoot ? 'Always loaded' : index.title}
        </h3>
        <span className="font-mono text-[11px] text-[var(--cos-muted)]">{index.file}</span>
        <span className="rounded-full bg-[var(--cos-panel)] px-2 font-mono text-[10px] text-[var(--cos-muted)]">
          {rows.length}
        </span>
        {!isRoot && index.pointer && (
          <span className="basis-full text-xs text-[var(--cos-muted)]">
            Opened when: <InlineCode text={index.pointer.rule} />
          </span>
        )}
      </header>
      {rows.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-[var(--cos-border)] px-4 py-6 text-center text-xs text-[var(--cos-muted)]">
          This index has no entries.
        </p>
      ) : (
        <ul className="divide-y divide-[var(--cos-border)]/60 overflow-hidden rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50">
          {rows.map((row) =>
            row.subIndex ? (
              <SubIndexRow key={row.entry.line} row={row} onJump={onJump} />
            ) : (
              <EntryRow
                key={row.entry.line}
                row={row}
                open={expanded.has(row.entry.slug ?? `line-${row.entry.line}`)}
                onToggle={onToggle}
                onOpenLink={onOpenLink}
              />
            ),
          )}
        </ul>
      )}
    </section>
  );
}
