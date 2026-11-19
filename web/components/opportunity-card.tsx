import { ArrowUpRight, CheckCircle2, CircleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { FeedbackButtons } from "@/components/feedback";
import { CHANNEL_LABELS, domainOf } from "@/lib/briefs";
import type { Opportunity } from "@/lib/types";

function Meter({ label, value, why }: { label: string; value: number; why: string }) {
  return (
    <div className="grid grid-cols-[5.5rem_auto_1fr] items-center gap-x-3 gap-y-0.5 text-xs">
      <span className="font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="flex gap-1" aria-label={`${label} ${value} of 5`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i} className={`h-2 w-4 rounded-sm ${i <= value ? "bg-foreground" : "bg-muted"}`} />
        ))}
      </div>
      <span className="text-muted-foreground">{why}</span>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[7rem_1fr] sm:gap-4">
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground sm:pt-0.5">{label}</dt>
      <dd className="text-sm leading-relaxed">{children}</dd>
    </div>
  );
}

export function OpportunityCard({ o, slug, runId }: { o: Opportunity; slug: string; runId: string }) {
  const metric = o.case_study.metrics[0];
  return (
    <Card id={`opp-${o.rank}`} className="scroll-mt-6">
      <CardContent className="space-y-4">
        {/* Header: score + title */}
        <div className="flex items-start gap-4">
          <div className="flex w-12 shrink-0 flex-col items-center rounded-lg border py-1.5">
            <span className="text-2xl font-semibold tabular-nums leading-none">{o.score}</span>
            <span className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">score</span>
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-semibold leading-snug">{o.title}</h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {o.channels.map((c) => (
                <Badge key={c} variant="secondary">{CHANNEL_LABELS[c] ?? c}</Badge>
              ))}
              {o.status === "new" && <Badge>New</Badge>}
              {o.uses_qr_or_links && <Badge variant="outline">Already uses QR/links</Badge>}
            </div>
          </div>
        </div>

        {/* The decision rows */}
        <dl className="space-y-3">
          <Row label="Happening">{o.what_is_happening}</Row>
          <Row label="Why Flowcode">
            {o.why_flowcode}{" "}
            <span className="inline-flex flex-wrap gap-1 align-middle">
              {o.products.map((p) => (
                <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
                  <Badge variant="outline" className="hover:bg-muted">{p.name}</Badge>
                </a>
              ))}
            </span>
          </Row>
          <Row label="Proof">
            <a href={o.case_study.url} target="_blank" rel="noreferrer" className="group inline-flex items-center gap-1">
              <strong>{o.case_study.brand}</strong>
              <span className="text-muted-foreground">·</span>
              <span>{metric}</span>
              <ArrowUpRight className="size-3 text-muted-foreground group-hover:text-foreground" />
            </a>
          </Row>
          <Row label="First step">
            <span className="font-medium">{o.first_step}</span>
          </Row>
        </dl>

        {/* Everything else, one click away */}
        <details className="rounded-lg border">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">
            Details · the play, scoring, {o.signals.length} verified source{o.signals.length === 1 ? "" : "s"}
          </summary>
          <div className="space-y-4 border-t px-3 py-3">
            <dl className="space-y-3">
              <Row label="The play">
                <span className="text-muted-foreground">{o.play.name}.</span> {o.suggested_play}
              </Row>
              <Row label="Contact">{o.contact_roles.join(" · ")}</Row>
              <Row label="Case study">
                {o.case_study.what_they_did} {o.case_study.metrics.join(" · ")}.
              </Row>
            </dl>

            <div className="space-y-1.5 border-t pt-3">
              <Meter label="Confidence" value={o.confidence} why={o.confidence_why} />
              <Meter label="Size" value={o.size} why={o.size_why} />
              <Meter label="Timing" value={o.timing} why={o.timing_why} />
              <p className="pt-1 text-xs text-muted-foreground">Score = confidence × size × timing, scaled to 100. Computed in code.</p>
              {o.adjustments.map((a) => (
                <p key={a} className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
                  <CircleAlert className="size-3" /> {a}
                </p>
              ))}
            </div>

            {o.signals.map((s) => (
              <div key={s.id} className="space-y-1.5 border-t pt-3 text-sm">
                <blockquote className="border-l-2 pl-3 italic">“{s.quote}”</blockquote>
                <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline underline-offset-4">
                    {domainOf(s.url)} <ArrowUpRight className="size-3" />
                  </a>
                  <span>{s.effective_date ?? "undated (live page)"}</span>
                  <span>{s.source_type.replace("_", " ")}</span>
                  {s.carried_over && <span>re-checked from earlier run</span>}
                </p>
                <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {Object.entries(s.checks).map(([k, v]) => (
                    <li key={k} className="inline-flex items-center gap-1">
                      <CheckCircle2 className="size-3 text-emerald-600" />
                      {k.replace("_", " ")}
                      {v !== "pass" && ` (${v})`}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>

        <FeedbackButtons slug={slug} run_id={runId} rank={o.rank} title={o.title} play_id={o.play_id} score={o.score} />
      </CardContent>
    </Card>
  );
}
