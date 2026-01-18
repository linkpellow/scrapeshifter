import { NextRequest, NextResponse } from 'next/server';
import Redis from 'ioredis';

/**
 * V2 PILOT - MISSION STATUS API
 * 
 * Returns real-time mission status, trauma signals, and pipeline statistics
 * 
 * This polls Redis for:
 * - Mission status (queued/processing/completed/failed)
 * - Trauma signals (CAPTCHA failures, timeouts, low confidence)
 * - VLM coordinate drift
 * - Entropy scores (poison detection)
 * - Mobile IP pinning verification
 */

interface Mission {
  id: string;
  name: string;
  location: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'timeout' | 'captcha_failure';
  timestamp: number;
  carrier?: string;
  trauma_signals?: string[];
  coordinate_drift?: {
    suggested: { x: number; y: number };
    actual: { x: number; y: number };
    confidence: number;
    drift_distance: number;
  };
  entropy_score?: number;
  fingerprint?: {
    ja3_hash: string;
    user_agent: string;
    sec_ch_ua: string;
    isp_carrier: string;
    session_id: string;
    ip_changed: boolean;
  };
  screenshot_url?: string;
  region_proposal?: string;
  grounding_bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  mouse_movements?: Array<{ x: number; y: number; timestamp: number }>;
  decision_trace?: Array<{
    step: string;
    action: string;
    timestamp: number;
    confidence?: number;
  }>;
  vision_confidence?: number;
  fallback_triggered?: boolean;
}

interface TraumaSignal {
  mission_id: string;
  type: 'CAPTCHA_AGENT_FAILURE' | 'NEEDS_OLMOCR_VERIFICATION' | 'TIMEOUT' | 'HONEYPOT_TRAP' | 'LOW_ENTROPY';
  severity: 'red' | 'yellow';
  timestamp: number;
  details: string;
}

// Get Redis client
function getRedisClient(): Redis {
  const redisUrl = process.env.REDIS_URL || process.env.APP_REDIS_URL;
  if (!redisUrl) {
    throw new Error('REDIS_URL not configured');
  }
  return new Redis(redisUrl, { maxRetriesPerRequest: 3 });
}

// Calculate entropy score for poison detection
function calculateEntropyScore(data: any): number {
  // Simple entropy calculation based on data uniqueness
  // Low entropy = likely poisoned data (identical values)
  const values = Object.values(data).filter(v => typeof v === 'string' && v.length > 0);
  const uniqueValues = new Set(values);
  return uniqueValues.size / Math.max(values.length, 1);
}

export async function GET(request: NextRequest) {
  try {
    const redisClient = getRedisClient();

    // Get all mission keys
    const missionKeys = await redisClient.keys('mission:*');
    
    const missions: Mission[] = [];
    const traumaSignals: TraumaSignal[] = [];

    // Fetch mission data
    for (const key of missionKeys.slice(0, 100)) { // Limit to 100 most recent
      const missionData = await redisClient.hgetall(key);
      if (Object.keys(missionData).length === 0) continue;

      const missionId = key.replace('mission:', '');
      
      // Parse status
      let status = missionData.status as Mission['status'] || 'queued';
      
      // Check for trauma signals in mission
      const signals: string[] = [];
      if (missionData.trauma_signals) {
        try {
          const parsedSignals = JSON.parse(missionData.trauma_signals);
          signals.push(...parsedSignals);
        } catch {}
      }

      // Parse coordinate drift if available
      let coordinateDrift: Mission['coordinate_drift'] | undefined;
      if (missionData.coordinate_drift) {
        try {
          const parsed = JSON.parse(missionData.coordinate_drift);
          // Calculate drift distance
          const driftDistance = Math.sqrt(
            Math.pow(parsed.actual.x - parsed.suggested.x, 2) +
            Math.pow(parsed.actual.y - parsed.suggested.y, 2)
          );
          coordinateDrift = { ...parsed, drift_distance: driftDistance };
        } catch {}
      }

      // Parse fingerprint data
      let fingerprint: Mission['fingerprint'] | undefined;
      if (missionData.fingerprint) {
        try {
          fingerprint = JSON.parse(missionData.fingerprint);
        } catch {}
      }

      // Parse mouse movements
      let mouseMovements: Mission['mouse_movements'] | undefined;
      if (missionData.mouse_movements) {
        try {
          mouseMovements = JSON.parse(missionData.mouse_movements);
        } catch {}
      }

      // Parse decision trace
      let decisionTrace: Mission['decision_trace'] | undefined;
      if (missionData.decision_trace) {
        try {
          decisionTrace = JSON.parse(missionData.decision_trace);
        } catch {}
      }

      // Parse grounding bounding box (VLM focus area)
      let groundingBbox: Mission['grounding_bbox'] | undefined;
      if (missionData.grounding_bbox) {
        try {
          groundingBbox = JSON.parse(missionData.grounding_bbox);
        } catch {}
      }

      // Calculate entropy score if result data available
      let entropyScore: number | undefined;
      if (missionData.result_data) {
        try {
          const resultData = JSON.parse(missionData.result_data);
          entropyScore = calculateEntropyScore(resultData);
        } catch {}
      }

      missions.push({
        id: missionId,
        name: missionData.name || 'Unknown',
        location: missionData.location || 'Unknown',
        status,
        timestamp: parseInt(missionData.timestamp || '0'),
        carrier: missionData.carrier,
        trauma_signals: signals.length > 0 ? signals : undefined,
        coordinate_drift: coordinateDrift,
        entropy_score: entropyScore,
        fingerprint,
        screenshot_url: missionData.screenshot_url,
        region_proposal: missionData.region_proposal, // Base64 encoded
        grounding_bbox: groundingBbox, // VLM focus area bounding box
        mouse_movements: mouseMovements,
        decision_trace: decisionTrace,
        vision_confidence: missionData.vision_confidence ? parseFloat(missionData.vision_confidence) : undefined,
        fallback_triggered: missionData.fallback_triggered === 'true',
      });

      // Add to trauma signals if any
      if (signals.length > 0) {
        for (const signal of signals) {
          traumaSignals.push({
            mission_id: missionId,
            type: signal as any,
            severity: signal.includes('FAILURE') || signal.includes('TIMEOUT') ? 'red' : 'yellow',
            timestamp: parseInt(missionData.timestamp || '0'),
            details: missionData.trauma_details || `Mission encountered ${signal}`,
          });
        }
      }

      // Add low entropy as trauma signal
      if (entropyScore !== undefined && entropyScore < 0.7) {
        traumaSignals.push({
          mission_id: missionId,
          type: 'LOW_ENTROPY',
          severity: 'red',
          timestamp: parseInt(missionData.timestamp || '0'),
          details: `Data entropy too low (${entropyScore.toFixed(2)}) - possible poisoned data`,
        });
      }
    }

    // Sort by timestamp (most recent first)
    missions.sort((a, b) => b.timestamp - a.timestamp);
    traumaSignals.sort((a, b) => b.timestamp - a.timestamp);

    // Calculate stats
    const stats = {
      total: missions.length,
      queued: missions.filter(m => m.status === 'queued').length,
      processing: missions.filter(m => m.status === 'processing').length,
      completed: missions.filter(m => m.status === 'completed').length,
      failed: missions.filter(m => ['failed', 'timeout', 'captcha_failure'].includes(m.status)).length,
      success_rate: missions.length > 0 
        ? (missions.filter(m => m.status === 'completed').length / missions.length) * 100 
        : 0,
    };

    return NextResponse.json({
      success: true,
      missions: missions.slice(0, 50), // Return most recent 50
      trauma_signals: traumaSignals.slice(0, 20), // Return most recent 20
      stats,
    });
  } catch (error) {
    console.error('Error fetching mission status:', error);
    return NextResponse.json(
      { 
        error: 'Internal server error', 
        message: error instanceof Error ? error.message : 'Unknown error',
        missions: [],
        trauma_signals: [],
        stats: {
          total: 0,
          queued: 0,
          processing: 0,
          completed: 0,
          failed: 0,
          success_rate: 0,
        },
      },
      { status: 500 }
    );
  }
}
