import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { FeedbackProvider, FeedbackSummary } from "@/components/feedback";
import { OpportunityCard } from "@/components/opportunity-card";
import { ACCOUNT_LABELS, CHANNEL_LABELS, DROP_LABELS, domainOf, getBrief, listBriefs } from "@/lib/briefs";

// Below this, an opportunity moves to the one-line watchlist (score is 0-100).
const STRONG_SCORE = 30;

export function generateStaticParams() {
  return listBriefs().map((b) => ({ slug: b.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const b = getBrief(slug);
  return { title: b ? `${b.resolution.official_name} · Opportunity brief` : "Not found" };
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-xl font-semibold tabular-nums">{value}</span>
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  );
}

export default async function BriefPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const b = getBrief(slug);
  if (!b) notFound();
  const st = b.stats;
  const dropped = b.signals.filter((s) => !s.verified);
  const strong = b.opportunities.filter((o) => o.score >= STRONG_SCORE);
  const watch = b.opportunities.filter((o) => o.score < STRONG_SCORE);
  const generated = new Date(b.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });

  return (
    <FeedbackProvider slug={b.slug} runId={b.run_id}>
      <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:py-12">
        <Link href="/" className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> All accounts
        </Link>

        {/* Account header */}
        <header className="mb-6">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant={b.account.label === "prospect" ? "default" : "secondary"}>{ACCOUNT_LABELS[b.account.label]}</Badge>
            <span className="text-sm text-muted-foreground">{b.resolution.category}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{b.resolution.official_name}</h1>
          <p className="mt-2 text-muted-foreground">{b.resolution.one_liner}</p>
          <p className="mt-2 flex flex-wrap gap-x-3 text-sm text-muted-foreground">
            <a className="inline-flex items-center gap-1 underline underline-offset-4" href={`https://${b.resolution.domain}`} target="_blank" rel="noreferrer">
              {b.resolution.domain} <ArrowUpRight className="size-3" />
            </a>
            {b.resolution.newsroom_url && (
              <a className="inline-flex items-center gap-1 underline underline-offset-4" href={b.resolution.newsroom_url} target="_blank" rel="noreferrer">
                newsroom <ArrowUpRight className="size-3" />
              </a>
            )}
            <span>Researched {generated}</span>
          </p>
        </header>

        {/* Header strip: found / verified / dropped / cost / time */}
        <section className="mb-8 rounded-xl border p-4">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <Stat value={st.signals_found} label="found" />
            <Stat value={st.signals_verified} label="verified" />
            <Stat value={st.signals_dropped} label="dropped" />
            <Stat value={`$${(st.total_cost_usd ?? st.cost_usd).toFixed(2)}`} label="cost" />
            <Stat value={st.total_web_searches ?? st.web_searches} label="searches" />
          </div>
          {st.reused_stages.length > 0 && st.run_cost_usd !== undefined && (
            <p className="mt-1 text-xs text-muted-foreground">
              Last refresh cost ${st.run_cost_usd.toFixed(2)} in {Math.round(st.elapsed_s)}s, reusing saved{" "}
              {st.reused_stages.join(", ")}.
              {st.carried_over
                ? ` ${st.carried_over_verified ?? 0} of ${st.carried_over} signals from earlier runs re-checked and kept.`
                : ""}
            </p>
          )}
          <p className="mt-3 text-sm text-muted-foreground">
            Every fact below was checked in code against its source page. Anything that failed was thrown out
            {Object.keys(st.drop_reasons).length > 0 && (
              <>
                {" "}(
                {Object.entries(st.drop_reasons)
                  .map(([k, v]) => `${v} ${DROP_LABELS[k] ?? k}`)
                  .join(", ")}
                )
              </>
            )}
            .
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {Object.entries(st.per_channel).map(([ch, c]) => (
              <Badge key={ch} variant={c.verified > 0 ? "secondary" : "outline"} className={c.verified ? "" : "text-muted-foreground"}>
                {CHANNEL_LABELS[ch] ?? ch} {c.verified}/{c.found}
              </Badge>
            ))}
          </div>
          <div className="mt-3 border-t pt-3">
            <FeedbackSummary total={b.opportunities.length} />
          </div>
        </section>

        {/* Strong bets get full cards; weak ones a one-line watchlist */}
        <h2 className="mb-4 text-xl font-semibold">
          {strong.length} opportunit{strong.length === 1 ? "y" : "ies"} worth chasing now
        </h2>
        {strong.length === 0 && <p className="text-muted-foreground">No strong opportunities this run.</p>}
        <div className="space-y-5">
          {strong.map((o) => (
            <OpportunityCard key={o.rank} o={o} slug={b.slug} runId={b.run_id} />
          ))}
        </div>

        {watch.length > 0 && (
          <section className="mt-10">
            <h2 className="mb-1 text-lg font-semibold">Also worth watching</h2>
            <p className="mb-3 text-sm text-muted-foreground">Scored below {STRONG_SCORE}: weaker evidence, smaller reach or a later window.</p>
            <ul className="divide-y rounded-xl border">
              {watch.map((o) => (
                <li key={o.rank}>
                  <details>
                    <summary className="flex cursor-pointer select-none items-baseline gap-3 px-4 py-3 text-sm">
                      <span className="w-7 shrink-0 font-semibold tabular-nums">{o.score}</span>
                      <span className="font-medium">{o.title}</span>
                      <span className="hidden truncate text-muted-foreground sm:inline">· {o.timing_why}</span>
                    </summary>
                    <div className="px-4 pb-4">
                      <OpportunityCard o={o} slug={b.slug} runId={b.run_id} />
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          </section>
        )}

        {b.expired_opportunities.length > 0 && (
          <section className="mt-10">
            <h2 className="mb-2 text-lg font-semibold">No longer active since last run</h2>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {b.expired_opportunities.map((e) => (
                <li key={e.title}>{e.title}</li>
              ))}
            </ul>
          </section>
        )}

        {/* What we threw out */}
        {dropped.length > 0 && (
          <details className="mt-10 rounded-xl border">
            <summary className="cursor-pointer select-none px-4 py-3 font-medium">
              What we threw out · {dropped.length} claim{dropped.length === 1 ? "" : "s"} that failed verification
            </summary>
            <ul className="divide-y border-t">
              {dropped.map((s) => (
                <li key={s.id + s.claim} className="px-4 py-3 text-sm">
                  <p>{s.claim}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    <span className="font-medium text-amber-700 dark:text-amber-400">
                      {DROP_LABELS[(s.drop_reason ?? "").split(":")[0]] ?? s.drop_reason}
                    </span>{" "}
                    · {domainOf(s.url)} · {Object.values(s.checks).filter((v) => v !== "pass").join("; ")}
                  </p>
                </li>
              ))}
            </ul>
          </details>
        )}

        <footer className="mt-12 border-t pt-4 text-xs text-muted-foreground">
          Run {b.run_id} · models: {Object.entries(b.models).map(([k, v]) => `${k} ${v}`).join(", ")} ·{" "}
          {st.llm_calls} LLM calls, {st.tokens_in.toLocaleString()} input / {st.tokens_out.toLocaleString()} output tokens
          {st.cache_read_tokens > 0 && `, ${st.cache_read_tokens.toLocaleString()} from cache`}
          {st.reused_stages.length > 0 && ` · reused stages: ${st.reused_stages.join(", ")}`}. Account status checked against
          Flowcode&apos;s public customer list; your CRM is the source of truth.
        </footer>
      </main>
    </FeedbackProvider>
  );
}
