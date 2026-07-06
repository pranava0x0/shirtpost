# ShirtPost — Full build-out plan (Phase 2 → live product)

_Drafted 2026-07-05 from web research + repo state. Review before executing._
_Phase 1 (Radar + Studio + Factory scaffold) is merged and verified — see STATUS.md._

## Progress (2026-07-06)

Every **code-doable, $0, no-account** item across 2A/2B/3/4 is now implemented and
verified (see the Phase-1.5/2A/2B/3 commits + PR). What's implemented:

- **2A #1 Rasterize print files** ✓ — `factory/render.py` (Pillow → transparent PNG).
- **2A #2 Print-file storage** ✓ — `factory/storage.py`: `local` (default) + `github_pages`
  backends, env-selected. `github_pages` pushes the PNG + polls until live, idempotent.
  R2 (boto3 + card) stays the deferred upgrade path.
- **2A #4 Retries + idempotency** ✓ — resumable pipeline + `POST /api/drops/{id}/retry`.
- **2A #5 Garment-color safety** ✓ — ink derives from `PRINTFUL_GARMENT_COLOR`.
- **2B Web Intent broadcast** ✓ — `X_BROADCAST_MODE=intent` default ($0, no keys) +
  "Post to X" button; API client behind `=api` with a per-post cost log and an
  `X_MONTHLY_BUDGET_USD` fail-loud guard.
- **3 #2 Real source** ✓ — Wikipedia most-viewed (open API, ToS-clean); Reddit dropped.
- **3 #3 Per-source lanes** ✓, **3 #4 `trend_observations`** ✓, **3 #5 family filter** ✓.
- **4 #4 Hash-locked installs** ✓ — `requirements*.lock` + CI `--require-hashes`.

**Genuinely human-gated (can't be coded — need you):**
- **2A #3 Printful account** — the client targets v1 and uploads PNG; needs a free
  account to exercise live publishing.
- **2A #2 hosting setup** — create the GitHub Pages artifacts repo + a token (or R2).
  The code is done; real-mode Printful just needs the repo to exist.
- **2B Quick Store validation** — a manual 30-min test with a real account.
- **Google Trends alpha** — apply (rolling access, weeks of lead time).
- **Phase 4 auth / deploy / backups** — the only paid phase; deferred until sales.
- **Phase 5** (better art, analytics, Postgres) — deferred until real drops prove the loop.

**Constraint: $0 to start.** Every phase below runs on free tiers or locally until
the first sales justify paid automation. The two paid items from the first draft
(hosted backend, X API) are deferred behind explicit upgrade triggers — see
"Free-to-start mode" and the cost table.

## Research findings that change the design

1. **Printful does not accept SVG print files.** Accepted formats are PNG/JPEG; DTG
   requires transparent-background PNG, sRGB (IEC61966-2.1), 150–300 DPI. Our pipeline
   writes `artifacts/<drop_id>.svg` — the SVG stays as the *source* artifact, but the
   Factory must rasterize to PNG at the print-area pixel size before upload. This
   invalidates the current `PRINTFUL_PRINT_FILE_BASE_URL`-points-at-SVG assumption.
2. **Printful product management lives in API v1 only.** The v2 beta has mockups and
   catalog but *not* sync-product management yet. Build against v1 for store/product
   sync; mockup generation is async (poll task + `mockup_task_finished` webhook backup).
   General rate limit 120 req/min, lower for mockup generation.
3. **X API has no free tier anymore.** Since 2026-02-06 new customers get pay-per-use
   only: **$0.015 per post, $0.20 per post containing a URL**; media upload is a
   3-step v2 flow (INIT/APPEND/FINALIZE — our client already targets v2). Each drop
   announcement with a store link ≈ $0.20. Cheap at drop volume, but it's a metered
   bill: log cost per broadcast and add a monthly cap env var.
4. **Reddit's free API tier is non-commercial only.** ShirtPost is commercial —
   using it as a radar source would violate ToS without an enterprise agreement.
   Drop Reddit from the source plan.
5. **Google Trends has an official API, in alpha, application-gated.** Apply now
   (rolling access, weeks–months of lead time); it's the only sanctioned trends feed.
   Until granted, the simulated source remains the default.
6. **Printful Quick Stores solves the storefront for $0.** Free Printful-hosted
   storefront with Stripe checkout — no checkout code, no monthly fee. Constraints:
   US-only (merchant tax residency + shipper address), no custom domain, not fully
   white-label. Perfect for the "don't announce a non-buyable drop" gap.
   **Open validation:** confirm API-created sync products appear in a Quick Store
   (docs are ambiguous — 30-min test with a real account; fallback: Shopify Starter
   ~$5/mo, or manual product publish as interim).
7. **Cloudflare R2 free tier hosts the print files.** 10 GB storage, 1M writes/10M
   reads per month, **zero egress**, public buckets supported, no expiry. Printful
   fetches print files by public URL — R2 public bucket is the host.
8. **Hosting: SQLite needs a persistent volume + single instance.** Railway Hobby
   ($5/mo, volume-backed) or Fly.io (no free tier, volume pins to one host). Either
   works; Railway is the lower-ops default. Add Litestream → R2 for DB backup.
   **Deferred** — free-to-start mode runs everything locally (below).
9. **R2's "free" tier may require a card on file.** Cloudflare's product page says
   no card; multiple 2025–26 user reports say enabling R2 requires a payment
   method. Don't depend on it: default print-file host is GitHub Pages (no card,
   hard $0); R2 is the upgrade path.

## Free-to-start mode (how each paid item goes to $0)

| Paid item (first draft) | Free replacement | Upgrade trigger |
|---|---|---|
| Railway $5/mo backend | **Run locally.** Studio is an internal admin tool; Phase 1 already runs on this machine. No always-on server needed until the radar must sweep unattended. Bonus: auth (Phase 4) stays deferred while nothing is exposed. | First consistent sales, or wanting unattended sweeps |
| X API $0.20/post | **X Web Intent** (`x.com/intent/post?text=...`) — free, no API key. Studio's drop card gets a "Post to X" button that opens a prefilled tweet (broadcast copy + Quick Store URL); the human clicks Post. Limitation: intents can't attach media — but the linked product page unfurls as a card with the mockup image, which covers it. Fits the human-in-the-loop model. | Posting volume makes the manual click annoying (~$0.20/drop then) |
| R2 print-file hosting | **GitHub Pages artifacts repo** — a separate public repo (`shirtpost-artifacts`), Factory pushes `drops/<drop_id>.png` via git/API, serves at a stable public URL Printful can fetch. Free, no card, 1 GB site / 100 GB-month bandwidth is thousands of drops. Separate repo keeps binaries out of the main repo per CLAUDE.md. Caveat: Pages deploys take ~1 min — the Factory polls the URL until it's live (200 + right content-length) before calling Printful. | R2 free tier if/when a card is acceptable (instant availability, no deploy wait) |

Already free, unchanged: Printful account + API + mockups ($0 up-front, COGS come
out of the customer's payment), Quick Stores ($0, Stripe-processed), Google Trends
alpha ($0), Wikipedia/YouTube sources ($0), Vercel/local frontend ($0).

## Phase 2A — Factory goes real (highest value, unblocks everything)

1. **Rasterize print files.** `factory/render.py`: SVG (kept as source) → transparent
   PNG at print-area px (Printful mockup-styles endpoint returns
   `print_area_width/height` + dpi). Use `resvg` (binary) or `cairosvg` (pure-ish
   Python, easier pin). Regression test: output dimensions, transparency, sRGB.
2. **Print-file publish step.** `factory/storage.py` behind a small interface with
   two backends: `github_pages` (default, $0 — push `drops/<drop_id>.png` to the
   artifacts repo, poll the public URL until live) and `r2` (S3 API via `boto3`,
   instant, needs card). Both idempotent by key; both return the public URL that
   replaces `PRINTFUL_PRINT_FILE_BASE_URL`. Env selects backend
   (`PRINT_FILE_STORAGE=github_pages|r2`).
3. **Printful v1 product creation** (existing `printful.py`, corrected): create sync
   product + variant with the PNG URL, then async mockup task with poll + timeout
   (webhook later, poll is the backup anyway). Store `printful_product_id`,
   `mockup_url` on the drop.
4. **Retries + idempotency** (backlog item): re-running a failed drop must not
   double-create products or double-post. Persist per-step state on the drop
   (`printful_done`, `tweet_id`), skip completed steps on retry. Add
   `POST /api/drops/{id}/retry`.
5. **Garment-color safety** (backlog item): print color derives from the variant's
   garment color instead of hardcoded white-on-dark.

Exit criteria: with a free Printful account, submit → PNG live on the artifacts
repo's Pages URL → Printful product + mockup → drop `published` with real mockup
URL. `FACTORY_DRY_RUN` still works keyless. Total spend: $0.

## Phase 2B — Storefront + honest broadcast

1. **Quick Store validation** (manual, first): create Quick Store, confirm an
   API-created sync product gets a shareable product URL. Decision gate — if no,
   fall back to Shopify Starter or manual publish.
2. **Wire `STORE_BASE_URL`** to the real product URL per drop (store the product's
   public URL on the drop at creation, not a guessed pattern).
3. **Broadcast, free first:** Studio drop card gets a "Post to X" Web Intent button
   (prefilled copy + product URL, human clicks Post — $0, no API key). The existing
   v2 API client stays behind `X_BROADCAST_MODE=api` for later automation, gaining
   per-post cost logging ($0.20 w/ link) and an `X_MONTHLY_BUDGET_USD` fail-loud
   guard when that mode turns on. Either way: only announce when the drop has a
   live, buyable product URL (existing rule).

Exit criteria: a tweet links a page where a human can actually buy the shirt —
with zero API spend.

## Phase 3 — Real Radar

1. **Apply for Google Trends API alpha now** (lead time). Integrate as a source
   when granted; until then simulated stays default.
2. **Interim real sources** (ToS-clean only): Wikipedia pageview API (free, open),
   YouTube trending via Data API (free quota). No Reddit (commercial ToS), no
   scraping Google Trends.
3. **Per-source ranking lanes** (backlog item): don't mix `measurement` types in one
   hype ranking; per-source normalization or lane tabs in the Studio.
4. **`trend_observations` append-only table** (backlog item) for true velocity
   curves; chart in the trend card.
5. **Family-friendly filter:** keyword blocklist + (optional) Haiku classification
   pass, cached by content hash, before a trend reaches the queue.

## Phase 4 — Auth + deploy (deferred until sales — the only paid phase)

Local-only operation makes this entirely optional at start: nothing is exposed, so
auth can wait with it. Free interim backup: nightly `sqlite3 .backup` to a private
GitHub repo (or any synced folder) — one cron line, $0.

When the upgrade trigger hits (consistent sales / unattended sweeps wanted):

1. **Admin auth first** (backlog design): dashboard calls go through Next.js Route
   Handlers server-side; `ADMIN_API_TOKEN` lives only server-side; FastAPI requires
   it on all `/api/*`. No browser-exposed token.
2. **Deploy:** Railway Hobby $5/mo (backend + volume for SQLite + artifacts) +
   Vercel free (frontend). Single backend instance always (SQLite).
3. **Backups:** Litestream sidecar → R2.
4. **Hash-locked installs** (backlog item, free, do anytime): `uv lock` backend,
   keep `npm ci` frontend.
5. **CI:** existing workflow + count-floor/regression additions as they arise.

## Phase 5 — Iterate on demand (not before)

- Better art: AI image gen → transparent PNG (replaces text-only SVG) — only once
  real drops prove the loop.
- Analytics (Cloudflare Web Analytics on any public page), drop performance
  tracking (clicks → sales via Printful order webhooks).
- Postgres migration only if concurrency ever demands it.

## Running costs

| Item | Now (free mode) | Later (upgrade trigger) |
|---|---|---|
| Backend + frontend | $0 — local | Railway $5/mo + Vercel free |
| Print-file hosting | $0 — GitHub Pages artifacts repo | R2 free tier (card on file) |
| Broadcast | $0 — X Web Intent, human clicks Post | X API ~$0.20/drop |
| Printful / Quick Store | $0 up-front, COGS per order | same |
| Trend sources | $0 — simulated / Wikipedia / YouTube / Trends alpha | same |
| Backups | $0 — nightly sqlite backup to private repo | Litestream → R2 |

**$0/mo now; ~$5/mo + pennies per drop only after the loop earns it.** The only
unavoidable money movement is Printful's per-order COGS, which comes out of the
customer's payment (Quick Store pays out margin, never invoices up-front).

## Sequencing & effort (rough)

| Step | Size | Blocked by |
|---|---|---|
| 2A rasterize + artifacts-repo publish + Printful v1 + retry | 2–3 sessions | Printful account (free) |
| 2B Quick Store validation + wiring + intent button | 1 session | Printful account (manual test first) |
| 3 real sources + lanes + observations | 2 sessions | Trends alpha approval (apply day 1) |
| 4 auth + deploy + backups | 1–2 sessions | first sales (the upgrade trigger) |

Order: **apply for Trends alpha + validate Quick Store (day 1, manual) → 2A → 2B →
3 → 4 only when triggered.** With no deploy cost, real radar moves ahead of
deployment — the loop runs end-to-end from this machine at $0.

## Sources

- Printful print-file specs: printful.com/creating-dtg-file, developers.printful.com/docs/ (v1), /docs/v2-beta/
- Quick Stores: printful.com/quick-stores, help.printful.com (billing, vs-integrations)
- X pricing: postproxy.dev/blog/x-api-pricing-2026, socialcrawl.dev/blog/x-twitter-api-2026
- Google Trends API alpha: developers.google.com/search/apis/trends
- Reddit ToS/pricing: octolens.com/blog/reddit-api-pricing, support.reddithelp.com Data API wiki
- R2 pricing: developers.cloudflare.com/r2/pricing/
- Hosting: fly.io/docs (SQLite volumes), railway.com (Hobby plan)
