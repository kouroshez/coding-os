import { SUPPORT_LINKS } from '@/layout/support-links';

// Community / support surface for the Hub (TASK-372). Rendered in the AppShell
// chrome — deliberately OUTSIDE the onboarding wizard tree so the links never
// appear during project creation.
export default function SupportFooter() {
  return (
    <footer
      className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-[var(--cos-border)] bg-[var(--cos-panel)] px-4 py-2 text-xs text-[var(--cos-muted)]"
      aria-label="Support and community"
    >
      <span className="font-semibold text-[var(--cos-text)]">Coding OS</span>
      <span aria-hidden="true">·</span>
      {SUPPORT_LINKS.map((link) => (
        <a
          key={link.label}
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded text-[var(--cos-muted)] transition-colors hover:text-[var(--cos-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cos-accent)]"
        >
          {link.label}
        </a>
      ))}
    </footer>
  );
}
