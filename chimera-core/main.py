#!/usr/bin/env python3
# Cache Breaker: 2026-01-18 02:45:00 UTC - Phase 1 Biological Signature Restoration
# Phase 3 Verification: 2026-01-18 03:15:00 UTC - Isomorphic Intelligence & Self-Healing
"""
Chimera Core - The Body (Python Worker)

Python 3.12 worker service that connects to The Brain via gRPC.
Stealth browser automation swarm achieving 100% Human trust score on CreepJS.
"""

import os
import random
import sys
import asyncio
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

THINK_LEVEL = 25
logging.addLevelName(THINK_LEVEL, "THINK")
if not hasattr(logging.Logger, "think"):
    def _think(self: logging.Logger, message, *args, **kwargs):
        if self.isEnabledFor(THINK_LEVEL):
            self._log(THINK_LEVEL, message, args, **kwargs)
    logging.Logger.think = _think  # type: ignore[assignment]

def _infer_log_identity() -> str:
    """
    Branding layer to prevent cross-service log context merging.
    """
    explicit = os.getenv("CHIMERA_LOG_TAG")
    if explicit:
        return explicit.strip()

    service_name = (os.getenv("RAILWAY_SERVICE_NAME") or "").strip().lower()
    if service_name == "chimera-core" or "chimera-core" in service_name:
        return "CHIMERA-BODY"
    if "scrapegoat-worker-swarm" in service_name or "worker-swarm" in service_name:
        return "CHIMERA-SWARM"

    return "CHIMERA"


_LOG_IDENTITY = _infer_log_identity()
_LOG_ROLE = "BODY" if _LOG_IDENTITY.endswith("BODY") else ("SWARM" if _LOG_IDENTITY.endswith("SWARM") else _LOG_IDENTITY)
LOG_LEVEL = "INFO"
os.environ["LOG_LEVEL"] = LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=f'[{_LOG_IDENTITY}] %(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from workers import PhantomWorker
from validation import validate_creepjs, validate_stealth_quick
from db_bridge import test_db_connection, log_mission_result, record_stealth_check
from stealth import set_fatigue_jitter_multiplier, thermal_mark_mission_start, thermal_mark_mission_end
from ghost_browser import perform_warmup


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for Railway healthchecks"""
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","service":"chimera-core"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass


def start_health_server(port: int = 8080):
    """Start HTTP healthcheck server, binding to 0.0.0.0 for Railway"""
    def run_server():
        server_address = ('0.0.0.0', port)
        server = HTTPServer(server_address, HealthCheckHandler)
        logger.info(f"✅ [{_LOG_ROLE}] Health check active on 0.0.0.0:{port}")
        server.serve_forever()
    
    thread = Thread(target=run_server, daemon=True)
    thread.start()
    return thread


async def initialize_worker_swarm(num_workers: int = 1, brain_address: str = "") -> list:
    """
    Initialize worker swarm with stealth browsers.
    
    Args:
        num_workers: Number of worker instances (default: 1 for Railway)
        brain_address: gRPC address of The Brain
    
    Returns:
        List of initialized PhantomWorker instances
    """
    workers = []
    
    for i in range(num_workers):
        worker_id = f"worker-{i}"
        logger.info(f"🦾 Initializing PhantomWorker {worker_id}...")
        
        worker = PhantomWorker(
            worker_id=worker_id,
            brain_address=brain_address,
            headless=True,  # Railway requires headless
        )
        
        await worker.start()
        workers.append(worker)
        
        # Quick stealth validation
        if worker._page:
            is_stealth = await validate_stealth_quick(worker._page)
            if not is_stealth:
                logger.critical(f"❌ Worker {worker_id} failed quick stealth validation!")
        
        logger.info(f"✅ PhantomWorker {worker_id} ready")

    # Ghost warmup: navigate to random news/social 30-60s to build session trust (parallel)
    await asyncio.gather(*[perform_warmup(w) for w in workers])
    logger.info("✅ Ghost warmup done for swarm")

    return workers


async def run_worker_swarm(workers: list):
    """
    Run worker swarm - process missions and maintain connections.

    Phase 8: Redis queue mission consumer (Swarm Hive).
    """
    logger.info(f"🚀 Worker swarm active ({len(workers)} workers)")
    
    # BLOCKING GATE: Validate stealth on first worker using CreepJS
    # If validation fails (score < 100%), validate_creepjs will exit with code 1
    if workers and workers[0]._page:
        logger.info("🔍 Running CreepJS validation on first worker...")
        logger.info("   BLOCKING GATE: Worker will exit if trust score < 100%")
        
        try:
            # Phase 6: Per-mission hardware identity rotation (GPU/Audio/Canvas seeds)
            mission_instance_id = f"creepjs_validation_{int(time.time())}_{workers[0]._session_mission_count + 1}"
            await workers[0].rotate_hardware_identity(mission_id=mission_instance_id)

            # Phase 4: Start tracing for validation mission
            trace_url = None
            await workers[0].start_tracing(mission_id=mission_instance_id)

            # Phase 5: Session aging (fatigue curve) - per-worker counter (thread-safe)
            session_count, jitter_mult, cognitive_mult = workers[0].next_fatigue_state()
            set_fatigue_jitter_multiplier(jitter_mult)
            logger.info(f"✅ Fatigue curve applied: Intensity {jitter_mult:.2f}x")

            # Phase 6: Thermal simulation start bump
            thermal_mark_mission_start(intensity=1.0)
            
            # VANGUARD: Cognitive Load Latency - Adjust delay based on DOM complexity
            # Higher complexity = higher processing delay (simulates human cognitive load)
            try:
                element_count = await workers[0]._page.evaluate("() => document.querySelectorAll('*').length")
                # Base delay: 100ms, additional delay: 1ms per 10 elements (max 500ms)
                cognitive_delay = min(0.1 + (element_count / 10) * 0.001, 0.5)
                # Phase 5 fatigue multiplier
                cognitive_delay *= cognitive_mult
                logger.debug(
                    f"   Cognitive load: {element_count} elements → {cognitive_delay*1000:.1f}ms delay "
                    f"(fatigue {cognitive_mult:.3f}x)"
                )
                await asyncio.sleep(cognitive_delay)
            except Exception as e:
                logger.debug(f"   Cognitive load calculation failed: {e}")
                await asyncio.sleep(0.1)  # Default delay
            
            t0 = time.time()
            result = await validate_creepjs(workers[0]._page)
            duration_s = max(0.0, time.time() - t0)

            # Phase 7: Autonomous Vision initialization probe (forces safe_click → Visual Attempt path once)
            try:
                # Use a Playwright engine selector that is not valid CSS so isomorphic healing returns null,
                # forcing the Visual Attempt path and emitting the BODY-THINK signature.
                await workers[0].safe_click(
                    'xpath=//*[@id="__chimera_phase7_probe__"]',
                    timeout=900,
                    intent="click_failure",
                )
            except Exception:
                pass
            
            # Stop tracing and upload
            trace_url = await workers[0].stop_tracing(mission_id=mission_instance_id)
            if trace_url:
                logger.info(f"✅ Trace uploaded: {trace_url}")

            # Phase 6: Thermal simulation finalization (logs required signature)
            thermal_mark_mission_end(duration_s=duration_s, intensity=1.0)
            
            # If we reach here, validation passed (100% score)
            if result.get("is_human") and result.get("trust_score", 0) >= 100.0:
                logger.info(f"✅ CreepJS Trust Score: {result['trust_score']}% - HUMAN")
                logger.info("🚀 Ready to achieve 100% Human trust score on CreepJS")
                logger.info("✅ BLOCKING GATE PASSED - Worker swarm approved for deployment")
                
                # Phase 2: Record stealth check to PostgreSQL (using connection pool)
                # Phase 4: Include trace URL in mission result
                from db_bridge import log_mission_result
                log_mission_result(
                    worker_id=workers[0].worker_id,
                    trust_score=result['trust_score'],
                    is_human=True,
                    validation_method="creepjs",
                    fingerprint_details=result.get("fingerprint_details", {}),
                    mission_type="stealth_validation",
                    mission_status="completed",
                    trace_url=trace_url
                )
            else:
                # This should not happen if validate_creepjs exits properly
                logger.critical(f"❌ CreepJS Trust Score: {result['trust_score']}% - NOT HUMAN")
                logger.critical("   CRITICAL: Stealth implementation failed validation!")
                logger.critical("   EXITING WITH CODE 1 - Deployment blocked")
                sys.exit(1)
        except SystemExit:
            # validate_creepjs called sys.exit(1) - propagate it
            raise
        except Exception as e:
            logger.critical(f"❌ CreepJS validation exception: {e}")
            logger.critical("   EXITING WITH CODE 1 - Deployment blocked due to validation error")
            sys.exit(1)
    
    # Keep workers alive and process missions (Phase 8: Redis Mission Consumer)
    try:
        # Phase 8: Swarm Hive Redis URL (primary: REDIS_URL; fallbacks for Railway variance)
        redis_url = (
            os.getenv("REDIS_URL")
            or os.getenv("APP_REDIS_URL")
            or os.getenv("REDIS_BRIDGE_URL")
            or os.getenv("REDIS_CONNECTION_URL")
        )
        mission_queue = os.getenv("CHIMERA_MISSION_QUEUE", "chimera:missions")
        mission_dlq = os.getenv("CHIMERA_MISSION_DLQ", "chimera:missions:failed")

        try:
            import json
            import redis
        except Exception:
            redis = None  # type: ignore[assignment]
            json = None  # type: ignore[assignment]

        if not redis_url:
            logger.warning("⚠️ Redis mission consumer disabled (missing REDIS_URL)")
            while True:
                await asyncio.sleep(60)
                logger.debug("Worker swarm heartbeat...")

        if not redis:
            logger.warning("⚠️ Redis mission consumer disabled (redis client unavailable)")
            while True:
                await asyncio.sleep(60)
                logger.debug("Worker swarm heartbeat...")

        r = redis.Redis.from_url(redis_url, decode_responses=True)
        logger.info(f"✅ [{_LOG_ROLE}] Swarm Hive consumer online: queue={mission_queue}")
        print("WORKER_STARTUP_SUCCESS: Redis connected and settings loaded", flush=True)

        # Phase 8: bootstrap prime missions if queue is empty (verification-safe).
        # In production, skip bootstrap so enrichment missions are not delayed by 5 long prime runs.
        bootstrapped = False
        rr = 0
        missions_since_coffee = 0
        coffee_at = random.randint(50, 100)
        skip_bootstrap = (
                    os.getenv("CHIMERA_SKIP_BOOTSTRAP") == "1"
                    or os.getenv("ENVIRONMENT") == "production"
                    or os.getenv("RAILWAY_ENVIRONMENT") == "production"
                )

        while True:
            if not bootstrapped:
                bootstrapped = True
                try:
                    if skip_bootstrap:
                        pass  # do not RPUSH primes; enrichment work gets consumed first
                    else:
                        qlen = await asyncio.to_thread(r.llen, mission_queue)
                        if qlen == 0:
                            bootstrap_ts = int(time.time())
                            prime_missions = [
                                {
                                    "mission_id": f"prime_truepeoplesearch_{bootstrap_ts}",
                                "type": "sequence",
                                "actions": [
                                    {"type": "goto", "url": "https://www.truepeoplesearch.com/", "wait_until": "domcontentloaded", "timeout": 45000},
                                    {"type": "wait_for", "selector": "input#search-name", "timeout": 15000},
                                    {"type": "prime_surface", "selector": "input#search-name", "label": "TruePeopleSearch"},
                                ],
                            },
                            {
                                "mission_id": f"prime_fastpeoplesearch_{bootstrap_ts}",
                                "type": "sequence",
                                "actions": [
                                    {"type": "goto", "url": "https://www.fastpeoplesearch.com/", "wait_until": "domcontentloaded", "timeout": 45000},
                                    {"type": "wait_for", "selector": "input#name-search", "timeout": 15000},
                                    {"type": "prime_surface", "selector": "input#name-search", "label": "FastPeopleSearch"},
                                ],
                            },
                            {
                                "mission_id": f"prime_zabasearch_{bootstrap_ts}",
                                "type": "sequence",
                                "actions": [
                                    {"type": "goto", "url": "https://www.zabasearch.com/", "wait_until": "domcontentloaded", "timeout": 45000},
                                    {"type": "click", "selector": "body", "intent": "prime_structure"},
                                    {"type": "wait", "ms": 300},
                                    {"type": "click", "selector": "body", "intent": "prime_structure_repeat"},
                                ],
                            },
                            {
                                "mission_id": f"prime_anywho_{bootstrap_ts}",
                                "type": "sequence",
                                "actions": [
                                    {"type": "goto", "url": "https://www.anywho.com/", "wait_until": "domcontentloaded", "timeout": 45000},
                                    {"type": "click", "selector": "body", "intent": "prime_structure"},
                                    {"type": "wait", "ms": 300},
                                    {"type": "click", "selector": "body", "intent": "prime_structure_repeat"},
                                ],
                            },
                            {
                                "mission_id": f"prime_enrichment_pivot_{bootstrap_ts}",
                                "type": "sequence",
                                "actions": [
                                    {
                                        "type": "enrichment_pivot",
                                        "lead_data": {
                                            "full_name": "John Doe",
                                            "source": "linkedin",
                                            "profile_url": "https://www.linkedin.com/in/john-doe"
                                        },
                                    }
                                ],
                            },
                            ]
                            await asyncio.to_thread(
                                r.rpush,
                                mission_queue,
                                *[json.dumps(m) for m in prime_missions],
                            )
                except Exception:
                    pass

            item = await asyncio.to_thread(r.brpop, mission_queue, timeout=10)
            if not item:
                continue

            missions_since_coffee += 1
            if missions_since_coffee >= coffee_at:
                break_sec = random.randint(60, 180)
                logger.info(f"☕ Coffee break: {break_sec}s (after {missions_since_coffee} missions)")
                await asyncio.sleep(break_sec)
                missions_since_coffee = 0
                coffee_at = random.randint(50, 100)

            _, payload = item
            try:
                mission = json.loads(payload)
            except Exception:
                mission = {"mission_id": f"mission_{int(time.time())}", "type": "noop"}

            mission_id = mission.get("mission_id") or mission.get("missionId") or mission.get("id") or f"mission_{int(time.time())}"

            # Safety Switch: do not start mission if SYSTEM_STATE:PAUSED (e.g. Capsolver <$1, VLM latency >10s)
            if r.get("SYSTEM_STATE:PAUSED"):
                await asyncio.to_thread(r.lpush, mission_queue, payload)
                logger.warning("SYSTEM_STATE:PAUSED set; re-queued mission and sleeping 30s")
                await asyncio.sleep(30)
                continue

            # Required signature (Phase 8)
            logger.info(
                f"[ChimeraCore] mission consumed: id={mission_id} instruction={mission.get('instruction')} target_provider={mission.get('target_provider')}"
            )

            if not workers:
                continue

            worker = workers[rr % len(workers)]
            rr += 1

            try:
                await worker.rotate_hardware_identity(
                    mission_id=str(mission_id),
                    carrier=mission.get("carrier"),
                )
            except Exception:
                pass

            # Phase 5: fatigue curve (jitter multiplier) for DiffusionMouse and _fatigue_delay
            try:
                _, jitter_mult, _ = worker.next_fatigue_state()
                set_fatigue_jitter_multiplier(jitter_mult)
            except Exception:
                pass

            mission_timeout = int(os.getenv("MISSION_TIMEOUT_SEC", "90"))
            try:
                logger.info(f"[ChimeraCore] executing: instruction={mission.get('instruction')} mission_id={mission_id} timeout={mission_timeout}s")
                result = await asyncio.wait_for(worker.execute_mission(mission), timeout=mission_timeout)
                if mission.get("instruction") == "deep_search" and mission_id:
                    key = f"chimera:results:{mission_id}"
                    try:
                        await asyncio.to_thread(r.lpush, key, json.dumps(result))
                        logger.info(f"[ChimeraCore] LPUSH {key} status={result.get('status', 'completed')} — Scrapegoat BRPOP will receive")
                    except Exception as e:
                        logger.warning(f"LPUSH chimera:results failed: {e}")
                    if os.getenv("BRAINSCRAPER_URL"):
                        try:
                            from telemetry_client import TelemetryClient
                            tc = TelemetryClient()
                            screenshot = await worker.take_screenshot()
                            await asyncio.to_thread(
                                tc.push,
                                mission_id=mission_id,
                                screenshot=screenshot,
                                vision_confidence=result.get("vision_confidence"),
                                status="completed" if result.get("status") != "failed" else "failed",
                                coordinate_drift=getattr(worker, "_last_coordinate_drift", None),
                                grounding_bbox=getattr(worker, "_last_grounding_bbox", None),
                            )
                        except Exception as te:
                            logger.debug("Telemetry push skipped: %s", te)
                # All missions: update mission:{id} so v2-pilot Mission Log and mission-status show correct status
                try:
                    key = f"mission:{mission_id}"
                    updates = {"status": result.get("status", "completed")}
                    if result.get("trauma_signals"):
                        updates["trauma_signals"] = json.dumps(result.get("trauma_signals") if isinstance(result.get("trauma_signals"), list) else [result.get("trauma_signals")])
                    if result.get("trauma_details"):
                        updates["trauma_details"] = str(result.get("trauma_details", ""))[:500]
                    elif result.get("error"):
                        updates["trauma_details"] = str(result.get("error", ""))[:500]
                    if updates:
                        await asyncio.to_thread(r.hset, key, mapping=updates)
                        await asyncio.to_thread(r.expire, key, 86400)
                except Exception:
                    pass
            except asyncio.TimeoutError:
                logger.warning(f"[ChimeraCore] mission timeout after {mission_timeout}s: mission_id={mission_id} — LPUSH failed so Scrapegoat BRPOP will not hang")
                if mission.get("instruction") == "deep_search" and mission_id:
                    key = f"chimera:results:{mission_id}"
                    try:
                        await asyncio.to_thread(
                            r.lpush, key,
                            json.dumps({"status": "failed", "error": f"mission_timeout_{mission_timeout}s", "mission_id": mission_id}),
                        )
                    except Exception as lerr:
                        logger.warning(f"LPUSH {key} on timeout failed: {lerr}")
                try:
                    await asyncio.to_thread(r.hset, f"mission:{mission_id}", mapping={
                        "status": "timeout", "trauma_signals": json.dumps(["MISSION_TIMEOUT"]),
                        "trauma_details": f"mission_timeout_{mission_timeout}s",
                    })
                    await asyncio.to_thread(r.expire, f"mission:{mission_id}", 86400)
                except Exception:
                    pass
                continue
            except Exception as e:
                logger.error(f"[ChimeraCore] mission execution failed: mission_id={mission_id} error={e}")
                if mission.get("instruction") == "deep_search" and mission_id:
                    key = f"chimera:results:{mission_id}"
                    try:
                        await asyncio.to_thread(
                            r.lpush, key,
                            json.dumps({"status": "failed", "error": str(e), "mission_id": mission_id}),
                        )
                        logger.info(f"[ChimeraCore] LPUSH {key} failed payload — Scrapegoat BRPOP will not hang")
                    except Exception as lerr:
                        logger.warning(f"[ChimeraCore] LPUSH {key} failed: {lerr} — Scrapegoat may BRPOP timeout")
                    if os.getenv("BRAINSCRAPER_URL"):
                        try:
                            from telemetry_client import TelemetryClient
                            tc = TelemetryClient()
                            await asyncio.to_thread(
                                tc.push,
                                mission_id=mission_id,
                                status="failed",
                                trauma_signals=["CHIMERA_FAILED"],
                                trauma_details=str(e)[:500],
                                coordinate_drift=getattr(worker, "_last_coordinate_drift", None),
                                grounding_bbox=getattr(worker, "_last_grounding_bbox", None),
                            )
                        except Exception as te:
                            logger.debug("Telemetry push (fail) skipped: %s", te)
                # On exception: update mission:{id} status=failed so Mission Log is correct
                try:
                    key = f"mission:{mission_id}"
                    await asyncio.to_thread(r.hset, key, mapping={
                        "status": "failed",
                        "trauma_signals": json.dumps(["CHIMERA_FAILED"]),
                        "trauma_details": str(e)[:500],
                    })
                    await asyncio.to_thread(r.expire, key, 86400)
                except Exception:
                    pass
                try:
                    await asyncio.to_thread(r.lpush, mission_dlq, payload)
                except Exception:
                    pass
    except KeyboardInterrupt:
        logger.info("Shutting down worker swarm")


async def main_async():
    """Async main entry point"""
    logger.info("🦾 Chimera Core - The Body - Starting...")
    logger.info("   Version: Python 3.12")
    
    # Get environment variables
    health_port = int(os.getenv("PORT", "8080"))
    brain_address = os.getenv("CHIMERA_BRAIN_ADDRESS", "http://chimera-brain.railway.internal:50051")
    railway_env = os.getenv("RAILWAY_ENVIRONMENT", "development")
    num_workers = int(os.getenv("NUM_WORKERS", "1"))
    
    logger.info(f"   Environment: {railway_env}")
    logger.info(f"   Brain Address: {brain_address}")
    logger.info(f"   Workers: {num_workers}")
    
    # Phase 2: Test PostgreSQL connection (MANDATORY - No memory = No excellence)
    # Worker MUST exit if database connection fails
    logger.info("🗄️ Testing PostgreSQL Persistence Layer connection...")
    db_connected = test_db_connection()
    if not db_connected:
        logger.critical("❌ CRITICAL: PostgreSQL connection failed - No memory = No excellence")
        logger.critical("   EXITING WITH CODE 1 - Worker cannot operate without persistence")
        sys.exit(1)
    logger.info(f"✅ [{_LOG_ROLE}] PostgreSQL Persistence Layer verified - Worker approved for deployment")
    
    # Start health check server (Railway requirement)
    start_health_server(health_port)
    
    # Initialize worker swarm
    try:
        workers = await initialize_worker_swarm(num_workers, brain_address)
        
        if workers:
            logger.info("✅ Chimera Core worker swarm started")
            logger.info("   - Health Server: Active")
            logger.info(f"   - Brain Connection: {'Connected' if workers[0]._brain_client else 'Not available'}")
            logger.info(f"   - Workers: {len(workers)} active")
            
            # Run worker swarm
            await run_worker_swarm(workers)
        else:
            logger.error("❌ Failed to initialize workers")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Failed to start worker swarm: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point for Chimera Core worker"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Shutting down Chimera Core worker")
        sys.exit(0)


if __name__ == "__main__":
    main()
# Build: 1768707112
# Final Build: 1768707437
# Final Build: 1768708137
# Vanguard Build: 1768708626
# Vanguard Verified: 1768708728
# Vanguard Evolution: 1768709598
# Vanguard Deployment v4.1: 2026-01-18T06:01Z
# Vanguard Build: 1768712438
# Vanguard Fix: 1768713093
# Vanguard Core Stabilize: 1768714004
# Vanguard Identity Lock: 1768715000
# Vanguard Phase 6: 1768715521
# Vanguard Phase 7: 1768716038
# Vanguard Phase 7: 1768716209
# Vanguard Phase 7: 1768716409
# Vanguard Phase 8: 1768717887
# Vanguard Phase 8: 1768718184
# Vanguard Phase 8: 1768718612
# Vanguard Phase 9: 1768719408
# Vanguard Apex v1.0: 1768720124
# Vanguard v2.0 Ghost: 1768720585
# Vanguard v2.0 Ghost: 1768720724
# Vanguard v7.0 Enrichment: 1768722226
# Vanguard v7.0 Enrichment: 1768722503
# Vanguard v7.0 Enrichment: 1768722965
# Vanguard v7.0 Enrichment: 1768723242
