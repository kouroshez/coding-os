import { memo, useCallback, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeHighlight from 'rehype-highlight';

export interface MarkdownBlockProps {
  source: string;
  className?: string;
}

// Strong-RTL Unicode blocks: Hebrew (U+0590–U+05FF), Arabic (U+0600–U+06FF,
// U+0750–U+077F), Arabic Supplement, Syriac, Thaana, NKo, Samaritan,
// plus the Arabic presentation forms (U+FB50–U+FDFF, U+FE70–U+FEFF) that
// Persian/Arabic text commonly normalises to.  We deliberately ignore
// neutral characters (digits, punctuation, ASCII), so the test is "does
// this string contain ANY strong-RTL character?" — exactly the Google
// Docs behaviour the user wants: any Persian present → whole block RTL.
const STRONG_RTL_RE = /[֐-׿؀-ۿ܀-ݏݐ-ݿހ-޿߀-߿ࠀ-࠿ࡀ-࡟ࢠ-ࣿיִ-﷿ﹰ-﻿]/;  // eslint-disable-line no-irregular-whitespace -- U+FEFF is a deliberate regex range bound

function hasStrongRtl(text: string): boolean {
  return STRONG_RTL_RE.test(text);
}

// Walk a React children tree and concatenate every text leaf.
// rehype-highlight wraps tokens in nested <span>s so a DOM .innerText
// read is the only fully-accurate fallback; the React-tree walk covers
// assistant prose well and avoids a useRef + DOM read per code block.
function extractText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (typeof node === 'object' && 'props' in node) {
    const el = node as { props?: { children?: ReactNode } };
    return extractText(el.props?.children);
  }
  return '';
}

function CodeBlock({
  children,
  language,
}: {
  children: ReactNode;
  language: string | null;
}) {
  const [copied, setCopied] = useState(false);
  const onCopy = useCallback(async () => {
    const text = extractText(children).replace(/\n$/, '');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API blocked (insecure context) — still flash so the
      // user knows the click registered and can ⌘-C the selection.
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }, [children]);

  return (
    <div
      dir="ltr"
      className="group relative my-2 overflow-hidden rounded-lg border border-zinc-700/60 bg-zinc-900 text-zinc-100"
    >
      <div className="flex items-center justify-between border-b border-zinc-700/60 bg-zinc-800/80 px-3 py-1">
        <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-400">
          {language ?? 'code'}
        </span>
        <button
          type="button"
          onClick={onCopy}
          aria-label="Copy code to clipboard"
          className={[
            'rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]',
            copied
              ? 'bg-emerald-500/25 text-emerald-300'
              : 'text-zinc-400 hover:bg-zinc-700/60 hover:text-zinc-100',
          ].join(' ')}
        >
          {copied ? '✓ copied' : 'copy'}
        </button>
      </div>
      <pre className="cos-code-block m-0 max-h-[480px] overflow-auto p-3 text-[12.5px] leading-snug text-zinc-100 cos-scroll">
        {children}
      </pre>
    </div>
  );
}

function MarkdownBlockInner({ source, className = '' }: MarkdownBlockProps) {
  // RTL priority rule — any strong-RTL character in the message anchors
  // the entire block to RTL.  Matches Google Docs / iOS / Slack: a
  // Persian author writing about an English file path expects RTL flow,
  // not LTR because the path is at the start.  Per-block dir="auto" on
  // every <p>/<li>/<h*>/<blockquote> still lets all-English paragraphs
  // inside a Persian message render LTR.
  const outerDir: 'rtl' | 'ltr' = hasStrongRtl(source) ? 'rtl' : 'ltr';
  return (
    <div
      dir={outerDir}
      className={[
        'cos-markdown text-sm leading-relaxed text-[var(--cos-text)]',
        outerDir === 'rtl' ? 'text-right' : 'text-left',
        className,
      ].join(' ')}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noreferrer noopener"
              className="text-[var(--cos-accent)] underline-offset-2 hover:underline"
            />
          ),
          code: ({ node: _node, className: codeClass, children, ...props }) => {
            const isBlock = /language-/.test(codeClass ?? '');
            if (isBlock) {
              return (
                <code className={codeClass} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                dir="ltr"
                className="rounded bg-[var(--cos-panel)] px-1 py-0.5 font-mono text-[12px] text-[var(--cos-accent)]"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ node: _node, children }) => {
            // Pull the language hint from the inner <code className="language-xxx">
            // emitted by rehype-highlight.  Null falls back to a "code" label.
            let language: string | null = null;
            if (children && typeof children === 'object' && 'props' in children) {
              const el = children as { props?: { className?: string } };
              const cls = el.props?.className;
              if (typeof cls === 'string') {
                const m = /language-([\w-]+)/.exec(cls);
                if (m) language = m[1];
              }
            }
            return <CodeBlock language={language}>{children}</CodeBlock>;
          },
          h1: ({ node: _node, ...props }) => (
            <h1 dir="auto" className="mb-2 mt-3 text-xl font-bold text-[var(--cos-text)]" {...props} />
          ),
          h2: ({ node: _node, ...props }) => (
            <h2 dir="auto" className="mb-2 mt-3 text-lg font-bold text-[var(--cos-text)]" {...props} />
          ),
          h3: ({ node: _node, ...props }) => (
            <h3 dir="auto" className="mb-1.5 mt-2.5 text-base font-bold text-[var(--cos-text)]" {...props} />
          ),
          h4: ({ node: _node, ...props }) => (
            <h4 dir="auto" className="mb-1.5 mt-2 text-sm font-bold text-[var(--cos-text)]" {...props} />
          ),
          p: ({ node: _node, ...props }) => <p dir="auto" className="my-1.5" {...props} />,
          ul: ({ node: _node, ...props }) => (
            <ul dir="auto" className="my-1.5 list-disc ps-6" {...props} />
          ),
          ol: ({ node: _node, ...props }) => (
            <ol dir="auto" className="my-1.5 list-decimal ps-6" {...props} />
          ),
          li: ({ node: _node, ...props }) => <li dir="auto" className="my-0.5" {...props} />,
          blockquote: ({ node: _node, ...props }) => (
            <blockquote
              dir="auto"
              className="my-2 border-s-2 border-[var(--cos-border)] ps-3 text-[var(--cos-muted)]"
              {...props}
            />
          ),
          table: ({ node: _node, ...props }) => (
            <div dir="ltr" className="my-2 overflow-x-auto cos-scroll">
              <table
                className="min-w-full border-collapse border border-[var(--cos-border)] text-[12px]"
                {...props}
              />
            </div>
          ),
          th: ({ node: _node, ...props }) => (
            <th
              className="border border-[var(--cos-border)] bg-[var(--cos-panel)] px-2 py-1 text-start font-semibold"
              {...props}
            />
          ),
          td: ({ node: _node, ...props }) => (
            <td className="border border-[var(--cos-border)] px-2 py-1" {...props} />
          ),
          hr: ({ node: _node, ...props }) => (
            <hr className="my-3 border-[var(--cos-border)]" {...props} />
          ),
          strong: ({ node: _node, ...props }) => (
            <strong className="font-semibold text-[var(--cos-text)]" {...props} />
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}

export const MarkdownBlock = memo(MarkdownBlockInner);
