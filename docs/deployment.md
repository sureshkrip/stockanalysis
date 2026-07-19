# Deployment & Operations Runbook

This document covers deploying the Data Center Stocks stack to the owner's
Coolify VPS via git-push-to-deploy, and the day-to-day operations of the
live pipeline once it's running.

The stack is two services — `backend` (FastAPI + Uvicorn) and `frontend`
(Next.js) — defined in the root `docker-compose.yml`. There is no `db`
container; SQLite lives on a Coolify persistent volume mounted on
`backend`. Coolify's compose file is the single source of truth for
service topology, internal networking, and (via its own UI) domain
assignment and volumes — none of that is expressed inside the compose
file itself.

## 1. Initial Coolify setup

1. In the Coolify dashboard: **New Resource -> Docker Compose**.
2. Connect this git repository and select the tracked branch.
3. Enable **git-push-to-deploy** for the compose resource, so a push to
   the tracked branch triggers an automatic redeploy with no manual build
   step.

> A git remote must exist and be reachable from Coolify before
> git-push-to-deploy can be wired up. As of this plan, this repository has
> no remote configured — add one (e.g. push to GitHub) before completing
> this step.

## 2. Environment variables

Set these in **Coolify Dashboard -> the project -> Environment Variables**
(never as literal values committed to `docker-compose.yml` or
`.env.example` — both files only ever reference `${VAR}` substitution):

| Variable | Required | Value |
|----------|----------|-------|
| `EDGAR_USER_AGENT` | **Yes, mandatory** | A descriptive app name plus a contact email, e.g. `DataCenterStocks sureshkrip@gmail.com`. SEC EDGAR's bot-detection returns a `403` and can IP-block the VPS for roughly ten minutes on a request carrying a generic or missing User-Agent — that failure mode fails *every remaining ticker* in the run that triggers it, not just one. Do not leave this unset or generic. |
| `DATABASE_URL` | No | Leave unset to use the SQLite default at the mounted volume path (`sqlite:////data/app.db`). Set a `postgresql://` URL to switch database engines with no application code change (see the Postgres upgrade path below). |

## 3. Domain assignment

Assign a public domain to the **`frontend`** service only:
**Coolify Dashboard -> the stack -> frontend service -> Domains**.

Do **not** assign a domain to `backend`. The frontend reaches the backend
internally at `http://backend:8000` over the stack's Docker network that
Coolify auto-creates per compose stack — no `networks:` block is needed in
`docker-compose.yml` for this. Leaving `backend` without a domain (and
without a published host port, per the compose file's production shape)
is the practical access control for an API that has no application-level
authentication (see the phase threat model, T-01-20 — this is a
consciously accepted risk for a single-user personal tool serving
already-public SEC filings and market prices, not an oversight).

## 4. Persistent volume for the SQLite database

**Coolify Dashboard -> the stack -> backend service -> Storages**: create
a persistent volume mounted at the backend container's `/data` path.

**This step is not optional.** Do this *before* the first deploy. Without
it, the SQLite file lives inside the container's writable layer instead
of on host storage, and **every redeploy silently starts from an empty
database** — no error, no warning, just a `GET /companies` that suddenly
returns zero rows. That failure mode looks exactly like an ingest that
never ran, not like a lost volume, so it can go unnoticed for a full day
until the owner happens to check the site.

## 5. The daily scheduled task

**Coolify Dashboard -> the stack -> Scheduled Tasks** -> create a new task:

- **Schedule:** `0 2 * * *`
- **Command:** `python -m app.ingest.refresh`
- **Target:** the `backend` container

### Why `0 2 * * *`, not literally "9pm ET"

D-11 (the phase's locked decision) asks for the refresh to run once daily,
after US market close, "around 9pm ET" — after the 4pm ET close and after
same-day EDGAR filings have finished processing. Coolify's scheduled
tasks run in server/container local time and expose **no timezone
override**, and standard five-field cron syntax cannot express a
DST-aware local time on its own. A literal "9pm ET" cron expression would
therefore actually run at 9pm ET during EST but drift to 8pm ET-equivalent
(or vice versa) across the twice-yearly DST transition, depending on how
it was written.

`0 2 * * *` (02:00 UTC daily) is a **deliberate fixed-UTC choice**, not a
literal translation of "9pm ET":

- 02:00 UTC = **9:00pm EST** (UTC-5, winter)
- 02:00 UTC = **10:00pm EDT** (UTC-4, summer)

Both land comfortably after the 4pm ET market close and after same-day
EDGAR filing processing, under both DST states. **Do not "correct" this
to a literal 9pm-ET cron expression later** — that would reintroduce the
exact DST ambiguity this fixed-UTC time was chosen to avoid. If the exact
run time ever needs to move, change the UTC hour deliberately and update
this rationale alongside it.

### Verifying the task

Trigger it manually once from the Coolify UI after creating it, and
confirm it completes (see Operations below for reading the result).

## 6. Operations

### Triggering a manual refresh

From the Coolify UI's Scheduled Tasks panel, use the manual "Run now"
action on the refresh task. This runs the same
`python -m app.ingest.refresh` command inside the already-running
`backend` container that the nightly schedule uses.

### Reading the refresh log

Each run writes exactly one `refresh_log` row — including a fully clean
run — recording `tickers_attempted`, `failure_count`, and a structured
`failures` list of `{ticker, stage, error}` entries (`stage` is one of
`price`, `cik`, or `fundamentals`). Query the database directly, or watch
the container's stdout/Coolify logs for the run's summary line:

```
Refresh run <uuid>: attempted=<n> succeeded=<n> failed=<n>
```

**Per-ticker failures are expected steady-state noise.** A flaky yfinance
429, a transient EDGAR timeout, or a single ticker whose CIK can't be
resolved yet are normal, isolated occurrences (STORE-02's whole design
goal is that one ticker's failure never blocks the other ~53). Check the
`failures` list for which tickers failed and why, but a non-zero
`failure_count` alone is not an incident.

**A non-zero process exit status is different — and IS an incident.** The
CLI entrypoint (`app.ingest.refresh._main`) exits `0` whenever the run
*completed*, even with per-ticker failures present, because the exit
status is what Coolify's scheduled-task alerting keys off of. A non-zero
exit means something propagated out of `run_refresh` itself — most likely
an invalid `sectors.yaml` (a taxonomy validation error is the one failure
mode allowed to propagate, since a malformed taxonomy is a real
configuration bug, not a ticker-level fetch failure) or an unreachable
database. Treat a non-zero exit as a genuine orchestration failure
requiring investigation, not routine noise.

### Editing the taxonomy

To add or retag a ticker: edit `backend/sectors.yaml` (ticker, company
name, sub-sector) and push to the tracked branch. Coolify's
git-push-to-deploy rebuilds and restarts the stack, and the backend's
startup path re-syncs the taxonomy into the `tickers` table automatically
— no manual seeding step or database migration is needed for a plain
add/retag.

Per D-02a, **delisted tickers are never automatically removed** from
`sectors.yaml` or the database by the pipeline. If a ticker delists or
goes stale, ingestion just logs a per-ticker failure on that stage every
run from then on — the per-run failure log (Reading the refresh log,
above) is the safety net between the owner's periodic taxonomy reviews.
The owner removes a ticker from `sectors.yaml` manually only if/when they
choose to during one of those reviews; the pipeline never does this on
its own.

## 7. The Postgres upgrade path

The MVP runs on SQLite by design (zero setup cost). To move to Postgres
later, with no application code changes (the models avoid
SQLite-specific constructs and Alembic runs with `render_as_batch=True`
from the very first migration):

1. Add a Postgres service in Coolify (or point at an external managed
   Postgres instance).
2. Set `DATABASE_URL` in Coolify's environment variables to the
   `postgresql://...` connection string for that service.
3. Run `alembic upgrade head` against the new database to create the
   schema.
4. Backfill existing data from the SQLite volume (a one-off export/import
   script, or a tool like `pgloader`).

No changes to `docker-compose.yml`, the SQLAlchemy models, or the ingest
code are required — this is the entire point of the `DATABASE_URL`-driven
config design from STORE-01.

## Verification checklist

Use this checklist after the initial deploy (and again after any
redeploy) to confirm the live pipeline is actually working, not just
"deployed":

- [ ] `git push` to the tracked branch triggers a Coolify redeploy with no
      manual build step
- [ ] The frontend is reachable over HTTPS at the assigned Coolify domain
      and renders the live company count
- [ ] The backend cannot be reached directly from outside the VPS (no
      port, no domain)
- [ ] Outbound egress from inside the backend container reaches
      `data.sec.gov` (and the price provider) over HTTPS
- [ ] The scheduled task has completed at least one manually-triggered run
      and written a `refresh_log` row
- [ ] After a redeploy: company/fundamentals row counts are unchanged, the
      scheduled task exists exactly once (not duplicated), and environment
      variables did not need re-entering
