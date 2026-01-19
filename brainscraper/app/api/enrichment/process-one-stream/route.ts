/**
 * Proxy to Scrapegoat POST /worker/process-one-stream.
 * Streams NDJSON progress events (step, pct, station, status) then {done, success, steps, logs}.
 * Use this so the Enrich UI can show a live progress feed instead of appearing frozen.
 */

import { getScrapegoatBase } from '@/utils/scrapegoatClient';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST() {
  const base = getScrapegoatBase();
  const url = `${base}/worker/process-one-stream`;

  const res = await fetch(url, { method: 'POST' });
  if (!res.ok || !res.body) {
    const text = await res.text();
    return new Response(
      JSON.stringify({
        done: true,
        processed: false,
        error: `Scrapegoat ${res.status}: ${text || res.statusText}`,
      }) + '\n',
      { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }
    );
  }

  return new Response(res.body, {
    headers: {
      'Content-Type': 'application/x-ndjson',
      'Cache-Control': 'no-cache',
      'X-Accel-Buffering': 'no',
    },
  });
}
