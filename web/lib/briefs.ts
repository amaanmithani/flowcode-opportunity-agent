import { readdirSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";
import type { Brief } from "./types";

// Briefs are written here by the Python pipeline. They are read at build time, so no backend is needed.
const DIR = path.join(process.cwd(), "data", "briefs");

export function listBriefs(): Brief[] {
  if (!existsSync(DIR)) return [];
  return readdirSync(DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as Brief)
    .sort((a, b) => b.generated_at.localeCompare(a.generated_at));
}

export function getBrief(slug: string): Brief | null {
  const file = path.join(DIR, `${slug}.json`);
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, "utf8")) as Brief;
}

export const CHANNEL_LABELS: Record<string, string> = {
  tv_broadcast: "TV & broadcast",
  social_digital: "Social",
  email_loyalty: "Email & loyalty",
  events: "Events",
  packaging: "Packaging",
  retail: "Retail",
  company_wide: "Company-wide",
};

export const ACCOUNT_LABELS: Record<string, string> = {
  prospect: "Prospect",
  expansion: "Customer · expansion",
  possible_expansion: "Possible expansion",
};

export const DROP_LABELS: Record<string, string> = {
  quote_not_found: "quote not on page",
  stale: "older than 90 days",
  fetch_failed: "site blocked our fetch",
  blocked_domain: "social platform",
  duplicate: "duplicate",
  quote_too_short: "quote too short",
};

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
