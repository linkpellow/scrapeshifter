# Railway CLI Deployment Force - Diagnostics & Actions

## ✅ Actions Completed

### 1. CLI Diagnostic Results

**Current Status:**
```bash
railway status
# Project: my-lead-engine
# Environment: production
# Service: Redis (currently linked)
```

**Note:** Railway CLI requires interactive prompts for service linking, so full diagnostics require manual execution.

### 2. Force Deployment (Bypass Git) ✅

**brainscraper:**
```bash
cd brainscraper
railway up --service brainscraper --detach
# ✅ Deployment triggered
# Build Logs: https://railway.com/project/.../service/.../id=...
```

**scrapegoat-worker-swarm:**
```bash
cd scrapegoat
railway up --service scrapegoat-worker-swarm --detach
# ✅ Deployment triggered
# Build Logs: https://railway.com/project/.../service/.../id=...
```

### 3. Cache Invalidation ✅

**Files Modified to Force New Hash:**

1. **brainscraper/next.config.js:**
   - Added comment: `// Cache invalidation: 2026-01-17 - Force Railway rebuild`

2. **scrapegoat/main.py:**
   - Added comment: `# Cache invalidation: 2026-01-17 - Force Railway rebuild`

3. **chimera-core/main.py:**
   - Added comment: `# Cache invalidation: 2026-01-17 - Force Railway rebuild`
   - Note: `chimera-core/src/main.rs` doesn't exist (service is Python, not Rust)

### 4. Port Alignment (502 Fix)

**To Check/Set PORT Variable:**

Since Railway CLI requires interactive prompts, use one of these methods:

**Option A: Railway Dashboard**
1. Go to: Railway Dashboard → scrapegoat-worker-swarm service
2. Settings → Variables
3. Check if `PORT=8080` exists
4. If missing, add it

**Option B: Railway CLI (Manual)**
```bash
# Link to service first (requires interactive prompt)
railway link --service scrapegoat-worker-swarm

# Check variables
railway variables | grep PORT

# Set PORT if missing
railway variables --set PORT=8080
```

**Option C: Verify in railway.toml**
The `scrapegoat/railway.toml` already has:
```toml
[env]
PORT = "8080"

[environments.production]
PORT = "8080"
```

## Next Steps

### 1. Commit Cache Invalidation Changes
```bash
cd /Users/linkpellow/Desktop/my-lead-engine
git add brainscraper/next.config.js scrapegoat/main.py chimera-core/main.py
git commit -m "ops: invalidate cache to force Railway rebuilds"
git push origin main
```

### 2. Monitor Deployments

**Check Build Status:**
- Railway Dashboard → Deployments tab
- Look for "Building..." status (not "Skipped")
- Monitor build logs via provided URLs

**Expected:**
- ✅ brainscraper: "Building..." (not "Skipped")
- ✅ scrapegoat-worker-swarm: "Building..." (not "Skipped")

### 3. Verify PORT Variable

**Manual Check Required:**
1. Railway Dashboard → scrapegoat-worker-swarm → Settings → Variables
2. Verify `PORT=8080` exists
3. If missing, add it

**Or via CLI (after linking):**
```bash
railway link --service scrapegoat-worker-swarm
railway variables --set PORT=8080
```

## Troubleshooting

### Issue: "Still showing Skipped"
**Fix:**
1. Wait 2-3 minutes for Railway to process
2. Check Railway Dashboard → Deployments
3. Verify watch paths are set correctly (see FIX_WATCH_PATHS.md)
4. Try another `railway up --service <name> --detach`

### Issue: "PORT variable not found"
**Fix:**
- Set via Dashboard: Settings → Variables → Add `PORT=8080`
- Or via CLI: `railway variables --set PORT=8080` (after linking)

### Issue: "CLI requires interactive prompt"
**Fix:**
- Railway CLI linking requires TTY
- Use Railway Dashboard for variable management
- Or run CLI commands manually in your terminal

## Summary

✅ **Deployments Forced:**
- brainscraper: Deployment triggered via CLI
- scrapegoat-worker-swarm: Deployment triggered via CLI

✅ **Cache Invalidated:**
- Modified 3 files to force new hash
- Ready to commit and push

⚠️ **Manual Action Required:**
- Verify PORT=8080 in Railway Dashboard for scrapegoat-worker-swarm
- Monitor build status in Railway Dashboard
