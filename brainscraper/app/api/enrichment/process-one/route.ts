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
  console.log('[process-one] POST /api/enrichment/process-one →', url);
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 115_000); // 115s

  try {
    const r = await fetch(url, { method: 'POST', signal: controller.signal });
    clearTimeout(t);
    console.log('[process-one] Scrapegoat response: status=%s ok=%s', r.status, r.ok);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = (data.detail || data.message || data.error || 'Scrapegoat error') as string;
      console.warn('[process-one] Scrapegoat non-OK. status=%s body=%s', r.status, JSON.stringify(data).slice(0, 400));
      return NextResponse.json({
        processed: false,
        error: err,
        steps: data.steps ?? [],
        logs: data.logs ?? [],
      });
    }
    console.log('[process-one] OK. processed=%s success=%s', data.processed, data.success);
    return NextResponse.json(data);
  } catch (e: unknown) {
    clearTimeout(t);
    const err = e instanceof Error ? e.message : 'Request failed';
    const isAbort = e instanceof Error && e.name === 'AbortError';
    console.error('[process-one] Request failed:', isAbort ? 'AbortError (timeout)' : err);
    return NextResponse.json({
      processed: false,
      error: isAbort ? 'Enrichment timed out (pipeline may still complete)' : err,
      steps: [],
      logs: [],
    });
  }
}
