import { env } from "./env";
import type { Drop, Trend } from "./types";

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
  submitDesign: (trendId: number, designCopy: string) =>
    http<Drop>(`/trends/${trendId}/submit`, {
      method: "POST",
      body: JSON.stringify({ design_copy: designCopy }),
    }),
};
