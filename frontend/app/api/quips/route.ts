import Anthropic from "@anthropic-ai/sdk";
import { NextResponse } from "next/server";
import { z } from "zod";

import { readHallOfFame } from "@/lib/hallOfFame";
import {
  buildGeneratePrompt,
  buildGenerateSystemPrompt,
  buildJudgePrompt,
  cleanAndFilter,
  FAMILY_BLOCKLIST,
  JUDGE_SYSTEM_PROMPT,
  parseBatch,
  QuipError,
  sampleAnchors,
} from "@/lib/quips";

// Node runtime: the Anthropic SDK isn't edge-compatible, and the key must stay
// server-side. This handler is the *only* place ANTHROPIC_API_KEY is read — it
// lives with the dashboard server, never on the FastAPI admin API.
export const runtime = "nodejs";

// Stage 1 writes (comedy is the product → Sonnet); Stage 2 judges (cheaper →
// Haiku). Both overridable; QUIP_MODEL keeps its meaning (the generator).
const DEFAULT_GENERATE_MODEL = "claude-sonnet-5";
const DEFAULT_JUDGE_MODEL = "claude-haiku-4-5";
const DEFAULT_COUNT = 6;
const DEFAULT_MAX_CHARS = 80;

// In-process caches. The dashboard is a single long-lived server, so a module-
// level Map is enough: stop re-billing repeat clicks on the same trend, and cap
// the blast radius of a hammered button. Both reset on restart — fine for a
// local, single-operator tool.
const CACHE_TTL_MS = 10 * 60 * 1000;
const RATE_LIMIT_MAX = 20; // generations
const RATE_LIMIT_WINDOW_MS = 60 * 1000;

type CacheEntry = { at: number; body: { quips: string[]; dropped: number } };
const quipCache = new Map<string, CacheEntry>();
const rateHits: number[] = [];

// The trend fields the browser already has (from GET /trends), plus the Part A
// grounding. Validated so a bad/huge body can't reach the model.
const bodySchema = z.object({
  term: z.string().min(1).max(200),
  source: z.string().max(100).default("unknown"),
  measurement: z.string().max(100).default("unknown"),
  context: z.string().max(1000).optional(),
  angles: z.array(z.string().max(120)).max(6).optional(),
  ip_risk: z.boolean().optional(),
  count: z.number().int().min(1).max(12).optional(),
});

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

function rateLimited(now: number): boolean {
  while (rateHits.length && now - rateHits[0] > RATE_LIMIT_WINDOW_MS) rateHits.shift();
  if (rateHits.length >= RATE_LIMIT_MAX) return true;
  rateHits.push(now);
  return false;
}

function textOf(message: Anthropic.Message): string {
  let out = "";
  for (const block of message.content) if (block.type === "text") out += block.text;
  return out.trim();
}

export async function POST(req: Request): Promise<NextResponse> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    // Fail loud so the operator knows to set the key (or paste copy manually).
    return NextResponse.json(
      {
        detail:
          "ANTHROPIC_API_KEY is not set on the dashboard server — cannot " +
          "auto-generate copy. Set the key, or paste design copy manually.",
      },
      { status: 503 },
    );
  }

  let json: unknown;
  try {
    json = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid JSON body" }, { status: 400 });
  }
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json(
      { detail: "invalid request body", errors: parsed.error.flatten().fieldErrors },
      { status: 400 },
    );
  }

  const { term, source, measurement, context, angles, ip_risk: ipRisk } = parsed.data;
  const configuredCount = envInt("QUIP_COUNT", DEFAULT_COUNT);
  const maxChars = envInt("QUIP_MAX_CHARS", DEFAULT_MAX_CHARS);
  const generateModel = process.env.QUIP_MODEL || DEFAULT_GENERATE_MODEL;
  const judgeModel = process.env.QUIP_JUDGE_MODEL || DEFAULT_JUDGE_MODEL;
  const count = Math.max(1, Math.min(parsed.data.count ?? configuredCount, 12));
  // Stage 1 over-generates so the judge and filters have a real pool to cut from.
  const generateCount = Math.min(20, Math.max(12, count * 3));

  const now = Date.now();
  const cacheKey = JSON.stringify([term, count, ipRisk ?? false, context ?? ""]);
  const cached = quipCache.get(cacheKey);
  if (cached && now - cached.at < CACHE_TTL_MS) {
    return NextResponse.json(cached.body);
  }
  if (rateLimited(now)) {
    return NextResponse.json(
      { detail: "too many generations — wait a few seconds and try again." },
      { status: 429 },
    );
  }

  const client = new Anthropic({ apiKey });
  const anchors = sampleAnchors(await readHallOfFame());

  // --- Stage 1: generate a spread of candidates (Sonnet, warm) --------------
  let candidates: string[];
  try {
    const message = await client.messages.create({
      model: generateModel,
      max_tokens: 1024,
      temperature: 1,
      system: buildGenerateSystemPrompt(anchors),
      messages: [
        {
          role: "user",
          content: buildGeneratePrompt({
            term,
            source,
            measurement,
            context,
            angles,
            ipRisk,
            count: generateCount,
          }),
        },
      ],
    });
    candidates = parseBatch(textOf(message));
  } catch (e) {
    if (e instanceof QuipError) {
      return NextResponse.json({ detail: e.message }, { status: 502 });
    }
    return NextResponse.json(
      { detail: `quip generation failed: ${e instanceof Error ? e.message : "unknown error"}` },
      { status: 502 },
    );
  }

  // Gate candidates BEFORE judging: family/cliché/IP/era drops are the auditable
  // signal, and there's no point spending judge tokens on lines we'd cut anyway.
  const prefiltered = cleanAndFilter(candidates, {
    blocklist: FAMILY_BLOCKLIST,
    maxChars,
    count: Number.POSITIVE_INFINITY,
    term,
    ipRisk,
  });
  const dropped = prefiltered.dropped;

  // If the pool already fits, skip the judge call (cheaper, and nothing to rank).
  let finalQuips: string[];
  if (prefiltered.kept.length <= count) {
    finalQuips = prefiltered.kept.slice(0, count);
  } else {
    // --- Stage 2: judge down to the best, most distinct `count` (Haiku) ------
    try {
      const message = await client.messages.create({
        model: judgeModel,
        max_tokens: 512,
        system: JUDGE_SYSTEM_PROMPT,
        messages: [
          { role: "user", content: buildJudgePrompt(term, prefiltered.kept, count) },
        ],
      });
      const ranked = parseBatch(textOf(message));
      // Re-clean the judge output (belt) and cap to count. Keep the term/ipRisk
      // guard; the extra drops here aren't part of the reported cliché count.
      const judged = cleanAndFilter(ranked, {
        blocklist: FAMILY_BLOCKLIST,
        maxChars,
        count,
        term,
        ipRisk,
      });
      // Judge occasionally drops everything (over-strict / bad JSON echo); fall
      // back to the prefiltered top-N so the operator always gets choices.
      finalQuips = judged.kept.length > 0 ? judged.kept : prefiltered.kept.slice(0, count);
    } catch {
      // Judge failed but Stage 1 succeeded — degrade gracefully to the pool,
      // never a hard error (we already have good, filtered candidates).
      finalQuips = prefiltered.kept.slice(0, count);
    }
  }

  const body = { quips: finalQuips, dropped };
  quipCache.set(cacheKey, { at: now, body });
  return NextResponse.json(body);
}
