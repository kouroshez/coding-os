import { describe, expect, it } from 'vitest';
import { applyHubDirection, resolveHubDir } from './direction';

describe('direction seam (TASK-251)', () => {
  it('defaults to ltr for empty / non-rtl input', () => {
    expect(resolveHubDir(undefined)).toBe('ltr');
    expect(resolveHubDir(null)).toBe('ltr');
    expect(resolveHubDir('')).toBe('ltr');
    expect(resolveHubDir('en')).toBe('ltr');
  });

  it('honors rtl case- and space-insensitively', () => {
    expect(resolveHubDir('rtl')).toBe('rtl');
    expect(resolveHubDir(' RTL ')).toBe('rtl');
  });

  it('applyHubDirection sets <html dir> from an explicit value', () => {
    const dir = applyHubDirection('rtl', document);
    expect(dir).toBe('rtl');
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    applyHubDirection('ltr', document);
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
  });
});
