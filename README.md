# ShirtPost

Fast-fashion print-on-demand for family-friendly internet trends. **Phase 1** = the
backend trend **Radar**, a human-in-the-loop admin **Studio**, and the automated
Printful + X.com **Factory**. No storefront or checkout yet.

```
backend/    FastAPI + SQLAlchemy — radar, scoring, API, factory pipeline (owns the DB)
frontend/   Next.js 15 (App Router) — internal admin dashboard, thin HTTP client
llms.txt    Machine-readable project map
security.md Supply-chain advisory sweep + mitigations
backlog.md  Deferred work
```

The Next.js app talks to FastAPI over HTTP only — FastAPI is the single owner of the
SQLite database (see [backlog.md](backlog.md) for why Prisma was deferred).

## Backend

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # prod
pip install -r requirements-dev.txt      # + pytest/httpx for tests
cp .env.example .env                      # fill in keys (or leave blank for radar-only)
uvicorn app.main:app --reload --port 8000
```

- `GET /health` — liveness
- `GET /api/trends?limit=100&source=<id>` — trends by Hype Score. Each carries a
  within-source `normalized_hype` (0..1) and a `spark` series (recent hype, for the inline
  sparkline). Optional `source` filter.
- `GET /api/trends/{id}/observations` — append-only observation history for one trend
  (newest first; `limit` caps the response, not what is stored)
- `POST /api/trends/{id}/submit` — `{ "design_copy": "..." }`, fires the Factory (409 if a drop for that trend is already in flight)
- `GET /api/drops` — drops, newest first
- `GET /api/drops/{id}` — one drop (the dashboard polls this while a drop is in flight)
- `POST /api/drops/{id}/retry` — re-run a **failed** drop. The pipeline resumes from the last
  committed step, so an already-posted tweet is never sent twice (409 if the drop isn't
  failed, or another drop for its trend is in flight)
- `POST /api/radar/sweep` — force an immediate radar sweep (the "Refresh radar" button)

Run tests:

```bash
cd backend && pytest
```

The Radar runs on a background interval (`RADAR_POLL_INTERVAL_SECONDS`). With the
default `RADAR_SOURCES=["simulated"]` it populates trends with no network or keys.

## Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                # NEXT_PUBLIC_API_BASE_URL
npm run dev                               # hands-on dev, http://localhost:3000
npm run typecheck                         # tsc --noEmit
npm run build && npm run start            # stable serve (what .claude/launch.json uses)
```

Note: do not run `next build` and `next dev` against the same `.next` — mixing
production and dev output corrupts the chunk manifest. Use one or the other.

## What works end-to-end today

- Radar → DB → Admin queue → submit → Factory pipeline runs and records status.
- Every sweep appends a `trend_observations` row, so the Studio draws a real hype
  **sparkline** per trend (not just the latest delta). Trends are grouped into
  **per-source lanes** — volumes aren't comparable across sources, so a within-source
  `normalized_hype` scales each lane instead of one misleading global ranking.
- The Factory builds the SVG as a source artifact and **rasterizes a transparent PNG**
  (Printful's DTG pipeline rejects SVG). Print ink color is derived from
  `PRINTFUL_GARMENT_COLOR` for contrast, so art never prints white-on-white.
- Broadcast defaults to **`X_BROADCAST_MODE=intent`** — the Studio shows a "Post to X"
  button linking a prefilled `x.com/intent/post` (X has no free API tier; this is $0, no
  keys). `=api` auto-posts via credentials and logs an estimated per-post cost.
- The Factory **fails loud** (drop `status=failed`, `error` surfaced in the UI) until
  Printful credentials *and* `PRINTFUL_PRINT_FILE_BASE_URL` (PNG hosting) are configured.
  A failed drop can be **retried** from the UI; the pipeline resumes from the last committed
  step and never re-posts a tweet it already sent. See [PLAN.md](docs/PLAN.md) / [backlog.md](backlog.md).
- Set `FACTORY_DRY_RUN=true` to complete the loop **without** any external service:
  drops reach `published` with clearly-marked simulated outputs (mockup = the served PNG;
  intent URL for the operator). Default off so a real misconfiguration still fails loud.

## Security

All secrets load from env (validated by Pydantic / Zod). Versions pinned exact. A
supply-chain sweep gated this scaffold — see [security.md](security.md). Notably:
`next` 15.5.10 / `react` 19.2.4 (React2Shell-patched), `axios` removed entirely, and
`TrustedHostMiddleware` mitigating the Starlette BadHost advisory.
