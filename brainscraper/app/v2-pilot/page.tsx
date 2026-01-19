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

/** Bump when deploying so you can confirm the live site has the new build. */
const V2_PILOT_UI_VERSION = 1;

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
  const [isClearingQueue, setIsClearingQueue] = useState(false);
  const [enrichStatus, setEnrichStatus] = useState<string | null>(null);
  const [enrichProgress, setEnrichProgress] = useState<{ step: number; total: number; pct: number; station: string; status: string; message?: string; duration_ms?: number; error?: string } | null>(null);
  const [enrichSteps, setEnrichSteps] = useState<Array<{ station: string; status: string; message?: string; duration_ms?: number; error?: string }>>([]);
  const [enrichSubsteps, setEnrichSubsteps] = useState<Array<{ station: string; substep: string; detail: string }>>([]);
  const [diagnosticOnlyFailures, setDiagnosticOnlyFailures] = useState(false);
  const diagnosticListRef = useRef<HTMLDivElement | null>(null);
  const [waitingCoreSince, setWaitingCoreSince] = useState<number | null>(null);
  const [coreStaleHint, setCoreStaleHint] = useState(false);
  const [lastEnrichRun, setLastEnrichRun] = useState<{
    at: string;
    processed?: boolean;
    success?: boolean;
    name?: string;
    linkedin_url?: string;
    error?: string;
    message?: string;
    steps?: Array<{
      station: string;
      started_at?: string;
      duration_ms: number;
      condition: string;
      status: string;
      error?: string;
      recent_logs?: string[];
      error_file?: string;
      error_line?: number;
      error_traceback?: string;
      suggested_fix?: string;
    }>;
    logs?: string[];
    diagnostic_log?: string[];
    http_status?: number;
    http_statusText?: string;
    error_name?: string;
    error_cause?: string;
    error_stack?: string;
    error_traceback?: string;
    failure_mode?: string;
    failure_at?: string;
    hint?: string;
  } | null>(null);
  const [showLastRunLogs, setShowLastRunLogs] = useState(false);
  const [isDownloadingLogs, setIsDownloadingLogs] = useState(false);
  const [preflight, setPreflight] = useState<{
    redis_connected?: boolean;
    scrapegoat_ok?: boolean;
    chimera_brain_http_url_set?: boolean;
    chimera_brain_address_set?: boolean;
    scrapegoat_url?: string;
    checked_at?: string;
  } | null>(null);

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

  // Pre-flight on mount
  useEffect(() => {
    loadPreflight();
  }, []);

  // Rehydrate last run from localStorage so it survives refresh (within 2h)
  useEffect(() => {
    try {
      if (typeof localStorage === 'undefined') return;
      const s = localStorage.getItem('v2pilot_last_run');
      if (!s) return;
      const x = JSON.parse(s) as { at?: string; processed?: boolean; success?: boolean; error?: string; steps?: unknown[]; logs?: string[] };
      const at = x?.at;
      if (!at) return;
      if (Date.now() - new Date(at).getTime() > 2 * 60 * 60 * 1000) return;
      setLastEnrichRun({ ...x, at } as any);
    } catch {
      // ignore
    }
  }, []);

  // While stuck at "waiting_core" with no Core telemetry for 15s, show stale hint (fail-sooner)
  useEffect(() => {
    if (!isEnriching || waitingCoreSince == null) return;
    const started = waitingCoreSince;
    const t = setInterval(() => {
      if (Date.now() - started > 15000) setCoreStaleHint(true);
    }, 5000);
    return () => clearInterval(t);
  }, [isEnriching, waitingCoreSince]);

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

  // Pre-flight: Redis, Scrapegoat, Chimera Brain — run before testing
  const loadPreflight = async () => {
    try {
      const r = await fetch('/api/v2-pilot/debug-info');
      if (r.ok) {
        const d = await r.json();
        setPreflight({ ...d, checked_at: new Date().toISOString() });
      }
    } catch {
      setPreflight(null);
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

  // Persist last run to localStorage so it survives refresh; truncate logs to avoid quota
  const persistLastRun = (obj: Record<string, unknown>) => {
    try {
      if (typeof localStorage === 'undefined') return;
      let o: Record<string, unknown> = { ...obj };
      if (Array.isArray(o.logs) && o.logs.length > 2000) {
        o = { ...o, logs: o.logs.slice(-2000), _logsTruncated: true };
      }
      localStorage.setItem('v2pilot_last_run', JSON.stringify(o));
    } catch {
      // ignore quota/parse
    }
  };

  // Process one from queue (Enrich) via Scrapegoat start + poll. No long-lived stream.
  // Fixes BodyStreamBuffer/AbortError when runs exceed 5–10 min (Chimera 6×90s + overhead).
  const handleEnrichOne = async () => {
    const diag: string[] = [];
    const t = () => new Date().toISOString().slice(11, 23);
    const log = (line: string) => {
      diag.push(line);
      console.log('[Enrich]', line);
    };
    const logErr = (line: string) => {
      diag.push(line);
      console.error('[Enrich]', line);
    };

    setIsEnriching(true);
    setEnrichStatus('Quick check…');
    setEnrichProgress(null);
    setEnrichSteps([]);
    setEnrichSubsteps([]);

    let diagRes: { redis_connected?: boolean; scrapegoat_ok?: boolean } | null = null;
    try {
      const dr = await fetch('/api/v2-pilot/debug-info', { signal: (typeof AbortSignal !== 'undefined' && AbortSignal.timeout) ? AbortSignal.timeout(6000) : undefined });
      if (dr.ok) {
        diagRes = await dr.json();
        setPreflight((prev: any) => ({ ...prev, ...diagRes, checked_at: new Date().toISOString() }));
      }
    } catch {
      /* ignore */
    }
    if (diagRes?.scrapegoat_ok === false) {
      setEnrichStatus(null);
      setIsEnriching(false);
      alert('Scrapegoat unreachable. Fix SCRAPEGOAT_API_URL or start Scrapegoat. Enrich skipped.');
      return;
    }
    if (diagRes?.redis_connected === false) {
      setEnrichStatus(null);
      setIsEnriching(false);
      alert('Redis not connected. Fix REDIS_URL. Enrich skipped.');
      return;
    }

    setEnrichStatus('Starting…');
    log(`[${t()}] Enrich started (start+poll). POST /api/enrichment/start`);

    try {
      const startRes = await fetch('/api/enrichment/start', { method: 'POST', signal: AbortSignal.timeout(15000) });
      const d = (await startRes.json()) as { run_id?: string; done?: boolean; processed?: boolean; message?: string; error?: string; hint?: string };
      if ((d.done && !d.processed) || d.message === 'Queue empty') {
        alert(d.message || d.hint || 'Queue empty. Add leads via Queue CSV first.');
        return;
      }
      if (!d.run_id) {
        setLastEnrichRun({ at: new Date().toISOString(), processed: false, error: d.error || 'No run_id', diagnostic_log: diag } as any);
        persistLastRun({ at: new Date().toISOString(), processed: false, error: d.error || 'No run_id' });
        setShowLastRunLogs(true);
        alert(d.error || 'Start failed: no run_id. Check Scrapegoat logs.');
        return;
      }
      const runId = d.run_id;
      setEnrichStatus('Processing…');

      const applyProgress = (ev: Record<string, unknown>) => {
        if (ev.event === 'log' && ev.action != null) {
          setEnrichSubsteps((s) => [...s, { station: String(ev.component ?? 'Pipeline'), substep: String(ev.action), detail: String(ev.detail ?? '') }]);
        }
        if (ev.substep != null) {
          const st = (ev.station as string) ?? '';
          const sb = String(ev.substep);
          setEnrichSubsteps((s) => [...s, { station: st, substep: sb, detail: String(ev.detail ?? '') }]);
          if (st === 'Chimera' && sb === 'waiting_core') setWaitingCoreSince(Date.now());
          if (st === 'Chimera' && /^(deep_search_start|pivot_|captcha_|capsolver_|vlm_|extract_|got_result|timeout|core_failed|parse_fail|core_bad_type|get_next_exhausted)/.test(sb)) setWaitingCoreSince(null);
        }
        if (ev.step != null && ev.total != null) {
          setEnrichProgress({
            step: (ev.step as number) ?? 0,
            total: (ev.total as number) ?? 0,
            pct: (ev.pct as number) ?? 0,
            station: (ev.station as string) ?? '?',
            status: (ev.status as string) ?? '?',
            message: ev.message as string | undefined,
            duration_ms: ev.duration_ms as number | undefined,
            error: ev.error as string | undefined,
          });
        }
        if (ev.status === 'running') {
          setEnrichSteps((s) => [...s, { station: (ev.station as string) ?? '?', status: 'running', message: ev.message as string }]);
        } else if (ev.step != null && ev.status != null) {
          setEnrichSteps((s) => {
            const n = [...s];
            if (n.length) n[n.length - 1] = { ...n[n.length - 1], status: (ev.status as string) ?? '?', duration_ms: ev.duration_ms as number | undefined, message: ev.message as string | undefined, error: ev.error as string | undefined };
            return n;
          });
        }
      };

      await new Promise<void>((resolve) => {
        const poll = async () => {
          try {
            const r = await fetch(`/api/enrichment/status?run_id=${encodeURIComponent(runId)}`, { signal: AbortSignal.timeout(10000) });
            const data = (r.status === 404 ? { status: 'error' as const, error: 'Run not found' } : await r.json()) as { status: string; progress?: Record<string, unknown>; result?: Record<string, unknown>; error?: string };
            if (data.status === 'done' && data.result) {
              const res = data.result as Record<string, unknown>;
              const run = {
                at: new Date().toISOString(),
                http_status: 200,
                diagnostic_log: ['Enrich (start+poll).', ...((res.steps as Array<{ station?: string; status?: string; duration_ms?: number }>) || []).map((s) => `Step: ${s.station ?? '?'} — ${s.status ?? '?'} ${s.duration_ms ?? 0}ms`), `Done: processed=${res.processed} success=${res.success}`],
                ...res,
              };
              setLastEnrichRun(run as any);
              persistLastRun(run);
              setShowLastRunLogs(true);
              if (res.processed) {
                alert((res.success as boolean) ? `✅ Enriched 1: ${(res.name as string) || 'saved'}` : `⚠ Processed 1 (not saved). See Last run logs; Download logs for full dump.`);
              } else {
                alert((res.message as string) || (res.error as string) || 'Done');
              }
              resolve();
              return;
            }
            if (data.status === 'error') {
              const run = { at: new Date().toISOString(), processed: false, error: data.error || 'Unknown error', diagnostic_log: diag };
              setLastEnrichRun(run as any);
              persistLastRun(run);
              setShowLastRunLogs(true);
              alert(`Error: ${data.error || 'Unknown'}`);
              resolve();
              return;
            }
            if (data.progress && typeof data.progress === 'object') applyProgress(data.progress as Record<string, unknown>);
            setTimeout(poll, 2000);
          } catch (e) {
            logErr(`[${t()}] Poll failed: ${e instanceof Error ? e.message : String(e)}`);
            const run = { at: new Date().toISOString(), processed: false, error: `Status poll failed: ${e instanceof Error ? e.message : String(e)}`, diagnostic_log: diag };
            setLastEnrichRun(run as any);
            persistLastRun(run);
            setShowLastRunLogs(true);
            alert(`Error: Status poll failed. See Last run logs.`);
            resolve();
          }
        };
        poll();
      });
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e));
      logErr(`[${t()}] Start failed. name=${err.name} message=${err.message}`);
      const run = { at: new Date().toISOString(), processed: false, error: err.message || 'Unknown', error_name: err.name, diagnostic_log: diag, failure_mode: 'NETWORK' as const };
      setLastEnrichRun(run as any);
      persistLastRun(run);
      setShowLastRunLogs(true);
      alert(`Error: ${err.message}\n\nSee Diagnostic log and Download logs.`);
    } finally {
      setEnrichStatus(null);
      setEnrichProgress(null);
      setEnrichSteps([]);
      setEnrichSubsteps([]);
      setWaitingCoreSince(null);
      setCoreStaleHint(false);
      setIsEnriching(false);
    }
  };

  // Clear leads_to_enrich and failed_leads (Redis). Refreshes queue display.
  const handleClearQueue = async () => {
    const { leads_to_enrich, failed_leads } = enrichmentQueue;
    if (leads_to_enrich === 0 && failed_leads === 0) return;
    if (!confirm(`Clear ${leads_to_enrich} from queue and ${failed_leads} from failed (DLQ)?`)) return;
    setIsClearingQueue(true);
    try {
      const r = await fetch('/api/enrichment/queue-clear', { method: 'POST' });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert(`Failed to clear: ${d.error || r.statusText}`);
        return;
      }
      setEnrichmentQueue((p) => ({ ...p, leads_to_enrich: 0, failed_leads: 0 }));
    } catch (e) {
      alert(`Error clearing queue: ${e instanceof Error ? e.message : e}`);
    } finally {
      setIsClearingQueue(false);
    }
  };

  // Shared: errors_summary + bottleneck_hint from lastEnrichRun (for Download and Copy for Cursor)
  type ErrEntry = {
    source: string;
    where: string;
    message: string;
    recent_logs?: string[];
    error_file?: string;
    error_line?: number;
    error_traceback?: string;
    error_stack?: string;
    suggested_fix?: string;
    step_index?: number;
    step_total?: number;
  };

  const computeErrorsAndBottleneck = (run: typeof lastEnrichRun) => {
    const allLogLines = run?.logs ?? [];
    const errs: ErrEntry[] = [];
    if (run?.error) {
      let msg = run.error;
      if (run.error_name) msg += ` (${run.error_name})`;
      if (run.error_cause) msg += ` [cause: ${run.error_cause}]`;
      if (run.http_status) msg += ` [HTTP ${run.http_status}]`;
      const e: ErrEntry = { source: 'enrichment', where: 'process-one', message: msg };
      if (run.error_stack) e.error_stack = run.error_stack;
      if (run.error_traceback) e.error_traceback = run.error_traceback;
      errs.push(e);
    }
    const stepTotal = run?.steps?.length ?? 0;
    run?.steps?.forEach((s, i) => {
      if (s.status === 'fail') {
        const e: ErrEntry = {
          source: 'pipeline',
          where: stepTotal ? `${s.station ?? '?'} (${i + 1}/${stepTotal})` : (s.station ?? '?'),
          message: s.error || 'Station failed',
          recent_logs: s.recent_logs?.length ? s.recent_logs : undefined,
          step_index: stepTotal ? i + 1 : undefined,
          step_total: stepTotal || undefined,
        };
        if (s.error_file) e.error_file = s.error_file;
        if (s.error_line != null) e.error_line = s.error_line;
        if (s.error_traceback) e.error_traceback = s.error_traceback;
        if (s.suggested_fix) e.suggested_fix = s.suggested_fix;
        errs.push(e);
      }
    });
    const chimeraRe = /Chimera|chimera/;
    const failRe = /timeout|failed|status=failed|parse error|not a dict|results timeout|mission push|brpop|Exception|Error/;
    let chimeraN = 0;
    allLogLines.forEach((line: string) => {
      if (chimeraRe.test(line) && failRe.test(line)) {
        chimeraN++;
        if (errs.filter((e) => e.source === 'chimera').length < 10) {
          const ln = String(line).slice(0, 520);
          const provider = ln.match(/provider[=:]\s*(\S+)/i)?.[1] || ln.match(/(SearchPeopleFree|FastPeopleSearch|ThatsThem|ZabaSearch|TruePeopleSearch|AnyWho)/i)?.[1];
          errs.push({
            source: 'chimera',
            where: provider ? `Chimera Deep Search (provider≈${provider})` : 'Chimera Deep Search',
            message: ln,
          });
        }
      }
    });
    let longest: { station: string; duration_ms: number } | null = null;
    const failCounts: Record<string, number> = {};
    run?.steps?.forEach((s) => {
      const d = s.duration_ms ?? 0;
      if (d > (longest?.duration_ms ?? 0)) longest = { station: s.station ?? '?', duration_ms: d };
      if (s.status === 'fail') failCounts[s.station ?? '?'] = (failCounts[s.station ?? '?'] ?? 0) + 1;
    });
    const mf = Object.keys(failCounts).length ? Object.entries(failCounts).sort((a, b) => b[1] - a[1])[0] : null;
    const bottleneck_hint = {
      longest_step: longest,
      most_failed_station: mf ? { station: mf[0], fail_count: mf[1] } : null,
      chimera_timeout_or_fail_count: chimeraN,
    };
    return { errorsSummary: errs, bottleneck_hint, allLogLines };
  };

  // Download logs: missions, trauma, enrichment, pipeline, config for debugging Chimera enrichment
  const handleDownloadLogs = async () => {
    setIsDownloadingLogs(true);
    try {
      const [missionRes, queueRes, pipelineRes, debugRes] = await Promise.all([
        fetch('/api/v2-pilot/mission-status'),
        fetch('/api/enrichment/queue-status'),
        fetch('/api/pipeline/status'),
        fetch('/api/v2-pilot/debug-info'),
      ]);
      const mission = missionRes.ok ? await missionRes.json() : {};
      const queue = queueRes.ok ? await queueRes.json() : {};
      const pipeline = pipelineRes.ok ? await pipelineRes.json() : {};
      const config = debugRes.ok ? await debugRes.json() : {};

      const { errorsSummary, bottleneck_hint, allLogLines } = computeErrorsAndBottleneck(lastEnrichRun);

      const readme =
        'HOW TO USE (paste this file or COPY FOR CURSOR into chat to plan fixes): (1) errors_summary = what broke and where (includes chimera timeouts/failures from logs). (2) bottleneck_hint = longest step + chimera failure count. (3) enrichment.lastEnrichRun = steps + full logs. (4) all_log_lines = every pipeline log. (5) config + pipeline = connectivity. (6) For people-search/Chimera: also paste Railway logs for chimera-core (last 50–100 lines) — Scrapegoat does not see Core’s internal errors (captcha, selectors, navigation). (7) AI: attach this file in Cursor, @-mention chimera-core/workers.py, scrapegoat/app/pipeline/stations/enrichment.py, scrapegoat/app/pipeline/stations/blueprint_loader.py, chimera-core/main.py, scrapegoat/main.py (and seed_magazine_blueprints.py if mapping_required; capsolver.py if CAPTCHA), then invoke rule debug-enrichment-with-ai. Full steps: PEOPLE_SEARCH_CHECKLIST.md § Debug with AI.';

      const blob = new Blob(
        [
          JSON.stringify(
            {
              readme,
              errors_summary: errorsSummary,
              bottleneck_hint,
              downloadedAt: new Date().toISOString(),
              userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
              page: 'v2-pilot',
              all_log_lines: allLogLines,
              _all_log_lines_note: 'Every pipeline log line from the last Enrich run. Use for grepping when Railway/terminal miss errors.',
              enrichment: {
                queue: { leads_to_enrich: queue.leads_to_enrich, failed_leads: queue.failed_leads, redis_connected: queue.redis_connected },
                lastQueueCsv,
                lastEnrichRun,
              },
              chimera: {
                missions: mission.missions || [],
                trauma_signals: mission.trauma_signals || [],
                stats: mission.stats || {},
              },
              pipeline: { health: pipeline.health, queue: pipeline.queue, success: pipeline.success, timestamp: pipeline.timestamp },
              config,
            },
            null,
            2
          ),
        ],
        { type: 'application/json' }
      );
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `chimera-enrichment-logs-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert(`Download failed: ${(e as Error)?.message || 'Unknown'}`);
    } finally {
      setIsDownloadingLogs(false);
    }
  };

  // Copy for Cursor: maximally comprehensive paste (errors with file:line, traceback, stack; run_context; connectivity; diagnostic_log; last_log_lines)
  const TRUNC_LOG = 40;
  const TRUNC_LINE = 260;
  const LAST_LOGS = 55;
  const formatErr = (e: ErrEntry, ix: number, total: number): string[] => {
    const out: string[] = [];
    const tag = total > 1 ? ` [${ix + 1}/${total}]` : '';
    out.push(`  [${e.source}] ${e.where}${tag}: ${e.message}`);
    if (e.error_file != null && e.error_line != null) {
      out.push(`    file:line => ${e.error_file}:${e.error_line}`);
    } else if (e.error_file != null) {
      out.push(`    file => ${e.error_file}`);
    }
    if (e.suggested_fix) out.push(`    suggested_fix: ${e.suggested_fix}`);
    if (e.recent_logs?.length) {
      out.push(`    recent_logs (${e.recent_logs.length}):`);
      e.recent_logs.slice(0, 22).forEach((ln) => out.push(`      ${String(ln).slice(0, TRUNC_LINE)}`));
      if (e.recent_logs.length > 22) out.push(`      ... and ${e.recent_logs.length - 22} more`);
    }
    if (e.error_traceback) {
      const tb = e.error_traceback.trim().split('\n').slice(0, TRUNC_LOG);
      out.push('    traceback:');
      tb.forEach((ln) => out.push(`      ${String(ln).slice(0, TRUNC_LINE)}`));
      if (e.error_traceback.split('\n').length > TRUNC_LOG) out.push(`      ... (traceback truncated)`);
    }
    if (e.error_stack) {
      const st = e.error_stack.trim().split('\n').slice(0, TRUNC_LOG);
      out.push('    stack:');
      st.forEach((ln) => out.push(`      ${String(ln).slice(0, TRUNC_LINE)}`));
      if (e.error_stack.split('\n').length > TRUNC_LOG) out.push(`      ... (stack truncated)`);
    }
    return out;
  };

  const handleCopyForCursor = () => {
    const run = lastEnrichRun;
    if (!run) {
      alert('Run Enrich first, then use Copy for Cursor.');
      return;
    }
    const { errorsSummary, bottleneck_hint, allLogLines } = computeErrorsAndBottleneck(run);
    const l = bottleneck_hint.longest_step as { station: string; duration_ms: number } | null;
    const mf = bottleneck_hint.most_failed_station as { station: string; fail_count: number } | null;

    const firstErr = errorsSummary[0];
    const oneLiner = [
      `processed=${run.processed} success=${run.success}`,
      run.failure_mode ? ` failure_mode=${run.failure_mode}` : '',
      firstErr ? ` first_error=[${firstErr.source}] ${firstErr.where}` : '',
      run.name ? ` lead="${String(run.name).slice(0, 40)}"` : run.linkedin_url ? ` linkedin=${String(run.linkedin_url).slice(0, 50)}` : '',
    ].join('');

    const errBlock =
      errorsSummary.length > 0
        ? errorsSummary.flatMap((e, i) => formatErr(e, i, errorsSummary.length))
        : ['  (none)'];

    const stepTotal = run.steps?.length ?? 0;
    const stepDetails = (run.steps ?? []).map((s: { station?: string; status?: string; condition?: string; duration_ms?: number; error?: string; error_file?: string; error_line?: number; suggested_fix?: string; started_at?: string }, i: number) => {
      const idx = stepTotal ? ` ${i + 1}/${stepTotal}` : '';
      const base = `${s.station}(${s.status},${s.condition ?? '?'})${s.duration_ms ?? 0}ms${idx}`;
      const extra: string[] = [];
      if (s.error) extra.push(`err=${String(s.error).slice(0, 64)}`);
      if (s.error_file != null && s.error_line != null) extra.push(`${s.error_file}:${s.error_line}`);
      if (s.suggested_fix) extra.push(`fix=${String(s.suggested_fix).slice(0, 52)}`);
      if (s.started_at && s.status === 'fail') extra.push(`started=${s.started_at}`);
      return extra.length ? `${base} [${extra.join('; ')}]` : base;
    });

    const lastLogs = allLogLines.slice(-LAST_LOGS).map((ln: string) => String(ln).slice(0, TRUNC_LINE));
    const diagLog = (run.diagnostic_log ?? []).slice(-22).map((ln: string) => String(ln).slice(0, TRUNC_LINE));

    const lines: string[] = [
      '--- v2-pilot: paste into Cursor to debug Chimera enrichment ---',
      '',
      '## one_line_summary',
      oneLiner,
      '',
      '## run_context',
      `  at: ${run.at}`,
      `  processed: ${run.processed} success: ${run.success}`,
      ...(run.name != null ? [`  lead.name: ${String(run.name).slice(0, 80)}`] : []),
      ...(run.linkedin_url != null ? [`  lead.linkedin_url: ${String(run.linkedin_url).slice(0, 100)}`] : []),
      ...(run.failure_mode != null ? [`  failure_mode: ${run.failure_mode}`] : []),
      ...(run.failure_at != null ? [`  failure_at: ${run.failure_at}`] : []),
      ...(run.hint != null ? [`  hint: ${run.hint}`] : []),
      ...(run.http_status != null ? [`  http_status: ${run.http_status}`] : []),
      ...(run.error_cause != null ? [`  error_cause: ${String(run.error_cause).slice(0, 120)}`] : []),
      ...(diagLog.length > 0
        ? [`  diagnostic_log (last ${diagLog.length}):`, ...diagLog.map((ln) => `    ${ln}`)]
        : []),
      '',
      '## connectivity (at copy time)',
      preflight != null
        ? `  preflight: redis=${preflight.redis_connected} scrapegoat=${preflight.scrapegoat_ok} url=${String(preflight.scrapegoat_url ?? '').slice(0, 50)} checked=${preflight.checked_at ?? '?'}`
        : '  preflight: (not run)',
      `  queue: leads_to_enrich=${enrichmentQueue.leads_to_enrich} failed_leads=${enrichmentQueue.failed_leads} redis=${enrichmentQueue.redis_connected}`,
      '',
      '## errors_summary',
      ...errBlock,
      '',
      '## bottleneck_hint',
      `  longest_step: ${l ? `${l.station} ${l.duration_ms}ms` : '-'}`,
      `  chimera_timeout_or_fail_count: ${bottleneck_hint.chimera_timeout_or_fail_count}`,
      `  most_failed: ${mf ? `${mf.station} (${mf.fail_count})` : '-'}`,
      '',
      '## steps',
      ...stepDetails.map((s) => `  ${s}`),
      '',
      `## last_log_lines (tail ${LAST_LOGS})`,
      ...lastLogs.map((ln) => `  ${ln}`),
      '',
      '## AI',
      'For people-search/Chimera: also paste Railway logs for chimera-core (last 50–100 lines).',
      '@chimera-core/workers.py @scrapegoat/app/pipeline/stations/enrichment.py @scrapegoat/app/pipeline/stations/blueprint_loader.py @chimera-core/main.py @scrapegoat/main.py and rule debug-enrichment-with-ai. See PEOPLE_SEARCH_CHECKLIST.md § Debug with AI.',
      '---',
    ].flat();

    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(
      () => alert('Copied. Paste into Cursor.'),
      () => alert('Clipboard failed. Use Download logs and attach the file.')
    );
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
      {/* Version badge: bump V2_PILOT_UI_VERSION when deploying to verify the live site. */}
      <div
        className="fixed top-3 right-3 z-[100] px-2.5 py-1 rounded border border-green-500/70 bg-black/90 text-green-400 text-xs font-mono font-bold"
        title="Bump V2_PILOT_UI_VERSION in page.tsx on each deploy to confirm the site has the new build"
      >
        v{V2_PILOT_UI_VERSION}
      </div>
      {/* Header */}
      <div className="mb-8 border-b border-green-500 pb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold mb-2">
            🧠 SOVEREIGN NEURAL PIPELINE - V2 PILOT
          </h1>
          <p className="text-sm text-green-600">
            Direct access to Chimera Core worker swarm • Real-time telemetry • Production verification
          </p>
          <p className="text-[10px] text-gray-500 mt-1">
            To get fixes fast: Copy for Cursor (or attach Download) + chimera-core Railway logs for people-search issues.
          </p>
          <p className="text-[10px] text-gray-500 mt-0.5">
            AI debug: Paste in Cursor with @chimera-core/workers.py @scrapegoat/app/pipeline/stations/enrichment.py @scrapegoat/app/pipeline/stations/blueprint_loader.py @chimera-core/main.py @scrapegoat/main.py and rule debug-enrichment-with-ai. Steps: PEOPLE_SEARCH_CHECKLIST.md § Debug with AI.
          </p>
          <p className="text-[10px] text-gray-600 mt-0.5">
            Version badge top-right — bump V2_PILOT_UI_VERSION on each deploy to confirm the site updated
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={handleCopyForCursor}
            className="bg-amber-600 hover:bg-amber-500 text-black font-bold py-2 px-4 rounded text-sm"
          >
            📋 COPY FOR CURSOR
          </button>
          <button
            onClick={handleDownloadLogs}
            disabled={isDownloadingLogs}
            className="bg-cyan-600 hover:bg-cyan-500 text-black font-bold py-2 px-4 rounded disabled:bg-gray-600 disabled:cursor-not-allowed text-sm"
          >
            {isDownloadingLogs ? '⏳ PREPARING…' : '⬇ DOWNLOAD LOGS'}
          </button>
        </div>
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

          {/* A. PRE-FLIGHT — Check before testing (A: test functionality) */}
          <div className="mb-6 p-4 rounded border border-emerald-500/70 bg-black/40">
            <p className="text-xs text-emerald-400 font-bold mb-2">A. PRE-FLIGHT — Check before testing</p>
            <p className="text-xs text-gray-400 mb-2">Redis and Scrapegoat are used by BrainScraper. To test: Pre-flight ✓ → Queue CSV → Enrich → Last run / Download logs.</p>
            <div className="flex flex-wrap gap-4 mb-2">
              <span className={preflight?.redis_connected ? 'text-green-400' : 'text-gray-500'}>
                Redis: {preflight?.redis_connected === true ? '✓' : preflight ? '✗' : '—'}
              </span>
              <span className={preflight?.scrapegoat_ok ? 'text-green-400' : 'text-gray-500'}>
                Scrapegoat: {preflight?.scrapegoat_ok === true ? '✓' : preflight ? '✗' : '—'}
              </span>
            </div>
            <p className="text-[10px] text-gray-500 mb-2">Chimera Brain: CHIMERA_BRAIN_HTTP_URL or CHIMERA_BRAIN_ADDRESS must be set in <strong>Scrapegoat</strong> and <strong>Chimera Core</strong> (BrainScraper does not use it).</p>
            <button type="button" onClick={loadPreflight} className="text-xs bg-emerald-600 hover:bg-emerald-500 text-black px-2 py-1 rounded font-bold">
              Check
            </button>
          </div>

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
              <button
                onClick={handleClearQueue}
                disabled={isEnriching || isClearingQueue || (enrichmentQueue.leads_to_enrich === 0 && enrichmentQueue.failed_leads === 0)}
                className="bg-red-600 text-white font-bold py-2 px-4 rounded hover:bg-red-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-sm"
                title="Clear leads_to_enrich and failed_leads in Redis"
              >
                {isClearingQueue ? '⏳' : 'CLEAR'}
              </button>
              <span className="text-xs text-gray-500">Process 1 from queue now · Clear empties leads_to_enrich + DLQ</span>
            </div>
            {isEnriching && (
              <div className="mb-3 p-3 rounded border border-amber-500/50 bg-black/50" role="status" aria-live="polite">
                {(enrichStatus || enrichProgress) && (
                  <p className="text-xs text-amber-400 mb-2">{enrichStatus || (enrichProgress ? `${enrichProgress.pct}% — ${enrichProgress.station} (${enrichProgress.status})` : '')}</p>
                )}
                {enrichProgress && enrichProgress.total > 0 && (
                  <div className="mb-2">
                    <div className="flex justify-between text-[10px] text-gray-400 mb-0.5">
                      <span>{enrichProgress.pct}%</span>
                      <span>of {enrichProgress.total} steps</span>
                    </div>
                    <div className="w-full h-2 bg-gray-700 rounded overflow-hidden">
                      <div className="h-full bg-amber-500 transition-all duration-300" style={{ width: `${enrichProgress.pct}%` }} />
                    </div>
                  </div>
                )}
                {enrichSteps.length > 0 && (
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {enrichSteps.map((s, i) => (
                      <div key={i} className="flex items-center gap-2 text-[10px]">
                        <span className={s.status === 'running' ? 'text-amber-400' : s.status === 'ok' || s.status === 'stop' ? 'text-green-400' : 'text-red-400'}>
                          {s.status === 'running' ? '⏳' : s.status === 'ok' || s.status === 'stop' ? '✓' : '✗'}
                        </span>
                        <span className="text-gray-300 truncate">{s.station}</span>
                        {s.duration_ms != null && <span className="text-gray-500">{s.duration_ms}ms</span>}
                        {s.status === 'fail' && s.error && <span className="text-red-400 truncate max-w-[140px]" title={s.error}>{s.error}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {enrichSubsteps.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-amber-500/30">
                    <p className="text-[10px] font-bold text-amber-400 mb-1">Diagnostic (root cause) — where the bot is:</p>
                    {coreStaleHint && (
                      <div className="mb-2 p-1.5 rounded bg-red-950/40 border border-red-500/60 text-[10px] text-red-300">
                        No result from Chimera Core for 15s. Timeout ~90s. Check chimera-core Railway logs (pivot_*, capsolver_*, DOM) and REDIS_URL.
                      </div>
                    )}
                    <div className="flex items-center gap-3 mb-1">
                      <label className="flex items-center gap-1 text-[10px] text-gray-400 cursor-pointer">
                        <input type="checkbox" checked={diagnosticOnlyFailures} onChange={(e) => setDiagnosticOnlyFailures(e.target.checked)} />
                        Show only failures
                      </label>
                      <button
                        type="button"
                        className="text-[10px] text-amber-400 hover:underline"
                        onClick={() => diagnosticListRef.current?.querySelector('.text-red-400')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })}
                      >
                        Jump to first failure
                      </button>
                    </div>
                    <div ref={diagnosticListRef} className="space-y-0.5 max-h-40 overflow-y-auto font-mono text-[10px]">
                      {(diagnosticOnlyFailures
                        ? enrichSubsteps.filter((x) => /fail|timeout|capsolver_fail|vlm_fail|selector_fail|mapping_required|parse_fail|core_failed|pivot_fill_fail|pivot_result_fail/i.test(x.substep + x.detail))
                        : enrichSubsteps
                      ).map((x, i) => (
                        <div key={i} className={`flex gap-1 break-all ${/fail|timeout|capsolver_fail|vlm_fail|selector_fail|mapping_required|parse_fail|core_failed/i.test(x.substep + x.detail) ? 'text-red-400' : 'text-cyan-300/90'}`}>
                          <span className="shrink-0">{x.station}</span>
                          <span>—</span>
                          <span>{x.substep}{x.detail ? `: ${x.detail}` : ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            <p className="text-[10px] text-gray-500 mt-1">Can take 1–5 min (Chimera). Full logs in Console (filter <code className="bg-black/60 px-0.5">[Enrich]</code>) and below. Last run saved across refresh.</p>
            {lastEnrichRun?.failure_mode && (
              <div className="mb-2 p-2 rounded border border-amber-500/80 bg-amber-950/20">
                <p className="text-xs font-bold text-amber-400 mb-1">Cause (inferred)</p>
                <p className="text-[10px] text-amber-200/90">
                  <span className="font-medium">{lastEnrichRun.failure_mode}</span>
                  {lastEnrichRun.failure_at && <span className="text-amber-400/80"> @ {lastEnrichRun.failure_at}</span>}
                </p>
                {lastEnrichRun.hint && (
                  <p className="text-[10px] text-gray-300 mt-1">{lastEnrichRun.hint}</p>
                )}
                {lastEnrichRun.hint && (
                  <button
                    type="button"
                    onClick={() => { navigator.clipboard?.writeText(lastEnrichRun!.hint || ''); }}
                    className="mt-1 text-[10px] text-cyan-400 hover:underline"
                  >
                    Copy hint
                  </button>
                )}
              </div>
            )}
            {(() => {
              const issues: { where: string; message: string }[] = [];
              if (lastEnrichRun?.error) {
                let msg = lastEnrichRun.error;
                if (lastEnrichRun.error_name) msg += ` (${lastEnrichRun.error_name})`;
                if (lastEnrichRun.error_cause) msg += ` [cause: ${lastEnrichRun.error_cause}]`;
                if (lastEnrichRun.http_status) msg += ` [HTTP ${lastEnrichRun.http_status}]`;
                issues.push({ where: 'process-one', message: msg });
              }
              lastEnrichRun?.steps?.forEach((s) => { if (s.status === 'fail') issues.push({ where: s.station, message: s.error || 'Station failed' }); });
              if (issues.length === 0) return null;
              return (
                <div className="mb-2 p-2 rounded border border-red-500/80 bg-red-950/30">
                  <p className="text-xs font-bold text-red-400 mb-1">B. ISSUES IN LAST RUN — fix these first</p>
                  {issues.map((i, j) => (
                    <div key={j} className="text-[10px]">
                      <span className="text-red-300 font-medium">{i.where}</span>: {i.message}
                    </div>
                  ))}
                </div>
              );
            })()}
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
            {lastEnrichRun && (
              <div className="mt-3 pt-3 border-t border-amber-500/40">
                {lastEnrichRun.processed && !lastEnrichRun.success && (
                  <p className="text-xs text-amber-400 mb-2">Last run: not saved (likely no phone or DNC). See steps and logs below; Download logs for full dump.</p>
                )}
                <button
                  type="button"
                  onClick={() => setShowLastRunLogs((s) => !s)}
                  className="text-xs font-bold text-amber-400 hover:text-amber-300"
                >
                  {showLastRunLogs ? '▼' : '▶'} Last run logs ({(lastEnrichRun.diagnostic_log?.length ?? 0) + (lastEnrichRun.steps?.length ?? 0) + (lastEnrichRun.logs?.length ?? 0)} entries) — {lastEnrichRun.at}
                </button>
                {showLastRunLogs && (
                  <div className="mt-2 max-h-96 overflow-y-auto bg-black/80 rounded border border-gray-700 p-2 text-[10px] leading-tight">
                    {lastEnrichRun.diagnostic_log && lastEnrichRun.diagnostic_log.length > 0 && (
                      <div className="mb-3 pb-2 border-b border-gray-600">
                        <p className="text-amber-400 font-bold mb-1">Diagnostic log (client + request/response)</p>
                        {lastEnrichRun.diagnostic_log.map((line, i) => (
                          <div key={`diag-${i}`} className={`font-mono whitespace-pre-wrap break-all ${/error|failed|Non-OK|Possible causes/i.test(line) ? 'text-red-400' : 'text-gray-300'}`}>{line}</div>
                        ))}
                      </div>
                    )}
                    {lastEnrichRun.steps?.map((s, i) => (
                      <div key={i} className="text-cyan-300/90 mb-0.5">
                        step {i + 1}: {s.station} — {s.duration_ms}ms {s.status} {s.error ? `(${s.error})` : ''}
                        {s.status === 'fail' && s.recent_logs?.length ? (
                          <div className="mt-1 ml-2 text-[9px] text-amber-400/80 max-h-16 overflow-y-auto">
                            {(s.recent_logs.length > 5 ? s.recent_logs.slice(-5) : s.recent_logs).map((l, j) => (
                              <div key={j}>{l}</div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                    {lastEnrichRun.logs?.map((line, i) => (
                      <div key={`log-${i}`} className="text-gray-400 whitespace-pre-wrap break-all">{line}</div>
                    ))}
                    {(!lastEnrichRun.logs?.length && !lastEnrichRun.steps?.length) && (
                      <div className="text-gray-500">
                        {lastEnrichRun.diagnostic_log?.length ? 'No pipeline steps or logs. See Diagnostic log above.' : 'No log lines or steps captured.'}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
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
          <p className="text-[10px] text-gray-500 mb-2">
            Data: mission:* .trauma_signals. Fire Swarm or Enrich (ChimeraStation) create mission:{'{id}'}; ChimeraStation writes trauma on timeout/fail. Chimera Core can add more via POST /api/v2-pilot/telemetry.
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
        <p className="text-xs text-cyan-600 mb-2">
          Real-time coordinate overlays • Blue = Blueprint • Green = VLM Click • Drift alerts
        </p>
        <p className="text-[10px] text-gray-500 mb-4">
          Data: mission:{'{id}'} .screenshot_url, .grounding_bbox, .coordinate_drift. Chimera Core must POST to /api/v2-pilot/telemetry (set BRAINSCRAPER_URL). Select a processing mission.
        </p>
        <p className="text-[10px] text-amber-600/90 mb-4">
          Why empty? Set <code className="bg-black/40 px-1">BRAINSCRAPER_URL</code> in chimera-core. Chimera sends screenshot, coordinate_drift, grounding_bbox when a VLM <code className="bg-black/40 px-1">process_vision</code> returns found. If no vision run or no Blueprint suggested coords, coordinate_drift stays empty. BrainScraper needs <code className="bg-black/40 px-1">REDIS_URL</code> (same as Chimera) so telemetry reaches <code className="bg-black/40 px-1">mission:&#123;id&#125;</code>.
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
        <p className="text-xs text-purple-600 mb-2">
          Real-time fingerprint monitoring • JA3, User-Agent, Proxy Pinning, Mouse Jitter
        </p>
        <p className="text-[10px] text-gray-500 mb-4">
          Data: mission:{'{id}'} .fingerprint, .mouse_movements. Chimera Core must POST to /api/v2-pilot/telemetry (set BRAINSCRAPER_URL). Select a mission.
        </p>
        <p className="text-[10px] text-amber-600/90 mb-4">
          Why empty? Chimera Core currently sends only <code className="bg-black/40 px-1">screenshot</code>, <code className="bg-black/40 px-1">vision_confidence</code>, <code className="bg-black/40 px-1">status</code> to telemetry. It does <strong>not</strong> yet send <code className="bg-black/40 px-1">fingerprint</code> or <code className="bg-black/40 px-1">mouse_movements</code>. Until Chimera implements those in its <code className="bg-black/40 px-1">tc.push()</code> calls, these panels stay empty. BRAINSCRAPER_URL must be set in chimera-core for any telemetry.
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
              <div className="text-gray-600 text-xs">
                No fingerprint data available.
                <span className="block text-[10px] text-amber-600/80 mt-1">Chimera does not yet send <code>fingerprint</code> to /api/v2-pilot/telemetry.</span>
              </div>
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
              <div className="text-gray-600 text-xs">
                No proxy data available.
                <span className="block text-[10px] text-amber-600/80 mt-1">Uses same <code>fingerprint</code> object; not sent by Chimera yet.</span>
              </div>
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
            {(!selectedMission?.mouse_movements || selectedMission.mouse_movements.length === 0) && (
              <div className="text-[10px] text-amber-600/80 mt-1">
                Chimera does not yet send <code>mouse_movements</code> to telemetry; heatmap stays empty.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* VLM Coordinate Drift Stream */}
      <div className="mb-8 bg-gray-900 p-6 rounded border border-blue-500">
        <h2 className="text-xl font-bold mb-4 flex items-center">
          🎯 VLM COORDINATE DRIFT (Neural Mirror)
        </h2>
        <p className="text-xs text-blue-600 mb-2">
          Real-time vision corrections • Suggested vs Actual coordinates
        </p>
        <p className="text-[10px] text-amber-600/90 mb-4">
          Needs <code className="bg-black/40 px-1">coordinate_drift</code> from Chimera: only set when <code className="bg-black/40 px-1">process_vision</code> is called with Blueprint <code className="bg-black/40 px-1">suggested_x/y</code> and VLM returns found. <code className="bg-black/40 px-1">BRAINSCRAPER_URL</code> + <code className="bg-black/40 px-1">REDIS_URL</code> in BrainScraper required.
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
          {missions.filter(m => m.coordinate_drift).length === 0 && (
            <div className="col-span-3 text-center py-6 text-gray-500 text-xs">
              No missions with coordinate_drift yet. Chimera sends it when a VLM run has Blueprint suggested coords and returns found.
            </div>
          )}
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
