"""
Redis Queue Worker
Processes leads from leads_to_enrich queue and enriches them.

Pipeline (routes.json) includes ChimeraStation, which pushes to chimera:missions.
Chimera Core consumes chimera:missions and runs Body+Brain (VLM, people-search);
results come back to chimera:results:{id}. So leads_to_enrich and chimera:missions
are bridged: queue-based enrichment uses the full AI stack.

- Contract-based stations (prerequisites)
- Stop conditions (early termination)
- Budget management (auto stop-loss)
- Full cost tracking
"""
import redis
import json
import os
import time
import sys
import asyncio
import threading
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

# Import new pipeline engine
from app.pipeline.loader import create_pipeline, get_default_pipeline_name
from app.pipeline.types import StopCondition

# Configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # Base delay in seconds (exponential backoff)
QUEUE_NAME = "leads_to_enrich"
FAILED_QUEUE_NAME = "failed_leads"

# Pipeline configuration
PIPELINE_NAME = os.getenv("PIPELINE_NAME", None)  # None = use default from routes.json
BUDGET_LIMIT = float(os.getenv("PIPELINE_BUDGET_LIMIT", "5.0"))  # Override budget limit

def get_redis_client() -> redis.Redis:
    """Get Redis client connection"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(redis_url)

# Global pipeline engine (initialized once)
_pipeline_engine = None

def get_pipeline_engine():
    """Get or create pipeline engine (singleton)"""
    global _pipeline_engine
    if _pipeline_engine is None:
        pipeline_name = PIPELINE_NAME or get_default_pipeline_name()
        logger.info(f"🚀 Initializing pipeline: {pipeline_name}")
        _pipeline_engine = create_pipeline(
            pipeline_name=pipeline_name,
            budget_override=BUDGET_LIMIT if BUDGET_LIMIT != 5.0 else None
        )
        logger.info(_pipeline_engine.visualize_route())
    return _pipeline_engine


async def process_lead_async(lead_data: Dict[str, Any]) -> bool:
    """
    Process a single lead through the Production-Grade Pipeline Engine
    
    Uses contract-based stations with:
    - Prerequisites (automatic validation)
    - Stop conditions (early termination)
    - Budget management (auto stop-loss)
    - Full cost tracking
    
    Args:
        lead_data: Lead data from Redis queue
        
    Returns:
        True if successful, False if failed or rejected
    """
    try:
        lead_name = lead_data.get('name', 'Unknown')
        linkedin_url = lead_data.get('linkedinUrl', '')
        logger.info(f"🔄 Processing lead: {lead_name} ({linkedin_url})")
        
        # Get pipeline engine
        engine = get_pipeline_engine()
        
        # Run pipeline
        enriched_data = await engine.run(lead_data)
        
        # Check if lead was saved (DatabaseSaveStation sets "saved": True)
        if enriched_data.get('saved'):
            logger.success(f"✅ Lead '{lead_name}' fully enriched and saved (cost: ${enriched_data.get('_pipeline_cost', 0):.4f})")
            return True
        else:
            # Check if we have a phone but didn't save (might be DNC or invalid)
            if enriched_data.get('phone'):
                logger.warning(f"⚠️  Lead '{lead_name}' enriched but not saved (likely DNC or invalid phone)")
            else:
                logger.warning(f"⚠️  Lead '{lead_name}' failed enrichment (no phone found)")
            return False
        
    except Exception as e:
        logger.error(f"❌ Error processing lead: {e}")
        import traceback
        traceback.print_exc()
        return False


async def process_lead_async_with_steps(
    lead_data: Dict[str, Any],
    log_buffer: Optional[List[str]] = None,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Like process_lead_async but returns (success, steps) for diagnostic logs.
    log_buffer: if provided, engine adds recent_logs to failed steps for where/why."""
    steps: List[Dict[str, Any]] = []
    try:
        engine = get_pipeline_engine()
        enriched_data = await engine.run(lead_data, step_collector=steps, log_buffer=log_buffer)
        success = bool(enriched_data.get('saved'))
        return (success, steps)
    except Exception as e:
        logger.exception(f"❌ Error processing lead: {e}")
        return (False, steps)


def process_lead_with_steps(lead_data: Dict[str, Any], log_buffer: Optional[List[str]] = None) -> Tuple[bool, List[Dict[str, Any]]]:
    """Sync wrapper for process_lead_async_with_steps. Returns (success, steps).
    If log_buffer is provided, all loguru output during the run is appended (thread-scoped).
    Used by /worker/process-one so Download logs gets every log from the pipeline."""
    log_id = None
    if log_buffer is not None:
        capture_thread = threading.current_thread()
        def _sink(m: str) -> None:
            if threading.current_thread() == capture_thread:
                log_buffer.append(m)
        log_id = logger.add(_sink, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(process_lead_async_with_steps(lead_data, log_buffer))
        finally:
            loop.close()
    except Exception as e:
        logger.exception(f"❌ Pipeline execution error: {e}")
        return (False, [])
    finally:
        if log_id is not None:
            logger.remove(log_id)


def process_lead(lead_data: Dict[str, Any]) -> bool:
    """
    Synchronous wrapper for async pipeline processing
    
    Args:
        lead_data: Lead data from Redis queue
        
    Returns:
        True if successful, False if failed or rejected
    """
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(process_lead_async(lead_data))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"❌ Pipeline execution error: {e}")
        return False

def worker_loop():
    """
    Main worker loop that continuously polls Redis queue
    """
    print("=" * 60)
    print("🚀 Scrapegoat Redis Queue Worker (Production-Grade Pipeline Engine)")
    print("=" * 60)
    
    # Get Redis connection
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        print(f"✅ Connected to Redis: {redis_url[:30]}..." if len(redis_url) > 30 else f"✅ Connected to Redis: {redis_url}")
    except Exception as e:
        print(f"❌ Failed to connect to Redis: {e}")
        sys.exit(1)
    
    # Initialize pipeline engine (will print route visualization)
    try:
        engine = get_pipeline_engine()
        print()
    except Exception as e:
        print(f"❌ Failed to initialize pipeline: {e}")
        sys.exit(1)
    
    print(f"📥 Listening on queue: {QUEUE_NAME}")
    print(f"📤 Failed leads queue: {FAILED_QUEUE_NAME}")
    print(f"🔄 Max retries per lead: {MAX_RETRIES}")
    print(f"💰 Budget limit: ${BUDGET_LIMIT:.2f} per lead")
    print("=" * 60)
    print()
    
    # Worker loop
    retry_count = {}
    
    while True:
        try:
            # Blocking pop from queue (timeout: 10 seconds)
            result = redis_client.brpop(QUEUE_NAME, timeout=10)
            
            if result:
                queue_name, lead_json = result
                
                try:
                    # Parse lead data
                    lead_data = json.loads(lead_json)
                    lead_id = lead_data.get('linkedinUrl') or lead_data.get('name', 'unknown')
                    
                    # Process lead
                    success = process_lead(lead_data)
                    
                    if success:
                        # Reset retry count on success
                        if lead_id in retry_count:
                            del retry_count[lead_id]
                        print(f"✅ Lead '{lead_id}' processed successfully\n")
                    else:
                        # Increment retry count
                        retry_count[lead_id] = retry_count.get(lead_id, 0) + 1
                        
                        if retry_count[lead_id] >= MAX_RETRIES:
                            # Move to failed queue
                            print(f"❌ Lead '{lead_id}' failed {MAX_RETRIES} times, moving to DLQ")
                            redis_client.lpush(FAILED_QUEUE_NAME, lead_json)
                            del retry_count[lead_id]
                        else:
                            # Re-queue for retry
                            delay = RETRY_DELAY_BASE * (2 ** (retry_count[lead_id] - 1))
                            print(f"⏳ Retrying lead '{lead_id}' in {delay} seconds (attempt {retry_count[lead_id]}/{MAX_RETRIES})")
                            time.sleep(delay)
                            redis_client.lpush(QUEUE_NAME, lead_json)
                            
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse lead JSON: {e}")
                    print(f"📤 Moving invalid JSON to failed queue")
                    redis_client.lpush(FAILED_QUEUE_NAME, lead_json)
                except Exception as e:
                    print(f"❌ Unexpected error processing lead: {e}")
                    import traceback
                    traceback.print_exc()
                    # Move to failed queue on unexpected errors
                    redis_client.lpush(FAILED_QUEUE_NAME, lead_json)
            
            else:
                # Timeout - no leads in queue
                # Print status every 60 seconds
                if int(time.time()) % 60 == 0:
                    queue_length = redis_client.llen(QUEUE_NAME)
                    failed_length = redis_client.llen(FAILED_QUEUE_NAME)
                    print(f"💤 Waiting for leads... (Queue: {queue_length}, Failed: {failed_length})")
                
        except redis.ConnectionError as e:
            print(f"❌ Redis connection error: {e}")
            print(f"⏳ Retrying connection in {RETRY_DELAY_BASE} seconds...")
            time.sleep(RETRY_DELAY_BASE)
            
            # Reconnect
            try:
                redis_client = get_redis_client()
                redis_client.ping()
                print("✅ Reconnected to Redis")
            except:
                print("❌ Failed to reconnect, will retry...")
                
        except KeyboardInterrupt:
            print("\n🛑 Received interrupt signal, shutting down gracefully...")
            break
        except Exception as e:
            print(f"❌ Unexpected error in worker loop: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)  # Brief pause before retrying
    
    print("✅ Worker stopped")

if __name__ == "__main__":
    worker_loop()
