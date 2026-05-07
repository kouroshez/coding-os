# coding-os — Development Makefile
# This project dogfoods its own Makefile.base

# Override COS paths for self-development
COS_ROOT := $(shell pwd)
COS_SCRIPTS := $(COS_ROOT)/core/scripts
COS_HOOKS := $(COS_ROOT)/core/hooks

export COS_STATE_DIR ?= .coding-os
export COS_DB_PATH ?= $(COS_STATE_DIR)/coding-os.db
export COS_BRAIN_DIR ?= $(COS_ROOT)/core/thinking_os

# ── Include base targets ────────────────────────────────────────────
include templates/_base/Makefile.base

# ── Project-Specific Overrides ──────────────────────────────────────
# Note: verify is overridden from base to add MCP test

.PHONY: test-mcp
test-mcp: ## Run MCP server self-test
	@mkdir -p /tmp/cos-test
	@cd core/thinking_os && COS_DB_PATH=/tmp/cos-test/test.db uv run python server.py --test 2>&1 | grep -E "PASS|FAIL"
	@rm -f /tmp/cos-test/test.db /tmp/cos-test/test.db-shm /tmp/cos-test/test.db-wal
	@rmdir /tmp/cos-test 2>/dev/null || true

.PHONY: test-install-claude test-install
test-install-claude: ## Claude-specific install smoke test (deeper than verify-install: checks generated files). Renamed from `test-install` to make adapter scope explicit.
	@mkdir -p /tmp/cos-install-test
	@cd /tmp/cos-install-test && bash $(COS_ROOT)/adapters/claude/install.sh 2>&1
	@echo "Checking generated files..."
	@ls /tmp/cos-install-test/.claude/settings.json > /dev/null && echo "  OK: settings.json"
	@ls /tmp/cos-install-test/.claude/hooks/thinking_os-gate.sh > /dev/null && echo "  OK: hooks symlinked"
	@ls /tmp/cos-install-test/.claude/rules/thinking_os.md > /dev/null && echo "  OK: rules symlinked"
	@rm -r /tmp/cos-install-test
	@echo "Install test PASSED"

# Backward-compat alias — old `make test-install` still works.
test-install: test-install-claude

.PHONY: test-cli
test-cli: ## Test CLI health command
	@uv run python -m cli.main health --project-dir .

.PHONY: verify-install
verify-install: ## Sandbox-test every adapters/*/install.sh with hard 15s timeout (catches bash 5.3.9 heredoc deadlocks BEFORE `make sync` does). Data-driven (Rule 11) — auto-detects new adapters via adapters/<id>/adapter.yaml.
	@found=0; \
	for adapter_yml in adapters/*/adapter.yaml; do \
	  [ -f "$$adapter_yml" ] || continue; \
	  adapter_dir=$$(dirname "$$adapter_yml"); \
	  adapter=$$(basename "$$adapter_dir"); \
	  if [ ! -f "$$adapter_dir/install.sh" ]; then \
	    printf "  skip %s (no install.sh)\n" "$$adapter"; \
	    continue; \
	  fi; \
	  found=$$((found + 1)); \
	  TEST=$$(mktemp -d); \
	  printf "  testing adapters/%s/install.sh ... " "$$adapter"; \
	  ( cd "$$TEST" && bash $(COS_ROOT)/adapters/$$adapter/install.sh ) > "$$TEST/install.log" 2>&1 & \
	  BPID=$$!; W=0; \
	  while kill -0 $$BPID 2>/dev/null && [ $$W -lt 15 ]; do sleep 1; W=$$((W+1)); done; \
	  if kill -0 $$BPID 2>/dev/null; then \
	    kill -9 $$BPID; \
	    echo "FAIL — hung > 15s"; \
	    echo "  --- last log lines ---"; tail -8 "$$TEST/install.log" | sed 's/^/  /'; \
	    rm -rf "$$TEST"; exit 1; \
	  fi; \
	  echo "OK ($${W}s)"; \
	  rm -rf "$$TEST"; \
	done; \
	if [ "$$found" -eq 0 ]; then \
	  echo "  WARN: no adapters with install.sh discovered under adapters/" >&2; \
	  exit 1; \
	fi

.PHONY: verify
verify: verify-hooks verify-install test-mcp ## Run all verification checks
	@echo ""
	@echo "All checks passed."

.PHONY: verify-claude
verify-claude: ## Claude-only fast subset: dispatcher + adapter + skill + branding tests (~30s)
	@echo "Running Claude-only verification subset..."
	@uv run --extra rag pytest \
	    core/thinking_os/tests/test_dispatcher.py \
	    core/thinking_os/tests/test_db.py \
	    tests/test_claude_dispatcher_options.py \
	    tests/test_skill_frontmatter.py \
	    tests/test_branding.py \
	    tests/test_no_hardcoded_anthropic.py \
	    tests/test_adapters.py \
	    -q --tb=short
	@echo ""
	@echo "Claude verification passed."

.PHONY: eval-operational eval-sandboxes eval-clean
eval-operational: ## Full operational evaluation — scaffolds sandboxes, runs all checks, writes .build/
	@uv run python scripts/operational_eval.py all

eval-sandboxes: ## Rebuild only the .build/sandboxes/ (fast, no verify steps)
	@uv run python scripts/operational_eval.py sandboxes

eval-clean: ## Remove .build/ entirely
	@uv run python scripts/operational_eval.py clean

.PHONY: debug-init debug-init-codex debug-doctor debug-inspect debug-clean manifest-regen
debug-init: ## cos init into .build/debug/the-script-output (Claude + nextjs)
	@uv run python -m cli.main init --agent claude --debug --name the-script-output --template nextjs --no-git --force

debug-init-codex: ## cos init into .build/debug/the-script-output-codex (Codex + nextjs)
	@uv run python -m cli.main init --agent codex --debug --name the-script-output-codex --template nextjs --no-git --force

debug-doctor: ## Run doctor on the Claude debug project
	@uv run python -m cli.main doctor --project-dir .build/debug/the-script-output

debug-inspect: ## List files + show key configs for the debug project
	@find .build/debug/the-script-output -type f 2>/dev/null | head -80
	@echo "---"
	@cat .build/debug/the-script-output/.coding-os.yaml 2>/dev/null || echo "no config"

debug-clean: ## Remove only .build/debug/
	@rm -rf .build/debug

manifest-regen: ## Regenerate core/scaffold_manifest.json from fresh sandboxes
	@uv run python scripts/generate_manifest.py

.PHONY: regen-rules regen-doctor-schema
regen-rules: ## Regenerate core/rules/{dimension-registry,skill-enforcement}.md from stack yaml
	@uv run python scripts/regen_rules.py

regen-doctor-schema: ## Regenerate core/doctor-config.yaml::schema from live db.py
	@uv run python scripts/regen_doctor_schema.py

.PHONY: logs-trim
logs-trim: ## Trim .coding-os/.hooks.log to last 200 lines (manual override of the opportunistic truncator)
	@LOG="$${COS_STATE_DIR:-.coding-os}/.hooks.log"; \
	if [ -f "$$LOG" ]; then \
	  BEFORE=$$(wc -l < "$$LOG"); \
	  tail -n 200 "$$LOG" > "$$LOG.tmp" && mv "$$LOG.tmp" "$$LOG"; \
	  AFTER=$$(wc -l < "$$LOG"); \
	  echo "  trimmed: $$BEFORE → $$AFTER lines"; \
	else \
	  echo "  no log at $$LOG"; \
	fi

.PHONY: dogfood-claude dogfood
dogfood-claude: ## Re-render only the Claude adapter (.claude/ + .mcp.json). Fast Claude-only iteration; for all-adapter sync use `make sync` or `make dogfood-full`.
	@bash adapters/claude/install.sh
	@echo "  Reload Claude Code to pick up the new config."

# Backward-compat alias — old `make dogfood` still works.
dogfood: dogfood-claude

.PHONY: dogfood-full
dogfood-full: ## Re-render every adapter discovered under adapters/ — re-links core + stack skills. Data-driven (Rule 11) — auto-detects new adapters via adapters/<id>/adapter.yaml.
	@found=0; \
	for adapter_yml in adapters/*/adapter.yaml; do \
	  [ -f "$$adapter_yml" ] || continue; \
	  adapter_dir=$$(dirname "$$adapter_yml"); \
	  if [ ! -f "$$adapter_dir/install.sh" ]; then \
	    printf "  skip %s (no install.sh)\n" "$$(basename $$adapter_dir)"; \
	    continue; \
	  fi; \
	  bash "$$adapter_dir/install.sh"; \
	  found=$$((found + 1)); \
	done; \
	if [ "$$found" -eq 0 ]; then \
	  echo "  WARN: no adapters with install.sh discovered under adapters/" >&2; \
	  exit 1; \
	fi; \
	echo "  Reload your agent runtime to pick up the new config ($$found adapter(s) installed)."

.PHONY: sync
sync: regen-adapter-templates dogfood-full ## One-shot: regen templates + re-link hooks/skills into every adapter discovered under adapters/. Data-driven (Rule 11) — handles new adapters automatically.
	@echo ""
	@echo "  ✅ Adapter sync complete."
	@echo ""
	@adapter_ids=$$(for d in adapters/*/adapter.yaml; do [ -f "$$d" ] && basename $$(dirname "$$d"); done | tr '\n' ',' | sed 's/,$$//; s/,/, /g'); \
	wrapper_dirs=$$(for d in adapters/*/adapter.yaml; do [ -f "$$d" ] && printf ".%s/ " "$$(basename $$(dirname "$$d"))"; done); \
	echo "  Adapters synced: $$adapter_ids"; \
	echo ""; \
	echo "  What just happened:"; \
	echo "    1. core/hooks/registry.yaml     → adapters/*/[settings|hooks].template.json"; \
	echo "    2. core/hooks/*.sh              → $$wrapper_dirs(hooks/, symlinks)"; \
	echo "    3. core/rules/*.md              → $$wrapper_dirs(rules/, symlinks)"; \
	echo "    4. core/skills/*/               → $$wrapper_dirs(skills/, symlinks)"; \
	echo "    5. templates/<stack>/skills/*/  → $$wrapper_dirs(skills/, stack overlay per installed-manifest.json)"; \
	echo "    6. core/commands/*.md           → $$wrapper_dirs(commands/, symlinks)"
	@echo ""
	@echo "  Reload your agent runtime to read the refreshed configs."

.PHONY: codex-mcp
codex-mcp: ## Re-register coding-os MCP in ~/.codex/config.toml (install.sh already does this; use for diagnostics)
	@uv run python -m cli.main codex-mcp-install

.PHONY: regen-adapter-templates
regen-adapter-templates: ## Regenerate adapters/*/[settings|hooks].template.json from core/hooks/registry.yaml
	@uv run python -m cli.hook_renderer

.PHONY: audit
audit: ## Run stale reference audit
	@echo "=== Stale Reference Audit ==="
	@echo -n "nako_ in code: " && grep -rn "nako_" --include="*.py" --include="*.sh" --include="*.json" 2>/dev/null | grep -v __pycache__ | grep -v .venv | grep -v .git | wc -l | tr -d ' '
	@echo -n ".claude/ in hooks (non-legit): " && grep -rn '\.claude/' core/hooks/ | grep -vE 'cos-env|legacy|fallback|pattern|skip|\.claude/\*|adapter|\.claude/settings|\.claude/skills|\.claude/hooks/test\.sh|\.claude/rules' | wc -l | tr -d ' '

.PHONY: cos-decay
cos-decay: ## Run confidence decay on learned patterns
	@cd core/thinking_os && COS_DB_PATH=$(COS_DB_PATH) uv run python decay.py

.PHONY: cos-decay-dry
cos-decay-dry: ## Preview confidence decay (no changes)
	@cd core/thinking_os && COS_DB_PATH=$(COS_DB_PATH) uv run python decay.py --dry-run

.PHONY: cos-stats
cos-stats: ## Show thinking_os DB statistics
	@cd core/thinking_os && COS_DB_PATH=$(COS_DB_PATH) uv run python -c "from db import init_db, get_db_stats; import json; c=init_db('$(COS_DB_PATH)'); print(json.dumps(get_db_stats(c), indent=2)); c.close()"

.PHONY: cos-compress
cos-compress: ## Compress old observations in DB
	@cd core/thinking_os && COS_DB_PATH=$(COS_DB_PATH) uv run python compress.py

.PHONY: stats
stats: ## Show project statistics
	@echo "=== coding-os Stats ==="
	@echo -n "Total files: " && find . -type f ! -path "*__pycache__*" ! -path "*.pyc" ! -path "*/.venv/*" ! -path "*/.git/*" ! -name ".DS_Store" | wc -l | tr -d ' '
	@echo -n "Core hooks: " && ls core/hooks/*.sh | wc -l | tr -d ' '
	@echo -n "Core scripts: " && ls core/scripts/*.sh | wc -l | tr -d ' '
	@echo -n "Core skills: " && ls core/skills/*/SKILL.md | wc -l | tr -d ' '
	@echo -n "Templates: " && find templates -type f | wc -l | tr -d ' '

.PHONY: docs-index-regen
docs-index-regen: ## Regenerate every docs/<dir>/00-index.md from frontmatter (TASK-157+161)
	@python3 scripts/regen_doc_index.py docs --all

.PHONY: docs-index-regen-dry
docs-index-regen-dry: ## Preview docs-index-regen output without writing
	@python3 scripts/regen_doc_index.py docs --all --dry-run

# ── Scheduled Jobs (CRON A + B) ─────────────────────────────────────
_PLIST_SRC  := $(COS_ROOT)/core/scheduled/launchd/com.codingos.nightly.plist.template
_PLIST_DEST := $(HOME)/Library/LaunchAgents/com.codingos.nightly.plist
_UV         := $(shell which uv)
# Override: COS_CRON_HOUR=22 make cron-install
COS_CRON_HOUR ?= 3
# Runtime PATH captured at install time so launchd inherits user's uv location
_RUNTIME_PATH := $(shell echo $$PATH)

.PHONY: cron-install
cron-install: ## Install + load nightly launchd job (macOS only; COS_CRON_HOUR=3 override)
	@mkdir -p $(HOME)/.coding-os/scheduled
	@sed \
		-e 's|{{CODING_OS_ROOT}}|$(COS_ROOT)|g' \
		-e 's|{{UV_PATH}}|$(_UV)|g' \
		-e 's|{{HOME}}|$(HOME)|g' \
		-e 's|{{PATH}}|$(_RUNTIME_PATH)|g' \
		-e 's|{{CRON_HOUR}}|$(COS_CRON_HOUR)|g' \
		$(_PLIST_SRC) > $(_PLIST_DEST)
	@launchctl load -w $(_PLIST_DEST)
	@echo "✓ cron-install: com.codingos.nightly loaded (runs daily at $(COS_CRON_HOUR):00)"
	@echo "  plist: $(_PLIST_DEST)"
	@echo "  logs:  $(HOME)/.coding-os/scheduled/"

.PHONY: cron-uninstall
cron-uninstall: ## Unload + remove nightly launchd job
	@launchctl unload -w $(_PLIST_DEST) 2>/dev/null || true
	@rm -f $(_PLIST_DEST)
	@echo "✓ cron-uninstall: com.codingos.nightly removed"

.PHONY: cron-run
cron-run: ## Run nightly maintenance right now (all projects)
	@$(_UV) run --project $(COS_ROOT) python $(COS_ROOT)/core/scheduled/nightly.py $(ARGS)

.PHONY: cron-dry
cron-dry: ## Simulate nightly run without writing (ARGS passthrough)
	@$(_UV) run --project $(COS_ROOT) python $(COS_ROOT)/core/scheduled/nightly.py --dry-run --verbose

.PHONY: cron-status
cron-status: ## Show last nightly run summary
	@if [ -f "$(HOME)/.coding-os/scheduled/last_summary.json" ]; then \
		cat "$(HOME)/.coding-os/scheduled/last_summary.json"; \
	else \
		echo "No nightly run recorded yet. Run: make cron-run"; \
	fi

.PHONY: cron-reset
cron-reset: ## Reset consecutive_failures counter for all projects
	@$(_UV) run --project $(COS_ROOT) python $(COS_ROOT)/core/scheduled/nightly.py --reset-failures --dry-run

.PHONY: cron-b-setup
cron-b-setup: ## Print CronCreate invocation for CRON B (weekly narrative agent)
	@echo "=== CRON B — Weekly Narrative Agent ==="
	@echo "Copy the prompt below into Claude Code and approve the CronCreate call."
	@echo ""
	@echo "Schedule: every Monday 09:00 (0 9 * * 1)"
	@echo ""
	@python3 -c "from core.scheduled.nightly import CRON_B_PROMPT; print(CRON_B_PROMPT)"
	@echo ""
	@echo "In Claude Code: 'Set up a weekly cron for me using CronCreate with the above prompt.'"

.PHONY: ui-dev
ui-dev: ## Vite dev server with HMR → http://127.0.0.1:5173 (proxies /api to hub on 9188)
	@echo "Starting Vite dev server — edits hot-reload without rebuild."
	@echo "  Dev URL:  http://127.0.0.1:5173"
	@echo "  API:      proxied to http://127.0.0.1:9188 (make sure hub is up: cos hub start)"
	@cd core/web/ui && npm run dev

.PHONY: ui-build
ui-build: ## Production rebuild of the SPA — hub at :9188 serves the new bundle
	@cd core/web/ui && npm run build
	@echo "  SPA rebuilt → core/web/ui/dist/  (hub picks up automatically; hard-refresh browser)"
