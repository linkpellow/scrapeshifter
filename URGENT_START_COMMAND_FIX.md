# 🚨 URGENT: Fix scrapegoat-worker-swarm Start Command

## 🔴 Confirmed Issue

**Current State:**
- `scrapegoat-worker-swarm` is running **Chimera Core** code
- Logs show: `🦾 Chimera Core - The Body - Starting...`
- **Worker loop is NOT running** - enrichment pipeline is inactive

**Expected State:**
- Should run **Scrapegoat Worker** code
- Logs should show: `🚀 SCRAPEGOAT TRI-CORE SYSTEM`
- Worker loop should process Redis queues

---

## ✅ REQUIRED FIX: Railway Dashboard

**This MUST be fixed in Railway Dashboard - CLI cannot set start commands per-service.**

### Step-by-Step Fix

1. **Go to Railway Dashboard:**
   - https://railway.com/project/4ea4e3a1-2f41-4dfd-a6a6-4af56084b195
   - Click on **scrapegoat-worker-swarm** service

2. **Fix Root Directory:**
   - Settings → **General** → **Root Directory**
   - **Set to:** `scrapegoat` (NOT `chimera-core`, NOT empty)
   - **Save**

3. **Fix Start Command:**
   - Settings → **Deploy** → **Start Command**
   - **Current (WRONG):** Likely `python main.py` or `python3 main.py` (from chimera-core)
   - **Change to:** `python start_redis_worker.py`
   - **Save**

4. **Verify Variables:**
   - Settings → **Variables**
   - Verify `REDIS_URL` = `redis://redis.railway.internal:6379`
   - Verify `APP_REDIS_URL` = `redis://redis.railway.internal:6379`
   - If missing, add them

5. **Redeploy:**
   - After saving, Railway should auto-redeploy
   - Or manually trigger: Deployments → "Redeploy"

---

## 🔍 Verification

### After Fix, Check Logs:

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

## 📋 Complete Configuration Checklist

**Railway Dashboard → scrapegoat-worker-swarm:**

- [ ] **Root Directory:** `scrapegoat`
- [ ] **Start Command:** `python start_redis_worker.py`
- [ ] **Watch Paths:** `scrapegoat/**` (for auto-deploys)
- [ ] **REDIS_URL:** `redis://redis.railway.internal:6379`
- [ ] **APP_REDIS_URL:** `redis://redis.railway.internal:6379`
- [ ] **DATABASE_URL:** Set (if needed for worker)
- [ ] **PORT:** `8080` (if worker exposes health endpoint)

---

## 🎯 Why This Is Critical

**Current Impact:**
- ❌ Enrichment pipeline is NOT running
- ❌ Redis queues are NOT being processed
- ❌ Leads are NOT being enriched
- ❌ Worker swarm is completely inactive

**After Fix:**
- ✅ Enrichment pipeline will start
- ✅ Redis queues will be processed
- ✅ Leads will be enriched automatically
- ✅ Worker swarm will be operational

---

## 📝 Summary

**Issue:** Wrong start command causing service to run Chimera Core instead of Scrapegoat Worker

**Fix:** Dashboard configuration only (Settings → Deploy → Start Command)

**Status:**
- ✅ Redis variables fixed
- ❌ Start command needs Dashboard fix (URGENT)
- ⏳ Waiting for Dashboard configuration

**Next Step:** Fix Start Command in Railway Dashboard → scrapegoat-worker-swarm → Settings → Deploy
