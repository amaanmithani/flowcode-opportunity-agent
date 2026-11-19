"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Check, Loader2, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Step = { key: string; label: string; detail?: string; state: "todo" | "active" | "done" };

const INITIAL: Step[] = [
  { key: "resolve", label: "Identify the brand", state: "todo" },
  { key: "sweep", label: "Read its newsroom and press wires", state: "todo" },
  { key: "research", label: "Research 7 channels", state: "todo" },
  { key: "extract", label: "Extract claims with quotes", state: "todo" },
  { key: "verify", label: "Verify every quote against its source", state: "todo" },
  { key: "rank", label: "Match to Flowcode plays and rank", state: "todo" },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Ev = Record<string, any>;

function apply(steps: Step[], e: Ev, channelsDone: Set<string>): Step[] {
  const set = (key: string, patch: Partial<Step>) => steps.map((s) => (s.key === key ? { ...s, ...patch } : s));
  const activate = (key: string) => set(key, { state: "active" });

  if (e.type === "run_start") return activate("resolve");
  if (e.type === "stage_done" && e.stage === "resolve") {
    steps = set("resolve", { state: "done", detail: `${e.name} · ${String(e.account).replace("_", " ")}` });
    return steps.map((s) => (s.key === "sweep" ? { ...s, state: "active" } : s));
  }
  if (e.type === "llm_call" && e.stage === "sweep") {
    steps = set("sweep", { state: "done" });
    return steps.map((s) => (s.key === "research" ? { ...s, state: "active", detail: "0 of 7 channels" } : s));
  }
  if (e.type === "llm_call" && e.stage === "research") {
    channelsDone.add(e.label);
    return set("research", { state: "active", detail: `${channelsDone.size} of 7 channels` });
  }
  if (e.type === "stage_done" && e.stage === "research") {
    steps = set("research", { state: "done", detail: "7 of 7 channels" });
    return steps.map((s) => (s.key === "extract" ? { ...s, state: "active" } : s));
  }
  if (e.type === "stage_done" && e.stage === "extract") {
    steps = set("extract", { state: "done", detail: `${e.signals} claims` });
    return steps.map((s) => (s.key === "verify" ? { ...s, state: "active" } : s));
  }
  if (e.type === "stage_done" && e.stage === "verify") {
    const dropped = Object.values((e.dropped ?? {}) as Record<string, number>).reduce((a, b) => a + b, 0);
    steps = set("verify", { state: "done", detail: `${e.verified} verified · ${dropped} dropped` });
    return steps.map((s) => (s.key === "rank" ? { ...s, state: "active" } : s));
  }
  if (e.type === "stage_done" && e.stage === "rank") {
    return set("rank", { state: "done", detail: `${e.opportunities} opportunities` });
  }
  return steps;
}

export function ResearchBox() {
  const router = useRouter();
  const [company, setCompany] = useState("");
  const [steps, setSteps] = useState<Step[] | null>(null);
  const [cost, setCost] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (busy || company.trim().length < 2) return;
    setBusy(true);
    setError(null);
    setCost(0);
    let current = INITIAL;
    setSteps(current);
    const channelsDone = new Set<string>();
    let slug: string | null = null;
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: company.trim() }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `Request failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let i: number;
        while ((i = buffer.indexOf("\n")) >= 0) {
          const msg = JSON.parse(buffer.slice(0, i));
          buffer = buffer.slice(i + 1);
          if (msg.type === "progress") {
            const ev = msg.event as Ev;
            if (ev.type === "llm_call") setCost((c) => c + (ev.cost_usd ?? 0));
            if (ev.type === "run_done") slug = ev.slug;
            current = apply(current, ev, channelsDone);
            setSteps(current);
          } else if (msg.type === "error") {
            throw new Error(msg.detail ? `${msg.message}\n${msg.detail}` : msg.message);
          }
        }
      }
      if (!slug) throw new Error("The run ended without producing a brief.");
      router.push(`/${slug}`);
      router.refresh();
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
      setBusy(false);
    }
  }

  function cancel() {
    abortRef.current?.abort();
    setBusy(false);
    setSteps(null);
  }

  return (
    <div className="rounded-xl border p-4">
      <form onSubmit={run} className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            disabled={busy}
            placeholder="Research a brand: name or website, e.g. Liquid Death"
            aria-label="Brand name or website"
            maxLength={80}
            className="h-10 w-full rounded-lg border bg-background pr-3 pl-9 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60"
          />
        </div>
        {busy ? (
          <Button type="button" variant="outline" className="h-10" onClick={cancel}>
            <X /> Cancel
          </Button>
        ) : (
          <Button type="submit" className="h-10" disabled={company.trim().length < 2}>
            Research
          </Button>
        )}
      </form>
      <p className="mt-2 text-xs text-muted-foreground">Takes about 90 seconds and costs about $1 in API usage per brand.</p>

      {steps && (
        <ol className="mt-4 space-y-2 border-t pt-4">
          {steps.map((s) => (
            <li key={s.key} className="flex items-center gap-2 text-sm">
              {s.state === "done" ? (
                <Check className="size-4 text-emerald-600" />
              ) : s.state === "active" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <span className="size-4 rounded-full border" />
              )}
              <span className={s.state === "todo" ? "text-muted-foreground" : ""}>{s.label}</span>
              {s.detail && <span className="text-muted-foreground">· {s.detail}</span>}
            </li>
          ))}
          <li className="pt-1 text-xs text-muted-foreground tabular-nums">Spent so far: ${cost.toFixed(2)}</li>
        </ol>
      )}
      {error && <p className="mt-3 whitespace-pre-wrap text-sm text-destructive">{error}</p>}
    </div>
  );
}
