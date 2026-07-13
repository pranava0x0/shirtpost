# ShirtPost v2 spec — trend discovery routine + actually-funny merch

_Drafted 2026-07-12 from a v1 audit (repo at 66877fb). Review before executing._
_Extends [PLAN.md](PLAN.md) (the Phase 2→5 build-out); nothing here contradicts it.
This is the implementation plan behind the **top backlog item** in [backlog.md](../backlog.md)._

---

## 0. Why — an honest audit of v1

The loop works end-to-end (radar → queue → quips → factory → post), but what flows
*through* it is dull. Five root causes, in order of impact:

1. **The radar measures attention, not wearability.** Wikipedia most-viewed is
   informational lookups — deaths, new movies, sports events, whoever is in the
   news. Google Trends RSS (wired, off by default) is the same: news-cycle spikes.
   Neither surfaces *phrases people would put on their body*. A shirt-worthy trend
   is an identity signal or an inside joke ("crashing out", "brat summer"), not a
   headline ("2026 NBA Finals"). No current source produces the former.
2. **The only meme-flavored source is 8 hardcoded seeds, and they're stale.**
   `radar/sources.py` `_SIMULATED` anchors on 2021–2023 memespeak ("gaslight
   gatekeep girlboss" ~2021, "villain era" ~2022, "delulu is the solulu" ~2023).
   In July 2026 these read as costume, not current — and `STYLE_ANCHORS` in
   `frontend/lib/quips.ts` feeds the same lines to the quip prompt as the house
   voice, so generated copy *inherits* the staleness.
3. **No shirt-worthiness or IP dimension in scoring.** `hype_score` ranks raw
   attention (a volume base with a capped velocity boost — see `scoring.py`).
   Nothing scores phrase-ness, durability,
   or identity value — and nothing flags IP risk. Wikipedia's top slots are mostly
   proper nouns (celebrities, franchises) that are legally unprintable
   (right-of-publicity / trademark), so the queue fills with trends we must not
   merch, unflagged.
4. **Quip generation is blind, one-shot, and judge-less.** The model gets only
   `term / source / measurement` — no "why is this trending" context, so it riffs
   blind on e.g. a bare surname. One pass on Haiku (cheapest, weakest at comedy),
   no generate→rank stage, no cliché ban (LLM shirt humor converges on "I survived
   X" / "X is my love language" / "POV:"), and no learning: the operator's picks
   (`design_copy` on published drops) are already stored but never fed back.
5. **Merch is monotone.** One garment, one color, one centered text layout. Even a
   great line looks like every other drop.

Fixes: **Part A** (new discovery source — the biggest lever, and the cloud routine
the owner asked for), **Part B** (copy generation v2), **Part C** (merch variety).

## Goals / non-goals

- **Goal:** every day, 5–15 *fresh, wearable, family-safe, IP-clean* phrase
  candidates land in the Studio with context, and the quip generator turns them
  into copy the operator would actually pick.
- **Goal:** the discovery sweep runs **on the cloud, unattended** — the backend
  stays local-only (no auth yet, per backlog), so discovery must not depend on
  the Mac being awake.
- **Non-goal:** auto-publishing. The human still picks (model proposes, human
  disposes) — unchanged.
- **Non-goal:** storefront, auth, deploy (tracked in PLAN.md Phase 2B/4).

---

## Part A — trend-discovery cloud routine (the top item)

### A1. Architecture: cloud agent → git → radar adapter

A **scheduled Claude cloud routine** (created with `/schedule`; runs Claude Code
against this GitHub repo on a cron) sweeps social/web sources, judges candidates,
and **appends them to a data file in the repo via a daily PR**. The local radar
gains one new source adapter, `discovered`, that reads the file and upserts into
the normal lanes/queue.

Why git-as-transport instead of POSTing to the backend:

- The FastAPI admin API is local-only and unauthenticated (deliberately, see
  backlog) — a cloud job can't and shouldn't reach it.
- A PR **is** the human-in-the-loop review gate, with diff, history, and rollback
  for free. Append-only JSONL honors the data rules (source attribution,
  capture dates, dedup by key).
- $0 infra. No new service, no webhook, no queue.

Flow:

```
[cloud routine, daily cron]
  sweep sources → judge (shirt-worthiness rubric) → dedupe vs existing
  → append data/trends/discovered.jsonl → open/update PR "radar: YYYY-MM-DD sweep"
[owner] merge PR (or let it sit — nothing breaks)
[local backend] RADAR_SOURCES includes "discovered"
  → adapter reads the JSONL from the local checkout → normal upsert/lanes/queue
```

### A2. Sources and their real contracts

Per CLAUDE.md, **verify every contract before building on it** — that's Phase T0
below. Current knowledge, marked by confidence:

| Source | How we read it | Contract status |
|---|---|---|
| **X trends** | Third-party public aggregator pages (e.g. trends24.in, getdaytrends.com) + web-search roundups. **Never the X API** for reads (paid tiers only — repo-verified no free tier since 2026-02) and never logged-in scraping (ToS-barred). | Aggregators' own ToS: **verify at T0** |
| **Reddit** | **No API** (free tier bars commercial use — repo-verified, already dropped once). Signal comes from reading *public, search-indexed* pages at human scale (a few pages/day) and secondary "what's trending on Reddit" coverage. | Gray zone — **owner decision at T0** (fallback: rely on aggregators/KYM, which track Reddit anyway) |
| **Google Trends** | `trending/rss?geo=US` — already wired in `config.py` + `sources.py`, just not enabled. Official alpha API application still pending (PLAN.md, human step). | RSS works today (repo-verified); apply for alpha in parallel |
| **Bluesky** | AT Protocol public API — open by design, no key, and the platform where a lot of meme-phrase culture now lives. Trending-topics endpoint. | Free/open expected — **verify exact endpoint + terms at T0** |
| **Mastodon** | `GET /api/v1/trends/tags\|statuses` on a big instance — public, no key. | Per-instance rules — **verify at T0** |
| **Know Your Meme** | Trending/editorial pages — the highest-precision "is this a *meme*, not news" source. One page/day, cached. | **Verify ToS at T0** |
| **TikTok Creative Center** | Trend pages, no API. | Optional; likely ToS-hostile — **T0 or skip** |

Any source that fails T0 gets cut from the sweep prompt, not worked around.
Fetch hygiene rules (≥1.5s per host, cache, informative UA) apply to the routine
too — it's stated in the routine prompt.

### A3. The judgment rubric (what makes a trend shirt-worthy)

The routine doesn't just collect — it **judges**. Each candidate is scored 0–5 on:

- **wearability** — does wearing it signal identity/membership in a joke?
- **funny potential** — can it be subverted, deadpanned, escalated?
- **durability** — still alive in 2–3 weeks? (production + shipping lag; a news
  spike is dead before the shirt arrives)
- **phrase-ness** — already a wearable phrase vs. a topic that needs a joke
  written about it (topics are allowed but score lower)

Plus two **kill gates** (not scores):

- **family-safety** — same standard as the existing keyword gate, but judged in
  context; the backend keyword filter still runs after it (defense in depth).
- **IP risk** — names of real people, brands, franchises, song lyrics → **kill**
  (or keep the *moment* but require copy that riffs around the name, flagged
  `ip_risk: true`). Right-of-publicity and trademark exposure is not worth a $0
  business; parody is not a safe harbor we can afford to litigate.

Composite `shirt_score` 0–100. The routine also writes a one-line **`context`**
("why this is trending, as of YYYY-MM-DD") and 2–3 **`angles`** hints — these are
the grounding Part B feeds to the quip generator.

### A4. Data schema — `data/trends/discovered.jsonl`

Append-only, one JSON object per line, one line per (normalized term, day):

```json
{"term": "crashing out", "term_raw": "crashing out", "key": "crashing out",
 "day": "2026-07-12", "captured_at": "2026-07-12T13:05:00Z",
 "sources": [{"id": "x_aggregator", "url": "https://…", "seen_at": "2026-07-12T13:01:00Z"}],
 "context": "resurgent on X this week as …",
 "scores": {"wearability": 4, "funny": 4, "durability": 3, "phraseness": 5},
 "shirt_score": 78, "ip_risk": false,
 "angles": ["deadpan self-diagnosis", "corporate-speak mashup"],
 "model": "claude-sonnet-5", "prompt_version": 1}
```

Rules (all existing CLAUDE.md data rules apply):

- **Dedup:** the routine loads the file first and skips any `key` seen in the
  last 14 days (re-running the same day is a no-op — idempotent).
- **No status field written by the routine.** Absence of a judgment = "not yet
  assessed"; approval is the PR merge + the operator submitting a drop.
- **Bound by content, not count:** the adapter reads a date window (default 14
  days); the file itself is never trimmed.
- The routine only ever touches `data/trends/*.jsonl` — never code. Stated as a
  hard rule in its prompt (blast-radius guard).

### A5. Radar integration (backend)

- New source id **`discovered`** in `RADAR_SOURCES`. Adapter in
  `radar/sources.py`: read `DISCOVERED_TRENDS_PATH` (default
  `../data/trends/discovered.jsonl`), parse the last 14 days, dedupe by `key`
  keeping max `shirt_score`, emit `RawTrend(volume=shirt_score,
  measurement="shirt_score")`. Lanes already prevent cross-source comparison, so
  a 0–100 score is an honest volume for its own lane.
- Malformed line → log + skip (never crash the sweep); empty/missing file → log
  a distinct "no discovery data" warning (empty ≠ broken).
- **New nullable `Trend.context` column** (+ migration): carried from the JSONL,
  shown on the TrendCard, and passed to `/api/quips` (Part B). Nullable so every
  existing row reads as before.
- Family keyword gate still applies after the adapter (defense in depth).
- Tests: fixture JSONL (happy path, malformed line, empty file, 15-day-old line
  excluded, dedupe-keeps-max-score), plus one seed per `measurement` enum value.

### A6. The routine itself

Cadence: **daily, 09:00 ET** (memes move daily; hourly is waste given days of
production lag). Start at 3×/week if cost matters. Budget: with ~15–25 page
reads + judging on Sonnet, a run is roughly **$0.15–0.60 → under ~$20/mo daily**;
revisit after a week of real runs. The routine prompt (copy-pasteable for
`/schedule`, kept in this file as the single source of truth):

```text
You are ShirtPost's trend-discovery sweep. Read docs/TRENDS-DISCOVERY-SPEC.md
(Part A) and follow it exactly. Sweep the T0-approved sources for phrases/memes
trending TODAY that someone would wear on a t-shirt. Judge each candidate on the
A3 rubric (wearability, funny, durability, phrase-ness; kill on family-safety or
IP risk — no real people, brands, franchises, or lyrics). Dedupe against
data/trends/discovered.jsonl (skip keys seen in the last 14 days). Append
qualifying candidates (shirt_score >= 55) as A4-schema JSONL lines. You may ONLY
modify data/trends/*.jsonl. Respect fetch hygiene: >=1.5s between requests to a
host, skip a source that errors and note it. Open or update a PR titled
"radar: <YYYY-MM-DD> discovery sweep" whose body reports per-source
fetched/considered/kept/killed counts, kill reasons, and any source that failed
(a source that returned nothing is reported as a failure, not silence). If NO
candidate qualifies, still open the PR with the empty-sweep report.
```

Ops notes: the PR body is the run report (per-source counts — a silently dead
source must be visible); a failed run simply doesn't PR, and the next day's run
covers the gap (each sweep is independent; the 14-day window self-heals).

### A7. Phasing

- **T0 — contract verification (½ day, mostly reading).** For each A2 source:
  fetch it by hand, read ToS/pricing, record verdict in the A2 table, cut
  failures. Owner decides the Reddit stance. Apply for the Google Trends alpha
  (human step, weeks of lead time — do it now).
- **T1 — MVP (≈1 day).** `discovered` adapter + tests + `Trend.context` column +
  TrendCard shows context; seed `data/trends/discovered.jsonl` with one
  hand-written line; create the scheduled routine with the A6 prompt; first
  real PR reviewed by the owner. Also: enable `google_trends` RSS in
  `RADAR_SOURCES` (already wired — free signal for $0 work).
- **T2 — deterministic collectors (≈1 day, after T1 proves the loop).** Move the
  structured feeds (Bluesky, Mastodon, Google Trends RSS) to plain code — either
  new `sources.py` adapters polled locally, or a tiny GitHub Actions cron
  committing raw JSON for the routine to judge. The routine then only does what
  needs judgment: the fuzzy web sweep + scoring. (Deterministic > agentic
  wherever the input is structured.)
- **T3 — feedback loop (after real posting volume).** Operator picks and X
  engagement per drop feed back into source weighting and the Part B
  hall-of-fame. Needs data that doesn't exist yet — do not build early.

**Success criteria (T1):** within 2 weeks, ≥5 candidates/week the operator rates
shirt-worthy; zero IP-risky terms reach the queue unflagged; routine cost within
budget; a day with no qualifying trends produces an explicit empty-sweep PR.

---

## Part B — copy generation v2 (make the quips land)

All in the Next.js quip path (`frontend/lib/quips.ts`, `app/api/quips/route.ts`)
— the Anthropic key stays on the dashboard server, never FastAPI (owner rule).

1. **Ground the model.** Pass the trend's `context` + `angles` (from Part A)
   through the existing POST body. A model that knows *why* something is trending
   writes jokes about the moment, not the words.
2. **Generate → judge.** Stage 1 generates 16–20 candidates at temperature ~1.0
   spread across 4 named comedic angles (deadpan literalism; self-deprecating
   confession; absurdist escalation; hyper-specific niche mashup). Stage 2 (Haiku
   — judging is cheaper than writing) scores each on funny/wearable/fresh and
   returns the top 6. Default `QUIP_MODEL` moves Haiku → **Sonnet** for stage 1
   (comedy is the product; ~1–2¢/click is fine), Haiku stays the judge.
3. **Cliché kill-list** in `cleanAndFilter`, mirroring the family gate pattern:
   `/^i survived/i`, `/love language/i`, `/^keep calm/i`, `/^pov:/i`,
   `/is my (spirit animal|cardio|therapy)/i`, `/but first,? coffee/i`,
   `/adulting/i`, plus at most one `…era` line per batch. Count what it drops
   (auditable), same as the family filter.
4. **Hall of fame replaces the stale anchors.** `data/copy/hall-of-fame.json`:
   every submitted drop's `design_copy` auto-appends (it's already stored on the
   drop); owner can hand-add/prune. The route samples 4–6 entries as few-shot
   style anchors; the hardcoded 2023-era `STYLE_ANCHORS` become the cold-start
   fallback only. This is the taste feedback loop — the house voice becomes
   *what the owner actually shipped*.
5. **IP guard in the prompt + filter:** never include real people/brand/franchise
   names in copy; when the trend is `ip_risk`-flagged, drop any candidate
   containing the term itself (riff around the moment instead).
6. **Tests finally land:** this work adds the deferred vitest harness (backlog
   item) — `quips.test.ts` covers parse/filter/dedupe/cliché/IP-drop paths.
   Fold in the existing backlog follow-ups while in the file: cache quips by
   trend term (stop re-billing repeat clicks) and a basic rate limit on the route.

**Success criteria:** in ≥50% of sessions the operator submits a generated line
unedited; the same batch never shows two rewrites of one joke; cliché-list drops
are visible in the response metadata.

## Part C — merch variety (small, code-only)

- 3–4 Pillow layout templates in `factory/render.py` (centered bold stack —
  current; top-left chest hit; oversized lowercase full-width; boxed/outline).
  Operator picks per drop (dropdown, default rotates). Regression test per
  template: containment + transparency (extends the existing render tests).
- 2–3 garment/ink pairs beyond black/white (`printful_garment_color` already
  drives ink contrast — expose the choice per drop instead of one global env).
- **Success criterion:** two consecutive drops never look identical.

---

## Sequencing, effort, cost

| Step | Effort | Cost |
|---|---|---|
| T0 contract verification | ½ day | $0 |
| T1 routine MVP + adapter + context plumbing | 1 day | ~$5–20/mo routine tokens |
| Part B copy v2 (+ vitest harness) | 1 day | ~1–2¢ per generate click |
| Part C merch variety | ½ day | $0 |
| T2 deterministic collectors | 1 day | $0 |
| T3 feedback loop | later | — |

Order: **T0 → T1 → B → C → T2** (T1 first — better inputs make every downstream
stage look smarter; B without A still riffs on boring trends).

## Open questions for the owner

1. **Reddit stance** (A2): human-scale public-page reading, or skip direct Reddit
   entirely and rely on aggregators/KYM?
2. **PR-per-day vs. direct commits to a data branch** once trust is established
   (start with PRs — the review gate is the point).
3. **Budget ceiling** for the routine + Sonnet quips (~$20–25/mo all-in as
   spec'd) — confirm.
4. **Google Trends alpha application** — human step, do it now (weeks of lead
   time).
5. Sweep geo is US-only today (`geo=US`, English sources) — fine for now?
