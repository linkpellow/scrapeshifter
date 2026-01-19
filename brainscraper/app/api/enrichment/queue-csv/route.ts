/**
 * Queue CSV for enrichment (leads_to_enrich -> Scrapegoat worker -> Postgres).
 * Parses CSV, maps columns to queue format, pushes via pushLeadsToEnrichQueueFromEnrichUI.
 * Results appear in /enriched when DatabaseSaveStation completes.
 */

import { NextRequest, NextResponse } from 'next/server';
import Papa from 'papaparse';
import { pushLeadsToEnrichQueueFromEnrichUI } from '@/utils/redisBridge';

function mapRow(row: Record<string, string>): Record<string, unknown> | null {
  const linkedinUrl = (
    row['LinkedIn URL'] ||
    row['linkedinUrl'] ||
    row['linkedin_url'] ||
    ''
  ).trim();
  if (!linkedinUrl) return null;

  const name = (row['Name'] || row['name'] || '').trim();
  const firstName = (row['First Name'] || row['firstName'] || row['first_name'] || '').trim();
  const lastName = (row['Last Name'] || row['lastName'] || row['last_name'] || '').trim();
  const fullName = name || [firstName, lastName].filter(Boolean).join(' ').trim() || 'Unknown';

  return {
    linkedinUrl,
    name: fullName,
    fullName: fullName,
    firstName: firstName || undefined,
    lastName: lastName || undefined,
    location: (row['Location'] || row['location'] || '').trim(),
    title: (row['Title'] || row['title'] || '').trim(),
    company: (row['Company'] || row['company'] || '').trim(),
    city: (row['City'] || row['city'] || '').trim(),
    state: (row['State'] || row['state'] || '').trim(),
    email: (row['Email'] || row['email'] || '').trim() || undefined,
    phone: (row['Phone'] || row['phone'] || '').trim() || undefined,
  };
}

export async function POST(request: NextRequest) {
  try {
    let csvText: string;
    const contentType = request.headers.get('content-type') || '';

    if (contentType.includes('multipart/form-data')) {
      const form = await request.formData();
      const file = form.get('file') || form.get('csv');
      if (!file || !(file instanceof Blob)) {
        return NextResponse.json(
          { success: false, error: 'Missing file', pushed: 0, skipped: 0, total: 0 },
          { status: 400 }
        );
      }
      csvText = await file.text();
    } else {
      const body = await request.json().catch(() => ({}));
      csvText = typeof body.csv === 'string' ? body.csv : '';
      if (!csvText) {
        return NextResponse.json(
          { success: false, error: 'Missing csv in body', pushed: 0, skipped: 0, total: 0 },
          { status: 400 }
        );
      }
    }

    const parsed = Papa.parse<Record<string, string>>(csvText, { header: true, skipEmptyLines: true });
    const rows = (parsed.data || []).filter((r) => r && Object.keys(r).length > 0);

    const mapped: Record<string, unknown>[] = [];
    for (const r of rows) {
      const m = mapRow(r);
      if (m) mapped.push(m);
    }

    if (mapped.length === 0) {
      return NextResponse.json({
        success: true,
        pushed: 0,
        skipped: rows.length,
        total: rows.length,
        message: 'No rows with LinkedIn URL found. Ensure the CSV has a "LinkedIn URL" column.',
      });
    }

    const { pushed, skipped } = await pushLeadsToEnrichQueueFromEnrichUI(mapped);

    return NextResponse.json({
      success: true,
      pushed,
      skipped,
      total: rows.length,
      message: `Queued ${pushed} leads for enrichment. Results will appear in Enriched Leads when the Scrapegoat worker finishes. Run: python start_redis_worker.py (in scrapegoat) with Redis + Postgres.`,
    });
  } catch (e) {
    return NextResponse.json(
      {
        success: false,
        error: e instanceof Error ? e.message : 'Queue failed',
        pushed: 0,
        skipped: 0,
        total: 0,
      },
      { status: 500 }
    );
  }
}
