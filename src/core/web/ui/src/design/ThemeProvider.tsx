/**
 * Generic design-system theme provider.
 *
 * PURPOSE: Sync theme/aesthetic/density state to <html data-*> attributes
 *          so the CSS token layer (public/cos-board-tokens.css) resolves
 *          to the correct palette for the current feature shell.
 * INPUT:   children (mount point), shell (feature id: cos-board | graph |
 *          search | cognition | hub), initialTweaks (optional override).
 * OUTPUT:  Context exposing { tweaks, setTweaks } via useDesignTheme().
 * NOTES:   Features that need extra tweaks (filters, agentSurface) wrap
 *          this provider with their own context that extends DesignTweaks.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react';
import { DEFAULT_DESIGN_TWEAKS, type DesignTweaks } from './types';

export type FeatureShell = 'cos-board' | 'graph' | 'search' | 'cognition' | 'hub';

interface DesignThemeContextValue {
  tweaks: DesignTweaks;
  setTweaks: Dispatch<SetStateAction<DesignTweaks>>;
  shell: FeatureShell;
}

const DesignThemeContext = createContext<DesignThemeContextValue | null>(null);

export function DesignThemeProvider({
  children,
  shell,
  initialTweaks,
  lockBodyScroll = true,
}: {
  children: ReactNode;
  shell: FeatureShell;
  initialTweaks?: Partial<DesignTweaks>;
  lockBodyScroll?: boolean;
}) {
  const [tweaks, setTweaks] = useState<DesignTweaks>({
    ...DEFAULT_DESIGN_TWEAKS,
    ...initialTweaks,
  });

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', tweaks.theme);
    root.setAttribute('data-aesthetic', tweaks.aesthetic);
    root.setAttribute('data-shell', shell);
    const prevOverflow = document.body.style.overflow;
    if (lockBodyScroll) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      root.removeAttribute('data-shell');
      if (lockBodyScroll) {
        document.body.style.overflow = prevOverflow;
      }
    };
  }, [tweaks.theme, tweaks.aesthetic, shell, lockBodyScroll]);

  const value = useMemo(() => ({ tweaks, setTweaks, shell }), [tweaks, shell]);
  return <DesignThemeContext.Provider value={value}>{children}</DesignThemeContext.Provider>;
}

export function useDesignTheme(): DesignThemeContextValue {
  const ctx = useContext(DesignThemeContext);
  if (!ctx) {
    throw new Error('useDesignTheme must be used within a DesignThemeProvider');
  }
  return ctx;
}
