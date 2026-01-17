# Vessel Mismatch Fix - scrapegoat-worker-swarm

## 🔴 Root Cause Analysis

**Problem:** Railway v2 builder is picking up the wrong `railway.toml` file, causing `scrapegoat-worker-swarm` to run Chimera Core (Rust) code instead of Scrapegoat Worker (Python) code.

**Evidence:**
- Logs show: `🦾 Chimera Core - The Body - Starting...`
- Service is running `chimera-core/main.py` instead of `scrapegoat/start_redis_worker.py`

**Why This Happens:**
1. **Root Directory Mismatch:** Service Root Directory may be set to project root or `chimera-core/`
2. **railway.toml Collision:** Railway finds `chimera-core/railway.toml` first (has `startCommand = "python3 main.py"`)
3. **Context Confusion:** v2 builder doesn't respect Root Directory for start command resolution

---

## ✅ Fix Strategy

### Option 1: Dashboard Configuration (RECOMMENDED)

**Railway Dashboard → scrapegoat-worker-swarm → Settings:**

1. **General → Root Directory:**
   - Set to: `scrapegoat` (NOT `chimera-core`, NOT empty, NOT root)
   - **Save**

2. **Deploy → Start Command:**
   - Set to: `python start_redis_worker.py` (NOT `python3 main.py`)
   - **Save**

3. **Variables:**
   - Verify `REDIS_URL` = `redis://redis.railway.internal:6379`
   - Verify `APP_REDIS_URL` = `redis://redis.railway.internal:6379`
   - **Save**

### Option 2: CLI Force (If Dashboard Doesn't Work)

**Note:** Railway CLI may not support setting start commands directly. Try:

```bash
# Verify service context
railway status

# Set environment variables (may help)
railway variable set PYTHONUNBUFFERED=1 --service scrapegoat-worker-swarm

# Force redeploy
railway redeploy --service scrapegoat-worker-swarm --yes
```

**But:** Start command must be set in Dashboard - CLI cannot override it.

---

## 🔍 Verification

### Check Root Directory

**Railway Dashboard → scrapegoat-worker-swarm → Settings → General:**
- **Root Directory:** Must be `scrapegoat`
- If wrong, change it and **Save**

### Check Start Command

**Railway Dashboard → scrapegoat-worker-swarm → Settings → Deploy:**
- **Start Command:** Must be `python start_redis_worker.py`
- If wrong, change it and **Save**

### Verify Logs

After fix, logs should show:
```
🚀 SCRAPEGOAT TRI-CORE SYSTEM
✅ All Systems Operational: [Factory] [Driver] [Keymaster]
🏭 Starting Enrichment Factory...
```

NOT:
```
🦾 Chimera Core - The Body - Starting...
✅ Chimera Core worker started
```

---

## 📋 Configuration Files Analysis

### chimera-core/railway.toml
```toml
[deploy]
startCommand = "python3 main.py"  # For Chimera Core
```

### scrapegoat/railway.toml
```toml
[deploy]
# startCommand removed - set per-service in Dashboard
```

### scrapegoat/railway.worker.toml
```toml
[deploy]
startCommand = "python start_redis_worker.py"  # For worker
```

**Issue:** Railway may be reading `chimera-core/railway.toml` if Root Directory is wrong.

---

## 🎯 Correct Configuration

**scrapegoat-worker-swarm should:**
- **Root Directory:** `scrapegoat` (Dashboard)
- **Start Command:** `python start_redis_worker.py` (Dashboard)
- **Watch Paths:** `scrapegoat/**` (Dashboard)
- **REDIS_URL:** `redis://redis.railway.internal:6379` (Variables)

**chimera-core should:**
- **Root Directory:** `chimera-core` (Dashboard)
- **Start Command:** `python3 main.py` (from railway.toml or Dashboard)
- **Watch Paths:** `chimera-core/**` (Dashboard)

---

## 🚨 Critical: Dashboard Configuration Required

**Railway CLI cannot set start commands per-service.** This MUST be done in Railway Dashboard.

**Why:**
- Start commands are service-specific
- Dashboard settings override `railway.toml`
- CLI doesn't support per-service start command override

---

## ✅ Summary

**Root Cause:** Wrong Root Directory causing Railway to read wrong `railway.toml`

**Fix:** Set Root Directory and Start Command in Railway Dashboard

**Status:**
- ✅ Redis variables fixed
- ❌ Root Directory needs Dashboard fix
- ❌ Start Command needs Dashboard fix
- ⏳ Waiting for Dashboard configuration
