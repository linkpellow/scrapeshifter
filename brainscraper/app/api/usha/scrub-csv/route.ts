import { NextRequest, NextResponse } from 'next/server';
import { getUshaToken, clearTokenCache } from '@/utils/getUshaToken';
import Papa from 'papaparse';

const USHA_API_URL = 'https://api-business-agent.ushadvisors.com/Leads/api/leads/scrubphonenumber';
const DEFAULT_AGENT_NUMBER = '00044447';
const BATCH_SIZE = 10;
const DELAY_BETWEEN_BATCHES = 500;

interface LeadRow {
  [key: string]: string | number;
}

interface DNCResult {
  isDoNotCall: boolean;
  canContact: boolean;
  reason?: string;
  error?: string;
}

/**
 * Scrub a single phone number using the USHA API with automatic token refresh
 */
async function scrubPhoneNumber(
  phone: string,
  token: string,
  agentNumber: string = DEFAULT_AGENT_NUMBER,
  getFreshToken?: () => Promise<string | null>
): Promise<DNCResult> {
  // Clean phone number - remove all non-digits
  const cleanedPhone = phone.replace(/\D/g, '');
  
  if (cleanedPhone.length < 10) {
    return {
      isDoNotCall: false,
      canContact: true,
      reason: 'Invalid phone number format',
      error: 'Phone number too short'
    };
  }

  // Handle 11-digit numbers (with country code 1) - strip leading 1
  const normalizedPhone = cleanedPhone.length === 11 && cleanedPhone.startsWith('1') 
    ? cleanedPhone.substring(1) 
    : cleanedPhone;

  try {
    const url = `${USHA_API_URL}?currentContextAgentNumber=${encodeURIComponent(agentNumber)}&phone=${encodeURIComponent(normalizedPhone)}`;
    
    let response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'accept': 'application/json, text/plain, */*',
        'Referer': 'https://agent.ushadvisors.com/',
        'Content-Type': 'application/json',
      },
    });

    // Retry once on auth failure with fresh token
    if ((response.status === 401 || response.status === 403) && getFreshToken) {
      console.log(`  🔄 [DNC CSV SCRUB] ${normalizedPhone}: Token expired (${response.status}), refreshing token...`);
      clearTokenCache();
      try {
        const freshToken = await getFreshToken();
        if (freshToken) {
          response = await fetch(url, {
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${freshToken}`,
              'accept': 'application/json, text/plain, */*',
              'Referer': 'https://agent.ushadvisors.com/',
              'Content-Type': 'application/json',
            },
          });
        }
      } catch (e) {
        console.error(`  ⚠️ [DNC CSV SCRUB] ${normalizedPhone}: Token refresh failed:`, e);
      }
    }

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`  ❌ API error ${response.status} for ${normalizedPhone}: ${errorText.substring(0, 100)}`);
      return {
        isDoNotCall: false,
        canContact: true,
        reason: `API Error: ${response.statusText}`,
        error: errorText.substring(0, 200)
      };
    }

    const result = await response.json();
    
    // Parse response - check nested data structure
    const responseData = result.data || result;
    const contactStatus = responseData.contactStatus || {};
    
    const isDNC = responseData.isDoNotCall === true || 
                  contactStatus.canContact === false ||
                  result.isDoNotCall === true || 
                  result.canContact === false;
    const canContact = contactStatus.canContact !== false && !isDNC;
    const reason = contactStatus.reason || responseData.reason || result.reason || 
                   (isDNC ? 'Do Not Call' : undefined);

    return {
      isDoNotCall: isDNC,
      canContact: canContact,
      reason: reason
    };
  } catch (error) {
    console.error(`  ❌ Error checking ${normalizedPhone}:`, error instanceof Error ? error.message : 'Unknown error');
    return {
      isDoNotCall: false,
      canContact: true,
      reason: 'Error checking DNC',
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
}

/**
 * Find phone number in a row by checking multiple column names
 */
function findPhoneNumber(row: LeadRow): string | null {
  const phoneColumns = [
    'phone',
    'Phone',
    'primaryPhone',
    'PrimaryPhone',
    'phoneNumber',
    'PhoneNumber',
    'mobile',
    'Mobile',
    '_matched_phone_10'
  ];

  for (const col of phoneColumns) {
    if (row[col] && String(row[col]).trim()) {
      return String(row[col]).trim();
    }
  }

  return null;
}

export async function POST(request: NextRequest) {
  const startTime = Date.now();
  console.log('\n🔍 [DNC CSV SCRUB] ============================================');
  console.log('🔍 [DNC CSV SCRUB] CSV File Upload Received');
  console.log('🔍 [DNC CSV SCRUB] ============================================\n');

  try {
    const formData = await request.formData();
    const file = formData.get('file') as File;

    if (!file) {
      return NextResponse.json({ error: 'No file uploaded' }, { status: 400 });
    }

    // Limit file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      return NextResponse.json(
        { error: 'File too large. Maximum size is 10MB. Please split your file.' },
        { status: 400 }
      );
    }

    console.log(`📁 [DNC CSV SCRUB] File: ${file.name} (${(file.size / 1024).toFixed(2)} KB)`);

    // Parse CSV first (before token check)
    console.log(`📖 [DNC CSV SCRUB] Parsing CSV file...`);
    const csvText = await file.text();
    const parseResult = Papa.parse(csvText, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (header: string) => header.trim(),
      transform: (value: string) => value.trim(),
    });

    if (parseResult.errors.length > 0) {
      console.warn('⚠️ [DNC CSV SCRUB] CSV parsing warnings:', parseResult.errors);
    }

    const rows: LeadRow[] = parseResult.data as LeadRow[];
    console.log(`✅ [DNC CSV SCRUB] Found ${rows.length} leads in CSV\n`);

    // Get USHA token (optional - DNC scrubbing is optional)
    console.log(`🔑 [DNC CSV SCRUB] Getting USHA JWT token (optional)...`);
    let token: string | null = null;
    try {
      token = await getUshaToken();
      if (token) {
        console.log(`✅ [DNC CSV SCRUB] Token obtained successfully\n`);
      } else {
        console.log('⚠️ [DNC CSV SCRUB] No USHA JWT token available - DNC scrubbing will be skipped');
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      console.warn(`⚠️ [DNC CSV SCRUB] Failed to get USHA token (DNC optional): ${errorMsg}`);
      // Don't return error - continue without DNC scrubbing
      token = null;
    }

    // If no token, return all leads as OK (DNC is optional)
    if (!token) {
      console.log('⚠️ [DNC CSV SCRUB] No token - returning all leads as OK (DNC scrubbing skipped)');
      
      const skippedLeads = rows.map(row => {
        const phone = findPhoneNumber(row);
        return {
          ...row,
          dncStatus: phone ? 'SKIPPED' : 'OK',
          canContact: 'Yes',
          dncReason: phone ? 'USHA JWT token not configured - DNC scrubbing skipped' : undefined
        };
      });

      const allColumns = rows.length > 0 ? Object.keys(rows[0]) : [];
      const skippedCsv = Papa.unparse(skippedLeads, {
        header: true,
        columns: [...allColumns, 'dncStatus', 'canContact', 'dncReason'],
      });

      return new NextResponse(skippedCsv, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="leads_skipped_dnc_${new Date().toISOString().split('T')[0]}.csv"`,
        },
      });
    }

    // At this point, TypeScript knows token is not null, but we need to help it in closures
    // Create a non-null variable for use in closures
    let currentToken: string = token;

    // Create a function to get fresh token (for retry on 401/403)
    // This will update the token variable for subsequent batches
    const getFreshToken = async (): Promise<string | null> => {
      console.log(`🔄 [DNC CSV SCRUB] Refreshing token for subsequent requests...`);
      clearTokenCache();
      const freshToken = await getUshaToken(null, true); // Force refresh
      if (freshToken) {
        currentToken = freshToken; // Update token for subsequent batches
        console.log(`✅ [DNC CSV SCRUB] Token refreshed, using for remaining requests`);
      }
      return freshToken;
    };

    // Separate rows with and without phones
    const cleanLeads: LeadRow[] = [];
    const rowsWithPhones: Array<{ row: LeadRow; phone: string }> = [];

    for (const row of rows) {
      const phone = findPhoneNumber(row);
      if (!phone) {
        // No phone number - include in clean leads (can't check DNC)
        cleanLeads.push(row);
      } else {
        rowsWithPhones.push({ row, phone });
      }
    }

    console.log(`📊 [DNC CSV SCRUB] Processing ${rowsWithPhones.length} leads with phone numbers...`);
    console.log(`📊 [DNC CSV SCRUB] ${rows.length - rowsWithPhones.length} leads without phones (included in clean leads)\n`);

    // Process in batches of 10
    const totalBatches = Math.ceil(rowsWithPhones.length / BATCH_SIZE);
    let processed = 0;

    for (let i = 0; i < rowsWithPhones.length; i += BATCH_SIZE) {
      const batch = rowsWithPhones.slice(i, i + BATCH_SIZE);
      const batchNum = Math.floor(i / BATCH_SIZE) + 1;
      
      console.log(`📦 [DNC CSV SCRUB] Batch ${batchNum}/${totalBatches}: Processing ${batch.length} phone numbers...`);
      
      // Process batch in parallel
      const batchPromises = batch.map(async ({ row, phone }) => {
        // Use current token, but allow refresh on 401/403
        const dncResult = await scrubPhoneNumber(phone, currentToken, DEFAULT_AGENT_NUMBER, getFreshToken);
        
        // Add DNC status to row
        (row as any).dncStatus = dncResult.isDoNotCall ? 'DNC' : 'OK';
        (row as any).canContact = dncResult.canContact ? 'Yes' : 'No';
        if (dncResult.reason) {
          (row as any).dncReason = dncResult.reason;
        }

        return { row, dncResult };
      });

      const batchResults = await Promise.all(batchPromises);
      
      // Process results
      for (const { row, dncResult } of batchResults) {
        processed++;
        
        // Filter: only include non-DNC leads
        if (!dncResult.isDoNotCall && dncResult.canContact) {
          cleanLeads.push(row);
        }
      }

      // Rate limiting delay between batches
      if (i + BATCH_SIZE < rowsWithPhones.length) {
        await new Promise(resolve => setTimeout(resolve, DELAY_BETWEEN_BATCHES));
      }
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    console.log(`\n✅ [DNC CSV SCRUB] Scrubbing complete in ${elapsed}s!`);
    console.log(`📊 [DNC CSV SCRUB] Statistics:`);
    console.log(`   Total leads: ${rows.length}`);
    console.log(`   Processed: ${processed}`);
    console.log(`   ✅ Clean leads (non-DNC): ${cleanLeads.length}`);
    console.log(`   ❌ DNC leads (filtered out): ${rowsWithPhones.length - (cleanLeads.length - (rows.length - rowsWithPhones.length))}\n`);

    // Generate CSV
    const allColumns = rows.length > 0 ? Object.keys(rows[0]) : [];
    const cleanCsv = Papa.unparse(cleanLeads, {
      header: true,
      columns: [...allColumns, 'dncStatus', 'canContact', 'dncReason'],
    });

    return new NextResponse(cleanCsv, {
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="clean_leads_${new Date().toISOString().split('T')[0]}.csv"`,
      },
    });
  } catch (error) {
    console.error('❌ [DNC CSV SCRUB] Error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error occurred' },
      { status: 500 }
    );
  }
}

