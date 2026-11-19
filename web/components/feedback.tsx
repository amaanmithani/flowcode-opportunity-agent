"use client";

// Rep feedback on each opportunity. The prototype keeps events in localStorage.
// In production the same event shape goes to PostHog/Amplitude and the CRM.

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore } from "react";
import { Check, Download, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export const DISMISS_REASONS = [
  "Not a real opportunity",
  "Bad fit for Flowcode",
  "Bad timing",
  "Already in progress",
  "Source looks wrong",
] as const;

export interface FeedbackEvent {
  event: "opportunity_accepted" | "opportunity_dismissed";
  slug: string;
  run_id: string;
  rank: number;
  title: string;
  play_id: string;
  score: number;
  reason?: string;
  ts: string;
}

interface Ctx {
  events: FeedbackEvent[];
  record: (e: Omit<FeedbackEvent, "ts">) => void;
  undo: (rank: number) => void;
}

const FeedbackContext = createContext<Ctx | null>(null);
const key = (slug: string, runId: string) => `fc-feedback:${slug}:${runId}`;

// localStorage as an external store. If storage is blocked, an in-memory copy keeps feedback working for the session.
const memory = new Map<string, string>();
const CHANGE = "fc-feedback-change";

function readRaw(k: string): string {
  try {
    return localStorage.getItem(k) ?? memory.get(k) ?? "[]";
  } catch {
    return memory.get(k) ?? "[]";
  }
}

function writeRaw(k: string, v: string) {
  memory.set(k, v);
  try {
    localStorage.setItem(k, v);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event(CHANGE));
}

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener(CHANGE, cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener(CHANGE, cb);
  };
}

export function FeedbackProvider({ slug, runId, children }: { slug: string; runId: string; children: React.ReactNode }) {
  const k = key(slug, runId);
  const raw = useSyncExternalStore(subscribe, () => readRaw(k), () => "[]");
  const events = useMemo<FeedbackEvent[]>(() => {
    try {
      return JSON.parse(raw);
    } catch {
      return [];
    }
  }, [raw]);

  const persist = useCallback((next: FeedbackEvent[]) => writeRaw(k, JSON.stringify(next)), [k]);

  const value = useMemo<Ctx>(
    () => ({
      events,
      record: (e) => persist([...events.filter((x) => x.rank !== e.rank), { ...e, ts: new Date().toISOString() }]),
      undo: (rank) => persist(events.filter((x) => x.rank !== rank)),
    }),
    [events, persist],
  );

  return <FeedbackContext.Provider value={value}>{children}</FeedbackContext.Provider>;
}

function useFeedback() {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error("FeedbackProvider missing");
  return ctx;
}

export function FeedbackSummary({ total }: { total: number }) {
  const { events } = useFeedback();
  const accepted = events.filter((e) => e.event === "opportunity_accepted").length;
  const dismissed = events.length - accepted;

  const download = () => {
    const blob = new Blob([JSON.stringify(events, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "feedback-events.json";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
      <span>
        Rep feedback: <strong className="text-foreground">{accepted}</strong> accepted ·{" "}
        <strong className="text-foreground">{dismissed}</strong> dismissed · {total - events.length} unreviewed
      </span>
      {events.length > 0 && (
        <Button variant="ghost" size="sm" onClick={download}>
          <Download /> Export events
        </Button>
      )}
    </div>
  );
}

export function FeedbackButtons(props: Omit<FeedbackEvent, "event" | "ts" | "reason">) {
  const { events, record, undo } = useFeedback();
  const [choosing, setChoosing] = useState(false);
  const current = events.find((e) => e.rank === props.rank);

  if (current) {
    const accepted = current.event === "opportunity_accepted";
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={accepted ? "font-medium text-emerald-700 dark:text-emerald-400" : "text-muted-foreground"}>
          {accepted ? "✓ Accepted. Added to rep queue" : `Dismissed: ${current.reason}`}
        </span>
        <Button variant="link" size="sm" onClick={() => undo(props.rank)}>
          Undo
        </Button>
      </div>
    );
  }

  if (choosing) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Why?</span>
        {DISMISS_REASONS.map((r) => (
          <Button
            key={r}
            variant="outline"
            size="sm"
            onClick={() => {
              record({ ...props, event: "opportunity_dismissed", reason: r });
              setChoosing(false);
            }}
          >
            {r}
          </Button>
        ))}
        <Button variant="ghost" size="sm" onClick={() => setChoosing(false)}>
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <Button size="sm" onClick={() => record({ ...props, event: "opportunity_accepted" })}>
        <Check /> Accept
      </Button>
      <Button size="sm" variant="outline" onClick={() => setChoosing(true)}>
        <X /> Dismiss
      </Button>
    </div>
  );
}
