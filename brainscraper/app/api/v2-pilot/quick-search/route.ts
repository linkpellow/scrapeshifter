import { NextRequest, NextResponse } from 'next/server';

/**
 * V2 PILOT - QUICK SEARCH API
 * 
 * Simplified interface to LinkedIn Sales Navigator RapidAPI
 * Generates real leads and pushes them directly to Chimera swarm
 * 
 * This endpoint bridges the existing LinkedIn API with V2 Pilot,
 * allowing quick testing with real data instead of manual input
 */

interface QuickSearchParams {
  location?: string;
  jobTitle?: string;
  companyName?: string;
  limit?: number;
}

export async function POST(request: NextRequest) {
  try {
    const params = await request.json() as QuickSearchParams;
    
    // Validate at least one search parameter
    if (!params.location && !params.jobTitle && !params.companyName) {
      return NextResponse.json(
        {
          error: 'Invalid parameters',
          message: 'At least one search parameter required (location, jobTitle, or companyName)'
        },
        { status: 400 }
      );
    }

    // Build LinkedIn Sales Navigator API request
    const linkedInParams: Record<string, unknown> = {
      endpoint: 'premium_search_person',
      page: 1,
      limit: params.limit || 25, // Default to 25 leads
    };

    // Map V2 Pilot parameters to LinkedIn API parameters
    if (params.location) {
      linkedInParams.location = params.location;
    }

    if (params.jobTitle) {
      linkedInParams.jobTitle = params.jobTitle;
    }

    if (params.companyName) {
      linkedInParams.companyName = params.companyName;
    }

    console.log('[V2_PILOT_QUICK_SEARCH] Calling LinkedIn API with params:', linkedInParams);

    // Import the LinkedIn handler directly instead of using fetch
    // This avoids SSL issues with internal API calls
    const { POST: linkedInHandler } = await import('@/app/api/linkedin-sales-navigator/route');
    
    // Create a mock request with the LinkedIn params
    const mockRequest = {
      json: async () => linkedInParams,
      nextUrl: request.nextUrl,
    } as NextRequest;

    const linkedInResponse = await linkedInHandler(mockRequest);
    const linkedInResult = await linkedInResponse.json();

    console.log('[V2_PILOT_QUICK_SEARCH] LinkedIn response status:', linkedInResponse.status);
    console.log('[V2_PILOT_QUICK_SEARCH] Response keys:', Object.keys(linkedInResult));

    // Check for error response
    if (linkedInResponse.status !== 200) {
      console.error('[V2_PILOT_QUICK_SEARCH] LinkedIn API error:', linkedInResult);
      return NextResponse.json(
        {
          error: 'LinkedIn API error',
          message: linkedInResult.message || linkedInResult.error || 'Failed to fetch leads',
          details: linkedInResult,
        },
        { status: linkedInResponse.status }
      );
    }

    // Extract leads from response (matching main page logic - lines 915-936)
    let leads: any[] = [];
    
    if (linkedInResult.data) {
      // Check nested response structures (LinkedIn API can return data in multiple formats)
      if (linkedInResult.data.response?.data && Array.isArray(linkedInResult.data.response.data)) {
        console.log('[V2_PILOT_QUICK_SEARCH] Found results in data.response.data');
        leads = linkedInResult.data.response.data;
      } else if (linkedInResult.data.data && Array.isArray(linkedInResult.data.data)) {
        console.log('[V2_PILOT_QUICK_SEARCH] Found results in data.data');
        leads = linkedInResult.data.data;
      } else if (Array.isArray(linkedInResult.data)) {
        console.log('[V2_PILOT_QUICK_SEARCH] Found results in data (direct array)');
        leads = linkedInResult.data;
      }
    } else if (Array.isArray(linkedInResult.results)) {
      console.log('[V2_PILOT_QUICK_SEARCH] Found results in results array');
      leads = linkedInResult.results;
    }
    
    console.log('[V2_PILOT_QUICK_SEARCH] Extracted leads count:', leads.length);
    
    // Validate leads is an array
    if (!Array.isArray(leads)) {
      console.error('[V2_PILOT_QUICK_SEARCH] ERROR: leads is not an array:', typeof leads);
      console.error('[V2_PILOT_QUICK_SEARCH] Full response structure:', JSON.stringify(linkedInResult, null, 2).substring(0, 1000));
      return NextResponse.json(
        {
          error: 'Invalid response format',
          message: 'LinkedIn API returned unexpected data structure',
          details: { receivedType: typeof leads, response: linkedInResult },
        },
        { status: 500 }
      );
    }
    
    if (leads.length === 0) {
      return NextResponse.json(
        {
          success: true,
          leads: [],
          count: 0,
          message: 'No leads found matching search criteria',
        }
      );
    }

    // Format leads for V2 Pilot
    const formattedLeads = leads.map((lead: any) => ({
      name: lead.fullName || lead.name || 'Unknown',
      location: lead.geoRegion || lead.location || 'Unknown',
      linkedinUrl: lead.profileUrl || lead.linkedinUrl || lead.url || '',
      title: lead.currentPosition?.title || lead.title || lead.headline || '',
      company: lead.currentPosition?.companyName || lead.companyName || lead.company || '',
      profilePictureUrl: lead.profilePictureUrl || lead.picture || '',
      headline: lead.headline || '',
    }));

    console.log(`[V2_PILOT_QUICK_SEARCH] ✅ Found ${formattedLeads.length} leads`);

    return NextResponse.json({
      success: true,
      leads: formattedLeads,
      count: formattedLeads.length,
      searchParams: params,
      totalResults: linkedInResult.totalResults || linkedInResult.total || formattedLeads.length,
    });

  } catch (error) {
    console.error('[V2_PILOT_QUICK_SEARCH] Error:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}
