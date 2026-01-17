# Fix Scrapegoat 502 Error - Port Alignment

## Problem
Scrapegoat service is healthy internally on port 8080, but public endpoint returns 502. Railway proxy port doesn't match container's internal listener.

## Solution Steps

### 1. Verify PORT Environment Variable

**Via Railway CLI:**
```bash
cd /Users/linkpellow/Desktop/my-lead-engine/scrapegoat
railway service  # Link to scrapegoat service
railway variables | grep PORT
```

**Expected:** `PORT=8080`

**If missing or wrong:**
```bash
railway variables --set PORT=8080
```

**Via Railway Dashboard:**
1. Go to: Railway Dashboard → scrapegoat service
2. Settings → Variables
3. Ensure `PORT=8080` exists
4. If missing, add it

### 2. Check Railway Service Port Mapping

**Via Railway Dashboard (REQUIRED):**
1. Go to: Railway Dashboard → scrapegoat service
2. Settings → **Public Networking**
3. Check the **"Port"** field
4. **MUST be set to: 8080** (not 8000 or 3000)
5. Save changes

**This is the critical fix** - Railway's public proxy must match the container's internal port.

### 3. Test Internal Connectivity (Cross-Vessel)

From brainscraper service or any Railway service:
```bash
# Test internal Railway network
curl http://scrapegoat.railway.internal:8080/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "scrapegoat",
  "timestamp": "2026-01-17T..."
}
```

**If this works but public URL doesn't:** Port mapping is misconfigured (go back to step 2).

### 4. Final Smoke Test (Public Endpoint)

After fixing port mapping:
```bash
curl -I https://scrapegoat-production-8d0a.up.railway.app/health
```

**Expected:**
```
HTTP/2 200
```

**If still 502:**
- Wait 1-2 minutes for Railway to update routing
- Check Railway Dashboard → Deployments → Latest deployment logs
- Verify service is actually listening on 8080 in logs

## Current Configuration

**scrapegoat/main.py:**
```python
port = int(os.getenv("PORT", 8000))  # Defaults to 8000 if PORT not set
uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```

**scrapegoat/railway.toml:**
```toml
[env]
PORT = "8080"

[environments.production]
PORT = "8080"
```

## Verification Checklist

- [ ] PORT environment variable = 8080 (in Railway Dashboard)
- [ ] Public Networking → Port = 8080 (in Railway Dashboard)
- [ ] Internal connectivity works: `curl http://scrapegoat.railway.internal:8080/health`
- [ ] Public endpoint works: `curl -I https://scrapegoat-production-8d0a.up.railway.app/health` → HTTP/2 200
- [ ] Service logs show: "Starting uvicorn on 0.0.0.0:8080..."

## Common Issues

### Issue: "PORT variable not found"
**Fix:** Set `PORT=8080` in Railway Dashboard → Variables

### Issue: "Public Networking Port is 8000"
**Fix:** Change to 8080 in Railway Dashboard → Settings → Public Networking

### Issue: "Internal works, public 502"
**Fix:** Port mapping mismatch - ensure Public Networking Port = 8080

### Issue: "Service logs show port 8000"
**Fix:** PORT environment variable not set - add `PORT=8080` in Railway Dashboard

## Quick Fix Commands

```bash
# 1. Link to service
cd /Users/linkpellow/Desktop/my-lead-engine/scrapegoat
railway service  # Select scrapegoat

# 2. Set PORT variable
railway variables --set PORT=8080

# 3. Check current variables
railway variables | grep PORT

# 4. Test internal (from another service)
curl http://scrapegoat.railway.internal:8080/health

# 5. Check logs
railway logs --service scrapegoat --tail 50 | grep -i port
```

**Note:** Public Networking Port must be changed in Railway Dashboard - CLI doesn't support this setting.
