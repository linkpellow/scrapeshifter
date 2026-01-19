/**
 * Process one lead from leads_to_enrich via Scrapegoat /worker/process-one.
 * BRPOP one, run pipeline, return. Use to "start" enrichment when the worker isn't running.
 */

import { NextResponse } from 'next/server';
import { getScrapegoatBase } from '@/utils/scrapegoatClient';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST() {
  const base = getScrapegoatBase();
  const url = `${base}/worker/process-one`;
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 295_000); // 295s, under maxDuration 300

  try {
    const r = await fetch(url, { method: 'POST', signal: controller.signal });
    clearTimeout(t);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = (data.detail || data.message || data.error || 'Scrapegoat error') as string;
      return NextResponse.json({
        processed: false,
        error: err,
        steps: data.steps ?? [],
        logs: data.logs ?? [],
      });
    }
    return NextResponse.json(data);
  } catch (e: unknown) {
    clearTimeout(t);
    const err = e instanceof Error ? e.message : 'Request failed';
    const isAbort = e instanceof Error && e.name === 'AbortError';
    if (process.env.NODE_ENV !== 'test') {
      console.error('[process-one]', isAbort ? 'Timeout' : err);
    }
    return NextResponse.json({
      processed: false,
      error: isAbort ? 'Enrichment timed out (pipeline may still complete)' : err,
      steps: [],
      logs: [],
    });
  }
}
