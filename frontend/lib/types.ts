// Mirrors backend/app/schemas.py. Keep in sync with the API contract.

export type Trend = {
  id: number;
  term: string;
  source: string;
  source_url: string | null;
  volume: number;
  velocity: number;
  hype_score: number;
  first_seen_at: string;
  last_seen_at: string;
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
  created_at: string;
  published_at: string | null;
};
