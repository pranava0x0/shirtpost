---
name: update-docs
description: >-
  Update the ShirtPost documentation set so it stays consistent with the code
  after a chunk of work. Covers CLAUDE.md, AGENTS.md, DESIGN.md, README.md,
  llms.txt, backlog.md, issues.md, docs/STATUS.md, docs/PLAN.md,
  docs/SESSION-HISTORY.md, and backend/.env.example. Use this whenever the user
  says "update the docs", "update documentation", "sync the docs", "document
  this session/PR", "log this bug", or finishes a feature/fix/review and the docs
  should reflect it — even if they name only one doc, because touching one almost
  always means a sibling (a test count, a config var, an endpoint, a backlog
  item) has drifted too. Also use before opening a PR to reconcile the docs with
  what actually shipped.
---

# Updating the ShirtPost docs

## The one rule

These docs are a contract with reality. The only real failure mode is a doc that
**claims something no longer true** — a stale test count, a renamed config var, a
changed endpoint, a "gap" that's now built. So: **verify every claim against the
code before you write it, and when you touch one doc, check whether its siblings
drifted too.** Everything below serves that.

## Step 1 — know the delta first

Before editing anything, establish what changed (cheap, and it's what keeps the
docs honest):

- `git diff main...HEAD --stat` (or the range for this work) — the changed areas.
- What's new/changed: endpoints, config/env vars, dependencies, DB fields, radar
  sources, CLI commands.
- The **current** backend test count — run it, never guess:
  `cd backend && source .venv/bin/activate && python -m pytest -q | tail -1`.

## Step 2 — the doc map

Touch what the change implies; skip the rest. A bug fix ≠ a feature ≠ a learning.

| File | Role | Update it when… |
|---|---|---|
| `CLAUDE.md` | Universal dev principles + "scar tissue" | The work taught a **transferable** lesson (a bug class, a gotcha, a pattern). Add a concise bullet near the related existing one. |
| `AGENTS.md` | The *how* for agents (workflow, verify, review) | You found an agent-facing technique (a verification approach, a review method). |
| `DESIGN.md` | The *look / UX* | A new UI primitive (§ 8 components) or a visual gotcha (§ 12 pitfalls). Reference the sibling data rule in CLAUDE.md, don't duplicate it. |
| `README.md` | Human entry point | Endpoints, "what works end-to-end," or any command/config changed. Keep it skimmable. |
| `llms.txt` | Machine-readable file index | A new source file or doc exists (add a one-liner), or a file's role changed. |
| `backlog.md` | Deferred work | An item shipped (move to **Done**, ~~strikethrough~~ + what shipped) or the work surfaced a new follow-up. Demote stale "high". |
| `issues.md` | Bug audit trail | Any bug was fixed (see the entry format below). Also log accepted limitations so they aren't "rediscovered." |
| `docs/STATUS.md` | Resume point (read first next session) | Always, for substantive work: bump "Last updated", the **verified test count** (the number you just ran), what's done, and the next-up gaps (remove what's built; renumber). |
| `docs/PLAN.md` | Build-out plan | Update the **Progress banner** (mark ✓, move newly-human-gated items). Leave the historical plan text as-is — it's the record of what was planned. |
| `docs/SESSION-HISTORY.md` | Narrative / decision log | Append: what shipped, agents spawned + headline findings, tools/skills used, key decisions + **why**, gotchas hit. |
| `backend/.env.example` | Config documentation | A config/env var was added (one-line comment + default) or removed (delete every reference). |

### issues.md entry format

Newest first. Each fixed bug gets: `date · area (file) · one-line description · **root
cause** (code bug / test bug / design bug) · status`, then the fix + commit + whether
a regression test was added. Example:

```
- **Budget guard under-counted spend** · `factory/pipeline.py` `_enforce_x_budget`
  · **code bug** · Fixed (`1579281`). Counted on published_at, not the x_tweet_id
  spend signal, so a post-then-crash drop escaped the cap. Now counts on x_tweet_id.
  **Regression test:** test_broadcast.py::test_x_budget_guard_counts_posted_but_unpublished_drops.
```

## Step 3 — write it like the humans here do

The prose is judged as hard as the code (full AI-tell list in DESIGN.md § 11.1):

- **No AI register.** Cut *delve, leverage, robust, seamless, "it's worth noting,"*
  rule-of-three padding, and hollow summaries. Lead with the specific.
- **Match the surrounding idiom.** Read the neighboring bullets and mirror their
  voice and length — a doc edit shouldn't announce a different author.
- **Explain the *why*, don't decree.** A scar-tissue note that names the failure
  mode ages better than an all-caps MUST.
- **Keep generated output consistent with its source.** If a change renamed a var
  or endpoint, fix every doc reference in the same pass — don't leave a live doc
  pointing at a dead name.

## Step 4 — sync checklist (before committing)

Run these so no doc lies. The greps are the point — a rename that's right in the
code but stale in three docs is the classic drift.

- [ ] STATUS.md test count == actual `pytest -q` tail.
- [ ] No removed config/endpoint still referenced:
      `grep -rn <removed_name> README.md llms.txt backlog.md docs/ backend/.env.example`
- [ ] New endpoints are in README's API list **and** described right.
- [ ] New source files / docs are in `llms.txt`.
- [ ] backlog.md "Done" matches what shipped; open items are still genuinely open.
- [ ] issues.md has an entry per bug fixed (with commit + regression-test note).
- [ ] Dates bumped: STATUS "Last updated," new issues.md entries, PLAN progress.
- [ ] Re-read each edited paragraph once for AI-tell and idiom.

## Step 5 — commit

Commit in the human's plain voice, **no AI co-author / footer** (CLAUDE.md git
discipline). Use a `docs:` prefix stating what changed and why. Docs describing
shipped code may ride with that code's commit or land as a focused `docs:` commit —
either is fine. A stale doc is not.
