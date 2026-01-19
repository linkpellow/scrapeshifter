/**
 * Enrichment queue status – Redis LLEN for leads_to_enrich and failed_leads.
 * No Scrapegoat dependency; uses REDIS_URL / APP_REDIS_URL only.
 * Used by v2-pilot to show enrichment pipeline visibility.
 */

import { NextResponse } from 'next/server';
import Redis from 'ioredis';

const QUEUE = 'leads_to_enrich';
const DLQ = 'failed_leads';

function getRedis(): Redis | null {
  const url = process.env.REDIS_URL || process.env.APP_REDIS_URL;
  if (!url) return null;
  try {
    return new Redis(url, { maxRetriesPerRequest: 2 });
  } catch {
    return null;
  }
}

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET() {
  const redis = getRedis();
  if (!redis) {
    return NextResponse.json({
      leads_to_enrich: 0,
      failed_leads: 0,
      redis_connected: false,
    });
  }

  try {
    const [leads_to_enrich, failed_leads] = await Promise.all([
      redis.llen(QUEUE),
      redis.llen(DLQ),
    ]);
    redis.quit().catch(() => {});
    return NextResponse.json({
      leads_to_enrich,
      failed_leads,
      redis_connected: true,
    });
  } catch (e) {
    redis.quit().catch(() => {});
    return NextResponse.json({
      leads_to_enrich: 0,
      failed_leads: 0,
      redis_connected: false,
      error: e instanceof Error ? e.message : 'Redis error',
    });
  }
}
