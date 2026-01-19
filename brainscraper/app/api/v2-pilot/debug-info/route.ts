/**
 * Debug info for v2-pilot Download logs.
 * Returns non-secret config and connectivity: Redis, Scrapegoat, Chimera Brain env.
 */

import { NextResponse } from 'next/server';
import Redis from 'ioredis';

export const dynamic = 'force-dynamic';

function getScrapegoatBase(): string {
  const u = process.env.SCRAPEGOAT_API_URL;
  if (!u) return 'https://scrapegoat-production-8d0a.up.railway.app';
  return u.replace(/\/$/, '');
}

export async function GET() {
  let redis_connected = false;
  try {
    const url = process.env.REDIS_URL || process.env.APP_REDIS_URL;
    if (url) {
      const r = new Redis(url, { maxRetriesPerRequest: 2 });
      await r.ping();
      redis_connected = true;
      r.quit().catch(() => {});
    }
  } catch {
    // redis_connected stays false
  }

  const scrapegoat_url = getScrapegoatBase();
  let scrapegoat_ok = false;
  try {
    const res = await fetch(`${scrapegoat_url}/health`, { signal: AbortSignal.timeout(5000) });
    scrapegoat_ok = res.ok;
  } catch {
    // scrapegoat_ok stays false
  }

  return NextResponse.json({
    redis_connected,
    scrapegoat_url,
    scrapegoat_ok,
    chimera_brain_http_url_set: !!(process.env.CHIMERA_BRAIN_HTTP_URL),
    chimera_brain_address_set: !!(process.env.CHIMERA_BRAIN_ADDRESS),
  });
}
