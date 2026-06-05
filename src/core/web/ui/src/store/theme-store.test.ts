import { beforeEach, describe, expect, it } from 'vitest';

import { useThemeStore } from './theme-store';

const KEY = 'cos-theme';

describe('theme-store', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    useThemeStore.setState({ theme: 'dark' });
  });

  it('setTheme persists to localStorage and applies data-theme', () => {
    useThemeStore.getState().setTheme('light');
    expect(useThemeStore.getState().theme).toBe('light');
    expect(window.localStorage.getItem(KEY)).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('toggle flips dark <-> light', () => {
    expect(useThemeStore.getState().theme).toBe('dark');
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().theme).toBe('light');
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().theme).toBe('dark');
  });

  it('toggle persists + applies data-theme on each flip', () => {
    useThemeStore.getState().toggle();
    expect(window.localStorage.getItem(KEY)).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('notifies subscribers on change (provider sync contract)', () => {
    let seen: string | null = null;
    const unsub = useThemeStore.subscribe((s) => {
      seen = s.theme;
    });
    useThemeStore.getState().setTheme('light');
    expect(seen).toBe('light');
    unsub();
  });
});
