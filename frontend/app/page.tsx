import { RadarControls } from "@/components/RadarControls";
import { TrendCard } from "@/components/TrendCard";
import { api } from "@/lib/api";
import { sourceLabel } from "@/lib/sources";
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

// Group trends into per-source lanes, preserving the API's hype-desc order
// within each. Volumes are not comparable across sources, so ranking them on one
// global scale would imply a comparison that doesn't exist. Lane order is by the
// hype of each source's top trend (trends already arrive hype-desc).
function trendsBySource(trends: Trend[]): [string, Trend[]][] {
  const lanes = new Map<string, Trend[]>();
  for (const trend of trends) {
    const lane = lanes.get(trend.source);
    if (lane) lane.push(trend);
    else lanes.set(trend.source, [trend]);
  }
  return [...lanes.entries()];
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
      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">ShirtPost Radar</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Trending hooks by Hype Score. Paste design copy to fire the factory.
          </p>
        </div>
        <RadarControls />
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
        <div className="space-y-8">
          {trendsBySource(trends).map(([source, laneTrends]) => (
            <section key={source} aria-label={`${sourceLabel(source)} trends`}>
              <h2 className="mb-2 flex items-baseline gap-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
                {sourceLabel(source)}
                <span className="font-normal normal-case text-neutral-600">
                  ranked within source
                </span>
              </h2>
              <ul className="space-y-3">
                {laneTrends.map((trend) => (
                  <TrendCard
                    key={trend.id}
                    trend={trend}
                    latestDrop={latest.get(trend.id) ?? null}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
