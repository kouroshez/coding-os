<!-- domain:FRONTEND | layer:asset | ssot:false | updated:2026-06-04 -->
# Frontend Review Checklist

Run when building or reviewing a component.

## Rendering
- [ ] No new-reference props passed to children/deps unnecessarily (inline `{}`/`[]`/`()=>` hoisted or memoized).
- [ ] List items have a stable `key` — never the array index.
- [ ] `useEffect` has a correct dependency array (not missing, not over-broad).
- [ ] `python3 scripts/check_frontend.py <components>` → `clean`.

## State
- [ ] State lives at the lowest common ancestor of its consumers.
- [ ] Inputs controlled (value + onChange) — one source of truth.
- [ ] Server data via a server-state library (TanStack Query), not hand-rolled useEffect.
- [ ] Layer model respected (server vs client vs URL vs local) — see state-management.

## Safety & UX
- [ ] No `dangerouslySetInnerHTML` without sanitization.
- [ ] Loading + error + empty states handled (not just the happy path).
- [ ] Accessible (semantic elements, labels, focus) — see a11y.

## Performance
- [ ] Long lists virtualized; heavy routes code-split.
- [ ] Web Vitals within budget (see performance).
