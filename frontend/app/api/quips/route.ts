import Anthropic from "@anthropic-ai/sdk";
import { NextResponse } from "next/server";
import { z } from "zod";

import {
  buildUserPrompt,
  cleanAndFilter,
  FAMILY_BLOCKLIST,
  parseBatch,
  QuipError,
  SYSTEM_PROMPT,
} from "@/lib/quips";

// Node runtime: the Anthropic SDK isn't edge-compatible, and the key must stay
// server-side. This handler is the *only* place ANTHROPIC_API_KEY is read — it
// lives with the dashboard server, never on the FastAPI admin API.
export const runtime = "nodejs";

const DEFAULT_MODEL = "claude-haiku-4-5";
const DEFAULT_COUNT = 6;
const DEFAULT_MAX_CHARS = 80;

// The trend fields the browser already has (from GET /trends). Validated so a
// bad/huge body can't reach the model. `count` is clamped 1..12 below too.
const bodySchema = z.object({
  term: z.string().min(1).max(200),
  source: z.string().max(100).default("unknown"),
  measurement: z.string().max(100).default("unknown"),
  count: z.number().int().min(1).max(12).optional(),
});

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
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

  const { term, source, measurement } = parsed.data;
  const configuredCount = envInt("QUIP_COUNT", DEFAULT_COUNT);
  const maxChars = envInt("QUIP_MAX_CHARS", DEFAULT_MAX_CHARS);
  const model = process.env.QUIP_MODEL || DEFAULT_MODEL;
  const count = Math.max(1, Math.min(parsed.data.count ?? configuredCount, 12));

  const client = new Anthropic({ apiKey });

  let text = "";
  try {
    const message = await client.messages.create({
      model,
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      messages: [
        { role: "user", content: buildUserPrompt(term, source, measurement, count) },
      ],
    });
    for (const block of message.content) {
      if (block.type === "text") text += block.text;
    }
    text = text.trim();
  } catch (e) {
    // Upstream model/API failure — a real error, surfaced (never silent []).
    return NextResponse.json(
      { detail: `quip generation failed: ${e instanceof Error ? e.message : "unknown error"}` },
      { status: 502 },
    );
  }

  try {
    const raw = parseBatch(text);
    const quips = cleanAndFilter(raw, {
      blocklist: FAMILY_BLOCKLIST,
      maxChars,
      count,
    });
    return NextResponse.json({ quips });
  } catch (e) {
    if (e instanceof QuipError) {
      return NextResponse.json({ detail: e.message }, { status: 502 });
    }
    throw e;
  }
}
