# Watch Paths + Root Directory Issue - Complete Analysis

## The Problem

Both `scrapegoat` and `scrapegoat-worker-swarm` are showing **"No changes to watched files"** even though:
- ✅ Watch paths are set to `**` in Dashboard
- ✅ We've modified files in `scrapegoat/` directory
- ✅ Multiple commits with changes to `scrapegoat/` files

## Root Cause Hypothesis

**Watch paths might be evaluated RELATIVE to Root Directory, not repository root!**

If:
- **Root Directory:** `scrapegoat` (set in Dashboard)
- **Watch Paths:** `**` (set in Dashboard)

Then Railway might be evaluating `**` as:
- "All files in `scrapegoat/` directory" (relative to root directory)
- NOT "All files in repository root"

But we've been changing files in `scrapegoat/`, so this should still work...

## Alternative Hypothesis

**Railway might be comparing to the LAST successful deployment, not the previous commit.**

If:
- Last successful deployment was from commit X
- Current commit is Y
- Railway compares: "Did any watched files change between X and Y?"
- If files changed but Railway's hash comparison fails, it skips

## What We've Changed

**Recent commits with scrapegoat/ changes:**
- `9b435cb` - Modified `scrapegoat/main.py` ✅ (just pushed)
- `9a1e3f0` - Created `scrapegoat/.railway_trigger` ✅
- `f0aa21a` - Modified `scrapegoat/start_redis_worker.py` ✅
- `3acdb78` - Modified `scrapegoat/railway.toml` ✅
- `2002715` - Modified `scrapegoat/railway.toml` ✅
- `8b10332` - Modified `scrapegoat/railway.toml` ✅

**All of these should have triggered deployments if watch paths are working.**

## Possible Issues

### Issue 1: Watch Path Evaluation
- Watch paths might be evaluated from repository root
- If root directory is `scrapegoat/`, Railway changes context
- Watch paths might need to be relative to root directory, not repo root

### Issue 2: File Hash Caching
- Railway might cache file hashes
- If file content hash hasn't changed (whitespace only), Railway might skip
- Our changes are small (comments), might not change hash significantly

### Issue 3: Root Directory + Watch Paths Conflict
- Root directory: `scrapegoat` (builds from this directory)
- Watch paths: `**` (from repo root or from root directory?)
- Railway might be confused about evaluation context

## Solution Attempts

### Try 1: Modify Actual Code (Not Just Comments)
Instead of just adding comments, let's modify actual functional code to ensure hash changes.

### Try 2: Check Root Directory Setting
Verify root directory is exactly `scrapegoat` (not `scrapegoat/` with trailing slash)

### Try 3: Force via CLI
Use `railway up` to bypass watch path detection entirely

## Next Steps

1. **Verify Root Directory:**
   - Railway Dashboard → scrapegoat → Settings → General
   - Root Directory should be: `scrapegoat` (no trailing slash, no leading slash)

2. **Verify Watch Paths:**
   - Railway Dashboard → scrapegoat → Settings → Build
   - Watch Paths should be: `**` (from repo root) or `./**` (from root directory)

3. **Try Different Watch Path Format:**
   - Try: `scrapegoat/**` (explicit path from repo root)
   - Try: `./**` (relative to root directory)
   - Try: `**` (from repo root - current setting)

4. **Force Deploy via CLI:**
   ```bash
   railway up --service scrapegoat --detach
   ```
