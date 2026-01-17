# Vessel Mismatch - Complete Fix Guide

## 🔴 Root Cause Confirmed

**Problem:** `scrapegoat-worker-swarm` is running **Chimera Core** (Python worker for Rust service) instead of **Scrapegoat Worker** (Python enrichment worker).

**Evidence:**
- Logs show: `🦾 Chimera Core - The Body - Starting...`
- Service is executing `chimera-core/main.py` instead of `scrapegoat/start_redis_worker.py`

**Why:**
- Railway v2 builder is reading `chimera-core/railway.toml` (has `startCommand = "python3 main.py"`)
- Root Directory may be set incorrectly
- Service context confusion between two Python services

---

## ✅ REQUIRED FIX: Railway Dashboard

**Railway CLI cannot set start commands per-service. This MUST be fixed in Dashboard.**

### Step 1: Fix Root Directory

**Railway Dashboard → scrapegoat-worker-swarm → Settings → General:**

1. **Root Directory:** 
   - **Current:** May be `chimera-core` or empty or root
   - **Change to:** `scrapegoat` (exactly this, no leading slash)
   - **Save**

**Why:** Root Directory determines which `railway.toml` Railway reads.

---

### Step 2: Fix Start Command

**Railway Dashboard → scrapegoat-worker-swarm → Settings → Deploy:**

1. **Start Command:**
   - **Current (WRONG):** Likely `python3 main.py` (from chimera-core)
   - **Change to:** `python start_redis_worker.py`
   - **Save**

**Why:** This is the correct entry point for the Scrapegoat worker loop.

---

### Step 3: Verify Variables

**Railway Dashboard → scrapegoat-worker-swarm → Settings → Variables:**

Verify these are set:
- ✅ `REDIS_URL` = `redis://redis.railway.internal:6379`
- ✅ `APP_REDIS_URL` = `redis://redis.railway.internal:6379`
- ✅ `PYTHONUNBUFFERED` = `1`

---

### Step 4: Set Watch Paths (For Auto-Deploys)

**Railway Dashboard → scrapegoat-worker-swarm → Settings → Build:**

1. **Watch Paths:**
   - Set to: `scrapegoat/**`
   - **Save**

**Why:** Prevents future "Skipped" deployments (v2 builder ignores railway.toml watchPatterns).

---

### Step 5: Redeploy

After saving all changes:
- Railway should auto-redeploy
- Or manually: Deployments → "Redeploy"

---

## 🔍 Verification

### Check Logs After Fix

```bash
railway logs --service scrapegoat-worker-swarm --tail 30
```

**Expected Output:**
```
🚀 SCRAPEGOAT TRI-CORE SYSTEM
✅ All Systems Operational: [Factory] [Driver] [Keymaster]
🏭 Starting Enrichment Factory...
🚗 Starting Spider Driver...
🔑 Starting Auth Keymaster...
```

**NOT:**
```
🦾 Chimera Core - The Body - Starting...
✅ Chimera Core worker started
```

---

### Check Health Endpoint

```bash
curl -I https://scrapegoat-production-8d0a.up.railway.app/health
```

**Expected:**
- `HTTP/2 200 OK` (if worker exposes health endpoint)
- Or service may not expose HTTP (worker-only, no health endpoint is OK)

---

## 📋 Configuration Comparison

### Correct Configuration

**scrapegoat-worker-swarm:**
- Root Directory: `scrapegoat`
- Start Command: `python start_redis_worker.py`
- Watch Paths: `scrapegoat/**`
- REDIS_URL: `redis://redis.railway.internal:6379`

**chimera-core:**
- Root Directory: `chimera-core`
- Start Command: `python3 main.py` (from railway.toml)
- Watch Paths: `chimera-core/**`
- CHIMERA_BRAIN_ADDRESS: `http://chimera-brain.railway.internal:50051`

---

## 🎯 Why This Happened

**Vessel Mismatch:**
- Two Python services (`scrapegoat-worker-swarm` and `chimera-core`)
- Both use Python, both have `main.py`
- Railway v2 builder confused which service to run
- Root Directory was wrong, causing wrong `railway.toml` to be read

**Solution:**
- Explicit Root Directory per service
- Explicit Start Command per service
- Dashboard configuration (not CLI) required

---

## ✅ Summary

**Issue:** Vessel mismatch - scrapegoat-worker-swarm running Chimera Core code

**Root Cause:** Wrong Root Directory causing wrong railway.toml to be read

**Fix:** Dashboard configuration required:
1. Root Directory = `scrapegoat`
2. Start Command = `python start_redis_worker.py`
3. Watch Paths = `scrapegoat/**`
4. Redis variables already fixed ✅

**Status:**
- ✅ Redis variables fixed
- ❌ Root Directory needs Dashboard fix (URGENT)
- ❌ Start Command needs Dashboard fix (URGENT)
- ⏳ Waiting for Dashboard configuration

---

## 🚨 Critical: Dashboard Only

**Railway CLI cannot fix this.** Start commands and Root Directory must be set in Railway Dashboard.

**Why:**
- CLI doesn't support per-service start command override
- Root Directory is a Dashboard-only setting
- v2 builder requires explicit Dashboard configuration

**Next Step:** Go to Railway Dashboard and fix Root Directory + Start Command for scrapegoat-worker-swarm service.
