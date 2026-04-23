import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { BoardTweaks } from './types';
import { DEFAULT_TWEAKS } from './types';

const BoardThemeContext = createContext<{
  tweaks: BoardTweaks;
  setTweaks: React.Dispatch<React.SetStateAction<BoardTweaks>>;
} | null>(null);

export function BoardThemeProvider({ children }: { children: ReactNode }) {
  const [tweaks, setTweaks] = useState<BoardTweaks>(DEFAULT_TWEAKS);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme);
    document.documentElement.setAttribute('data-aesthetic', tweaks.aesthetic);
    document.documentElement.setAttribute('data-shell', 'cos-board');
    document.body.style.overflow = 'hidden';
    return () => {
      document.documentElement.removeAttribute('data-shell');
      document.body.style.overflow = '';
    };
  }, [tweaks.theme, tweaks.aesthetic]);

  const value = useMemo(() => ({ tweaks, setTweaks }), [tweaks]);
  return <BoardThemeContext.Provider value={value}>{children}</BoardThemeContext.Provider>;
}

export function useBoardTheme() {
  const ctx = useContext(BoardThemeContext);
  if (!ctx) {
    throw new Error('useBoardTheme must be used within BoardThemeProvider');
  }
  return ctx;
}
