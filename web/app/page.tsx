import Link from "next/link";
import { Suspense } from "react";
import { connection } from "next/server";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ResearchBox } from "@/components/research-box";
import { ACCOUNT_LABELS, listBriefs } from "@/lib/briefs";
import type { Brief } from "@/lib/types";

// Live research needs the Python agent running next to the web app, which is true locally.
// It is off automatically on Vercel (which sets VERCEL=1) or when LIVE_RUNS=off.
const LIVE = process.env.VERCEL !== "1" && process.env.LIVE_RUNS !== "off";

// The demo brand gets the large card. Every other brief is listed below it.
const FEATURED = "hershey";

function cost(b: Brief) {
  return `$${(b.stats.total_cost_usd ?? b.stats.cost_usd).toFixed(2)}`;
}

function FeaturedCard({ b }: { b: Brief }) {
  const top = b.opportunities.slice(0, 3);
  return (
    <Link href={`/${b.slug}`} className="group block rounded-2xl border p-5 transition-colors hover:bg-muted/40 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={b.account.label === "prospect" ? "default" : "secondary"}>{ACCOUNT_LABELS[b.account.label]}</Badge>
        <span className="text-sm text-muted-foreground">Sample brief</span>
      </div>
      <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">{b.resolution.official_name}</h2>
      <p className="mt-1 text-muted-foreground">{b.resolution.one_liner}</p>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        <span><strong className="tabular-nums">{b.stats.signals_verified}</strong> <span className="text-muted-foreground">verified facts</span></span>
        <span><strong className="tabular-nums">{b.stats.signals_dropped}</strong> <span className="text-muted-foreground">thrown out</span></span>
        <span><strong className="tabular-nums">{b.stats.opportunities}</strong> <span className="text-muted-foreground">opportunities</span></span>
        <span><strong className="tabular-nums">{cost(b)}</strong> <span className="text-muted-foreground">to research</span></span>
      </div>

      <ol className="mt-5 divide-y rounded-xl border bg-background">
        {top.map((o) => (
          <li key={o.rank} className="flex items-baseline gap-3 px-4 py-3">
            <span className="w-7 shrink-0 text-lg font-semibold tabular-nums">{o.score}</span>
            <div className="min-w-0">
              <p className="font-medium">{o.title}</p>
              <p className="truncate text-sm text-muted-foreground">{o.products.map((p) => p.name).join(" · ")} · like {o.case_study.brand}</p>
            </div>
          </li>
        ))}
      </ol>

      <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium">
        Open the full brief <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

function AccountCard({ b }: { b: Brief }) {
  const top = b.opportunities[0];
  return (
    <Link href={`/${b.slug}`} className="group flex flex-col rounded-xl border p-4 transition-colors hover:bg-muted/40">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{b.resolution.official_name}</span>
        <Badge variant={b.account.label === "prospect" ? "default" : "secondary"}>{ACCOUNT_LABELS[b.account.label]}</Badge>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        {b.stats.opportunities} opportunities · {b.stats.signals_verified} verified facts · {cost(b)}
      </p>
      {top && (
        <p className="mt-3 text-sm">
          <span className="font-semibold tabular-nums">{top.score}</span> <span className="text-muted-foreground">·</span> {top.title}
        </p>
      )}
      <span className="mt-auto inline-flex items-center gap-1 pt-3 text-sm text-muted-foreground group-hover:text-foreground">
        Open brief <ArrowRight className="size-4" />
      </span>
    </Link>
  );
}

async function Accounts() {
  await connection(); // read briefs at request time, so new runs appear without a rebuild
  const briefs = listBriefs();
  const featured = briefs.find((b) => b.slug === FEATURED) ?? briefs[0];
  const others = briefs.filter((b) => b !== featured);

  if (!featured) return <p className="rounded-xl border p-4 text-sm text-muted-foreground">No briefs yet.</p>;
  return (
    <>
      <FeaturedCard b={featured} />
      {others.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">More researched accounts</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {others.map((b) => (
              <AccountCard key={b.slug} b={b} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-10 sm:py-14">
      <p className="text-sm font-medium text-muted-foreground">Flowcode Opportunity Agent</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">What every account is doing right now</h1>
      <p className="mt-3 max-w-2xl text-muted-foreground">
        The agent researches a brand&apos;s current campaigns across TV, social, email, events, packaging and retail. It checks
        every fact against its source and matches each opportunity to a Flowcode product and a case study.
      </p>

      <div className="mt-8">
        <Suspense fallback={<div className="h-80 animate-pulse rounded-2xl border bg-muted/40" />}>
          <Accounts />
        </Suspense>
      </div>

      <section className="mt-10">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Research another brand</h2>
        {LIVE ? (
          <ResearchBox />
        ) : (
          <p className="rounded-xl border p-4 text-sm text-muted-foreground">
            Live research runs on the presenter&apos;s machine. The briefs above were produced by the same agent.
          </p>
        )}
      </section>
    </main>
  );
}
