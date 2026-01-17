#!/usr/bin/env python3
"""
Scrapegoat Unified Worker (Tri-Core)
Runs Enrichment, Spider Execution, AND Auth Maintenance in parallel.
# Cache invalidation: 2026-01-17 23:10 - Force Railway rebuild for worker-swarm

Workers:
  - Enrichment Worker (Factory): Listens to 'leads_to_enrich' queue, runs 6-stage pipeline
  - Spider Worker (Driver): Listens to 'spider_jobs' queue, executes generated spiders
  - Auth Worker (Keymaster): Refreshes USHA DNC tokens every 4 hours

Architecture:
  - LinkedIn: Uses RapidAPI (auth handled by them - no credentials needed)
  - USHA DNC: Native automation (Auth Worker manages session tokens)

Usage:
    python start_redis_worker.py

Environment Variables:
    REDIS_URL: Redis connection URL
    DATABASE_URL: PostgreSQL connection URL
    SPIDER_FORWARD_TO_ENRICHMENT: Set to "true" to auto-forward spider results
    USHA_EMAIL / USHA_PASSWORD: For Auth Worker to refresh USHA DNC tokens
    AUTH_REFRESH_INTERVAL_HOURS: Hours between token refreshes (default: 4)
"""
import os
import sys
import threading
import time
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set default environment
os.environ.setdefault("PYTHONUNBUFFERED", "1")

from loguru import logger

# Import workers
try:
    from app.workers.redis_queue_worker import worker_loop as enrichment_loop
    from app.workers.spider_worker import start_worker as spider_loop
    from app.workers.auth_worker import start_auth_loop as auth_loop
    from init_db import init_db
except ImportError as e:
    logger.error(f"❌ Failed to import workers: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


def start_enrichment_thread():
    """Runs the lead enrichment pipeline"""
    logger.info("🏭 Starting Enrichment Factory...")
    try:
        enrichment_loop()
    except Exception as e:
        logger.exception(f"💥 Enrichment Factory Crashed: {e}")


def start_spider_thread():
    """Runs the spider execution engine"""
    logger.info("🕷️ Starting Spider Driver...")
    try:
        spider_loop()
    except Exception as e:
        logger.exception(f"💥 Spider Driver Crashed: {e}")


def start_auth_thread():
    """Runs the authentication cookie harvester"""
    logger.info("🔐 Starting Auth Keymaster...")
    try:
        auth_loop()
    except Exception as e:
        logger.exception(f"💥 Auth Keymaster Crashed: {e}")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 SCRAPEGOAT TRI-CORE SYSTEM")
    logger.info("=" * 60)
    logger.info(f"📝 Environment: {os.getenv('ENVIRONMENT', 'production')}")
    logger.info(f"📡 Redis: {os.getenv('REDIS_URL', 'redis://localhost:6379')[:40]}...")
    logger.info(f"🗄️ Database: {os.getenv('DATABASE_URL', 'not set')[:40]}...")
    logger.info("=" * 60)
    
    # 0. Initialize Database
    logger.info("🗄️ Initializing database schema...")
    init_db()
    
    # 1. Start Enrichment Worker (The Factory)
    enrichment_thread = threading.Thread(
        target=start_enrichment_thread, 
        daemon=True,
        name="EnrichmentFactory"
    )
    enrichment_thread.start()
    
    # Small delay to stagger startup
    time.sleep(0.5)
    
    # 2. Start Spider Worker (The Driver)
    spider_thread = threading.Thread(
        target=start_spider_thread, 
        daemon=True,
        name="SpiderDriver"
    )
    spider_thread.start()
    
    # Small delay to stagger startup
    time.sleep(0.5)
    
    # 3. Start Auth Worker (The Keymaster)
    auth_thread = threading.Thread(
        target=start_auth_thread, 
        daemon=True,
        name="AuthKeymaster"
    )
    auth_thread.start()
    
    logger.success("✅ All Systems Operational: [Factory] [Driver] [Keymaster]")
    logger.info("   🏭 Enrichment Factory: leads_to_enrich queue")
    logger.info("   🕷️ Spider Driver: spider_jobs queue")
    logger.info("   🔐 Auth Keymaster: USHA token refresh every 4h")
    logger.info("=" * 60)
    
    # Keep the main process alive and monitor threads
    try:
        while True:
            time.sleep(5)
            
            # Check if threads are alive and restart if needed
            if not enrichment_thread.is_alive():
                logger.warning("⚠️ Enrichment thread died! Restarting...")
                enrichment_thread = threading.Thread(
                    target=start_enrichment_thread, 
                    daemon=True,
                    name="EnrichmentFactory"
                )
                enrichment_thread.start()
            
            if not spider_thread.is_alive():
                logger.warning("⚠️ Spider thread died! Restarting...")
                spider_thread = threading.Thread(
                    target=start_spider_thread, 
                    daemon=True,
                    name="SpiderDriver"
                )
                spider_thread.start()
            
            if not auth_thread.is_alive():
                logger.warning("⚠️ Auth thread died! Restarting...")
                auth_thread = threading.Thread(
                    target=start_auth_thread, 
                    daemon=True,
                    name="AuthKeymaster"
                )
                auth_thread.start()
                
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down workers...")
        logger.info("👋 Goodbye!")
