# coding-os — Development Makefile
# This project dogfoods its own Makefile.base

# Override COS paths for self-development
COS_ROOT := $(shell pwd)
COS_SCRIPTS := $(COS_ROOT)/core/scripts
COS_HOOKS := $(COS_ROOT)/core/hooks

export COS_STATE_DIR ?= .coding-os
export COS_DB_PATH ?= $(COS_STATE_DIR)/thinking_os.db
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

.PHONY: test-install
test-install: ## Test Claude adapter install on temp dir
	@mkdir -p /tmp/cos-install-test
	@cd /tmp/cos-install-test && bash $(COS_ROOT)/adapters/claude/install.sh 2>&1
	@echo "Checking generated files..."
	@ls /tmp/cos-install-test/.claude/settings.json > /dev/null && echo "  OK: settings.json"
	@ls /tmp/cos-install-test/.claude/hooks/thinking_os-gate.sh > /dev/null && echo "  OK: hooks symlinked"
	@ls /tmp/cos-install-test/.claude/rules/thinking_os.md > /dev/null && echo "  OK: rules symlinked"
	@rm -r /tmp/cos-install-test
	@echo "Install test PASSED"

.PHONY: test-cli
test-cli: ## Test CLI health command
	@uv run python -m cli.main health --project-dir .

.PHONY: verify-install
verify-install: ## Sandbox-test all 3 adapter install.sh scripts with hard 15s timeout (catches bash 5.3.9 heredoc deadlocks BEFORE `make sync` does)
	@for adapter in claude codex cursor; do \
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
	done

.PHONY: verify
verify: verify-hooks verify-install test-mcp ## Run all verification checks
	@echo ""
	@echo "All checks passed."

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

.PHONY: dogfood
dogfood: ## Re-render this repo's .claude/ + .mcp.json by running the Claude adapter install
	@bash adapters/claude/install.sh
	@echo "  Reload Claude Code to pick up the new config."

.PHONY: dogfood-full
dogfood-full: ## Re-render claude + codex + cursor adapters — re-links core + stack skills
	@bash adapters/claude/install.sh
	@bash adapters/codex/install.sh
	@bash adapters/cursor/install.sh
	@echo "  Reload your agent (Claude Code, Codex CLI, or Cursor) to pick up the new config."

.PHONY: sync
sync: regen-adapter-templates dogfood-full ## One-shot: regen templates + re-link hooks/skills into claude, codex, and cursor (run after adding any core/ or templates/ asset)
	@echo ""
	@echo "  ✅ Adapter sync complete."
	@echo ""
	@echo "  What just happened:"
	@echo "    1. core/hooks/registry.yaml     → adapters/*/[settings|hooks].template.json"
	@echo "    2. core/hooks/*.sh              → .claude/ + .codex/ + .cursor/hooks/  (symlinks)"
	@echo "    3. core/rules/*.md              → .claude/ + .codex/ + .cursor/rules/ (symlinks)"
	@echo "    4. core/skills/*/               → .claude/ + .codex/ + .cursor/skills/ (symlinks)"
	@echo "    5. templates/<stack>/skills/*/  → .claude/ + .codex/ + .cursor/skills/ (stack overlay, per installed-manifest.json)"
	@echo "    6. core/commands/*.md           → .claude/ + .codex/ + .cursor/commands/ (symlinks)"
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
