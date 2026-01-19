'use client';

import { useState, useEffect, useRef } from 'react';
import Image from 'next/image';

/**
 * V2 PILOT - SOVEREIGN NEURAL PIPELINE DIAGNOSTIC COMMAND CENTER
 * 
 * Advanced diagnostic interface with:
 * - Neural Sight Live Feed (coordinate overlays)
 * - Stealth Health Dashboard (fingerprint audit)
 * - Trauma Triage & Execution Log
 * - Interactive decision trace viewing
 * - Real-time telemetry streaming
 * 
 * NOT FOR END USERS - Internal testing only
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
  region_proposal?: string; // Base64 200x200 crop
  grounding_bbox?: { // NEW: Bounding box for VLM focus area
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

export default function SovereignPilotPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [traumaSignals, setTraumaSignals] = useState<TraumaSignal[]>([]);
  const [bulkInput, setBulkInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedMission, setSelectedMission] = useState<Mission | null>(null);
  const [stats, setStats] = useState({
    total: 0,
    queued: 0,
    processing: 0,
    completed: 0,
    failed: 0,
    success_rate: 0,
  });

  // Quick Search state
  const [quickSearchLocation, setQuickSearchLocation] = useState('');
  const [quickSearchJobTitle, setQuickSearchJobTitle] = useState('');
  const [quickSearchLimit, setQuickSearchLimit] = useState('25');
  const [isQuickSearching, setIsQuickSearching] = useState(false);

  // Queue CSV for enrichment (leads_to_enrich -> Scrapegoat -> Postgres -> /enriched)
  const [isQueueingCsv, setIsQueueingCsv] = useState(false);
  const csvInputRef = useRef<HTMLInputElement | null>(null);
  const [lastQueueCsv, setLastQueueCsv] = useState<{ pushed: number; skipped: number; total: number; at: string } | null>(null);
  const [enrichmentQueue, setEnrichmentQueue] = useState({ leads_to_enrich: 0, failed_leads: 0, redis_connected: false });
  const [isEnriching, setIsEnriching] = useState(false);

  // Polling interval for status updates
  const pollInterval = useRef<NodeJS.Timeout | null>(null);
  const mouseHeatmapCanvas = useRef<HTMLCanvasElement | null>(null);

  // Draw mouse movement heatmap
  useEffect(() => {
    if (mouseHeatmapCanvas.current && selectedMission?.mouse_movements) {
      const canvas = mouseHeatmapCanvas.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw background grid
      ctx.strokeStyle = '#1a1a1a';
      ctx.lineWidth = 1;
      for (let i = 0; i < canvas.width; i += 20) {
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i, canvas.height);
        ctx.stroke();
      }
      for (let i = 0; i < canvas.height; i += 20) {
        ctx.beginPath();
        ctx.moveTo(0, i);
        ctx.lineTo(canvas.width, i);
        ctx.stroke();
      }

      const movements = selectedMission.mouse_movements.slice(-10); // Last 10 movements

      // Draw path
      if (movements.length > 1) {
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(movements[0].x % canvas.width, movements[0].y % canvas.height);
        for (let i = 1; i < movements.length; i++) {
          ctx.lineTo(movements[i].x % canvas.width, movements[i].y % canvas.height);
        }
        ctx.stroke();
      }

      // Draw points
      movements.forEach((movement, idx) => {
        const opacity = (idx + 1) / movements.length;
        ctx.fillStyle = `rgba(0, 255, 0, ${opacity})`;
        ctx.beginPath();
        ctx.arc(movement.x % canvas.width, movement.y % canvas.height, 4, 0, 2 * Math.PI);
        ctx.fill();
      });

      // Check for mechanical movement (straight lines)
      if (movements.length >= 3) {
        let straightLineCount = 0;
        for (let i = 2; i < movements.length; i++) {
          const dx1 = movements[i-1].x - movements[i-2].x;
          const dy1 = movements[i-1].y - movements[i-2].y;
          const dx2 = movements[i].x - movements[i-1].x;
          const dy2 = movements[i].y - movements[i-1].y;
          
          // Check if angles are too similar (mechanical)
          const angle1 = Math.atan2(dy1, dx1);
          const angle2 = Math.atan2(dy2, dx2);
          const angleDiff = Math.abs(angle1 - angle2);
          
          if (angleDiff < 0.1) { // Less than ~6 degrees
            straightLineCount++;
          }
        }
        
        if (straightLineCount > movements.length / 2) {
          ctx.fillStyle = 'rgba(255, 0, 0, 0.3)';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = '#ff0000';
          ctx.font = '12px monospace';
          ctx.fillText('⚠️ MECHANICAL MOVEMENT', 10, 20);
        }
      }
    }
  }, [selectedMission]);

  // Poll for mission status updates
  useEffect(() => {
    pollInterval.current = setInterval(async () => {
      try {
        const response = await fetch('/api/v2-pilot/mission-status');
        if (response.ok) {
          const data = await response.json();
          setMissions(data.missions || []);
          setTraumaSignals(data.trauma_signals || []);
          setStats(data.stats || stats);
        }
      } catch (error) {
        console.error('Failed to poll mission status:', error);
      }
    }, 2000); // Poll every 2 seconds

    return () => {
      if (pollInterval.current) {
        clearInterval(pollInterval.current);
      }
    };
  }, []);

  // Poll enrichment queue (leads_to_enrich, failed_leads) for pipeline visibility
  useEffect(() => {
    const fetchEnrichment = async () => {
      try {
        const r = await fetch('/api/enrichment/queue-status');
        if (r.ok) {
          const d = await r.json();
          setEnrichmentQueue({
            leads_to_enrich: d.leads_to_enrich ?? 0,
            failed_leads: d.failed_leads ?? 0,
            redis_connected: d.redis_connected ?? false,
          });
        }
      } catch {
        setEnrichmentQueue((prev) => ({ ...prev, redis_connected: false }));
      }
    };
    fetchEnrichment();
    const t = setInterval(fetchEnrichment, 4000);
    return () => clearInterval(t);
  }, []);

  // Fire 25-lead batch to Chimera swarm
  const handleFireSwarm = async () => {
    if (!bulkInput.trim()) {
      alert('Please enter lead data in format: Name | Location (one per line)');
      return;
    }

    setIsProcessing(true);
    try {
      const lines = bulkInput.split('\n').filter(line => line.trim());
      const leads = lines.slice(0, 25).map(line => {
        const [name, location] = line.split('|').map(s => s.trim());
        return { name: name || 'Unknown', location: location || 'Unknown' };
      });

      const response = await fetch('/api/v2-pilot/fire-swarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leads }),
      });

      if (response.ok) {
        const result = await response.json();
        alert(`✅ Fired ${result.missions_queued} missions to Chimera swarm`);
        setBulkInput('');
      } else {
        const error = await response.json();
        alert(`❌ Failed to fire swarm: ${error.message}`);
      }
    } catch (error) {
      console.error('Error firing swarm:', error);
      alert('❌ Network error firing swarm');
    } finally {
      setIsProcessing(false);
    }
  };

  // Quick Search - Generate leads from LinkedIn RapidAPI
  const handleQuickSearch = async () => {
    if (!quickSearchLocation && !quickSearchJobTitle) {
      alert('Please enter at least one search parameter (Location or Job Title)');
      return;
    }

    setIsQuickSearching(true);
    try {
      // Call Quick Search API
      const searchResponse = await fetch('/api/v2-pilot/quick-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          location: quickSearchLocation || undefined,
          jobTitle: quickSearchJobTitle || undefined,
          limit: parseInt(quickSearchLimit) || 25,
        }),
      });

      if (!searchResponse.ok) {
        const error = await searchResponse.json();
        const msg = error.retryAfter
          ? `Too many requests. Wait ${error.retryAfter} seconds and try again. Use Manual Input to fire leads while you wait.`
          : `Search failed: ${error.message}`;
        alert(`❌ ${msg}`);
        return;
      }

      const searchResult = await searchResponse.json();
      
      if (searchResult.leads.length === 0) {
        alert('⚠️ No leads found matching search criteria');
        return;
      }

      // Automatically fire leads to swarm
      const fireResponse = await fetch('/api/v2-pilot/fire-swarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leads: searchResult.leads }),
      });

      if (fireResponse.ok) {
        const fireResult = await fireResponse.json();
        alert(`✅ Found ${searchResult.leads.length} leads and fired ${fireResult.missions_queued} missions to Chimera swarm`);
        
        // Clear search fields
        setQuickSearchLocation('');
        setQuickSearchJobTitle('');
      } else {
        const error = await fireResponse.json();
        alert(`❌ Found ${searchResult.leads.length} leads but failed to fire swarm: ${error.message}`);
      }

    } catch (error) {
      console.error('Error in quick search:', error);
      alert('❌ Network error during quick search');
    } finally {
      setIsQuickSearching(false);
    }
  };

  // Queue CSV for enrichment (leads_to_enrich -> Scrapegoat worker -> Postgres; view /enriched)
  const handleQueueCsv = async () => {
    const input = csvInputRef.current;
    const file = input?.files?.[0];
    if (!file) {
      alert('Please select a CSV file (columns: Name, LinkedIn URL, Location, Title, Company, etc.)');
      return;
    }
    setIsQueueingCsv(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/enrichment/queue-csv', { method: 'POST', body: form });
      const data = await res.json();
      if (data.success) {
        setLastQueueCsv({
          pushed: data.pushed ?? 0,
          skipped: data.skipped ?? 0,
          total: data.total ?? 0,
          at: new Date().toLocaleTimeString(),
        });
        alert(`Queued ${data.pushed} for enrichment (${data.skipped} skipped).\n\nEnsure Redis + Postgres + Scrapegoat worker are running. Results in /enriched.`);
        if (input) input.value = '';
      } else {
        alert(`Queue failed: ${data.error || data.message}`);
      }
    } catch (e) {
      alert(`Error: ${(e as Error)?.message || 'Unknown'}`);
    } finally {
      setIsQueueingCsv(false);
    }
  };

  // Process one from queue (Enrich = run pipeline on 1 lead via Scrapegoat)
  const handleEnrichOne = async () => {
    setIsEnriching(true);
    try {
      const r = await fetch('/api/enrichment/process-one', { method: 'POST' });
      const d = await r.json();
      if (d.processed) {
        alert(d.success ? `✅ Enriched 1: ${d.name || 'saved'}` : `⚠ Processed 1 (not saved: likely no phone or DNC)`);
      } else {
        alert(d.message || d.error || 'Queue empty or Scrapegoat unavailable.');
      }
    } catch (e) {
      alert(`Error: ${(e as Error)?.message || 'Unknown'}`);
    } finally {
      setIsEnriching(false);
    }
  };

  // Get severity color
  const getSeverityColor = (severity: 'red' | 'yellow') => {
    return severity === 'red' ? 'bg-red-500' : 'bg-yellow-500';
  };

  // Get status color
  const getStatusColor = (status: Mission['status']) => {
    switch (status) {
      case 'completed': return 'bg-green-500';
      case 'processing': return 'bg-blue-500';
      case 'queued': return 'bg-gray-500';
      case 'failed': return 'bg-red-500';
      case 'timeout': return 'bg-orange-500';
      case 'captcha_failure': return 'bg-purple-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="min-h-screen bg-black text-green-400 p-8 font-mono">
      {/* Header */}
      <div className="mb-8 border-b border-green-500 pb-4">
        <h1 className="text-3xl font-bold mb-2">
          🧠 SOVEREIGN NEURAL PIPELINE - V2 PILOT
        </h1>
        <p className="text-sm text-green-600">
          Direct access to Chimera Core worker swarm • Real-time telemetry • Production verification
        </p>
      </div>

      {/* Stats Dashboard */}
      <div className="grid grid-cols-6 gap-4 mb-8">
        <div className="bg-gray-900 p-4 rounded border border-green-500">
          <div className="text-xs text-green-600">TOTAL MISSIONS</div>
          <div className="text-2xl font-bold">{stats.total}</div>
        </div>
        <div className="bg-gray-900 p-4 rounded border border-gray-500">
          <div className="text-xs text-gray-400">QUEUED</div>
          <div className="text-2xl font-bold text-gray-400">{stats.queued}</div>
        </div>
        <div className="bg-gray-900 p-4 rounded border border-blue-500">
          <div className="text-xs text-blue-400">PROCESSING</div>
          <div className="text-2xl font-bold text-blue-400">{stats.processing}</div>
        </div>
        <div className="bg-gray-900 p-4 rounded border border-green-500">
          <div className="text-xs text-green-400">COMPLETED</div>
          <div className="text-2xl font-bold text-green-400">{stats.completed}</div>
        </div>
        <div className="bg-gray-900 p-4 rounded border border-red-500">
          <div className="text-xs text-red-400">FAILED</div>
          <div className="text-2xl font-bold text-red-400">{stats.failed}</div>
        </div>
        <div className="bg-gray-900 p-4 rounded border border-green-500">
          <div className="text-xs text-green-600">SUCCESS RATE</div>
          <div className="text-2xl font-bold">{stats.success_rate.toFixed(1)}%</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8 mb-8">
        {/* Left Column: Lead Input */}
        <div className="bg-gray-900 p-6 rounded border border-green-500">
          <h2 className="text-xl font-bold mb-4 flex items-center">
            🔥 LEAD INJECTION CONTROLLER
          </h2>

          {/* Queue CSV for enrichment (leads_to_enrich -> Scrapegoat -> Postgres -> /enriched) */}
          <div className="mb-6 p-4 rounded border border-cyan-500 bg-black/40">
            <p className="text-xs text-cyan-400 font-bold mb-2">📤 QUEUE CSV FOR ENRICHMENT</p>
            <p className="text-xs text-gray-400 mb-3">CSV with LinkedIn URL, Name, Location, etc. → leads_to_enrich → Scrapegoat → Postgres. View results in /enriched.</p>
            <div className="flex gap-2 items-center">
              <input
                ref={csvInputRef}
                type="file"
                accept=".csv"
                className="flex-1 text-xs text-gray-300 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-cyan-600 file:text-black file:font-bold"
              />
              <button
                onClick={handleQueueCsv}
                disabled={isQueueingCsv}
                className="bg-cyan-500 text-black font-bold py-2 px-4 rounded hover:bg-cyan-400 disabled:bg-gray-600 disabled:cursor-not-allowed text-sm"
              >
                {isQueueingCsv ? '⏳ QUEUING...' : 'QUEUE FOR ENRICHMENT'}
              </button>
            </div>
          </div>

          {/* Enrichment Pipeline status – queue depth, last action, link to /enriched */}
          <div className="mb-6 p-4 rounded border border-amber-500/70 bg-black/40">
            <p className="text-xs text-amber-400 font-bold mb-2">📊 ENRICHMENT PIPELINE</p>
            <p className="text-xs text-gray-400 mb-3">leads_to_enrich → Scrapegoat worker → Postgres. Queue depth updates as workers drain it.</p>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="bg-black/60 p-2 rounded border border-gray-600">
                <span className="text-[10px] text-gray-500 uppercase">In queue</span>
                <div className={`text-lg font-bold ${enrichmentQueue.leads_to_enrich > 0 ? 'text-amber-400' : 'text-gray-500'}`}>
                  {enrichmentQueue.leads_to_enrich}
                </div>
              </div>
              <div className="bg-black/60 p-2 rounded border border-gray-600">
                <span className="text-[10px] text-gray-500 uppercase">Failed (DLQ)</span>
                <div className={`text-lg font-bold ${enrichmentQueue.failed_leads > 0 ? 'text-red-400' : 'text-gray-500'}`}>
                  {enrichmentQueue.failed_leads}
                </div>
              </div>
            </div>
            {!enrichmentQueue.redis_connected && (
              <p className="text-xs text-yellow-500/80 mb-2">⚠ Redis not configured or unreachable (REDIS_URL)</p>
            )}
            <div className="flex gap-2 items-center flex-wrap mb-2">
              <button
                onClick={handleEnrichOne}
                disabled={isEnriching || enrichmentQueue.leads_to_enrich === 0}
                className="bg-amber-500 text-black font-bold py-2 px-4 rounded hover:bg-amber-400 disabled:bg-gray-600 disabled:cursor-not-allowed text-sm"
              >
                {isEnriching ? '⏳ ENRICHING…' : 'ENRICH'}
              </button>
              <span className="text-xs text-gray-500">Process 1 from queue now</span>
            </div>
            {lastQueueCsv && (
              <p className="text-xs text-cyan-300 mb-2">
                Last: Queued <strong>{lastQueueCsv.pushed}</strong> ({lastQueueCsv.skipped} skipped) at {lastQueueCsv.at}
              </p>
            )}
            <a
              href="/enriched"
              className="inline-block text-xs font-bold text-amber-400 hover:text-amber-300 underline"
            >
              View results in /enriched →
            </a>
          </div>
          
          {/* Tab Selector */}
          <div className="flex gap-2 mb-4 border-b border-gray-700">
            <button
              onClick={() => {
                setQuickSearchLocation('');
                setQuickSearchJobTitle('');
              }}
              className={`px-4 py-2 font-bold text-sm transition ${
                quickSearchLocation === '' && quickSearchJobTitle === ''
                  ? 'bg-green-500 text-black border-b-2 border-green-400'
                  : 'text-green-600 hover:text-green-400'
              }`}
            >
              📝 MANUAL INPUT
            </button>
            <button
              onClick={() => {}}
              className={`px-4 py-2 font-bold text-sm transition ${
                quickSearchLocation !== '' || quickSearchJobTitle !== ''
                  ? 'bg-blue-500 text-black border-b-2 border-blue-400'
                  : 'text-blue-600 hover:text-blue-400'
              }`}
            >
              🔍 QUICK SEARCH (RapidAPI)
            </button>
          </div>

          {/* Quick Search Form */}
          <div className="mb-6">
            <p className="text-xs text-blue-600 mb-3">
              Generate real leads from LinkedIn Sales Navigator
            </p>
            <div className="space-y-3">
              <input
                type="text"
                value={quickSearchLocation}
                onChange={(e) => setQuickSearchLocation(e.target.value)}
                placeholder="Location (e.g., Naples, FL)"
                className="w-full bg-black text-green-400 border border-blue-500 p-2 rounded font-mono text-sm focus:outline-none focus:border-blue-300"
                disabled={isQuickSearching}
              />
              <input
                type="text"
                value={quickSearchJobTitle}
                onChange={(e) => setQuickSearchJobTitle(e.target.value)}
                placeholder="Job Title (e.g., CEO, Marketing Director)"
                className="w-full bg-black text-green-400 border border-blue-500 p-2 rounded font-mono text-sm focus:outline-none focus:border-blue-300"
                disabled={isQuickSearching}
              />
              <select
                value={quickSearchLimit}
                onChange={(e) => setQuickSearchLimit(e.target.value)}
                className="w-full bg-black text-green-400 border border-blue-500 p-2 rounded font-mono text-sm focus:outline-none focus:border-blue-300"
                disabled={isQuickSearching}
              >
                <option value="10">10 leads</option>
                <option value="25">25 leads</option>
                <option value="50">50 leads</option>
                <option value="100">100 leads</option>
              </select>
            </div>
            <button
              onClick={handleQuickSearch}
              disabled={isQuickSearching || (!quickSearchLocation && !quickSearchJobTitle)}
              className="w-full mt-3 bg-blue-500 text-black font-bold py-3 px-6 rounded hover:bg-blue-400 disabled:bg-gray-600 disabled:cursor-not-allowed transition"
            >
              {isQuickSearching ? '⏳ SEARCHING & FIRING...' : '🔍 QUICK SEARCH & FIRE'}
            </button>
          </div>

          {/* Manual Bulk Input */}
          <div>
            <p className="text-xs text-green-600 mb-2">
              Or manually enter leads: Name | Location (one per line, max 25)
            </p>
            <textarea
              value={bulkInput}
              onChange={(e) => setBulkInput(e.target.value)}
              placeholder="John Doe | Naples, FL&#10;Jane Smith | Miami, FL&#10;..."
              className="w-full h-32 bg-black text-green-400 border border-green-500 p-3 rounded font-mono text-sm resize-none focus:outline-none focus:border-green-300"
              disabled={isProcessing}
            />
            <div className="mt-3 flex gap-4">
              <button
                onClick={handleFireSwarm}
                disabled={isProcessing}
                className="flex-1 bg-green-500 text-black font-bold py-3 px-6 rounded hover:bg-green-400 disabled:bg-gray-600 disabled:cursor-not-allowed transition"
              >
                {isProcessing ? '⏳ FIRING...' : '🚀 FIRE MANUAL BATCH'}
              </button>
              <button
                onClick={() => setBulkInput('')}
                disabled={isProcessing}
                className="bg-red-500 text-black font-bold py-3 px-6 rounded hover:bg-red-400 disabled:bg-gray-600 disabled:cursor-not-allowed transition"
              >
                CLEAR
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Trauma Triage Panel */}
        <div className="bg-gray-900 p-6 rounded border border-yellow-500">
          <h2 className="text-xl font-bold mb-4 flex items-center">
            🚨 TRAUMA TRIAGE PANEL
          </h2>
          <p className="text-xs text-yellow-600 mb-4">
            Real-time trauma signals from Chimera swarm
          </p>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {traumaSignals.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                ✅ No trauma signals detected
              </div>
            ) : (
              traumaSignals.map((signal, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded border-l-4 ${
                    signal.severity === 'red' ? 'border-red-500 bg-red-900/20' : 'border-yellow-500 bg-yellow-900/20'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-bold ${signal.severity === 'red' ? 'text-red-400' : 'text-yellow-400'}`}>
                      {signal.type}
                    </span>
                    <span className="text-xs text-gray-500">
                      {new Date(signal.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-xs text-gray-400">
                    Mission: {signal.mission_id.substring(0, 20)}...
                  </div>
                  <div className="text-xs text-gray-300 mt-1">
                    {signal.details}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Neural Sight Live Feed (Grounding Mirror) */}
      <div className="mb-8 bg-gray-900 p-6 rounded border border-cyan-500">
        <h2 className="text-xl font-bold mb-4 flex items-center">
          👁️ NEURAL SIGHT LIVE FEED (Grounding Mirror)
        </h2>
        <p className="text-xs text-cyan-600 mb-4">
          Real-time coordinate overlays • Blue = Blueprint • Green = VLM Click • Drift alerts
        </p>
        <div className="grid grid-cols-2 gap-6">
          {/* Main Screenshot with Coordinate Overlay */}
          <div className="bg-black rounded border border-cyan-500 p-4">
            <div className="text-xs text-cyan-400 mb-2 font-bold">LIVE SCREENSHOT + OVERLAY</div>
            {selectedMission?.screenshot_url ? (
              <div className="relative">
                <img 
                  src={selectedMission.screenshot_url} 
                  alt="Target site screenshot"
                  className="w-full rounded border border-gray-700"
                />
                {/* Grounding Heatmap - Bounding box for VLM focus area */}
                {selectedMission.grounding_bbox && (
                  <div 
                    className="absolute border-4 border-cyan-400 bg-cyan-400 bg-opacity-10"
                    style={{
                      left: `${selectedMission.grounding_bbox.x}px`,
                      top: `${selectedMission.grounding_bbox.y}px`,
                      width: `${selectedMission.grounding_bbox.width}px`,
                      height: `${selectedMission.grounding_bbox.height}px`,
                    }}
                  >
                    <div className="absolute -top-6 left-0 bg-cyan-500 text-black px-2 py-0.5 text-xs font-bold rounded">
                      VLM FOCUS AREA
                    </div>
                  </div>
                )}
                {selectedMission.coordinate_drift && (
                  <>
                    {/* Blue Dot - Blueprint prediction */}
                    <div 
                      className="absolute w-3 h-3 bg-blue-500 rounded-full border-2 border-white shadow-lg z-10"
                      style={{
                        left: `${selectedMission.coordinate_drift.suggested.x}px`,
                        top: `${selectedMission.coordinate_drift.suggested.y}px`,
                        transform: 'translate(-50%, -50%)'
                      }}
                      title="Blueprint Prediction"
                    />
                    {/* Green Crosshair - Actual VLM click */}
                    <div 
                      className="absolute z-10"
                      style={{
                        left: `${selectedMission.coordinate_drift.actual.x}px`,
                        top: `${selectedMission.coordinate_drift.actual.y}px`,
                        transform: 'translate(-50%, -50%)'
                      }}
                      title="VLM Actual Click"
                    >
                      <div className="w-6 h-0.5 bg-green-400 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 shadow-lg" />
                      <div className="w-0.5 h-6 bg-green-400 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 shadow-lg" />
                      <div className="w-3 h-3 border-2 border-green-400 rounded-full absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 shadow-lg" />
                    </div>
                    {/* Drift Distance Indicator */}
                    {selectedMission.coordinate_drift.drift_distance > 50 && (
                      <div className="absolute top-2 right-2 bg-yellow-500 text-black px-3 py-1 rounded font-bold text-xs shadow-lg z-10">
                        ⚠️ DRIFT: {selectedMission.coordinate_drift.drift_distance.toFixed(0)}px
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-600 border border-gray-700 rounded">
                Select a processing mission to see live feed
              </div>
            )}
          </div>

          {/* Region Proposal (Zoom-In) */}
          <div className="bg-black rounded border border-cyan-500 p-4">
            <div className="text-xs text-cyan-400 mb-2 font-bold">REGION PROPOSAL (200x200)</div>
            {selectedMission?.region_proposal ? (
              <div>
                <img 
                  src={`data:image/png;base64,${selectedMission.region_proposal}`}
                  alt="Region proposal crop"
                  className="w-full rounded border border-gray-700"
                  style={{ imageRendering: 'pixelated' }}
                />
                <div className="mt-2 text-xs text-gray-400">
                  VLM analyzing this region • Target element highlighted
                </div>
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-600 border border-gray-700 rounded">
                No region proposal available
              </div>
            )}

            {/* VLM Confidence Meter */}
            {selectedMission?.vision_confidence !== undefined && (
              <div className="mt-4 bg-gray-800 p-3 rounded">
                <div className="text-xs text-cyan-400 mb-2">VLM CONFIDENCE METER</div>
                <div className="relative h-6 bg-gray-700 rounded overflow-hidden">
                  <div 
                    className={`h-full transition-all ${
                      selectedMission.vision_confidence >= 0.95 ? 'bg-green-500' : 
                      selectedMission.vision_confidence >= 0.80 ? 'bg-yellow-500' : 
                      'bg-red-500'
                    }`}
                    style={{ width: `${selectedMission.vision_confidence * 100}%` }}
                  />
                  <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
                    {(selectedMission.vision_confidence * 100).toFixed(1)}%
                  </div>
                </div>
                {selectedMission.fallback_triggered && (
                  <div className="mt-2 text-xs text-yellow-400">
                    ⚡ FALLBACK TRIGGERED: olmOCR-2 Secondary Pass Active
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Stealth Health Dashboard (Fingerprint Audit) */}
      <div className="mb-8 bg-gray-900 p-6 rounded border border-purple-500">
        <h2 className="text-xl font-bold mb-4 flex items-center">
          🕵️ STEALTH HEALTH DASHBOARD (Fingerprint Audit)
        </h2>
        <p className="text-xs text-purple-600 mb-4">
          Real-time fingerprint monitoring • JA3, User-Agent, Proxy Pinning, Mouse Jitter
        </p>
        <div className="grid grid-cols-3 gap-6">
          {/* Fingerprint Snapshot */}
          <div className="bg-black rounded border border-purple-500 p-4">
            <div className="text-xs text-purple-400 mb-3 font-bold">FINGERPRINT SNAPSHOT</div>
            {selectedMission?.fingerprint ? (
              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-gray-500">JA3 Hash:</span>
                  <div className="font-mono text-green-400 truncate">
                    {selectedMission.fingerprint.ja3_hash}
                  </div>
                </div>
                <div>
                  <span className="text-gray-500">User-Agent:</span>
                  <div className="text-gray-300 text-[10px] break-words">
                    {selectedMission.fingerprint.user_agent}
                  </div>
                </div>
                <div>
                  <span className="text-gray-500">Sec-Ch-Ua:</span>
                  <div className="font-mono text-gray-300 text-[10px] break-words">
                    {selectedMission.fingerprint.sec_ch_ua}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-gray-600 text-xs">No fingerprint data available</div>
            )}
          </div>

          {/* Proxy Pinning Status */}
          <div className="bg-black rounded border border-purple-500 p-4">
            <div className="text-xs text-purple-400 mb-3 font-bold">PROXY PINNING STATUS</div>
            {selectedMission?.fingerprint ? (
              <div className="space-y-3">
                <div>
                  <span className="text-gray-500 text-xs">ISP/Carrier:</span>
                  <div className={`text-lg font-bold ${
                    selectedMission.fingerprint.isp_carrier.includes('T-Mobile') ? 'text-pink-400' :
                    selectedMission.fingerprint.isp_carrier.includes('AT&T') ? 'text-blue-400' :
                    selectedMission.fingerprint.isp_carrier.includes('Verizon') ? 'text-red-400' :
                    'text-green-400'
                  }`}>
                    {selectedMission.fingerprint.isp_carrier}
                  </div>
                </div>
                <div>
                  <span className="text-gray-500 text-xs">Session ID:</span>
                  <div className="font-mono text-gray-300 text-[10px] truncate">
                    {selectedMission.fingerprint.session_id}
                  </div>
                </div>
                {selectedMission.fingerprint.ip_changed ? (
                  <div className="bg-red-900 border border-red-500 p-2 rounded">
                    <div className="text-red-400 font-bold text-xs">🚨 SESSION BROKEN</div>
                    <div className="text-red-300 text-[10px]">IP changed mid-mission</div>
                  </div>
                ) : (
                  <div className="bg-green-900 border border-green-500 p-2 rounded">
                    <div className="text-green-400 font-bold text-xs">✅ SESSION STABLE</div>
                    <div className="text-green-300 text-[10px]">IP pinned successfully</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-gray-600 text-xs">No proxy data available</div>
            )}
          </div>

          {/* Human Jitter Heatmap */}
          <div className="bg-black rounded border border-purple-500 p-4">
            <div className="text-xs text-purple-400 mb-3 font-bold">HUMAN JITTER HEATMAP</div>
            <canvas 
              ref={mouseHeatmapCanvas}
              width={300}
              height={200}
              className="w-full border border-gray-700 rounded"
            />
            <div className="text-[10px] text-gray-500 mt-2">
              Last 10 mouse movements • Green = natural • Red overlay = mechanical
            </div>
          </div>
        </div>
      </div>

      {/* VLM Coordinate Drift Stream */}
      <div className="mb-8 bg-gray-900 p-6 rounded border border-blue-500">
        <h2 className="text-xl font-bold mb-4 flex items-center">
          🎯 VLM COORDINATE DRIFT (Neural Mirror)
        </h2>
        <p className="text-xs text-blue-600 mb-4">
          Real-time vision corrections • Suggested vs Actual coordinates
        </p>
        <div className="grid grid-cols-3 gap-4">
          {missions
            .filter(m => m.coordinate_drift)
            .slice(0, 6)
            .map((mission, idx) => (
              <div 
                key={idx} 
                className={`bg-black p-4 rounded border cursor-pointer transition-all ${
                  selectedMission?.id === mission.id ? 'border-cyan-400 shadow-lg' : 'border-blue-500 hover:border-blue-400'
                }`}
                onClick={() => setSelectedMission(mission)}
              >
                <div className="text-xs text-blue-400 mb-2">
                  {mission.name.substring(0, 20)}...
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Suggested:</span>
                    <span className="text-yellow-400">
                      ({mission.coordinate_drift!.suggested.x}, {mission.coordinate_drift!.suggested.y})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Actual:</span>
                    <span className="text-green-400">
                      ({mission.coordinate_drift!.actual.x}, {mission.coordinate_drift!.actual.y})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Confidence:</span>
                    <span className={mission.coordinate_drift!.confidence >= 0.95 ? 'text-green-400' : 'text-yellow-400'}>
                      {(mission.coordinate_drift!.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                  {mission.coordinate_drift!.drift_distance && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Drift:</span>
                      <span className={mission.coordinate_drift!.drift_distance > 50 ? 'text-yellow-400 font-bold' : 'text-green-400'}>
                        {mission.coordinate_drift!.drift_distance.toFixed(0)}px
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
        </div>
      </div>

      {/* Mission Log with Interactive Traceability */}
      <div className="bg-gray-900 p-6 rounded border border-green-500">
        <h2 className="text-xl font-bold mb-4">📋 MISSION LOG (Live) - Click any row for Decision Trace</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-green-500">
                <th className="text-left p-2">Status</th>
                <th className="text-left p-2">Mission ID</th>
                <th className="text-left p-2">Name</th>
                <th className="text-left p-2">Location</th>
                <th className="text-left p-2">Carrier</th>
                <th className="text-left p-2">VLM Conf</th>
                <th className="text-left p-2">Entropy</th>
                <th className="text-left p-2">Trauma</th>
                <th className="text-left p-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {missions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-gray-500">
                    No missions yet. Fire the swarm to begin.
                  </td>
                </tr>
              ) : (
                missions.map((mission, idx) => (
                  <tr 
                    key={idx} 
                    className={`border-b border-gray-700 cursor-pointer transition-all ${
                      selectedMission?.id === mission.id ? 'bg-cyan-900' : 'hover:bg-gray-800'
                    }`}
                    onClick={() => setSelectedMission(mission)}
                  >
                    <td className="p-2">
                      <span className={`inline-block px-2 py-1 rounded text-[10px] font-bold text-black ${getStatusColor(mission.status)}`}>
                        {mission.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="p-2 font-mono text-[10px]">
                      {mission.id.substring(0, 16)}...
                    </td>
                    <td className="p-2">{mission.name}</td>
                    <td className="p-2">{mission.location}</td>
                    <td className="p-2">
                      {mission.carrier ? (
                        <span className="text-blue-400">{mission.carrier}</span>
                      ) : (
                        <span className="text-gray-600">-</span>
                      )}
                    </td>
                    <td className="p-2">
                      {mission.vision_confidence !== undefined ? (
                        <span className={mission.vision_confidence >= 0.95 ? 'text-green-400' : 'text-yellow-400'}>
                          {(mission.vision_confidence * 100).toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-gray-600">-</span>
                      )}
                    </td>
                    <td className="p-2">
                      {mission.entropy_score !== undefined ? (
                        <span className={mission.entropy_score >= 0.7 ? 'text-green-400' : 'text-red-400'}>
                          {mission.entropy_score.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-gray-600">-</span>
                      )}
                    </td>
                    <td className="p-2">
                      {mission.trauma_signals && mission.trauma_signals.length > 0 ? (
                        <span className="text-red-400">{mission.trauma_signals.length}</span>
                      ) : (
                        <span className="text-green-600">✓</span>
                      )}
                    </td>
                    <td className="p-2 text-gray-500">
                      {new Date(mission.timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Decision Trace Modal */}
      {selectedMission && selectedMission.decision_trace && (
        <div className="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50 p-8">
          <div className="bg-gray-900 border border-cyan-500 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-cyan-500 flex justify-between items-center sticky top-0 bg-gray-900">
              <h2 className="text-xl font-bold text-cyan-400">
                🧠 DECISION TRACE - {selectedMission.name}
              </h2>
              <button 
                onClick={() => setSelectedMission(null)}
                className="text-gray-400 hover:text-white text-2xl"
              >
                ×
              </button>
            </div>
            <div className="p-6">
              {/* Mission Summary */}
              <div className="mb-6 bg-black p-4 rounded border border-gray-700">
                <div className="grid grid-cols-3 gap-4 text-xs">
                  <div>
                    <span className="text-gray-500">Mission ID:</span>
                    <div className="font-mono text-green-400">{selectedMission.id}</div>
                  </div>
                  <div>
                    <span className="text-gray-500">Status:</span>
                    <div className={`font-bold ${
                      selectedMission.status === 'completed' ? 'text-green-400' :
                      selectedMission.status === 'processing' ? 'text-blue-400' :
                      selectedMission.status === 'failed' ? 'text-red-400' :
                      'text-gray-400'
                    }`}>
                      {selectedMission.status.toUpperCase()}
                    </div>
                  </div>
                  <div>
                    <span className="text-gray-500">Location:</span>
                    <div className="text-white">{selectedMission.location}</div>
                  </div>
                </div>
              </div>

              {/* Decision Timeline */}
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-cyan-400 mb-3">EXECUTION TIMELINE:</h3>
                {selectedMission.decision_trace.map((trace, idx) => (
                  <div 
                    key={idx}
                    className="flex items-start gap-4 bg-black p-4 rounded border border-gray-700"
                  >
                    <div className="flex-shrink-0 w-8 h-8 bg-cyan-500 text-black rounded-full flex items-center justify-center font-bold text-xs">
                      {idx + 1}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-bold text-cyan-400">{trace.step}</span>
                        <span className="text-xs text-gray-500">
                          {new Date(trace.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="text-xs text-gray-300 mb-2">{trace.action}</div>
                      {trace.confidence !== undefined && (
                        <div className="flex items-center gap-2">
                          <div className="text-xs text-gray-500">Confidence:</div>
                          <div className="flex-1 h-2 bg-gray-700 rounded overflow-hidden">
                            <div 
                              className={`h-full ${
                                trace.confidence >= 0.95 ? 'bg-green-500' :
                                trace.confidence >= 0.80 ? 'bg-yellow-500' :
                                'bg-red-500'
                              }`}
                              style={{ width: `${trace.confidence * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-cyan-400 font-bold">
                            {(trace.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Entropy Poison Check */}
              {selectedMission.entropy_score !== undefined && (
                <div className="mt-6 bg-black p-4 rounded border border-gray-700">
                  <h3 className="text-sm font-bold text-cyan-400 mb-3">DATA FRESHNESS CHECK:</h3>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-gray-500">Entropy Score:</div>
                      <div className={`text-2xl font-bold ${
                        selectedMission.entropy_score >= 0.7 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {selectedMission.entropy_score.toFixed(2)}
                      </div>
                    </div>
                    {selectedMission.entropy_score < 0.7 ? (
                      <div className="bg-red-900 border border-red-500 p-3 rounded">
                        <div className="text-red-400 font-bold text-sm">⚠️ POISON DETECTED</div>
                        <div className="text-red-300 text-xs">Data likely poisoned or identical</div>
                      </div>
                    ) : (
                      <div className="bg-green-900 border border-green-500 p-3 rounded">
                        <div className="text-green-400 font-bold text-sm">✅ DATA FRESH</div>
                        <div className="text-green-300 text-xs">Entropy within acceptable range</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Footer Info */}
      <div className="mt-8 text-xs text-gray-600 border-t border-gray-700 pt-4">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <div className="font-bold text-green-600 mb-1">MOBILE IP PINNING</div>
            <div>Sticky sessions verified • Carrier-locked per mission</div>
          </div>
          <div>
            <div className="font-bold text-green-600 mb-1">POISON DETECTION</div>
            <div>Entropy threshold: 0.70 • Cross-source consensus active</div>
          </div>
          <div>
            <div className="font-bold text-green-600 mb-1">STEALTH STATUS</div>
            <div>Bezier paths • Micro-tremor • Fatigue curves active</div>
          </div>
        </div>
      </div>
    </div>
  );
}
