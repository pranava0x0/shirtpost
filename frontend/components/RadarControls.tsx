"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { api } from "@/lib/api";

export function RadarControls() {
  const router = useRouter();
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function refresh() {
    setMsg(null);
    startTransition(async () => {
      try {
        const { touched } = await api.triggerSweep();
        setMsg(`Swept ${touched} trends.`);
        router.refresh();
      } catch (e) {
        setMsg(e instanceof Error ? e.message : "Sweep failed.");
      }
    });
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={refresh}
        disabled={pending}
        className="min-h-[44px] rounded-lg border border-neutral-700 px-4 text-sm font-medium text-neutral-200 transition hover:border-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-500 disabled:opacity-50"
      >
        {pending ? "Sweeping…" : "Refresh radar"}
      </button>
      {msg ? <span className="text-xs text-neutral-400">{msg}</span> : null}
    </div>
  );
}
