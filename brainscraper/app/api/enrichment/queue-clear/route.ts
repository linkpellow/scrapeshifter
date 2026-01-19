/**
 * Clear enrichment queues (leads_to_enrich and failed_leads).
 * Uses REDIS_URL / APP_REDIS_URL. Used by v2-pilot "Clear" to reset pipeline.
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

export async function POST() {
  const redis = getRedis();
  if (!redis) {
    return NextResponse.json({ ok: false, error: 'Redis not configured (REDIS_URL)' }, { status: 503 });
  }

  try {
    const [qn, dq] = await Promise.all([redis.llen(QUEUE), redis.llen(DLQ)]);
    await redis.del(QUEUE);
    await redis.del(DLQ);
    redis.quit().catch(() => {});
    return NextResponse.json({
      ok: true,
      cleared: qn,
      cleared_failed: dq,
    });
  } catch (e) {
    redis.quit().catch(() => {});
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : 'Redis error' },
      { status: 500 }
    );
  }
}
