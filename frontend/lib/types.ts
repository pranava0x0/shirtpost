// Mirrors backend/app/schemas.py. Keep in sync with the API contract.

export type Trend = {
  id: number;
  term: string;
  source: string;
  source_url: string | null;
  measurement: string;
  volume: number;
  velocity: number;
  hype_score: number;
  // Hype relative to its own source (0..1). Volumes are not comparable across
  // sources, so this is a within-lane scale only — never a cross-source rank.
  normalized_hype: number;
  // Recent hype trajectory, oldest -> newest, for the inline sparkline.
  spark: number[];
  first_seen_at: string;
  last_seen_at: string;
};

export type TrendObservation = {
  id: number;
  trend_id: number;
  volume: number;
  velocity: number;
  hype_score: number;
  measurement: string;
  observed_at: string;
};

export type DropStatus = "pending" | "processing" | "published" | "failed";

export type Drop = {
  id: number;
  trend_id: number;
  design_copy: string;
  status: DropStatus;
  error: string | null;
  printful_mockup_url: string | null;
  printful_sync_product_id: string | null;
  x_tweet_id: string | null;
  dry_run: boolean;
  created_at: string;
  published_at: string | null;
};
