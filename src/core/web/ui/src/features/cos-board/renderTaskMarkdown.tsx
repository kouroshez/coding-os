import type { ReactNode } from 'react';

/**
 * Tiny, safe markdown renderer for task MD files.
 *
 * PURPOSE: Render docs/tasks/TASK-*.md content inside the task drawer
 *          with the md-body classes defined in cos-board-tokens.css
 *          (headings, lists, GIVEN/WHEN/THEN blocks, fenced code,
 *          blockquotes, images, task-id links).
 * INPUT:   md — full markdown string (frontmatter already stripped).
 * OUTPUT:  ReactNode array.
 * DEPENDENCIES: none (custom tiny parser, no DOMPurify needed — we
 *               escape HTML before inline formatting).
 * NOTES:   Supports the exact subset used by the Claude Design
 *          prototype (core/web/ui/coding-os-scrumban/project/task_detail.jsx):
 *          # .. #### headings, paragraphs, -/* lists with checkboxes,
 *          1. ordered lists, > blockquotes, --- hr, fenced code with
 *          language label, inline `code`, **bold**, *em*, [links](url),
 *          ![images](url), TASK-NNN refs, GIVEN/WHEN/THEN callouts.
 */

// Quotes are escaped alongside the angle brackets because the output feeds
// double-quoted src/href/alt attributes: without them `![a](x" onerror="…)`
// closes the attribute and lands executable markup in dangerouslySetInnerHTML.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const ALLOWED_URL_SCHEMES = new Set(['http', 'https', 'mailto']);

// Escaping alone does not stop `[click](javascript:alert(1))` — that payload
// contains no HTML metacharacters. Anything carrying a scheme we do not trust
// resolves to an empty attribute; relative links pass through untouched.
function safeUrl(url: string): string {
  // Browsers strip C0 control characters and spaces before reading the
  // scheme, so `java\tscript:` is live — normalise the same way first.
  // Char-code filter, not a regex: a \u0000-\u0020 class is a no-control-regex
  // lint error, and spelling the bound out is clearer than escaping around it.
  const probe = Array.from(url)
    .filter((ch) => ch.charCodeAt(0) > 0x20)
    .join('');
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(probe);
  if (scheme && !ALLOWED_URL_SCHEMES.has(scheme[1].toLowerCase())) return '';
  return url;
}

export function inlineHtml(txt: string): string {
  // Escaped once, up front: every capture below is already attribute-safe,
  // so re-escaping a URL here would turn `?a=1&b=2` into `&amp;amp;`.
  let safe = escapeHtml(txt);
  // `code` first so subsequent markup doesn't eat backticks.
  safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
  safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  safe = safe.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  // Images before links — shared syntax.
  safe = safe.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    (_m, alt, url) => `<img class="md-img" alt="${alt}" src="${safeUrl(url)}" />`,
  );
  safe = safe.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_m, text, url) => `<a href="${safeUrl(url)}" target="_blank" rel="noopener">${text}</a>`,
  );
  safe = safe.replace(
    /\b(TASK-\d{3,4})\b/g,
    '<a class="md-tasklink" data-task="$1">$1</a>',
  );
  return safe;
}

function Inline({ text }: { text: string }) {
  return <span dangerouslySetInnerHTML={{ __html: inlineHtml(text) }} />;
}

export function renderTaskMarkdown(md: string): ReactNode[] {
  if (!md) return [];
  const lines = md.split('\n');
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // blank
    if (!line.trim()) {
      i += 1;
      continue;
    }

    // heading (# .. ####)
    const h = /^(#{1,4})\s+(.+)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const text = h[2];
      const className = `md-h md-h${level}`;
      if (level === 1) out.push(<h2 key={key++} className={className}><Inline text={text} /></h2>);
      else if (level === 2) out.push(<h3 key={key++} className={className}><Inline text={text} /></h3>);
      else if (level === 3) out.push(<h4 key={key++} className={className}><Inline text={text} /></h4>);
      else out.push(<h5 key={key++} className={className}><Inline text={text} /></h5>);
      i += 1;
      continue;
    }

    // fenced code
    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      i += 1;
      out.push(
        <pre key={key++} className="md-pre">
          {lang && <div className="md-lang">{lang}</div>}
          <code>{buf.join('\n')}</code>
        </pre>,
      );
      continue;
    }

    // blockquote
    if (/^>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, ''));
        i += 1;
      }
      out.push(
        <blockquote key={key++} className="md-quote">
          <Inline text={buf.join(' ')} />
        </blockquote>,
      );
      continue;
    }

    // GIVEN / WHEN / THEN / AND callout.
    //
    // Two input shapes we have to support, both in use in real task files:
    //   (1) bare keyword on its own line, as in the Claude Design fixture:
    //       `GIVEN the repro case from TASK-NNN`
    //   (2) bold-keyword list item, as in templates/_base/task.template.md:
    //       `- **Given** the repro case from TASK-NNN`
    //       `- **When**  the fix lands on \`main\``
    //       `- **Then**  all tests pass`
    //
    // gwtMatch returns {keyword, rest} for either shape (case-insensitive,
    // optional leading list marker, optional bold wrapping) or null.
    const gwtMatch = (raw: string): { kw: string; rest: string } | null => {
      const s = raw.trim();
      const patterns: RegExp[] = [
        /^(GIVEN|WHEN|THEN|AND)\s+(.+)$/, // bare uppercase
        /^[-*]\s+\*\*(GIVEN|WHEN|THEN|AND)\*\*\s*[:\-—]?\s*(.+)$/i, // - **Given** rest
        /^\*\*(GIVEN|WHEN|THEN|AND)\*\*\s*[:\-—]?\s*(.+)$/i, // **Given** rest
        /^[-*]\s+(GIVEN|WHEN|THEN|AND)\s+(.+)$/i, // - Given rest (no bold)
      ];
      for (const re of patterns) {
        const m = re.exec(s);
        if (m) return { kw: m[1].toUpperCase(), rest: m[2].trim() };
      }
      return null;
    };

    if (gwtMatch(line)) {
      const rows: { kw: string; rest: string }[] = [];
      while (i < lines.length) {
        const m = gwtMatch(lines[i]);
        if (!m) break;
        rows.push(m);
        i += 1;
      }
      out.push(
        <div key={key++} className="md-gwt">
          {rows.map((r, idx) => (
            <div key={idx} className="md-gwt-row">
              <span className={`md-gwt-kw md-gwt-${r.kw.toLowerCase()}`}>{r.kw}</span>
              <span><Inline text={r.rest} /></span>
            </div>
          ))}
        </div>,
      );
      continue;
    }

    // unordered list (supports [ ] / [x] checkboxes)
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i += 1;
      }
      out.push(
        <ul key={key++} className="md-ul">
          {items.map((it, idx) => {
            const cb = /^\[([ xX])\]\s+(.+)$/.exec(it);
            if (cb) {
              const done = cb[1].toLowerCase() === 'x';
              return (
                <li key={idx} className={`md-li md-check ${done ? 'done' : ''}`}>
                  <span className="md-box">{done ? '✓' : ''}</span>
                  <Inline text={cb[2]} />
                </li>
              );
            }
            return (
              <li key={idx} className="md-li">
                <Inline text={it} />
              </li>
            );
          })}
        </ul>,
      );
      continue;
    }

    // ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i += 1;
      }
      out.push(
        <ol key={key++} className="md-ol">
          {items.map((it, idx) => (
            <li key={idx} className="md-li">
              <Inline text={it} />
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    // horizontal rule
    if (/^---+\s*$/.test(line)) {
      out.push(<hr key={key++} className="md-hr" />);
      i += 1;
      continue;
    }

    // paragraph — consume until blank / new block marker
    const buf = [line];
    i += 1;
    while (
      i < lines.length
      && lines[i].trim()
      && !/^(#|```|>|\s*[-*]\s|\s*\d+\.\s|---)/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    out.push(
      <p key={key++} className="md-p">
        <Inline text={buf.join(' ')} />
      </p>,
    );
  }

  return out;
}

/** Split a TASK-*.md string into (frontmatter-as-object, body). */
export function splitFrontmatter(md: string): {
  frontmatter: Record<string, string | string[]>;
  body: string;
} {
  const m = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(md);
  if (!m) return { frontmatter: {}, body: md };
  const fm: Record<string, string | string[]> = {};
  for (const line of m[1].split('\n')) {
    const kv = /^([\w-]+):\s*(.+)$/.exec(line);
    if (!kv) continue;
    let v: string = kv[2];
    if (v.startsWith('[') && v.endsWith(']')) {
      try {
        fm[kv[1]] = JSON.parse(v) as string[];
        continue;
      } catch {
        /* fall through to string */
      }
    }
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    fm[kv[1]] = v;
  }
  return { frontmatter: fm, body: m[2] };
}
