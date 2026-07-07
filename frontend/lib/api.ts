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
    trend: Pick<Trend, "term" | "source" | "measurement">,
    count?: number,
  ): Promise<{ quips: string[] }> => {
    const res = await fetch("/api/quips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        term: trend.term,
        source: trend.source,
        measurement: trend.measurement,
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
    return (await res.json()) as { quips: string[] };
  },
  submitDesign: (trendId: number, designCopy: string) =>
    http<Drop>(`/trends/${trendId}/submit`, {
      method: "POST",
      body: JSON.stringify({ design_copy: designCopy }),
    }),
  retryDrop: (dropId: number) =>
    http<Drop>(`/drops/${dropId}/retry`, { method: "POST" }),
};
