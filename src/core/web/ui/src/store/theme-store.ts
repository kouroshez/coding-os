import { create } from 'zustand';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'cos-theme';

function readInitial(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === 'light' || saved === 'dark' ? saved : 'dark';
}

function applyToDocument(theme: Theme): void {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
  }
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readInitial(),
  setTheme: (theme) => {
    if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, theme);
    applyToDocument(theme);
    set({ theme });
  },
  toggle: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
}));

// Apply the persisted choice on module load so the first paint matches the
// toggle, before any DesignThemeProvider mounts.
applyToDocument(useThemeStore.getState().theme);
