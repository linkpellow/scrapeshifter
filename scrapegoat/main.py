"""
Scrapegoat: AI-Powered Lead Enrichment Worker Swarm
Consumer service that processes leads from Redis queue
# Cache invalidation: 2026-01-17 23:15 - Force Railway rebuild for scrapegoat service
# Force build: 2026-01-17-v1
"""

# Critical: Print immediately to verify script is executing
print("🔧 [STARTUP] Script started", flush=True)

import sys
import os
import traceback

# Flush output immediately for Railway logs
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    # Python < 3.7 or reconfigure not available, use flush instead
    pass

print("🔧 [STARTUP] Loading Scrapegoat module...", flush=True)

try:
    from fastapi import FastAPI, HTTPException, Request, Body
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    import redis
    # Handling redis-py version differences for search index definition (snake_case vs camelCase)
    try:
        from redis.commands.search.index_definition import IndexDefinition, IndexType  # type: ignore
    except ImportError:
        try:
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType  # type: ignore
        except ImportError:
            IndexDefinition = None  # type: ignore
            IndexType = None  # type: ignore
    import asyncio
    import json
    import queue
    import time
    import uuid
    from contextlib import asynccontextmanager
    from typing import Dict, Any, Optional
    from loguru import logger
    logger.info("[STARTUP] Core imports successful")
except ImportError as e:
    print(f"❌ [STARTUP] Import error: {e}", flush=True)  # logger not yet available
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Redis connection - lazy initialization to prevent startup failures
redis_url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
logger.info("Redis URL configured: %s...", redis_url[:50] if len(redis_url) > 50 else redis_url)

_redis_client = None

def get_redis():
    """Get or create Redis client (lazy initialization)"""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(redis_url)
            _redis_client.ping()  # Test connection
            print("✅ Redis connected successfully")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            _redis_client = redis.from_url(redis_url)  # Create anyway for later retry
    return _redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure leads and site_blueprints exist (idempotent). Seed Magazine blueprints when SEED_MAGAZINE_ON_STARTUP=1."""
    try:
        from init_db import init_db
        init_db()
    except Exception as e:
        logger.warning("init_db at startup (non-fatal): %s", e)

    if os.getenv("SEED_MAGAZINE_ON_STARTUP") == "1":
        try:
            r = get_redis()
            if r:
                from app.enrichment.blueprint_commit import commit_blueprint_impl
                _mag = [
                    ("fastpeoplesearch.com", {"targetUrl": "https://www.fastpeoplesearch.com/", "name_selector": "input#name-search", "result_selector": "div.search-item", "extraction": {}}),
                    ("truepeoplesearch.com", {"targetUrl": "https://www.truepeoplesearch.com/", "name_selector": "input#search-name", "result_selector": "div.card-summary", "extraction": {}}),
                    ("zabasearch.com", {"targetUrl": "https://www.zabasearch.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
                    ("searchpeoplefree.com", {"targetUrl": "https://www.searchpeoplefree.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
                    ("thatsthem.com", {"targetUrl": "https://thatsthem.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
                    ("anywho.com", {"targetUrl": "https://www.anywho.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
                ]
                for domain, bp in _mag:
                    try:
                        commit_blueprint_impl(domain, bp, r)
                        logger.info("Seed-magazine on startup: %s", domain)
                    except Exception as e:
                        logger.warning("Seed-magazine on startup %s: %s", domain, e)
                logger.info("Seed-magazine on startup: done (6 Magazine domains)")
        except Exception as e:
            logger.warning("Seed-magazine on startup (non-fatal): %s", e)
    yield
    # shutdown: nothing to do

app = FastAPI(
    title="Scrapegoat API",
    description="AI-powered lead enrichment worker swarm",
    version="1.0.1",  # Bumped to trigger Railway deployment
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Scrapegoat AI Enrichment Swarm Active", "status": "online"}

@app.get("/health")
async def health():
    """Health check endpoint - returns 200 immediately for Railway healthchecks"""
    # Return immediately - don't block on Redis checks for healthcheck
    # Railway just needs to know the service is responding
    return {
        "status": "healthy",
        "service": "scrapegoat",
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }

@app.get("/skip-tracing/health")
async def skip_tracing_health():
    """Skip tracing health endpoint (for Railway compatibility)"""
    return await health()

@app.get("/queue/status")
async def queue_status():
    """Get Redis queue status"""
    try:
        leads_queue_length = get_redis().llen("leads_to_enrich")
        failed_queue_length = get_redis().llen("failed_leads")

        return {
            "leads_to_enrich": leads_queue_length,
            "failed_leads": failed_queue_length,
            "status": "active"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Queue status check failed: {str(e)}")


# Probe: which people-search site returns a reachable, non-blocked page (HTTP/stealth)
PROBE_URLS = {
    "fastpeoplesearch.com": "https://www.fastpeoplesearch.com/",
    "thatsthem.com": "https://thatsthem.com/",
    "truepeoplesearch.com": "https://www.truepeoplesearch.com/",
}
_PROBE_BLOCK = ["access denied", "blocked", "forbidden", "cloudflare", "checking your browser", "please enable javascript", "captcha", "rate limit", "too many requests"]
_PROBE_SUCCESS = ["people", "search", "find", "name", "address", "phone", "email"]


@app.get("/probe/sites")
async def probe_sites(site: Optional[str] = None):
    """Probe people-search sites (HTTP/stealth). Returns per site: ok, block, empty, client_error, timeout.
    ?site=fastpeoplesearch.com to probe one. Use to see which site will actually work."""
    from app.scraping.base import BaseScraper

    to_probe = [site] if (site and site in PROBE_URLS) else list(PROBE_URLS.keys())
    out: Dict[str, str] = {}
    for s in to_probe:
        url = PROBE_URLS[s]
        try:
            async with BaseScraper(stealth=True, timeout=15, max_retries=1) as scraper:
                r = await scraper.get(url)
            text = (r or {}).get("text") or ""
            status = int((r or {}).get("status") or 0)
            if status >= 400:
                out[s] = f"http_{status}"
                await asyncio.sleep(2)
                continue
        except Exception as e:
            msg = str(e).lower()
            if "impersonate" in msg or "not supported" in msg:
                out[s] = "client_error"
            elif "timeout" in msg or "timed out" in msg:
                out[s] = "timeout"
            else:
                out[s] = "client_error"
            await asyncio.sleep(2)
            continue

        low = text.lower()
        if any(b in low for b in _PROBE_BLOCK):
            out[s] = "block"
        elif any(k in low for k in _PROBE_SUCCESS):
            out[s] = "ok"
        else:
            out[s] = "empty"
        await asyncio.sleep(2)
    return out


@app.post("/worker/process-lead")
async def process_lead(lead_data: Dict[str, Any]):
    """Manually trigger lead processing (for testing)"""
    try:
        # Add lead to Redis queue
        get_redis().lpush("leads_to_enrich", json.dumps(lead_data))

        return {
            "status": "queued",
            "lead_id": lead_data.get("id", "unknown"),
            "message": "Lead added to enrichment queue"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue lead: {str(e)}")


@app.post("/worker/process-one")
async def process_one():
    """Pop one lead from leads_to_enrich and run the enrichment pipeline.
    Use to process one on demand when the worker is not running or to 'start' enrichment.
    Returns steps[] and logs[] (every log line from the pipeline) for v2-pilot Download logs.
    Always returns 200 with processed/error so the client avoids 5xx and can show the error."""
    log_buffer: list = []
    steps: list = []
    try:
        r = get_redis()
        result = r.brpop("leads_to_enrich", timeout=1)
        if not result:
            return {"processed": False, "message": "Queue empty", "steps": [], "logs": []}
        _q, raw = result
        lead_json = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        lead_data = json.loads(lead_json)
        from app.workers.redis_queue_worker import process_lead_with_steps
        ok, steps = await asyncio.to_thread(process_lead_with_steps, lead_data, log_buffer)
        return {
            "processed": True,
            "success": ok,
            "name": lead_data.get("name"),
            "linkedin_url": lead_data.get("linkedinUrl"),
            "steps": steps,
            "logs": log_buffer,
        }
    except Exception as e:
        from loguru import logger
        logger.exception("process_one failed: %s", e)
        return {
            "processed": False,
            "success": False,
            "error": str(e),
            "steps": steps,
            "logs": log_buffer,
        }


def _infer_failure(success: bool, steps: list, recent: list) -> tuple:
    """From steps + recent substeps, infer failure_mode, failure_at, hint. Returns (mode, at, hint)."""
    if success:
        return (None, None, "")
    substeps = [e for e in recent if isinstance(e, dict)]
    for ev in reversed(substeps):
        substep = (ev.get("substep") or "").lower()
        detail = (ev.get("detail") or "")[:300]
        station = (ev.get("station") or "").lower()

        if "mapping_required" in substep:
            domain = detail or "unknown"
            return ("MAPPING", "BlueprintLoader", f"Run POST /api/blueprints/seed-magazine or add blueprint for {domain}")
        if "pivot_selector_fail" in substep or "pivot_result_fail" in substep:
            return ("SELECTOR", "ChimeraCore", f"Update name_selector/result_selector for people-search. {detail[:120]}")
        if "capsolver_fail" in substep:
            return ("CAPTCHA", "ChimeraCore", "Check CAPSOLVER_API_KEY and balance; chimera-core logs.")
        if "vlm_fail" in substep or "captcha_fail" in substep:
            return ("CAPTCHA", "ChimeraCore", "VLM or CapSolver failed; Chimera Brain and CAPSOLVER_API_KEY.")
        if substep == "timeout" and "chimera" in station:
            any_captcha = any("captcha" in str(e.get("substep", "")).lower() or "captcha" in str(e.get("detail", "")).lower() for e in substeps)
            return ("CORE_TIMEOUT", "ChimeraCore", "Core 120s timeout. Likely CAPTCHA/slow site; check chimera-core and CapSolver." if any_captcha else "Core 120s timeout. Is chimera-core running and same Redis?")
        if "parse_fail" in substep or "core_failed" in substep or "core_bad_type" in substep:
            return ("CORE_RESULT", "ChimeraStation", f"Core bad/failed result. {detail[:120]}")

    for s in (steps or []):
        if (s.get("status") or "") == "fail":
            st = s.get("station") or "?"
            err = (s.get("error") or "")[:200]
            if "Blueprint" in st:
                return ("MAPPING", st, f"BlueprintLoader failed: {err}. Run /api/blueprints/seed-magazine.")
            if "Chimera" in st:
                return ("CORE", st, f"ChimeraStation failed: {err}. Check Core and Redis.")
            return ("DOWNSTREAM", st, f"{st} failed: {err}")
    return ("UNKNOWN", None, "See Diagnostic and Download logs.")


async def _process_one_stream_gen(lead_data: dict, log_buffer: list):
    """Async generator yielding NDJSON lines: progress events, then {done, success, steps, logs, failure_mode?, failure_at?, hint?}."""
    from app.workers.redis_queue_worker import process_lead_with_steps

    progress_queue = queue.Queue()
    task = asyncio.create_task(asyncio.to_thread(process_lead_with_steps, lead_data, log_buffer, progress_queue))
    # First chunk in <1s so client can fail in 12s if stream never starts
    yield json.dumps({"event": "stream_started", "ts": time.time()}) + "\n"
    recent: list = []
    cap = 100

    while True:
        try:
            ev = progress_queue.get_nowait()
        except queue.Empty:
            if task.done():
                break
            await asyncio.sleep(0.05)
            continue
        recent.append(ev)
        if len(recent) > cap:
            recent.pop(0)
        yield json.dumps(ev) + "\n"

    while True:
        try:
            ev = progress_queue.get_nowait()
            recent.append(ev)
            if len(recent) > cap:
                recent.pop(0)
            yield json.dumps(ev) + "\n"
        except queue.Empty:
            break

    try:
        ok, steps = task.result()
        out = {
            "done": True,
            "processed": True,
            "success": ok,
            "name": lead_data.get("name"),
            "linkedin_url": lead_data.get("linkedinUrl"),
            "steps": steps,
            "logs": log_buffer,
        }
        fm, fa, h = _infer_failure(ok, steps, recent)
        if fm:
            out["failure_mode"] = fm
            out["failure_at"] = fa
            out["hint"] = h
        yield json.dumps(out) + "\n"
    except Exception as e:
        from loguru import logger
        logger.exception("process_one_stream pipeline error: %s", e)
        out = {
            "done": True,
            "processed": True,
            "success": False,
            "error": str(e),
            "error_traceback": traceback.format_exc(),
            "steps": [],
            "logs": log_buffer,
        }
        fm, fa, h = _infer_failure(False, [], recent)
        if fm:
            out["failure_mode"] = fm
            out["failure_at"] = fa
            out["hint"] = h
        yield json.dumps(out) + "\n"


@app.post("/worker/process-one-stream")
async def process_one_stream():
    """Pop one lead, run the pipeline, and stream NDJSON progress events (step, pct, station, status) then {done, success, steps, logs}.
    Clients get a live feed so the UI does not look frozen. Content-Type: application/x-ndjson."""
    try:
        r = get_redis()
        result = r.brpop("leads_to_enrich", timeout=1)
        if not result:
            return StreamingResponse(
                iter([json.dumps({
                    "done": True, "processed": False, "message": "Queue empty",
                    "failure_mode": "EMPTY", "hint": "Queue leads first (Queue CSV) or check REDIS_URL and llens.",
                }) + "\n"]),
                media_type="application/x-ndjson",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        _q, raw = result
        lead_json = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        lead_data = json.loads(lead_json)
        log_buffer = []
        return StreamingResponse(
            _process_one_stream_gen(lead_data, log_buffer),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        from loguru import logger
        logger.exception("process_one_stream failed: %s", e)
        return StreamingResponse(
            iter([json.dumps({
                "done": True, "processed": False, "error": str(e),
                "error_traceback": traceback.format_exc(),
                "failure_mode": "STARTUP", "hint": f"Scrapegoat error before pipeline: {str(e)[:150]}",
            }) + "\n"]),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


async def _background_run(run_id: str, lead_data: dict) -> None:
    """Run pipeline in background, writing progress and result to Redis. No long-lived HTTP."""
    log_buffer = []
    key = f"enrich:run:{run_id}"
    r = get_redis()
    try:
        async for line in _process_one_stream_gen(lead_data, log_buffer):
            # Generator yields NDJSON lines (str); parse to dict for .get() and for progress/result
            try:
                obj = json.loads(line.strip()) if isinstance(line, str) else (line if isinstance(line, dict) else {})
            except Exception:
                obj = {"_raw": line[:500] if isinstance(line, str) else str(line)[:500]}
            r.hset(key, mapping={"progress": json.dumps(obj), "updated_at": str(time.time())})
            r.expire(key, 3600)
            if isinstance(obj, dict) and obj.get("done"):
                r.hset(key, mapping={"status": "done", "result": json.dumps(obj)})
                r.expire(key, 3600)
                return
    except Exception as e:
        logger.exception("_background_run error: %s", e)
        r.hset(key, mapping={"status": "error", "error": str(e)[:2000], "updated_at": str(time.time())})
        r.expire(key, 3600)


@app.post("/worker/process-one-start")
async def process_one_start():
    """Pop one lead, start pipeline in background, return run_id immediately. No long-lived stream.
    Client polls GET /worker/process-one-status?run_id=X until status=done|error.
    Fixes BodyStreamBuffer/AbortError when runs exceed 5–10 min (Chimera 6×90s + overhead)."""
    try:
        r = get_redis()
        result = r.brpop("leads_to_enrich", timeout=1)
        if not result:
            return {
                "done": True,
                "processed": False,
                "message": "Queue empty",
                "failure_mode": "EMPTY",
                "hint": "Queue leads first (Queue CSV) or check REDIS_URL and llens.",
            }
        _q, raw = result
        lead_json = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        lead_data = json.loads(lead_json)
        if not isinstance(lead_data, dict):
            # Queue may contain double-encoded JSON; try once
            if isinstance(lead_data, str):
                try:
                    lead_data = json.loads(lead_data)
                except Exception:
                    pass
            if not isinstance(lead_data, dict):
                return {
                    "done": True,
                    "processed": False,
                    "error": "Lead in queue must be a JSON object (name, linkedinUrl, etc.). Got " + type(lead_data).__name__,
                    "failure_mode": "STARTUP",
                    "hint": "Queue CSV must push objects. Check leads_to_enrich.",
                }
        run_id = str(uuid.uuid4())
        key = f"enrich:run:{run_id}"
        r.hset(key, mapping={"status": "running", "progress": "{}", "created_at": str(time.time())})
        r.expire(key, 3600)
        asyncio.create_task(_background_run(run_id, lead_data))
        return {"run_id": run_id, "status": "started", "message": "Processing"}
    except Exception as e:
        logger.exception("process_one_start failed: %s", e)
        return {
            "done": True,
            "processed": False,
            "error": str(e),
            "failure_mode": "STARTUP",
            "hint": f"Scrapegoat error: {str(e)[:150]}",
        }


def _hgetall_str(redis_client, key: str) -> dict:
    raw = redis_client.hgetall(key) or {}
    return {
        (k.decode("utf-8") if isinstance(k, bytes) else k): (v.decode("utf-8") if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


@app.get("/worker/process-one-status")
async def process_one_status(run_id: str):
    """Poll for run progress and result. status=running|done|error. progress=latest event; result=final when done."""
    r = get_redis()
    key = f"enrich:run:{run_id}"
    data = _hgetall_str(r, key)
    if not data:
        raise HTTPException(status_code=404, detail="Run not found")
    status = data.get("status") or "running"
    try:
        progress = json.loads(data.get("progress") or "{}")
    except Exception:
        progress = {}
    result = None
    if data.get("result"):
        try:
            result = json.loads(data.get("result"))
        except Exception:
            result = {"error": "result parse error"}
    return {"status": status, "progress": progress, "result": result, "error": data.get("error"), "updated_at": data.get("updated_at")}


# ============================================
# DLQ (Dead Letter Queue) Endpoints
# ============================================

@app.get("/dlq")
async def get_dlq(limit: int = 100):
    """Get list of failed leads from DLQ"""
    try:
        # Get failed leads from Redis list
        failed_leads_raw = get_redis().lrange("failed_leads", 0, limit - 1)
        failed_leads = []
        
        for i, item in enumerate(failed_leads_raw):
            try:
                lead_data = json.loads(item)
                failed_leads.append({
                    "index": i,
                    "lead_data": lead_data.get("lead", lead_data),
                    "error": lead_data.get("error", "Unknown error"),
                    "retry_count": lead_data.get("retry_count", 0),
                    "failed_at": lead_data.get("failed_at", "Unknown"),
                })
            except json.JSONDecodeError:
                failed_leads.append({
                    "index": i,
                    "lead_data": {"raw": str(item)},
                    "error": "Failed to parse lead data",
                    "retry_count": 0,
                    "failed_at": "Unknown",
                })
        
        total = get_redis().llen("failed_leads")
        
        return {
            "failed_leads": failed_leads,
            "total": total
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch DLQ: {str(e)}")

@app.post("/dlq/retry/{index}")
async def retry_one(index: int):
    """Retry a single failed lead by index"""
    try:
        # Get the failed lead at the specified index
        failed_leads_raw = get_redis().lrange("failed_leads", index, index)
        
        if not failed_leads_raw:
            raise HTTPException(status_code=404, detail=f"No lead found at index {index}")
        
        lead_raw = failed_leads_raw[0]
        
        try:
            lead_data = json.loads(lead_raw)
            # Extract the original lead data
            original_lead = lead_data.get("lead", lead_data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Failed to parse lead data")
        
        # Re-queue the lead for processing
        get_redis().lpush("leads_to_enrich", json.dumps(original_lead))
        
        # Remove from DLQ (set to a marker value, then remove)
        # Note: Redis doesn't have direct index-based removal, so we use LSET + LREM
        marker = "__REMOVED__"
        get_redis().lset("failed_leads", index, marker)
        get_redis().lrem("failed_leads", 1, marker)
        
        return {
            "success": True,
            "message": f"Lead at index {index} re-queued for processing",
            "retried_count": 1
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry lead: {str(e)}")

@app.post("/dlq/retry-all")
async def retry_all():
    """Retry all failed leads"""
    try:
        # Get all failed leads
        failed_leads_raw = get_redis().lrange("failed_leads", 0, -1)
        
        if not failed_leads_raw:
            return {
                "success": True,
                "message": "No failed leads to retry",
                "retried_count": 0
            }
        
        retried_count = 0
        
        for lead_raw in failed_leads_raw:
            try:
                lead_data = json.loads(lead_raw)
                original_lead = lead_data.get("lead", lead_data)
                get_redis().lpush("leads_to_enrich", json.dumps(original_lead))
                retried_count += 1
            except (json.JSONDecodeError, Exception):
                # Skip malformed entries
                continue
        
        # Clear the DLQ
        get_redis().delete("failed_leads")
        
        return {
            "success": True,
            "message": f"Re-queued {retried_count} leads for processing",
            "retried_count": retried_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry all leads: {str(e)}")

# ============================================
# Spider Fleet Endpoints
# ============================================

import ast
import importlib.util
from pathlib import Path
from datetime import datetime

SPIDERS_DIR = Path(__file__).parent / "app" / "scraping" / "spiders"

def get_spider_metadata(filepath: Path) -> Dict[str, Any]:
    """Extract metadata from a spider file"""
    try:
        content = filepath.read_text()
        
        # Parse the Python file to extract docstring and class info
        tree = ast.parse(content)
        
        # Get module docstring
        docstring = ast.get_docstring(tree) or "No description available"
        
        # Find spider classes
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name.endswith("Spider"):
                    class_docstring = ast.get_docstring(node) or ""
                    classes.append({
                        "name": node.name,
                        "docstring": class_docstring
                    })
        
        # Get file stats
        stat = filepath.stat()
        
        return {
            "id": filepath.stem,
            "filename": filepath.name,
            "name": filepath.stem.replace("_", " ").title(),
            "description": docstring.split("\n")[0][:200],  # First line, max 200 chars
            "classes": classes,
            "size": stat.st_size,
            "lastModified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "createdAt": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        }
    except Exception as e:
        return {
            "id": filepath.stem,
            "filename": filepath.name,
            "name": filepath.stem.replace("_", " ").title(),
            "description": f"Error parsing: {str(e)}",
            "classes": [],
            "size": 0,
            "lastModified": None,
            "createdAt": None,
        }

@app.get("/spiders")
async def list_spiders():
    """List all available spider files in the spiders directory"""
    try:
        # Ensure directory exists
        SPIDERS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Scan for Python files (excluding __init__.py and __pycache__)
        spider_files = [
            f for f in SPIDERS_DIR.glob("*.py") 
            if f.name != "__init__.py" and not f.name.startswith("_")
        ]
        
        spiders = []
        for spider_file in spider_files:
            metadata = get_spider_metadata(spider_file)
            
            # Get run stats from Redis
            stats_key = f"spider:stats:{metadata['id']}"
            stats_raw = get_redis().hgetall(stats_key)
            
            if stats_raw:
                # Decode Redis bytes
                stats = {k.decode(): v.decode() for k, v in stats_raw.items()}
                metadata["status"] = stats.get("status", "idle")
                metadata["lastRunAt"] = stats.get("lastRunAt")
                metadata["totalLeads"] = int(stats.get("totalLeads", 0))
                metadata["lastError"] = stats.get("lastError")
            else:
                metadata["status"] = "idle"
                metadata["lastRunAt"] = None
                metadata["totalLeads"] = 0
                metadata["lastError"] = None
            
            spiders.append(metadata)
        
        # Sort by last modified (newest first)
        spiders.sort(key=lambda x: x.get("lastModified") or "", reverse=True)
        
        return {
            "spiders": spiders,
            "total": len(spiders),
            "directory": str(SPIDERS_DIR)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list spiders: {str(e)}")

@app.get("/spiders/{spider_id}")
async def get_spider(spider_id: str):
    """Get detailed information about a specific spider"""
    try:
        spider_file = SPIDERS_DIR / f"{spider_id}.py"
        
        if not spider_file.exists():
            raise HTTPException(status_code=404, detail=f"Spider '{spider_id}' not found")
        
        metadata = get_spider_metadata(spider_file)
        
        # Get full source code
        metadata["source"] = spider_file.read_text()
        
        # Get run history from Redis
        history_key = f"spider:history:{spider_id}"
        history_raw = get_redis().lrange(history_key, 0, 19)  # Last 20 runs
        
        history = []
        for item in history_raw:
            try:
                history.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        
        metadata["runHistory"] = history
        
        # Get current stats
        stats_key = f"spider:stats:{spider_id}"
        stats_raw = get_redis().hgetall(stats_key)
        
        if stats_raw:
            stats = {k.decode(): v.decode() for k, v in stats_raw.items()}
            metadata["status"] = stats.get("status", "idle")
            metadata["lastRunAt"] = stats.get("lastRunAt")
            metadata["totalLeads"] = int(stats.get("totalLeads", 0))
            metadata["lastError"] = stats.get("lastError")
        else:
            metadata["status"] = "idle"
            metadata["lastRunAt"] = None
            metadata["totalLeads"] = 0
            metadata["lastError"] = None
        
        return metadata
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get spider: {str(e)}")

@app.post("/spiders/{spider_id}/run")
async def run_spider(spider_id: str, params: Dict[str, Any] = None):
    """Trigger a spider run by adding a job to Redis queue"""
    try:
        spider_file = SPIDERS_DIR / f"{spider_id}.py"
        
        if not spider_file.exists():
            raise HTTPException(status_code=404, detail=f"Spider '{spider_id}' not found")
        
        # Create a spider job
        job = {
            "type": "spider_run",
            "spider_id": spider_id,
            "params": params or {},
            "queued_at": datetime.now().isoformat(),
        }
        
        # Push to spider jobs queue
        get_redis().lpush("spider_jobs", json.dumps(job))
        
        # Update spider status to "running"
        stats_key = f"spider:stats:{spider_id}"
        get_redis().hset(stats_key, "status", "running")
        get_redis().hset(stats_key, "lastRunAt", datetime.now().isoformat())
        
        return {
            "success": True,
            "message": f"Spider '{spider_id}' job queued",
            "jobId": f"{spider_id}_{datetime.now().timestamp()}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run spider: {str(e)}")

@app.get("/spiders/{spider_id}/stats")
async def get_spider_stats(spider_id: str):
    """Get run statistics for a specific spider"""
    try:
        stats_key = f"spider:stats:{spider_id}"
        stats_raw = get_redis().hgetall(stats_key)
        
        if not stats_raw:
            return {
                "spider_id": spider_id,
                "status": "idle",
                "totalRuns": 0,
                "successfulRuns": 0,
                "failedRuns": 0,
                "totalLeads": 0,
                "averageRunTime": 0,
                "lastRunAt": None,
                "lastError": None,
            }
        
        stats = {k.decode(): v.decode() for k, v in stats_raw.items()}
        
        return {
            "spider_id": spider_id,
            "status": stats.get("status", "idle"),
            "totalRuns": int(stats.get("totalRuns", 0)),
            "successfulRuns": int(stats.get("successfulRuns", 0)),
            "failedRuns": int(stats.get("failedRuns", 0)),
            "totalLeads": int(stats.get("totalLeads", 0)),
            "averageRunTime": float(stats.get("averageRunTime", 0)),
            "lastRunAt": stats.get("lastRunAt"),
            "lastError": stats.get("lastError"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get spider stats: {str(e)}")

@app.delete("/spiders/{spider_id}")
async def delete_spider(spider_id: str):
    """Delete a spider file (with safety checks)"""
    try:
        spider_file = SPIDERS_DIR / f"{spider_id}.py"
        
        if not spider_file.exists():
            raise HTTPException(status_code=404, detail=f"Spider '{spider_id}' not found")
        
        # Safety: Only allow deletion of files in spiders directory
        if not spider_file.resolve().is_relative_to(SPIDERS_DIR.resolve()):
            raise HTTPException(status_code=403, detail="Security violation: Path traversal detected")
        
        # Archive the file instead of deleting (move to .archive folder)
        archive_dir = SPIDERS_DIR / ".archive"
        archive_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"{spider_id}_{timestamp}.py"
        spider_file.rename(archive_path)
        
        # Clear Redis stats
        get_redis().delete(f"spider:stats:{spider_id}")
        get_redis().delete(f"spider:history:{spider_id}")
        
        return {
            "success": True,
            "message": f"Spider '{spider_id}' archived",
            "archivedTo": str(archive_path)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete spider: {str(e)}")


# ============================================
# Cookie/Auth Status Endpoints
# ============================================

@app.get("/auth/status")
async def get_auth_status():
    """
    Get status of all stored authentication cookies.
    
    Shows which platforms have fresh cookies and when they were last refreshed.
    """
    try:
        from app.scraping.cookie_store import get_cookie_store
        
        store = get_cookie_store()
        status = await store.get_all_status()
        
        # Add freshness check for each platform
        result = {}
        for platform, info in status.items():
            meta = info.get("metadata", {})
            result[platform] = {
                "has_cookies": info.get("has_cookies", False),
                "is_fresh": info.get("is_fresh", False),
                "refreshed_at": meta.get("refreshed_at"),
                "cookie_count": meta.get("cookie_count", 0),
                "ttl": meta.get("ttl", 0),
            }
        
        # List platforms that need credentials set
        missing_credentials = []
        if not os.getenv("LINKEDIN_EMAIL") or not os.getenv("LINKEDIN_PASSWORD"):
            missing_credentials.append("linkedin")
        if not os.getenv("FACEBOOK_EMAIL") or not os.getenv("FACEBOOK_PASSWORD"):
            missing_credentials.append("facebook")
        if not os.getenv("USHA_EMAIL") or not os.getenv("USHA_PASSWORD"):
            missing_credentials.append("ushadvisors")
        
        return {
            "platforms": result,
            "missing_credentials": missing_credentials,
            "auth_worker_interval_hours": float(os.getenv("AUTH_REFRESH_INTERVAL_HOURS", "6")),
        }
    except ImportError:
        return {
            "error": "Cookie store not available",
            "platforms": {},
            "missing_credentials": ["all"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auth status: {str(e)}")


@app.get("/auth/cookies/{platform}")
async def get_platform_cookies(platform: str):
    """
    Get cookies for a specific platform (for debugging).
    
    Returns cookie names only (not values for security).
    """
    try:
        from app.scraping.cookie_store import get_cookie_store
        
        store = get_cookie_store()
        cookies = await store.get_cookies(platform)
        
        if not cookies:
            return {
                "platform": platform,
                "has_cookies": False,
                "cookies": [],
            }
        
        # Return cookie metadata without values (security)
        cookie_info = []
        for cookie in cookies:
            cookie_info.append({
                "name": cookie.get("name"),
                "domain": cookie.get("domain"),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
                "expires": cookie.get("expires"),
            })
        
        meta = await store.get_metadata(platform)
        
        return {
            "platform": platform,
            "has_cookies": True,
            "cookie_count": len(cookies),
            "refreshed_at": meta.get("refreshed_at") if meta else None,
            "is_fresh": await store.is_fresh(platform),
            "cookies": cookie_info,
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="Cookie store not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cookies: {str(e)}")


@app.post("/auth/refresh/{platform}")
async def trigger_auth_refresh(platform: str):
    """
    Manually trigger cookie refresh for a platform.
    
    Runs the Auth Worker login flow for the specified platform.
    """
    try:
        from app.workers.auth_worker import AuthWorker
        
        worker = AuthWorker(headless=True)
        
        if platform == "linkedin":
            result = await worker.login_linkedin()
        elif platform == "salesnavigator":
            result = await worker.login_salesnavigator()
        elif platform == "facebook":
            result = await worker.login_facebook()
        elif platform == "ushadvisors":
            result = await worker.login_usha()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
        
        # Store cookies if successful
        if result.success:
            from app.scraping.cookie_store import get_cookie_store
            store = get_cookie_store()
            await store.set_cookies(platform, result.cookies)
        
        return {
            "success": result.success,
            "platform": result.platform,
            "cookie_count": len(result.cookies),
            "error": result.error,
            "timestamp": result.timestamp,
        }
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"Auth worker not available: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth refresh failed: {str(e)}")

# ============================================
# HTML Fetching for Dojo Selector Discovery
# ============================================

from pydantic import BaseModel

class FetchHTMLRequest(BaseModel):
    url: str
    useProxy: bool = True
    useStealth: bool = True
    useBrowser: bool = False
    timeout: int = 30


@app.post("/api/fetch-html")
async def fetch_html(request: FetchHTMLRequest):
    """
    Fetch HTML from a URL using BaseScraper (with stealth/proxy/browser options).
    
    Used by Dojo to discover CSS selectors on people search sites.
    """
    try:
        from app.scraping.base import BaseScraper, BROWSER_MODE_AVAILABLE, STEALTH_AVAILABLE
        
        # Create a simple scraper
        class HTMLFetcher(BaseScraper):
            async def extract(self, url: str):
                return await self.get(url)
        
        # Determine if we should use browser mode
        use_browser = request.useBrowser and BROWSER_MODE_AVAILABLE
        
        fetcher = HTMLFetcher(
            stealth=request.useStealth and STEALTH_AVAILABLE,
            proxy=None,  # Auto-detect from env
            timeout=request.timeout,
            browser_mode=use_browser,
            max_retries=2,
        )
        
        try:
            result = await fetcher.run(url=request.url)
            
            # Get HTML text
            html = result.get('text', '')
            status_code = result.get('status', 200)
            
            # Check for CAPTCHA indicators
            captcha_detected = False
            if html:
                captcha_indicators = ['captcha', 'challenge', 'cf-browser-verification', 'hcaptcha', 'recaptcha']
                captcha_detected = any(indicator in html.lower() for indicator in captcha_indicators)
            
            return {
                "success": True,
                "html": html,
                "statusCode": status_code,
                "htmlLength": len(html) if html else 0,
                "captchaDetected": captcha_detected,
                "usedBrowser": use_browser,
                "usedStealth": request.useStealth and STEALTH_AVAILABLE,
            }
            
        finally:
            await fetcher.close()
            
    except Exception as e:
        error_msg = str(e)
        
        # Detect common blocking patterns
        is_blocked = any(x in error_msg.lower() for x in ['403', '503', 'blocked', 'access denied', 'cloudflare'])
        
        return {
            "success": False,
            "error": error_msg,
            "isBlocked": is_blocked,
            "suggestBrowser": is_blocked and not request.useBrowser,
        }


@app.post("/api/blueprints/save")
async def save_blueprint(request: Dict[str, Any]):
    """
    Save a blueprint (called by Dojo to sync blueprints).
    
    This allows BrainScraper's Dojo to push blueprints directly to Scrapegoat.
    """
    try:
        domain = request.get('domain')
        blueprint = request.get('blueprint', request)
        
        if not domain:
            raise HTTPException(status_code=400, detail="Domain is required")
        
        # Normalize domain
        domain = domain.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
        
        # Get blueprint directory
        from app.enrichment.scraper_enrichment import BLUEPRINT_DIR
        
        # Save blueprint
        blueprint_file = BLUEPRINT_DIR / f"{domain}.json"
        
        with open(blueprint_file, 'w') as f:
            json.dump(blueprint, f, indent=2)
        
        return {
            "success": True,
            "domain": domain,
            "path": str(blueprint_file),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save blueprint: {str(e)}")


@app.post("/api/blueprints/commit-to-swarm")
async def commit_blueprint_to_swarm(request: Dict[str, Any]):
    """
    Commit to Swarm: write Dojo Golden Route to Redis (data + updated_at), file, and site_blueprints.
    All workers pull from Redis; no restarts. Map-to-Engine / Zero-Bot.
    """
    try:
        domain = request.get("domain")
        blueprint = request.get("blueprint", request)
        if not domain:
            raise HTTPException(status_code=400, detail="domain required")
        domain = str(domain).replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if not domain:
            raise HTTPException(status_code=400, detail="domain required")
        r = get_redis()
        if not r:
            raise HTTPException(status_code=503, detail="Redis unavailable")
        from app.enrichment.blueprint_commit import commit_blueprint_impl

        commit_blueprint_impl(domain, blueprint, r)
        return {"success": True, "domain": domain, "redis": "ok", "message": "Blueprint committed to swarm"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blueprints/auto-map")
async def auto_map_blueprint(request: Dict[str, Any]):
    """
    Attempt to discover and verify a blueprint for a domain from HTML. Rate-limited per domain.
    Body: {domain, target_url?}. Returns {status, committed, pending, blueprint?, error?}.
    """
    try:
        domain = request.get("domain")
        target_url = request.get("target_url")
        if not domain:
            raise HTTPException(status_code=400, detail="domain required")
        domain = str(domain).replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if not domain:
            raise HTTPException(status_code=400, detail="domain required")
        from app.enrichment.auto_map import attempt_auto_map

        result = await attempt_auto_map(domain, target_url=target_url)
        return {**result, "domain": domain}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/trigger-dojo-domain")
async def trigger_dojo_domain(request: Request):
    """
    Dojo pipeline activation: when Dojo publishes/commits a blueprint, call this to
    set dojo:active_domain:{domain}=1 (1h TTL). Workers can use it to prefer this domain.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}
    domain = (data or {}).get("domain") or ""
    domain = str(domain).replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    if not domain:
        raise HTTPException(status_code=400, detail="domain required")
    r = get_redis()
    if r:
        r.set(f"dojo:active_domain:{domain}", "1", ex=3600)
    return {"success": True, "domain": domain, "message": "Dojo domain activated for 1h"}


@app.post("/api/dojo/trauma")
async def dojo_trauma(request: Dict[str, Any]):
    """
    Self-Correction: VLM/worker reports broken selector. Dojo can mark domain as NEEDS MAPPING.
    """
    try:
        domain = request.get("domain")
        selector = request.get("selector") or request.get("field", "")
        reason = request.get("reason", "selector_broken")
        if not domain:
            raise HTTPException(status_code=400, detail="domain required")
        domain = str(domain).replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        payload = json.dumps({"selector": selector, "reason": reason, "ts": __import__("datetime").datetime.utcnow().isoformat()})
        r = get_redis()
        if r:
            r.set(f"trauma:{domain}", payload, ex=86400 * 7)  # 7 days
        return {"success": True, "domain": domain, "message": "Trauma recorded"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dojo/coordinate-drift")
async def dojo_coordinate_drift(payload: Dict[str, Any] = Body(default=None)):
    """
    Dojo Cartography: VLM detected coordinates differ from Blueprint. Update
    blueprint:{domain} in Redis with {field}_x, {field}_y so workers adopt the new map.
    Body: {"domain": "...", "field": "phone|age|income", "x": int, "y": int}
    """
    try:
        payload = payload or {}
        domain = payload.get("domain")
        field = payload.get("field") or "unknown"
        x = payload.get("x")
        y = payload.get("y")
        if not domain:
            raise HTTPException(status_code=400, detail="domain required")
        domain = str(domain).replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        r = get_redis()
        if r and x is not None and y is not None:
            key = f"blueprint:{domain}"
            r.hset(key, mapping={f"{field}_x": str(int(x)), f"{field}_y": str(int(y))})
        return {"success": True, "domain": domain, "field": field, "x": x, "y": y, "message": "Blueprint coords updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dojo/domains-need-mapping")
async def dojo_domains_need_mapping():
    """Domains that need a blueprint (BlueprintLoader SADDs when none found). Dojo UI can list these."""
    try:
        r = get_redis()
        if not r:
            return {"domains": []}
        domains = list(r.smembers("dojo:domains_need_mapping") or [])
        return {"domains": [d for d in domains if isinstance(d, str)]}
    except Exception:
        return {"domains": []}


# Minimal blueprints for the 6 Magazine people-search sites. Selectors aligned with chimera-core workers._MAGAZINE_TARGETS.
_MAGAZINE_BLUEPRINTS = [
    ("fastpeoplesearch.com", {"targetUrl": "https://www.fastpeoplesearch.com/", "name_selector": "input#name-search", "result_selector": "div.search-item", "extraction": {}}),
    ("truepeoplesearch.com", {"targetUrl": "https://www.truepeoplesearch.com/", "name_selector": "input#search-name", "result_selector": "div.card-summary", "extraction": {}}),
    ("zabasearch.com", {"targetUrl": "https://www.zabasearch.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
    ("searchpeoplefree.com", {"targetUrl": "https://www.searchpeoplefree.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
    ("thatsthem.com", {"targetUrl": "https://thatsthem.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
    ("anywho.com", {"targetUrl": "https://www.anywho.com/", "name_selector": "input[name='q']", "result_selector": None, "extraction": {}}),
]


@app.post("/api/blueprints/seed-magazine")
async def seed_magazine_blueprints():
    """
    Seed Redis + file + DB with minimal blueprints for all 6 Magazine people-search domains.
    Idempotent; safe to call multiple times. Aligns BlueprintLoader and Chimera overrides with chimera-core _MAGAZINE_TARGETS.
    """
    try:
        from app.enrichment.blueprint_commit import commit_blueprint_impl

        r = get_redis()
        if not r:
            raise HTTPException(status_code=503, detail="Redis not available")
        seeded = []
        for domain, blueprint in _MAGAZINE_BLUEPRINTS:
            try:
                commit_blueprint_impl(domain, blueprint, r)
                seeded.append(domain)
            except Exception as e:
                logger.warning("seed-magazine: commit failed for %s: %s", domain, e)
        return {"status": "ok", "seeded": seeded, "count": len(seeded)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("seed-magazine: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/blueprints")
async def list_blueprints():
    """
    List all available blueprints.
    """
    try:
        from app.enrichment.scraper_enrichment import BLUEPRINT_DIR
        
        blueprints = []
        if BLUEPRINT_DIR.exists():
            for f in BLUEPRINT_DIR.glob("*.json"):
                try:
                    with open(f, 'r') as file:
                        data = json.load(file)
                        blueprints.append({
                            "domain": f.stem,
                            "site": data.get('site', f.stem),
                            "responseType": data.get('responseType', 'html'),
                            "requiresBrowser": data.get('requiresBrowser', False),
                            "fields": list(data.get('extraction', {}).keys()),
                        })
                except Exception:
                    continue
        
        return {
            "success": True,
            "count": len(blueprints),
            "blueprints": blueprints,
            "directory": str(BLUEPRINT_DIR),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/test-blueprint")
async def test_blueprint(request: Dict[str, Any]):
    """
    Test a blueprint against a URL to verify selectors work.
    
    Used by Dojo to validate before saving.
    """
    try:
        from app.enrichment.scraper_enrichment import BlueprintExtractor
        
        blueprint = request.get('blueprint', {})
        test_params = request.get('params', {})
        
        if not blueprint.get('targetUrl'):
            raise HTTPException(status_code=400, detail="Blueprint must have targetUrl")
        
        extractor = BlueprintExtractor(
            blueprint,
            stealth=True,
            browser_mode=blueprint.get('requiresBrowser', False),
            max_retries=2,
            timeout=30,
        )
        
        try:
            result = await extractor.run(**test_params)
            
            return {
                "success": True,
                "extractedFields": result,
                "fieldsFound": list(result.keys()),
                "stats": extractor.get_stats(),
            }
        finally:
            await extractor.close()
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    logger.info("SCRAPEGOAT API STARTUP port=%s python=%s cwd=%s", port, sys.version.split()[0], os.getcwd())
    try:
        logger.info("Starting uvicorn on 0.0.0.0:%s", port)
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Failed to start server: %s", e)
        sys.exit(1)