/**
 * Process one lead from leads_to_enrich via Scrapegoat /worker/process-one.
 * BRPOP one, run pipeline, return. Use to "start" enrichment when the worker isn't running.
 */

import { NextResponse } from 'next/server';

function getScrapegoatBase(): string {
  const u = process.env.SCRAPEGOAT_API_URL;
  if (!u) return 'https://scrapegoat-production-8d0a.up.railway.app';
  return u.replace(/\/$/, '');
}

export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function POST() {
  const base = getScrapegoatBase();
  const url = `${base}/worker/process-one`;
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 115_000); // 115s

  try {
    const r = await fetch(url, { method: 'POST', signal: controller.signal });
    clearTimeout(t);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { processed: false, error: data.detail || data.message || 'Scrapegoat error' },
        { status: r.status >= 500 ? 503 : r.status }
      );
    }
    return NextResponse.json(data);
  } catch (e: unknown) {
    clearTimeout(t);
    const err = e instanceof Error ? e.message : 'Request failed';
    const isAbort = e instanceof Error && e.name === 'AbortError';
    return NextResponse.json(
      { processed: false, error: isAbort ? 'Enrichment timed out (pipeline may still complete)' : err },
      { status: 503 }
    );
  }
}
