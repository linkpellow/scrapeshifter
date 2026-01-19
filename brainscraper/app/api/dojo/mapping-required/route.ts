/**
 * GET /api/dojo/mapping-required
 * Domains that need a blueprint (BlueprintLoader adds when none found).
 * Proxies to Scrapegoat /api/dojo/domains-need-mapping.
 */

import { NextResponse } from 'next/server';

const SCRAPEGOAT = process.env.SCRAPEGOAT_URL || process.env.SCRAPEGOAT_API_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${SCRAPEGOAT}/api/dojo/domains-need-mapping`, { cache: 'no-store' });
    const data = await res.json().catch(() => ({ domains: [] }));
    return NextResponse.json({ domains: Array.isArray(data.domains) ? data.domains : [] });
  } catch {
    return NextResponse.json({ domains: [] });
  }
}
