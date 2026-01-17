"""
Scrapegoat: AI-Powered Lead Enrichment Worker Swarm
Consumer service that processes leads from Redis queue
"""

# Critical: Print immediately to verify script is executing
print("🔧 [STARTUP] Script started", flush=True)

import sys
import os

# Flush output immediately for Railway logs
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    # Python < 3.7 or reconfigure not available, use flush instead
    pass

print("🔧 [STARTUP] Loading Scrapegoat module...", flush=True)

try:
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import redis
import json
from typing import Dict, Any
    print("✅ [STARTUP] Core imports successful", flush=True)
except ImportError as e:
    print(f"❌ [STARTUP] Import error: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

app = FastAPI(
    title="Scrapegoat API",
    description="AI-powered lead enrichment worker swarm",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection - lazy initialization to prevent startup failures
redis_url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
print(f"🔧 Redis URL configured: {redis_url[:30]}..." if len(redis_url) > 30 else f"🔧 Redis URL configured: {redis_url}")

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
    
    print("=" * 60, flush=True)
    print("🚀 SCRAPEGOAT API STARTUP", flush=True)
    print("=" * 60, flush=True)
    
    port = int(os.getenv("PORT", 8000))
    print(f"🔧 Port: {port}", flush=True)
    print(f"🔧 Python version: {sys.version}", flush=True)
    print(f"🔧 Working directory: {os.getcwd()}", flush=True)
    print(f"🔧 PYTHONUNBUFFERED: {os.getenv('PYTHONUNBUFFERED', 'not set')}", flush=True)
    print("=" * 60, flush=True)
    
    try:
        print(f"🌐 Starting uvicorn on [::]:{port}...", flush=True)
        uvicorn.run(app, host="::", port=port, log_level="info")  # IPv6 binding for Railway dual-stack networking
    except KeyboardInterrupt:
        print("\n⚠️ Server interrupted by user", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed to start server: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)