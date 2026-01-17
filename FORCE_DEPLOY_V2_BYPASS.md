# Force Deploy - Railway v2 Builder Bypass

## 🎯 Objective
Bypass Railway v2 builder's ignored `watchPatterns` and force deployments for all services.

---

## Step 1: Manual CLI Force-Push

### Deploy brainscraper
```bash
railway up --service brainscraper --detach
```

**Expected Output:**
```
✅ Build started for brainscraper
Deployment URL: https://railway.app/...
```

### Deploy scrapegoat-worker-swarm
```bash
railway up --service scrapegoat-worker-swarm --detach
```

**Expected Output:**
```
✅ Build started for scrapegoat-worker-swarm
Deployment URL: https://railway.app/...
```

### Deploy scrapegoat (main)
```bash
railway up --service scrapegoat --detach
```

### Deploy chimera_brain
```bash
railway up --service chimera-brain-v1 --detach
```

### Deploy chimera-core
```bash
railway up --service chimera-core --detach
```

---

## Step 2: Dashboard Alignment (Permanent Fix)

Since `watchPatterns` in `railway.toml` is **ignored by v2 builder**, set Watch Paths in Railway Dashboard:

### brainscraper
1. Railway Dashboard → **brainscraper** service
2. Settings → **Build** → **Watch Paths**
3. Set to: `brainscraper/**`
4. **Save**

### scrapegoat-worker-swarm
1. Railway Dashboard → **scrapegoat-worker-swarm** service
2. Settings → **Build** → **Watch Paths**
3. Set to: `scrapegoat/**`
4. **Save**

### scrapegoat (main)
1. Railway Dashboard → **scrapegoat** service
2. Settings → **Build** → **Watch Paths**
3. Set to: `scrapegoat/**`
4. **Save**

### chimera-brain-v1
1. Railway Dashboard → **chimera-brain-v1** service
2. Settings → **Build** → **Watch Paths**
3. Set to: `chimera_brain/**`
4. **Save**

### chimera-core
1. Railway Dashboard → **chimera-core** service
2. Settings → **Build** → **Watch Paths**
3. Set to: `chimera-core/**`
4. **Save**

---

## Step 3: Verify Health Check Routing

### Verify PORT Environment Variables

**scrapegoat:**
1. Railway Dashboard → **scrapegoat** → Settings → **Variables**
2. Verify: `PORT=8080` exists
3. If missing, add it

**scrapegoat-worker-swarm:**
1. Railway Dashboard → **scrapegoat-worker-swarm** → Settings → **Variables**
2. Verify: `PORT=8080` exists (if worker exposes health endpoint)
3. Verify: `REDIS_URL` is set

### Verify Public Networking Ports

**scrapegoat:**
1. Railway Dashboard → **scrapegoat** → Settings → **Public Networking**
2. Verify: **Port** field is set to `8080`
3. If wrong, change it to `8080` and **Save**

---

## Step 4: Final Smoke Test

### Wait for Deployments to Complete
Monitor Railway Dashboard → **Deployments** tab:
- ✅ Status should show "Success" (green)
- ❌ If "Failed", check build logs

### Health Check Tests

**scrapegoat:**
```bash
curl -f https://scrapegoat-production-8d0a.up.railway.app/health
```

**Expected:**
```json
{"status":"healthy"}
```

**brainscraper:**
```bash
curl -f https://brainscraper-production.up.railway.app/
```

**Expected:** Next.js HTML page (200 OK)

**chimera-brain-v1:**
```bash
curl -f https://chimera-brain-v1-production.up.railway.app/health
```

**Expected:**
```json
{"status":"healthy","service":"chimera-brain"}
```

---

## Verification Checklist

After completing all steps:

- [ ] All services deployed via CLI (`railway up`)
- [ ] Watch Paths set in Dashboard for all services
- [ ] `PORT=8080` verified for scrapegoat services
- [ ] Public Networking Port set to `8080` for scrapegoat
- [ ] All health checks return 200 OK
- [ ] No 502 errors on public endpoints

---

## Troubleshooting

### Issue: "Service not found"
**Fix:** Use exact service name from Railway Dashboard:
```bash
railway service list  # List all services
```

### Issue: "Build failed"
**Fix:** Check build logs:
```bash
railway logs --service <service-name> --tail 50
```

### Issue: "502 Bad Gateway"
**Fix:** 
1. Verify `PORT=8080` in Variables
2. Verify Public Networking Port = `8080`
3. Check service logs for binding errors

### Issue: "Still skipping deployments"
**Fix:**
1. Verify Watch Paths are set in Dashboard (not just railway.toml)
2. Make a small change to a file in watched directory
3. Commit and push
4. Verify deployment triggers

---

## Summary

**Immediate Fix:** Use `railway up --service <name>` to force deployments.

**Permanent Fix:** Set Watch Paths in Railway Dashboard (v2 builder ignores railway.toml).

**Health Check Fix:** Verify `PORT=8080` and Public Networking Port = `8080`.
