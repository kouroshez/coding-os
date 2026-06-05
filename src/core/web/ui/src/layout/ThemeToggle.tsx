import { Moon, Sun } from 'lucide-react';
import { useThemeStore } from '@/store/theme-store';

/**
 * Global dark/light switch — lives in the AppShell header. Persists via the
 * theme-store (localStorage + `data-theme` on <html>), so the choice
 * survives reloads and applies before first paint.
 */
export default function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      onClick={toggle}
      title={`Switch to ${next} mode`}
      aria-label={`Switch to ${next} mode`}
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--cos-border)] bg-[var(--cos-panel)] text-[var(--cos-muted)] transition-colors hover:border-[var(--cos-accent)] hover:text-[var(--cos-text)]"
    >
      {theme === 'dark' ? <Sun size={15} aria-hidden /> : <Moon size={15} aria-hidden />}
    </button>
  );
}
