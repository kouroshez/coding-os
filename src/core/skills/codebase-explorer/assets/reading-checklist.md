<!-- domain:UNIVERSAL | layer:asset | ssot:false | updated:2026-06-04 -->
# Code-Reading Checklist

Use when picking up an unfamiliar area before changing it.

## Orient (cheap, first)
- [ ] Found the entry point (route/command/handler) for the feature.
- [ ] `python3 scripts/outline.py <file>` — have the file's shape.
- [ ] Read the README / docs for the area.
- [ ] Read the tests — intended usage + edge cases.

## Trace
- [ ] Followed the spine of the feature, skimmed off-path helpers.
- [ ] Named the core entity and tracked its shape through transforms.
- [ ] Identified the boundaries (DB / queue / HTTP / other service).

## Switch tools when the question turns precise
- [ ] "who calls / what breaks / rename" → graph-explorer, not more reading.
- [ ] "where is this literal" → search (grep).

## Confirm understanding
- [ ] Can state the model in two sentences; gaps resolved.
- [ ] (If non-trivial) wrote the model down for the next reader.
- [ ] `git log -p --follow <file>` consulted for any surprising code.
