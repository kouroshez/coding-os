# core/web/ui

Unified React 18 + Vite + TypeScript SPA — graph + board + cognition + search.
Served at `http://127.0.0.1:9188` by FastAPI (`core/web/server.py`) in
production, `http://127.0.0.1:5173` via `npm run dev` (proxies `/api/*`
to :9188).

## Layout

```
src/
├── App.tsx, main.tsx        — entry + router
├── design/                  — ThemeProvider, design tokens
├── layout/                  — AppShell, Inspector, ProjectSwitcher, ErrorBoundary
├── features/
│   ├── cognition/           — trace replay
│   ├── cos-board/           — Scrumban board (incl. useBoardStream SSE)
│   ├── graph/               — Sigma.js canvas, NodeInspector, layouts
│   └── search/              — search UI
├── lib/
│   ├── api-client.ts        — typed fetch wrapper, FastAPI envelope unwrap
│   ├── api-types.ts         — auto-generated from /openapi.json (do not edit)
│   ├── hooks.ts             — shared React hooks
│   └── node-colors.ts       — graph node coloring
├── pages/                   — route entries (HubHome, Graph, Cognition, Search, Settings)
├── store/                   — zustand stores
└── test/setup.ts            — vitest jsdom setup
```

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server on :5173 (HMR, /api proxy → :9188) |
| `npm run build` | Type-check + Vite production build to `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Run vitest once |
| `npm run test:watch` | Vitest watch mode |
| `npm run gen-api` | Regenerate `src/lib/api-types.ts` from running hub's `/openapi.json` |

## API contract

`api-client.ts` is a thin envelope-aware wrapper around `fetch`. It unwraps
the FastAPI shape `{ data, meta }` on 2xx and throws `ApiError` (with
category) on 4xx/5xx.

For per-route type safety, import `paths` from `./api-types` (auto-generated)
and derive request/response shapes:

```ts
import { apiGet, type paths } from '@/lib/api-client';
type CtxResp = paths['/api/graph/context/{uid_or_name}']['get']['responses']['200']['content']['application/json'];
const [ctx] = await apiGet<CtxResp>(`/api/graph/context/${uid}`);
```

Refresh after backend route changes:
```bash
cos hub start         # ensure hub is running on :9188
npm run gen-api
```

## Tests

Vitest + jsdom. Smoke test in `src/lib/api-client.test.ts` covers envelope
unwrap, error mapping, and per-project path rewrite. Add `*.test.ts` /
`*.test.tsx` next to the file under test.

## `coding-os-scrumban/` (sibling dir)

**Not application code.** Design handoff bundle from Claude Design — HTML/CSS/JS
mockups exported as a reference for implementing the board UI. The agent that
built the board feature (`features/cos-board/`) used those mockups as visual spec.
See `coding-os-scrumban/README.md` for the original handoff instructions. Safe
to leave in place; never imported by Vite. Do not delete without checking the
board feature still matches the design.
