import { describe, expect, it } from 'vitest';
import fc from 'fast-check';

import { inlineHtml } from './renderTaskMarkdown';

/**
 * Property-based fuzzing of the task-markdown inline renderer.
 *
 * inlineHtml() output goes straight into dangerouslySetInnerHTML, so its one
 * invariant is: whatever markdown a task file carries, the emitted HTML must
 * never gain an executable surface. Example-based tests only cover payloads
 * someone thought of; these generators explore the space around them.
 *
 * Regression anchors: CodeQL js/incomplete-html-attribute-sanitization on the
 * img/a sinks — escapeHtml left `"` and `'` intact, so `![a](x" onerror="…)`
 * closed the attribute, and `[a](javascript:…)` needed no metacharacter at all.
 */

const EXECUTABLE_SCHEME = /^\s*(?:javascript|data|vbscript)\s*:/i;

// The building blocks an attacker composes from, mixed with ordinary prose so
// the generator spends its budget on structure rather than rediscovering '<'.
const HOSTILE_FRAGMENTS = [
  '"', "'", '<', '>', '&', '`', '\\', '\t', '\n', '\0',
  '![', '](', ')', '[', ']', '*', '**',
  'javascript:', 'JaVaScRiPt:', 'java\tscript:', 'data:text/html',
  'onerror=', 'onload=', '<script>', '</script>', 'alert(1)',
  'https://example.com', '/docs/x.md', 'TASK-123', 'plain text',
];

const hostileMarkdown = fc
  .array(fc.constantFrom(...HOSTILE_FRAGMENTS), { minLength: 1, maxLength: 24 })
  .map((parts) => parts.join(''));

function parse(html: string): Document {
  return new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html');
}

// jsdom parsing dominates the runtime, so the budget is spent on breadth of
// generated input rather than repetition; 500 runs keeps each property ~2s.
const RUNS = { numRuns: 500 };
const TIMEOUT_MS = 30_000;

describe('inlineHtml — XSS invariants under fuzzing', () => {
  it('never emits an event-handler attribute', () => {
    fc.assert(
      fc.property(fc.oneof(hostileMarkdown, fc.string()), (md) => {
        for (const el of parse(inlineHtml(md)).querySelectorAll('*')) {
          for (const attr of el.attributes) {
            expect(attr.name.toLowerCase().startsWith('on')).toBe(false);
          }
        }
      }),
      RUNS,
    );
  }, TIMEOUT_MS);

  it('never emits a script element', () => {
    fc.assert(
      fc.property(fc.oneof(hostileMarkdown, fc.string()), (md) => {
        expect(parse(inlineHtml(md)).querySelectorAll('script').length).toBe(0);
      }),
      RUNS,
    );
  }, TIMEOUT_MS);

  it('never emits an executable href or src', () => {
    fc.assert(
      fc.property(fc.oneof(hostileMarkdown, fc.string()), (md) => {
        for (const el of parse(inlineHtml(md)).querySelectorAll('[href], [src]')) {
          for (const name of ['href', 'src']) {
            const value = el.getAttribute(name);
            if (value !== null) expect(EXECUTABLE_SCHEME.test(value)).toBe(false);
          }
        }
      }),
      RUNS,
    );
  }, TIMEOUT_MS);

  it('confines a generated link to a single top-level element', () => {
    // A breakout shows up as an extra element beside the anchor the renderer
    // intended. Nesting inside it (inline `code`, **bold**) is legitimate, so
    // the invariant counts direct children of the container, not descendants.
    fc.assert(
      fc.property(fc.string(), fc.string(), (text, url) => {
        const doc = parse(inlineHtml(`[${text.replace(/[[\]]/g, '')}](${url.replace(/[()]/g, '')})`));
        expect(doc.querySelector('div')!.children.length).toBeLessThanOrEqual(1);
      }),
      RUNS,
    );
  }, TIMEOUT_MS);
});

describe('inlineHtml — non-regression on legitimate markdown', () => {
  it('keeps a query string intact instead of double-escaping the ampersand', () => {
    expect(inlineHtml('[x](https://example.com/?a=1&b=2)')).toContain(
      'href="https://example.com/?a=1&amp;b=2"',
    );
  });

  it('preserves relative links, which carry no scheme', () => {
    expect(inlineHtml('[spec](../docs/engineering/ci-gates.md)')).toContain(
      'href="../docs/engineering/ci-gates.md"',
    );
  });

  it('blanks the href of a javascript: link rather than dropping the anchor', () => {
    expect(inlineHtml('[click](javascript:alert(1)')).toContain('href=""');
  });
});
