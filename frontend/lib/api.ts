import { env } from "./env";
import type { Drop, Trend, TrendObservation } from "./types";

const BASE = env.NEXT_PUBLIC_API_BASE_URL;

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${detail.slice(0, 300)}`);
  }
  return (await res.json()) as T;
}

export const api = {
  listTrends: () => http<Trend[]>("/trends?limit=100"),
  listDrops: () => http<Drop[]>("/drops"),
  getDrop: (id: number) => http<Drop>(`/drops/${id}`),
  getObservations: (trendId: number) =>
    http<TrendObservation[]>(`/trends/${trendId}/observations`),
  triggerSweep: () => http<{ touched: number }>("/radar/sweep", { method: "POST" }),
  // Hits the Next.js server route (same origin — NOT the FastAPI backend), so
  // the Anthropic key stays with the dashboard server. Sends the trend fields
  // the browser already has; no round-trip to FastAPI.
  generateQuips: async (
    trend: Pick<
      Trend,
      "term" | "source" | "measurement" | "context" | "angles" | "ip_risk"
    >,
    count?: number,
  ): Promise<{ quips: string[]; dropped?: number }> => {
    const res = await fetch("/api/quips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        term: trend.term,
        source: trend.source,
        measurement: trend.measurement,
        // Discovery grounding — only sent when present (null omitted).
        ...(trend.context ? { context: trend.context } : {}),
        ...(trend.angles && trend.angles.length ? { angles: trend.angles } : {}),
        ...(trend.ip_risk ? { ip_risk: true } : {}),
        ...(count ? { count } : {}),
      }),
      cache: "no-store",
    });
    if (!res.ok) {
      const body = await res.text();
      let detail = body;
      try {
        detail = (JSON.parse(body) as { detail?: string }).detail ?? body;
      } catch {
        // non-JSON error body — use the raw text
      }
      throw new Error(detail.slice(0, 300));
    }
    return (await res.json()) as { quips: string[]; dropped?: number };
  },
  // Fire-and-forget: append a shipped design line to the hall-of-fame so the
  // house voice becomes what the operator actually picks. Best-effort — a failure
  // never blocks the submit that triggered it.
  recordHallOfFame: (copy: string): void => {
    void fetch("/api/hall-of-fame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ copy }),
      cache: "no-store",
    }).catch(() => {});
  },
  submitDesign: (
    trendId: number,
    designCopy: string,
    opts?: { layout?: string; garmentColor?: string },
  ) =>
    http<Drop>(`/trends/${trendId}/submit`, {
      method: "POST",
      body: JSON.stringify({
        design_copy: designCopy,
        ...(opts?.layout ? { layout: opts.layout } : {}),
        ...(opts?.garmentColor ? { garment_color: opts.garmentColor } : {}),
      }),
    }),
  retryDrop: (dropId: number) =>
    http<Drop>(`/drops/${dropId}/retry`, { method: "POST" }),
};
