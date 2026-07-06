// Human labels for radar source ids. Trends are grouped into per-source lanes
// because volumes are NOT comparable across sources (see `measurement`), so one
// global ranking would imply a comparison that doesn't exist.

export const SOURCE_LABELS: Record<string, string> = {
  simulated: "Simulated (seed data)",
  wikipedia: "Wikipedia (most viewed)",
  google_trends: "Google Trends",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}
