import { NextResponse } from "next/server";
import { z } from "zod";

import { appendHallOfFame } from "@/lib/hallOfFame";

// Node runtime: writes a JSON file on the dashboard server's disk. Same server
// that holds the Anthropic key — never the public FastAPI admin API.
export const runtime = "nodejs";

const bodySchema = z.object({ copy: z.string().min(1).max(80) });

export async function POST(req: Request): Promise<NextResponse> {
  let json: unknown;
  try {
    json = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid JSON body" }, { status: 400 });
  }
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ detail: "invalid request body" }, { status: 400 });
  }
  // Best-effort append; appendHallOfFame swallows its own write errors.
  await appendHallOfFame(parsed.data.copy);
  return NextResponse.json({ ok: true });
}
