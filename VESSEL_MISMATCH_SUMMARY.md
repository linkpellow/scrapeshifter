# Vessel Mismatch - Executive Summary

## 🔴 Confirmed Issue

**Current State:**
- `scrapegoat-worker-swarm` is running **Chimera Core** code
- Logs show: `🦾 Chimera Core - The Body - Starting...`
- Service is executing `chimera-core/main.py` instead of `scrapegoat/start_redis_worker.py`

**Impact:**
- ❌ Enrichment pipeline is NOT running
- ❌ Redis queues are NOT being processed
- ❌ Worker swarm is completely inactive
- ❌ Leads are NOT being enriched

---

## ✅ Root Cause

**Railway v2 builder is reading the wrong `railway.toml` file:**

1. **Root Directory Mismatch:** Service Root Directory may be set to `chimera-core` or empty
2. **Config Collision:** Railway finds `chimera-core/railway.toml` first (has `startCommand = "python3 main.py"`)
3. **Context Confusion:** v2 builder doesn't properly respect Root Directory for start command resolution

**Files Involved:**
- `chimera-core/railway.toml` → `startCommand = "python3 main.py"` (WRONG for scrapegoat-worker-swarm)
- `scrapegoat/railway.toml` → `startCommand` removed (should be set in Dashboard)
- `scrapegoat/railway.worker.toml` → `startCommand = "python start_redis_worker.py"` (CORRECT, but not being read)

---

## 🛠️ REQUIRED FIX: Railway Dashboard

**Railway CLI cannot fix this. Dashboard configuration is required.**

### Critical Settings

**Railway Dashboard → scrapegoat-worker-swarm → Settings:**

1. **General → Root Directory:**
   - **Set to:** `scrapegoat` (NOT `chimera-core`, NOT empty)
   - **Save**

2. **Deploy → Start Command:**
   - **Set to:** `python start_redis_worker.py` (NOT `python3 main.py`)
   - **Save**

3. **Build → Watch Paths:**
   - **Set to:** `scrapegoat/**`
   - **Save**

4. **Variables:** (Already fixed ✅)
   - `REDIS_URL` = `redis://redis.railway.internal:6379` ✅
   - `APP_REDIS_URL` = `redis://redis.railway.internal:6379` ✅

---

## 🔍 Verification

**After fix, logs should show:**
```
🚀 SCRAPEGOAT TRI-CORE SYSTEM
✅ All Systems Operational: [Factory] [Driver] [Keymaster]
🏭 Starting Enrichment Factory...
```

**NOT:**
```
🦾 Chimera Core - The Body - Starting...
✅ Chimera Core worker started
```

---

## 📋 Complete Status

| Component | Status | Action Required |
|-----------|--------|----------------|
| **Redis Variables** | ✅ Fixed | None |
| **Root Directory** | ❌ Wrong | Dashboard fix |
| **Start Command** | ❌ Wrong | Dashboard fix |
| **Watch Paths** | ❌ Not set | Dashboard fix |

---

## 🎯 Next Steps

1. **Go to Railway Dashboard**
2. **Fix Root Directory** → `scrapegoat`
3. **Fix Start Command** → `python start_redis_worker.py`
4. **Set Watch Paths** → `scrapegoat/**`
5. **Redeploy** (auto or manual)
6. **Verify Logs** show Scrapegoat worker, not Chimera Core

---

## 📝 Why Dashboard Only

**Railway CLI Limitations:**
- ❌ Cannot set per-service Root Directory
- ❌ Cannot set per-service Start Command
- ❌ Cannot set Watch Paths (v2 builder ignores railway.toml)

**Dashboard Required:**
- ✅ Only way to set Root Directory per-service
- ✅ Only way to override Start Command per-service
- ✅ Only way to set Watch Paths for v2 builder

---

## ✅ Summary

**Issue:** Vessel mismatch - wrong service code running

**Root Cause:** Wrong Root Directory causing wrong railway.toml to be read

**Fix:** Dashboard configuration (3 settings)

**Status:** 
- ✅ Redis variables fixed
- ❌ Dashboard configuration needed (URGENT)

**See:** `FINAL_DASHBOARD_FIX_CHECKLIST.md` for step-by-step instructions.
