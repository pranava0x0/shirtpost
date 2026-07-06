// Tiny inline hype-trajectory sparkline. Pure SVG, no chart dependency. Points
// are the last N hype scores (oldest -> newest) from trend_observations.

export function Sparkline({
  points,
  width = 80,
  height = 24,
}: {
  points: number[];
  width?: number;
  height?: number;
}) {
  // Need at least two points to draw a line.
  if (points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const flat = max === min; // a flat series draws a centered horizontal line
  const span = max - min;
  const stepX = width / (points.length - 1);
  const pad = 2;
  const usableH = height - pad * 2;

  const coords = points.map((p, i) => {
    const x = i * stepX;
    const y = flat ? height / 2 : pad + usableH * (1 - (p - min) / span);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const rising = points[points.length - 1] >= points[0];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Hype trend over ${points.length} observations, latest ${Math.round(
        points[points.length - 1],
      ).toLocaleString()}`}
      className="overflow-visible"
    >
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={rising ? "rgb(52 211 153)" : "rgb(148 163 184)"}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
