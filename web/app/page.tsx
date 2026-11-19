import Link from "next/link";
import { Suspense } from "react";
import { connection } from "next/server";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ResearchBox } from "@/components/research-box";
import { ACCOUNT_LABELS, listBriefs } from "@/lib/briefs";

// Live research needs the Python agent running next to the web app, which is true locally.
// It is off automatically on Vercel (which sets VERCEL=1) or when LIVE_RUNS=off.
const LIVE = process.env.VERCEL !== "1" && process.env.LIVE_RUNS !== "off";

async function AccountList() {
  await connection(); // read briefs at request time, so new runs appear without a rebuild
  const briefs = listBriefs();
  return (
    <ul className="divide-y rounded-xl border">
      {briefs.length === 0 && <li className="p-4 text-sm text-muted-foreground">No briefs yet.</li>}
      {briefs.map((b) => {
        const top = b.opportunities[0];
        return (
          <li key={b.slug}>
            <Link href={`/${b.slug}`} className="flex items-center gap-4 p-4 hover:bg-muted/50">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{b.resolution.official_name}</span>
                  <Badge variant={b.account.label === "prospect" ? "default" : "secondary"}>{ACCOUNT_LABELS[b.account.label]}</Badge>
                </div>
                <p className="mt-1 truncate text-sm text-muted-foreground">
                  {b.stats.opportunities} opportunities · {b.stats.signals_verified} verified signals
                  {top ? ` · top: ${top.title}` : ""}
                </p>
              </div>
              <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
            </Link>
          </li>
        );
      })}
    </ul>
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
        {LIVE ? (
          <ResearchBox />
        ) : (
          <p className="rounded-xl border p-4 text-sm text-muted-foreground">
            Live research runs on the presenter&apos;s machine. The briefs below were produced by the same agent.
          </p>
        )}
      </div>

      <h2 className="mt-10 mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Researched accounts</h2>
      <Suspense fallback={<div className="h-24 animate-pulse rounded-xl border bg-muted/40" />}>
        <AccountList />
      </Suspense>
    </main>
  );
}
