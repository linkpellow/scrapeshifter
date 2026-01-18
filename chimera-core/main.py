#!/usr/bin/env python3
# Cache Breaker: 2026-01-18 02:45:00 UTC - Phase 1 Biological Signature Restoration
# Phase 3 Verification: 2026-01-18 03:15:00 UTC - Isomorphic Intelligence & Self-Healing
"""
Chimera Core - The Body (Python Worker)

Python 3.12 worker service that connects to The Brain via gRPC.
Stealth browser automation swarm achieving 100% Human trust score on CreepJS.
"""

import os
import sys
import asyncio
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

from workers import PhantomWorker
from validation import validate_creepjs, validate_stealth_quick
from db_bridge import test_db_connection, log_mission_result, record_stealth_check

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        logger.info(f"🏥 Health check server started on 0.0.0.0:{port}")
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
    
    return workers


async def run_worker_swarm(workers: list):
    """
    Run worker swarm - process missions and maintain connections.
    
    TODO: Add Redis queue processing for missions
    """
    logger.info(f"🚀 Worker swarm active ({len(workers)} workers)")
    
    # BLOCKING GATE: Validate stealth on first worker using CreepJS
    # If validation fails (score < 100%), validate_creepjs will exit with code 1
    if workers and workers[0]._page:
        logger.info("🔍 Running CreepJS validation on first worker...")
        logger.info("   BLOCKING GATE: Worker will exit if trust score < 100%")
        
        try:
            # Phase 4: Start tracing for validation mission
            trace_url = None
            await workers[0].start_tracing(mission_id="creepjs_validation")
            
            # VANGUARD: Cognitive Load Latency - Adjust delay based on DOM complexity
            # Higher complexity = higher processing delay (simulates human cognitive load)
            try:
                element_count = await workers[0]._page.evaluate("() => document.querySelectorAll('*').length")
                # Base delay: 100ms, additional delay: 1ms per 10 elements (max 500ms)
                cognitive_delay = min(0.1 + (element_count / 10) * 0.001, 0.5)
                logger.debug(f"   Cognitive load: {element_count} elements → {cognitive_delay*1000:.1f}ms delay")
                await asyncio.sleep(cognitive_delay)
            except Exception as e:
                logger.debug(f"   Cognitive load calculation failed: {e}")
                await asyncio.sleep(0.1)  # Default delay
            
            result = await validate_creepjs(workers[0]._page)
            
            # Stop tracing and upload
            trace_url = await workers[0].stop_tracing(mission_id="creepjs_validation")
            if trace_url:
                logger.info(f"✅ Trace uploaded: {trace_url}")
            
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
    
    # Keep workers alive and process missions
    try:
        while True:
            # TODO: Process Redis queue for missions
            # For now, just keep workers alive
            await asyncio.sleep(60)
            logger.debug("Worker swarm heartbeat...")
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
    logger.info("✅ PostgreSQL Persistence Layer verified - Worker approved for deployment")
    
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
