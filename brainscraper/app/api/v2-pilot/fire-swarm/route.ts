import { NextRequest, NextResponse } from 'next/server';
import Redis from 'ioredis';

/**
 * V2 PILOT - FIRE SWARM API
 * 
 * Accepts 25-lead batch and pushes missions directly to chimera:missions queue
 * 
 * This bypasses standard UI enrichment and goes straight to Chimera Core
 */

interface Lead {
  name: string;
  location: string;
}

interface MissionPayload {
  mission_id: string;
  mission_type: 'enrichment';
  lead_data: {
    name: string;
    location: string;
    city?: string;
    state?: string;
  };
  carrier_preference?: string;
  sticky_session_id?: string;
  timestamp: number;
}

// Parse location into city/state
function parseLocation(location: string): { city?: string; state?: string } {
  const parts = location.split(',').map(s => s.trim());
  if (parts.length >= 2) {
    return {
      city: parts[0],
      state: parts[1],
    };
  }
  return { city: location };
}

// Generate sticky session ID for mobile IP pinning
function generateStickySessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(7)}`;
}

// Get Redis client
function getRedisClient(): Redis {
  const redisUrl = process.env.REDIS_URL || process.env.APP_REDIS_URL;
  if (!redisUrl) {
    throw new Error('REDIS_URL not configured');
  }
  return new Redis(redisUrl, { maxRetriesPerRequest: 3 });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { leads } = body as { leads: Lead[] };

    if (!leads || !Array.isArray(leads) || leads.length === 0) {
      return NextResponse.json(
        { error: 'Invalid request', message: 'leads array required' },
        { status: 400 }
      );
    }

    // Limit to 25 leads
    const batchLeads = leads.slice(0, 25);

    // Connect to Redis
    const redisClient = getRedisClient();

    // Generate missions and push to queue
    const missions: MissionPayload[] = [];
    for (const lead of batchLeads) {
      const missionId = `mission_${Date.now()}_${Math.random().toString(36).substring(7)}`;
      const { city, state } = parseLocation(lead.location);

      const mission: MissionPayload = {
        mission_id: missionId,
        mission_type: 'enrichment',
        lead_data: {
          name: lead.name,
          location: lead.location,
          city,
          state,
        },
        sticky_session_id: generateStickySessionId(), // Mobile IP pinning
        timestamp: Date.now(),
      };

      missions.push(mission);

      // Push to chimera:missions queue (LPUSH for FIFO with BRPOP)
      await redisClient.lpush('chimera:missions', JSON.stringify(mission));
    }

    // Also store mission metadata for status tracking
    for (const mission of missions) {
      await redisClient.hset(
        `mission:${mission.mission_id}`,
        'status', 'queued',
        'name', mission.lead_data.name,
        'location', mission.lead_data.location,
        'sticky_session_id', mission.sticky_session_id || '',
        'timestamp', mission.timestamp.toString()
      );
      // Set expiry (24 hours)
      await redisClient.expire(`mission:${mission.mission_id}`, 86400);
    }

    return NextResponse.json({
      success: true,
      missions_queued: missions.length,
      mission_ids: missions.map(m => m.mission_id),
    });
  } catch (error) {
    console.error('Error firing swarm:', error);
    return NextResponse.json(
      { 
        error: 'Internal server error', 
        message: error instanceof Error ? error.message : 'Unknown error' 
      },
      { status: 500 }
    );
  }
}
