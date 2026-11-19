// Mirrors the brief JSON written by agent/src/opportunity_agent/pipeline.py

export type AccountLabel = "prospect" | "expansion" | "possible_expansion";

export interface Signal {
  id: string;
  url_hash: string;
  claim: string;
  url: string;
  quote: string;
  published_date: string | null;
  channel: string;
  touchpoint: string;
  source_type: string;
  uses_qr_or_links: boolean;
  verified: boolean;
  checks: Record<string, string>;
  match_score: number;
  verified_via: string | null;
  page_date: string | null;
  effective_date: string | null;
  undated: boolean;
  drop_reason: string | null;
  first_seen: string | null;
  is_new: boolean;
  carried_over?: boolean;
}

export interface Product {
  id: string;
  name: string;
  url: string;
  page_quote: string;
  what_it_does: string;
}

export interface CaseStudy {
  id: string;
  brand: string;
  url: string;
  channel: string;
  what_they_did: string;
  metrics: string[];
}

export interface Play {
  id: string;
  name: string;
  play: string;
}

export interface Opportunity {
  rank: number;
  title: string;
  what_is_happening: string;
  why_flowcode: string;
  play_id: string;
  play: Play;
  products: Product[];
  case_study: CaseStudy;
  signal_ids: string[];
  signals: Signal[];
  confidence: number;
  confidence_why: string;
  size: number;
  size_why: string;
  timing: number;
  timing_why: string;
  score: number;
  suggested_play: string;
  contact_roles: string[];
  first_step: string;
  adjustments: string[];
  channels: string[];
  uses_qr_or_links: boolean;
  status: "new" | "continuing";
}

export interface Brief {
  slug: string;
  input: string;
  run_id: string;
  generated_at: string;
  account: { label: AccountLabel; evidence: string[] };
  resolution: {
    official_name: string;
    domain: string;
    newsroom_url: string | null;
    parent_company: string | null;
    category: string;
    sub_brands: string[];
    one_liner: string;
  };
  stats: {
    signals_found: number;
    signals_verified: number;
    signals_dropped: number;
    drop_reasons: Record<string, number>;
    new_signals: number;
    opportunities: number;
    per_channel: Record<string, { found: number; verified: number }>;
    cost_usd: number;
    elapsed_s: number;
    web_searches: number;
    web_fetches: number;
    llm_calls: number;
    tokens_in: number;
    tokens_out: number;
    cache_read_tokens: number;
    reused_stages: string[];
    run_cost_usd?: number;
    total_cost_usd?: number;
    total_web_searches?: number;
    carried_over?: number;
    carried_over_verified?: number;
  };
  models: Record<string, string>;
  opportunities: Opportunity[];
  expired_opportunities: { title: string; play_id: string; last_seen: string }[];
  rejected_opportunities: { title: string; reason: string }[];
  signals: Signal[];
}
