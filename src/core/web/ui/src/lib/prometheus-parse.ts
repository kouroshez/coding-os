// Tiny Prometheus text-format parser.
// Coding OS metrics use one of three shapes:
//
//   cos_web_requests_total{route='board.list'} 42.0
//   cos_web_request_duration_seconds{route='board.list'}_avg 0.005
//   cos_web_request_duration_seconds{route='board.list'}{quantile='0.95'} 0.011
//
// We don't try to be exhaustive — the goal is to feed the Doctor /
// Health dashboards with the cos_web_* family. # TYPE / # HELP lines
// are ignored.

export interface MetricSample {
  name: string;
  labels: Record<string, string>;
  value: number;
}

const LABEL_RE = /\{([^}]*)\}/g;
const PAIR_RE = /([A-Za-z_][A-Za-z0-9_]*)=['"]([^'"]+)['"]/g;

function parseLabels(blocks: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const block of blocks) {
    PAIR_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = PAIR_RE.exec(block)) !== null) {
      out[m[1]] = m[2];
    }
  }
  return out;
}

export function parsePrometheus(text: string): MetricSample[] {
  const samples: MetricSample[] = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;

    // Find the first whitespace after the metric+labels portion. The
    // value is the LAST whitespace-delimited token; everything before
    // is the identifier.
    const idx = line.lastIndexOf(' ');
    if (idx < 1) continue;
    const head = line.slice(0, idx);
    const valStr = line.slice(idx + 1);
    const value = Number(valStr);
    if (!Number.isFinite(value)) continue;

    // Extract every `{...}` block, then strip them from `head` to get
    // the bare metric name (including any trailing `_count` / `_sum`).
    const blocks: string[] = [];
    let stripped = head;
    LABEL_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = LABEL_RE.exec(head)) !== null) blocks.push(m[1]);
    stripped = stripped.replace(LABEL_RE, '');

    samples.push({
      name: stripped,
      labels: parseLabels(blocks),
      value,
    });
  }
  return samples;
}

/** Index samples by metric name for O(1) lookup in the dashboards. */
export function indexByName(samples: MetricSample[]): Map<string, MetricSample[]> {
  const m = new Map<string, MetricSample[]>();
  for (const s of samples) {
    const arr = m.get(s.name) ?? [];
    arr.push(s);
    m.set(s.name, arr);
  }
  return m;
}

/** Convenience: total of a counter, summed across labels. */
export function sumByName(samples: MetricSample[], name: string): number {
  let total = 0;
  for (const s of samples) if (s.name === name) total += s.value;
  return total;
}
