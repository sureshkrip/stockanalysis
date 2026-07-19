---
phase: 1
slug: data-foundation-taxonomy-ingestion-deployment
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest) — none configured yet, greenfield repo |
| **Config file** | none yet — see Wave 0 Requirements |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/` |
| **Estimated runtime** | ~30 seconds (estimate — greenfield, no tests exist yet) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/`
- **Before `/gsd-verify-work`:** Full suite must be green, plus the docker-compose smoke test green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | all | — | Test harness installed; EDGAR fixtures recorded for both taxonomies; end-to-end taxonomy test exists and is RED | scaffold | `uv run pytest tests/test_companies_endpoint.py -x` (expected RED) | ❌ W0 (this task creates it) | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | TAXO-01 | T-01-01 | `sectors.yaml` loads and validates without code changes; malformed YAML raises a clear pydantic error; safe YAML loader only | unit | `pytest tests/test_taxonomy.py::test_load_sectors_yaml -x` | ❌ W0 | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | STORE-01 | — | SQLAlchemy models persist to SQLite; point-in-time unique constraint enforced; `DATABASE_URL` swap needs no code change | unit | `pytest tests/test_models.py::test_crud_roundtrip -x` | ❌ W0 | ⬜ pending |
| 01-01-T3 | 01-01 | 1 | DEPLOY-01 | T-01-03, T-01-05 | docker-compose stack builds and both services start; backend responds on its internal port; status page renders count and degrades to error copy | smoke | `docker compose up --build -d && curl -sf http://localhost:8000/health` | ❌ W0 (compose file is the artifact under test) | ⬜ pending |
| 01-02-T1 | 01-02 | 2 | INGEST-01 | T-01-06, T-01-07 | Daily close fetched and persisted per ticker (mocked provider); bounded retry with jitter; single-vs-multi response shape normalized | unit/integration | `pytest tests/test_prices.py::test_fetch_price_success -x` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 01-02 | 2 | STORE-02 | T-01-09 | Refresh continues past a simulated per-ticker failure and logs it; clean runs still write a refresh_log row | unit | `pytest tests/test_refresh.py::test_partial_failure_continues -x` | ❌ W0 | ⬜ pending |
| 01-02-T3 | 01-02 | 2 | INGEST-01 | — | `GET /companies` returns latest price with source and as-of; null for tickers with none | integration | `pytest tests/test_companies_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 01-03 | 2 | INGEST-02 | T-01-10, T-01-11, T-01-12 | CIK resolves zero-padded to 10 digits, caches, fails cleanly on unknown tickers; every EDGAR request identified, timed out, paced | unit | `pytest tests/test_cik_resolver.py -x` | ❌ W0 | ⬜ pending |
| 01-03-T2 | 01-03 | 2 | INGEST-02 | T-01-13 | Revenue/net income extracted correctly for both `us-gaap` and `ifrs-full` filers (recorded NVDA/TSM fixtures); USD-only filtering | integration | `pytest tests/test_fundamentals.py::test_filer_type_branching -x` | ❌ W0 | ⬜ pending |
| 01-04-T1 | 01-04 | 3 | INGEST-02 | T-01-17 | Market cap derived in exact Decimal from shares × nearest close; null (not zero) when uncomputable | unit | `pytest tests/test_fundamentals.py -x` | ❌ W0 | ⬜ pending |
| 01-04-T2 | 01-04 | 3 | STORE-01, STORE-02 | T-01-15, T-01-16 | Re-run leaves fundamentals row count unchanged; restatement under a new accession inserts alongside the original; stages fail independently | integration | `pytest tests/test_refresh.py -x` | ❌ W0 | ⬜ pending |
| 01-04-T3 | 01-04 | 3 | INGEST-02 | T-01-18 | `GET /companies` returns the full multi-year fundamentals history with per-filing provenance, in a stable order | integration | `pytest tests/test_companies_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 01-05-T1 | 01-05 | 4 | DEPLOY-01 | T-01-21 | Compose is production-shaped (backend unexposed, no committed secrets); runbook documents cron, volume, and User-Agent | smoke | `docker compose config && docker compose up --build -d && curl -sf http://localhost:8000/health` | ❌ W0 | ⬜ pending |
| 01-05-T2 | 01-05 | 4 | DEPLOY-01 | T-01-20, T-01-22, T-01-23 | Deployed stack live on Coolify; egress to SEC verified from inside the container; data survives redeploy; scheduled task completes | manual (blocking checkpoint) | manual — see Manual-Only Verifications below | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Threat Ref column maps to the `<threat_model>` STRIDE registers in the corresponding PLAN.md.*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — fixtures: temp SQLite DB session, recorded EDGAR `companyfacts` JSON fixtures for one `us-gaap` company (NVDA) and one `ifrs-full` company (TSM), mocked yfinance responses
- [ ] `tests/test_taxonomy.py` — covers TAXO-01
- [ ] `tests/test_cik_resolver.py` — covers CIK zero-padding + cache-hit/miss paths
- [ ] `tests/test_fundamentals.py` — covers INGEST-02 filer-type branching (the highest-risk area this phase)
- [ ] `tests/test_prices.py` — covers INGEST-01
- [ ] `tests/test_refresh.py` — covers STORE-02 partial-failure isolation
- [ ] `tests/test_models.py` — covers STORE-01 CRUD + point-in-time unique constraint
- [ ] Framework install: `uv add --dev pytest pytest-mock respx`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` config (testpaths, etc.)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Coolify scheduled task fires the daily refresh and the git-push-to-deploy pipeline works end-to-end | DEPLOY-01 | Requires the owner's actual Coolify VPS; not reproducible in CI/local | After deploy, trigger the scheduled task manually from the Coolify UI once and confirm the refresh log shows a completed run |
| Outbound egress from the Coolify VPS to `data.sec.gov` and Yahoo Finance is unblocked | INGEST-01, INGEST-02 | Network/firewall behavior of the owner's specific VPS, not testable pre-deploy | Wave 0 smoke test: `curl` both hosts from inside the deployed backend container |

*Automated coverage handles all other phase behaviors.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
