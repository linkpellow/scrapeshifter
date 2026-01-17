# 🚨 CRITICAL: Start Command Error Fix

## The Error

```
ERROR: Error loading ASGI app. Could not import module "app.main".
```

## Root Cause

**Railway Dashboard has wrong start command!**

**Current (WRONG):**
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Should Be:**
```
python3 main.py
```

## Why This Happens

The file structure is:
```
scrapegoat/
├── main.py          ← FastAPI app is here (root level)
├── app/             ← This is a package, not where main.py is
│   ├── enrichment/
│   ├── pipeline/
│   └── workers/
└── start_redis_worker.py
```

**The FastAPI app (`app`) is defined in `main.py` at the root, not in `app/main.py`.**

## The Fix

### Railway Dashboard → scrapegoat Service

1. **Settings → Deploy → Custom Start Command**
2. **Change from:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. **Change to:** `python3 main.py`
4. **Save**

### Why `python3 main.py` Works

Looking at `scrapegoat/main.py`:
```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```

Running `python3 main.py` executes this block, which:
- Reads `PORT` from environment (8080)
- Calls `uvicorn.run(app, ...)` with correct settings
- Starts the FastAPI server properly

## Verification

After fixing start command:
- Service should start successfully
- Logs should show: `🚀 SCRAPEGOAT API STARTUP`
- Logs should show: `🌐 Starting uvicorn on 0.0.0.0:8080...`
- Health check should work: `curl http://scrapegoat-url/health`

## Summary

**The Problem:** Dashboard start command is `uvicorn app.main:app` (wrong path)
**The Fix:** Change to `python3 main.py` (correct - runs main.py which starts uvicorn)
**Location:** Railway Dashboard → scrapegoat → Settings → Deploy → Custom Start Command
