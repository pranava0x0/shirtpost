import { TrendCard } from "@/components/TrendCard";
import { api } from "@/lib/api";
import type { Drop, Trend } from "@/lib/types";

// Always render fresh — the radar updates Hype Scores in the background.
export const dynamic = "force-dynamic";

function latestDropByTrend(drops: Drop[]): Map<number, Drop> {
  // drops arrive newest-first; keep the first seen per trend.
  const map = new Map<number, Drop>();
  for (const drop of drops) {
    if (!map.has(drop.trend_id)) map.set(drop.trend_id, drop);
  }
  return map;
}

export default async function AdminPage() {
  let trends: Trend[] = [];
  let drops: Drop[] = [];
  let error: string | null = null;

  try {
    [trends, drops] = await Promise.all([api.listTrends(), api.listDrops()]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to reach the radar API.";
  }

  const latest = latestDropByTrend(drops);

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">ShirtPost Radar</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Trending hooks by Hype Score. Paste design copy to fire the factory.
        </p>
      </header>

      {error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          <p className="font-semibold">Couldn&apos;t load trends.</p>
          <p className="mt-1 break-words text-red-400/90">{error}</p>
          <p className="mt-2 text-red-400/70">
            Is the backend running on{" "}
            <code>{process.env.NEXT_PUBLIC_API_BASE_URL}</code>?
          </p>
        </div>
      ) : trends.length === 0 ? (
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-6 text-center text-sm text-neutral-400">
          No trends yet. The radar populates within one poll interval.
        </div>
      ) : (
        <ul className="space-y-3">
          {trends.map((trend) => (
            <TrendCard
              key={trend.id}
              trend={trend}
              latestDrop={latest.get(trend.id) ?? null}
            />
          ))}
        </ul>
      )}
    </main>
  );
}
