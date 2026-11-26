# Supply-Chain Hardening

The most common vector in the 2024-2025 breach landscape. Defense is a layered process, not a single tool.

## The Threat Surface

A modern app pulls hundreds of transitive dependencies. Each one is a potential vector:

1. **Typosquatting** — `requests` vs `requets`, `lodash` vs `lodash-es-utils`. Devs mistype, install malware.
2. **Compromised maintainer account** — original maintainer's npm/PyPI account hijacked, malicious version published. (Examples: `event-stream` 2018, `colors.js` 2022, `xz-utils` 2024.)
3. **Dependency confusion** — internal package name registered on public registry by attacker; pip/npm prefers public version.
4. **Source-code injection** — malicious PR merged into legitimate package.
5. **Build-time compromise** — CI pipeline tokens leaked → attacker publishes a tainted release.

## Defenses — The Layered Approach

### Layer 1: Lockfiles (mandatory)

Every package manager produces a lockfile that pins exact transitive versions + integrity hashes:

| Ecosystem | Lockfile |
|---|---|
| Go | `go.sum` |
| Python (uv) | `uv.lock` |
| Python (poetry) | `poetry.lock` |
| Python (pip-tools) | `requirements.txt` (compiled, with hashes) |
| Node (npm) | `package-lock.json` |
| Node (yarn) | `yarn.lock` |
| Node (pnpm) | `pnpm-lock.yaml` |

Rules:

- **Commit the lockfile**.
- **CI uses `--frozen-lockfile`** (or equivalent: `npm ci`, `yarn install --immutable`, `pnpm install --frozen-lockfile`, `uv sync --frozen`). Fails if `package.json` and lockfile disagree.
- **Hash verification on install** — every package manager does this when given a lockfile with hashes.

### Layer 2: Vulnerability Scanning (CI)

Run on every PR. Fail on high-severity. Don't merge until resolved (or explicitly waived with an expiration).

```yaml
# .github/workflows/audit.yml
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Go
      - run: go install golang.org/x/vuln/cmd/govulncheck@latest
      - run: govulncheck ./...

      # Python
      - run: pipx install pip-audit
      - run: pip-audit --strict

      # Node (RN client)
      - run: cd mobile && yarn install --immutable
      - run: cd mobile && yarn npm audit --severity high --recursive

      # Cross-ecosystem (preferred — single tool, full coverage)
      - run: pipx install osv-scanner
      - run: osv-scanner --recursive .
```

OSV (Open Source Vulnerabilities) database aggregates across ecosystems. Use it as the canonical scanner.

### Layer 3: Dependency Review on PRs

- **GitHub Dependency Review** (built-in) — flags new vulnerabilities introduced by the PR.
- **Dependabot / Renovate** — automated PRs to update deps. Review like any other PR (don't auto-merge transitives blindly; let security patches auto-merge with full test pass).

### Layer 4: Minimize Surface

- **Audit every new dependency** at PR time. One paragraph in the PR description: what does this do? Is there a smaller alternative? Could you write it yourself in <100 lines?
- **Remove unused deps** quarterly: `depcheck` (Node), `pip-autoremove` (Python), `go mod tidy` (Go).
- **Avoid abandoned packages**: check last-commit timestamp; replace anything inactive >2 years.
- **Pin major versions** in `package.json` / `pyproject.toml` (`^` is fine for minor/patch with lockfile; never `latest`).

### Layer 5: Dependency Confusion Defense

For internal packages (private monorepo, internal SDK):

- **Scoped packages** in npm: `@app/internal-utils` — register the scope on npmjs.org even if you never publish, claiming it.
- **Private registry first** in `.npmrc`:
  ```
  registry=https://registry.npmjs.org
  @app:registry=https://npm.internal.app.com
  ```
- **Python**: Pin internal packages with `extra-index-url` strict ordering, OR install from URL/path directly.
- **Verify package source** in your build: assert that `@app/internal-utils` resolves from your private registry, not public.

### Layer 6: Provenance + Sigstore

For packages you PUBLISH (your own libraries, internal SDKs):

- **npm provenance** (`--provenance` flag on publish) — attaches verifiable build metadata via Sigstore.
- **Sigstore** for Go modules and container images.
- **Reproducible builds** where feasible.

For packages you CONSUME, look for and prefer those with provenance attestations (npm + GitHub now show this on the package page).

### Layer 7: Build Pipeline Hardening

- **Short-lived OIDC tokens** for cloud auth in CI (no long-lived secrets in GitHub Actions / GitLab CI).
- **Pin GitHub Action versions to commit SHA**, not tag (`uses: actions/checkout@8e5e7e5...` not `@v4`).
- **Restrict who can approve releases**.
- **Two-person rule** for publishing high-impact packages.
- **Separate publish-only credentials** (no PR-merge perms).
- **Scan the build environment** itself: minimal base images, no unnecessary tools.

### Layer 8: Runtime Detection

You can't catch every bad dep at install. Some defenses run at runtime:

- **Outbound-traffic allowlist** at the network layer (your prod app should only talk to known endpoints). Sudden new outbound destination = exfiltration alert.
- **Process-level monitoring** (Falco, Tracee) — alerts on `curl | sh` patterns, unusual syscalls.
- **Container image scanning** (Trivy, Grype) on every build.

## The Build Manifest — SBOM

Generate a Software Bill of Materials per build artifact. Standard format: CycloneDX or SPDX.

```bash
# Cross-language
syft scan ./mobile -o cyclonedx-json > sbom-mobile.json
syft scan ./backend -o cyclonedx-json > sbom-backend.json

# Then verify SBOM doesn't have known vulns:
grype sbom:sbom-mobile.json
```

Attach SBOMs to GitHub releases. Customers / auditors / compliance teams will ask.

## Operational Practices

### Weekly Dependency Hygiene

- [ ] `osv-scanner --recursive .` — zero high-severity.
- [ ] Dependabot / Renovate PRs reviewed and merged.
- [ ] One pass through `pnpm/npm/yarn audit` looking for transitives that snuck in.

### Monthly Dependency Audit

- [ ] Quarterly `pnpm dlx depcheck` / `pip-autoremove` / `go mod tidy` — drop unused.
- [ ] Review of new direct deps added since last audit — still justified?
- [ ] Refresh of "abandoned package" check — anyone left maintainership?

### Incident: "Compromised Package"

When a notice drops ("colors.js v1.4.x is malicious"):

1. **Pin LOWER** in your lockfile + redeploy in <2 hours.
2. **Audit logs** for the time window when the compromised version was deployed.
3. **Rotate any secrets** the deployment had access to.
4. **Notify users** if data was at risk.
5. **Post-mortem** — what could have caught this earlier?

## Common Supply-Chain Mistakes

1. **Lockfile not committed** — non-reproducible builds; transitive surprise.
2. **`npm install` instead of `npm ci`** in CI — re-resolves; lockfile becomes advisory.
3. **No `audit` in CI** — vulnerabilities ship to prod.
4. **Auto-merging Dependabot** without test pass — broken release in 5 minutes.
5. **GitHub Actions tags pinned** instead of SHAs — tag re-pointed at malicious commit = supply-chain attack.
6. **Long-lived secrets** in CI — first leak forever.
7. **Public package install before private check** — dependency confusion.
8. **No SBOM** — can't quickly answer "are we affected by CVE-X" without grepping every lockfile.
9. **Pulling Docker `image:latest`** in production — non-reproducible; new "latest" = silent change.
10. **`curl | sh` install** in CI — full code-execution from a remote server you didn't audit.

## Source Material

- *OWASP CycloneDX*: <https://cyclonedx.org/>
- *Sigstore*: <https://www.sigstore.dev/>
- *SLSA framework*: <https://slsa.dev/>
- *npm provenance*: <https://docs.npmjs.com/generating-provenance-statements>
- *OSV database*: <https://osv.dev/>
- *Snyk supply-chain reports* (annual) — current threat landscape data.
