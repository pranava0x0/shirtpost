"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { Sparkline } from "@/components/Sparkline";
import { api } from "@/lib/api";
import type { Drop, DropStatus, Trend } from "@/lib/types";

const STATUS_STYLES: Record<DropStatus, string> = {
  pending: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  processing: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  published: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  failed: "bg-red-500/15 text-red-300 border-red-500/30",
};

function isInFlight(status: DropStatus | undefined): boolean {
  return status === "pending" || status === "processing";
}

function StatusBadge({ status }: { status: DropStatus }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

export function TrendCard({ trend, latestDrop }: { trend: Trend; latestDrop: Drop | null }) {
  const router = useRouter();
  const [copy, setCopy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [drop, setDrop] = useState<Drop | null>(latestDrop);
  const [pending, startTransition] = useTransition();
  const [retrying, startRetry] = useTransition();

  // Adopt a newer drop coming from the server (e.g. after router.refresh()).
  useEffect(() => {
    setDrop(latestDrop);
  }, [latestDrop]);

  // Poll an in-flight drop until it settles, then refresh server data.
  useEffect(() => {
    if (!drop || !isInFlight(drop.status)) return;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const fresh = await api.getDrop(drop.id);
        if (!active) return;
        setDrop(fresh);
        if (!isInFlight(fresh.status)) {
          clearInterval(timer);
          router.refresh();
        }
      } catch {
        // transient — keep polling
      }
    }, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [drop, router]);

  function submit() {
    const value = copy.trim();
    if (!value) {
      setError("Design copy is required.");
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const created = await api.submitDesign(trend.id, value);
        setCopy("");
        setDrop(created);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Submission failed.");
      }
    });
  }

  function retry() {
    if (!drop) return;
    setError(null);
    startRetry(async () => {
      try {
        // Backend resumes from the last committed step — an already-posted tweet
        // is never sent twice. The poll effect then tracks it to completion.
        const requeued = await api.retryDrop(drop.id);
        setDrop(requeued);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Retry failed.");
      }
    });
  }

  return (
    <li className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{trend.term}</h2>
        <span className="flex items-center gap-2">
          <Sparkline points={trend.spark} />
          <span
            className="font-mono text-sm text-neutral-400"
            aria-label={`Hype score ${trend.hype_score}`}
          >
            hype {Math.round(trend.hype_score).toLocaleString()}
          </span>
        </span>
      </div>

      <div
        className="mt-2 h-1 w-full overflow-hidden rounded-full bg-neutral-800"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={Number(trend.normalized_hype.toFixed(2))}
        aria-label="Hype relative to this source"
      >
        <div
          className="h-full rounded-full bg-neutral-500"
          style={{ width: `${Math.round(trend.normalized_hype * 100)}%` }}
        />
      </div>

      <p className="mt-1 text-xs text-neutral-500">
        {trend.source_url ? (
          <a
            href={trend.source_url}
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-neutral-300"
          >
            {trend.source}
          </a>
        ) : (
          <span>{trend.source}</span>
        )}
        {" · "}
        {trend.volume.toLocaleString()} {trend.measurement}
        {" · vel "}
        {trend.velocity.toFixed(1)}/hr
        {" · seen "}
        {new Date(`${trend.last_seen_at}Z`).toLocaleString()}
      </p>
      {!trend.source_url ? (
        <p className="mt-0.5 text-[11px] text-amber-400/80">
          {trend.source === "simulated"
            ? "seed data — not real demand; verify before publishing"
            : "no source link — verify the trend before publishing"}
        </p>
      ) : null}

      <div className="mt-3">
        <label htmlFor={`copy-${trend.id}`} className="sr-only">
          Design copy for {trend.term}
        </label>
        <textarea
          id={`copy-${trend.id}`}
          value={copy}
          onChange={(e) => setCopy(e.target.value)}
          rows={2}
          maxLength={500}
          placeholder="Paste design copy from your LLM…"
          className="w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm focus:border-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-500"
        />
      </div>

      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={pending}
          className="min-h-[44px] rounded-lg bg-neutral-100 px-4 text-sm font-semibold text-neutral-900 transition hover:bg-white focus:outline-none focus:ring-2 focus:ring-neutral-400 disabled:opacity-50"
        >
          {pending ? "Submitting…" : "Submit to Factory"}
        </button>
        {drop ? <StatusBadge status={drop.status} /> : null}
      </div>

      {error ? <p className="mt-2 text-sm text-red-400">{error}</p> : null}

      {drop?.error ? (
        <p className="mt-2 break-words text-xs text-red-400">
          Last drop error: {drop.error}
        </p>
      ) : null}

      {drop?.status === "failed" ? (
        <button
          type="button"
          onClick={retry}
          disabled={retrying}
          className="mt-2 min-h-[44px] rounded-lg border border-red-500/40 px-4 text-sm font-medium text-red-300 transition hover:border-red-400 hover:text-red-200 focus:outline-none focus:ring-2 focus:ring-red-500/50 disabled:opacity-50"
        >
          {retrying ? "Retrying…" : "Retry drop"}
        </button>
      ) : null}

      {drop?.status === "published" ? (
        <p className="mt-2 text-xs text-emerald-400">
          Published{drop.dry_run ? " (dry run)" : ""}
          {drop.x_tweet_id ? ` · tweet ${drop.x_tweet_id}` : ""}
          {drop.printful_mockup_url ? (
            <>
              {" · "}
              <a
                href={drop.printful_mockup_url}
                target="_blank"
                rel="noreferrer"
                className="underline hover:text-emerald-300"
              >
                mockup
              </a>
            </>
          ) : null}
        </p>
      ) : null}
    </li>
  );
}
