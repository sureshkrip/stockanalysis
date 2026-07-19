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
| TBD | TBD | TBD | TAXO-01 | — | `sectors.yaml` loads and validates without code changes; malformed YAML raises a clear pydantic error | unit | `pytest tests/test_taxonomy.py::test_load_sectors_yaml -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | INGEST-01 | — | Daily close price fetched and persisted per ticker (mocked yfinance) | unit/integration | `pytest tests/test_prices.py::test_fetch_price_success -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | INGEST-02 | — | Revenue/net income/market cap extracted correctly for both `us-gaap` and `ifrs-full` filers (recorded TSM/NVDA fixtures) | integration | `pytest tests/test_fundamentals.py::test_filer_type_branching -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STORE-01 | — | SQLAlchemy models persist to SQLite; `DATABASE_URL` swap doesn't require code changes | unit | `pytest tests/test_models.py::test_crud_roundtrip -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STORE-02 | — | Refresh continues past a simulated per-ticker failure and logs it | unit | `pytest tests/test_refresh.py::test_partial_failure_continues -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DEPLOY-01 | — | docker-compose stack builds and both services start; backend responds on its internal port | smoke | `docker compose up --build -d && curl -sf http://localhost:8000/health` | ❌ W0 (compose file itself is the artifact under test) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task ID/Plan/Wave columns are TBD — the planner has not yet assigned tasks; populate from PLAN.md frontmatter once plans exist for this phase.*

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
