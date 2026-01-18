import { NextRequest, NextResponse } from 'next/server';
import Redis from 'ioredis';

/**
 * V2 PILOT - TELEMETRY INGESTION API
 * 
 * Accepts real-time telemetry from Chimera Core workers
 * 
 * Telemetry includes:
 * - Live screenshots with coordinate overlays
 * - Fingerprint data (JA3, User-Agent, headers)
 * - Mouse movement heatmap data
 * - VLM confidence scores
 * - Decision trace (THINK steps)
 * - Region proposals (200x200 crops)
 */

interface TelemetryPayload {
  mission_id: string;
  
  // Coordinate drift data
  coordinate_drift?: {
    suggested: { x: number; y: number };
    actual: { x: number; y: number };
    confidence: number;
  };
  
  // Fingerprint data
  fingerprint?: {
    ja3_hash: string;
    user_agent: string;
    sec_ch_ua: string;
    isp_carrier: string;
    session_id: string;
    ip_changed: boolean;
  };
  
  // Screenshot and region proposal
  screenshot_url?: string; // URL or data URI
  region_proposal?: string; // Base64 encoded 200x200 crop
  grounding_bbox?: { // Bounding box for VLM focus area
    x: number;
    y: number;
    width: number;
    height: number;
  };
  
  // Mouse movements (last 10)
  mouse_movements?: Array<{
    x: number;
    y: number;
    timestamp: number;
  }>;
  
  // Decision trace
  decision_trace?: Array<{
    step: string;
    action: string;
    timestamp: number;
    confidence?: number;
  }>;
  
  // VLM confidence
  vision_confidence?: number;
  fallback_triggered?: boolean;
  
  // Status update
  status?: 'queued' | 'processing' | 'completed' | 'failed' | 'timeout' | 'captcha_failure';
  
  // Trauma signals
  trauma_signals?: string[];
  trauma_details?: string;
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
    const body = await request.json() as TelemetryPayload;
    const { mission_id } = body;

    if (!mission_id) {
      return NextResponse.json(
        { error: 'mission_id required' },
        { status: 400 }
      );
    }

    const redisClient = getRedisClient();

    // Update mission hash with telemetry data
    const updates: Record<string, string> = {};

    if (body.coordinate_drift) {
      updates.coordinate_drift = JSON.stringify(body.coordinate_drift);
    }

    if (body.fingerprint) {
      updates.fingerprint = JSON.stringify(body.fingerprint);
    }

    if (body.screenshot_url) {
      updates.screenshot_url = body.screenshot_url;
    }

    if (body.region_proposal) {
      updates.region_proposal = body.region_proposal;
    }

    if (body.grounding_bbox) {
      updates.grounding_bbox = JSON.stringify(body.grounding_bbox);
    }

    if (body.mouse_movements) {
      updates.mouse_movements = JSON.stringify(body.mouse_movements);
    }

    if (body.decision_trace) {
      updates.decision_trace = JSON.stringify(body.decision_trace);
    }

    if (body.vision_confidence !== undefined) {
      updates.vision_confidence = body.vision_confidence.toString();
    }

    if (body.fallback_triggered !== undefined) {
      updates.fallback_triggered = body.fallback_triggered.toString();
    }

    if (body.status) {
      updates.status = body.status;
    }

    if (body.trauma_signals) {
      updates.trauma_signals = JSON.stringify(body.trauma_signals);
      if (body.trauma_details) {
        updates.trauma_details = body.trauma_details;
      }
    }

    // Update timestamp
    updates.last_update = Date.now().toString();

    // Write to Redis
    if (Object.keys(updates).length > 0) {
      await redisClient.hset(`mission:${mission_id}`, updates);
      // Reset expiry
      await redisClient.expire(`mission:${mission_id}`, 86400);
    }

    return NextResponse.json({
      success: true,
      mission_id,
      fields_updated: Object.keys(updates).length,
    });
  } catch (error) {
    console.error('Error processing telemetry:', error);
    return NextResponse.json(
      { 
        error: 'Internal server error', 
        message: error instanceof Error ? error.message : 'Unknown error' 
      },
      { status: 500 }
    );
  }
}
