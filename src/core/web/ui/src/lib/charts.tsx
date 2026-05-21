// Inline SVG chart primitives.  No external chart library — keeps the
// SPA bundle small and avoids React lifecycle quirks from canvas-based
// charters.  Each component is purely declarative; the caller owns the
// data + rolling-buffer state.

import { useMemo } from 'react';

const PALETTE = {
  line: 'var(--cos-accent, #ff7a3d)',
  area: 'rgba(255,122,61,0.18)',
  grid: 'var(--cos-border, rgba(0,0,0,0.18))',
  muted: 'var(--cos-muted, #6b665e)',
  text: 'var(--cos-text, #221715)',
  danger: '#ef4444',
  ok: '#16a34a',
  warn: '#fbbf24',
};

// ----- Sparkline ------------------------------------------------------
// Compact line chart for a rolling buffer (e.g. last N polled values).
// Auto-scales Y to data range; first sample sits at y0, last at right
// edge — newest on the right is the convention this codebase uses
// (HookStream, presence widget).
export function Sparkline({
  data,
  width = 160,
  height = 36,
  stroke = PALETTE.line,
  fill = PALETTE.area,
  label,
}: {
  data: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
  label?: string;
}) {
  const path = useMemo(() => {
    if (data.length < 2) return { line: '', area: '', last: null };
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = width / (data.length - 1);
    const points = data.map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return [x, y] as const;
    });
    const line = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
    const area = `${line} L ${width} ${height} L 0 ${height} Z`;
    const last = points[points.length - 1];
    return { line, area, last };
  }, [data, width, height]);

  return (
    <svg
      role="img"
      aria-label={label ?? 'sparkline'}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      preserveAspectRatio="none"
      className="block"
    >
      {path.area && <path d={path.area} fill={fill} />}
      {path.line && <path d={path.line} fill="none" stroke={stroke} strokeWidth={1.4} />}
      {path.last && <circle cx={path.last[0]} cy={path.last[1]} r={2} fill={stroke} />}
    </svg>
  );
}

// ----- Horizontal bar list -------------------------------------------
// Renders a sorted top-N bar chart (rows). Each row: label + numeric +
// proportional bar.  Caller sorts upstream — we only render.
export function BarList({
  rows,
  maxValue,
  formatValue,
  emptyText = 'no data',
}: {
  rows: { label: string; value: number; hint?: string }[];
  maxValue?: number;
  formatValue?: (v: number) => string;
  emptyText?: string;
}) {
  if (rows.length === 0) return <p className="text-xs text-[var(--cos-muted)]">{emptyText}</p>;
  const peak = maxValue ?? Math.max(...rows.map((r) => r.value), 1);
  return (
    <ul className="space-y-1">
      {rows.map((r) => {
        const pct = Math.min(100, (r.value / peak) * 100);
        return (
          <li key={r.label} className="flex items-center gap-2 text-[11px]">
            <span className="w-32 shrink-0 truncate font-mono text-[var(--cos-muted)]" title={r.hint ?? r.label}>
              {r.label}
            </span>
            <div className="relative h-3 flex-1 overflow-hidden rounded bg-[var(--cos-grain,rgba(0,0,0,0.05))]">
              <div
                className="absolute inset-y-0 left-0 rounded"
                style={{ width: `${pct}%`, background: PALETTE.line, opacity: 0.85 }}
                aria-hidden
              />
            </div>
            <span className="w-16 shrink-0 text-right font-mono">{formatValue ? formatValue(r.value) : r.value}</span>
          </li>
        );
      })}
    </ul>
  );
}

// ----- Gauge ---------------------------------------------------------
// Simple semicircular gauge: value 0..max projected on an arc, colored
// by threshold.  Used for "health score" / "cap utilisation".
export function Gauge({
  value,
  max,
  label,
  warnFrom = 0.7,
  dangerFrom = 0.9,
  size = 110,
  formatValue,
}: {
  value: number;
  max: number;
  label?: string;
  warnFrom?: number;
  dangerFrom?: number;
  size?: number;
  formatValue?: (v: number, m: number) => string;
}) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const stroke =
    ratio >= dangerFrom ? PALETTE.danger : ratio >= warnFrom ? PALETTE.warn : PALETTE.ok;
  const radius = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;
  // semicircle: angle from π (left) → 0 (right)
  const angle = Math.PI * (1 - ratio);
  const endX = cx + radius * Math.cos(angle);
  const endY = cy - radius * Math.sin(angle);
  // arc flag: large=0 for a semicircle slice
  const startX = cx - radius;
  const startY = cy;
  const arcPath = `M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX.toFixed(2)} ${endY.toFixed(2)}`;
  const bgPath = `M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;
  return (
    <div className="inline-flex flex-col items-center">
      <svg width={size} height={size / 2 + 6} viewBox={`0 0 ${size} ${size / 2 + 6}`} role="img" aria-label={label}>
        <path d={bgPath} fill="none" stroke={PALETTE.grid} strokeWidth={6} strokeLinecap="round" />
        <path d={arcPath} fill="none" stroke={stroke} strokeWidth={6} strokeLinecap="round" />
      </svg>
      <span className="-mt-2 text-sm font-semibold" style={{ color: stroke }}>
        {formatValue ? formatValue(value, max) : `${value} / ${max}`}
      </span>
      {label && <span className="text-[10px] uppercase tracking-wider text-[var(--cos-muted)]">{label}</span>}
    </div>
  );
}

// ----- StatTile ------------------------------------------------------
// Big number + label + optional sparkline + trend indicator.
export function StatTile({
  label,
  value,
  trend,
  spark,
  tone = 'neutral',
}: {
  label: string;
  value: string | number;
  trend?: number; // % vs previous window, +/-
  spark?: number[];
  tone?: 'neutral' | 'ok' | 'warn' | 'danger';
}) {
  const accent =
    tone === 'ok' ? PALETTE.ok : tone === 'warn' ? PALETTE.warn : tone === 'danger' ? PALETTE.danger : PALETTE.line;
  const glowClass =
    tone === 'ok' ? 'glow-emerald' : tone === 'warn' ? 'glow-amber' : tone === 'danger' ? 'glow-rose' : '';
  const trendStr = trend == null ? null : trend === 0 ? '0%' : `${trend > 0 ? '+' : ''}${trend.toFixed(1)}%`;
  const trendColor = trend == null ? PALETTE.muted : trend > 0 ? PALETTE.ok : trend < 0 ? PALETTE.danger : PALETTE.muted;
  return (
    <div className="glass-card rounded-2xl border border-[var(--cos-border)] bg-[var(--cos-panel)]/50 p-4 transition-all duration-200 hover:-translate-y-0.5 shadow-sm">
      <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--cos-muted)]">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`text-2xl font-extrabold tracking-tight ${glowClass}`} style={{ color: accent }}>
          {value}
        </span>
        {trendStr && (
          <span className="text-[10px] font-mono font-semibold" style={{ color: trendColor }}>
            {trendStr}
          </span>
        )}
      </div>
      {spark && spark.length > 1 && (
        <div className="mt-3">
          <Sparkline data={spark} width={150} height={28} stroke={accent} fill={`${accent}15`} label={`${label} trend`} />
        </div>
      )}
    </div>
  );
}
