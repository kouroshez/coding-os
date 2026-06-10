import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { BoardTweaks } from './types';
import { DEFAULT_TWEAKS } from './types';

/**
 * Board-local theme context.
 *
 * PURPOSE: Thin wrapper that reuses the shared DesignThemeProvider and
 *          keeps board-only tweaks (filters, agentSurface, WIP toggles)
 *          that do not belong to the shared DesignTweaks surface.
 * NOTES:   Sets data-shell="cos-board" via the generic provider; other
 *          features set their own shell when they mount.
 */

import { DesignThemeProvider } from '@/design';
import { useThemeStore } from '@/store/theme-store';

const BoardThemeContext = createContext<{
  tweaks: BoardTweaks;
  setTweaks: React.Dispatch<React.SetStateAction<BoardTweaks>>;
} | null>(null);

// Board view-layout toggles persist across reloads (like cos-zoom /
// cos-collapsed-lanes in CosBoardPage). Without this, switching to flat and
// refreshing reverted to swimlanes — DEFAULT_TWEAKS won on every mount.
const VIEW_PREFS_KEY = 'cos-board-view';

function loadViewPrefs(): Partial<Pick<BoardTweaks, 'showSwimlanes' | 'showArchive'>> {
  try {
    const raw = localStorage.getItem(VIEW_PREFS_KEY);
    if (!raw) return {};
    const p = JSON.parse(raw) as Record<string, unknown>;
    const out: Partial<Pick<BoardTweaks, 'showSwimlanes' | 'showArchive'>> = {};
    if (typeof p.showSwimlanes === 'boolean') out.showSwimlanes = p.showSwimlanes;
    if (typeof p.showArchive === 'boolean') out.showArchive = p.showArchive;
    return out;
  } catch {
    return {};
  }
}

export function BoardThemeProvider({ children }: { children: ReactNode }) {
  const [tweaks, setTweaks] = useState<BoardTweaks>(() => ({
    ...DEFAULT_TWEAKS,
    theme: useThemeStore.getState().theme,
    ...loadViewPrefs(),
  }));

  // Persist the view-layout toggles whenever they change.
  useEffect(() => {
    try {
      localStorage.setItem(
        VIEW_PREFS_KEY,
        JSON.stringify({ showSwimlanes: tweaks.showSwimlanes, showArchive: tweaks.showArchive }),
      );
    } catch {
      // storage disabled/full — non-fatal; the toggle just won't persist.
    }
  }, [tweaks.showSwimlanes, tweaks.showArchive]);

  // Mirror the global theme-store so the board theme follows the header
  // toggle (the Theme tweak below writes back to the store) — no divergence.
  useEffect(() => {
    return useThemeStore.subscribe((s) =>
      setTweaks((prev) => (prev.theme === s.theme ? prev : { ...prev, theme: s.theme })),
    );
  }, []);

  // Keep <html data-*> in sync when filters/density/agentSurface change
  // through the local BoardTweaks surface.  DesignThemeProvider already
  // manages the shared attributes on mount; we mirror theme/aesthetic
  // here because BoardTweaks extends DesignTweaks with extra keys.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-aesthetic', tweaks.aesthetic);
  }, [tweaks.theme, tweaks.aesthetic]);

  const value = useMemo(() => ({ tweaks, setTweaks }), [tweaks]);
  return (
    <DesignThemeProvider
      shell="cos-board"
      initialTweaks={{
        theme: tweaks.theme,
        density: tweaks.density,
        aesthetic: tweaks.aesthetic,
        quietMode: tweaks.quietMode,
      }}
    >
      <BoardThemeContext.Provider value={value}>{children}</BoardThemeContext.Provider>
    </DesignThemeProvider>
  );
}

export function useBoardTheme() {
  const ctx = useContext(BoardThemeContext);
  if (!ctx) {
    throw new Error('useBoardTheme must be used within BoardThemeProvider');
  }
  return ctx;
}
