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

const BoardThemeContext = createContext<{
  tweaks: BoardTweaks;
  setTweaks: React.Dispatch<React.SetStateAction<BoardTweaks>>;
} | null>(null);

export function BoardThemeProvider({ children }: { children: ReactNode }) {
  const [tweaks, setTweaks] = useState<BoardTweaks>(DEFAULT_TWEAKS);

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
