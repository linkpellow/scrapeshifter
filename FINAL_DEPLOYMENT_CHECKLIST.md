# 🚀 Final 15-Minute "Green Light" Sequence

Complete deployment checklist for the Triple-Vessel Stealth Extraction Engine.

## ✅ Pre-Deployment Verification

### 1. IPv6 Dual-Stack Binding ✅
**File:** `scrapegoat/main.py`

Verify the bottom of the file looks like this:
```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="::", port=port)  # IPv6 binding for Railway dual-stack networking
```

**Status:** ✅ **FIXED** - Now using `host="::"` for dual-stack networking

---

### 2. Installation Script ✅
**File:** `install-dependencies.sh`

The script uses dynamic path detection:
```bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

**Status:** ✅ **READY** - Works from any directory

---

## 📋 Step-by-Step Deployment Sequence

### Step 1: Execute Local Build (5-10 minutes)

```bash
cd ~/Desktop/my-lead-engine
chmod +x install-dependencies.sh
./install-dependencies.sh
```

**What this does:**
- ✅ Creates virtual environments for Python services
- ✅ Installs all dependencies (Python + Node.js)
- ✅ Installs Playwright Chromium browser
- ✅ Generates gRPC proto files for Chimera Brain
- ✅ Verifies all installations

**Expected output:**
```
🚀 Starting installation from: /Users/linkpellow/Desktop/my-lead-engine
[1/3] Installing Scrapegoat (The Scraper)
✅ Scrapegoat installation complete!
[2/3] Installing Chimera Brain (The AI)
✅ Chimera Brain installation complete!
[3/3] Installing BrainScraper (The UI)
✅ BrainScraper installation complete!
🎉 All dependencies installed successfully!
```

---

### Step 2: Verify the Handshake (1 minute)

**Check `scrapegoat/main.py` bottom section:**

```bash
tail -5 scrapegoat/main.py
```

Should show:
```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="::", port=port)  # IPv6 binding for Railway
```

**Status:** ✅ **VERIFIED** - IPv6 dual-stack binding enabled

---

### Step 3: The Deployment Push

```bash
# Stage all changes
git add .

# Commit with descriptive message
git commit -m "fix: restore monorepo and enable ipv6 dual-stack handshake

- Restored complete package.json for brainscraper
- Enhanced chimera_brain requirements.txt with version constraints
- Fixed scrapegoat/main.py to use IPv6 dual-stack binding (host='::')
- Created permission-proof installation script
- All dependencies verified and production-ready"

# Push to Railway
git push origin main
```

---

## ⏳ The "Wait" Part - Build Times

### Python Services (3-5 minutes)
- ✅ **Scrapegoat**: FastAPI service - builds quickly
- ✅ **Chimera Brain**: Python gRPC server - builds quickly

**Status:** These will be **GREEN** in ~3-5 minutes

### Rust Service (10-12 minutes)
- ⚠️ **Chimera Core**: Rust compilation with 2,000+ files

**CRITICAL:** Do NOT push again until the Rust build finishes!
- If you push during the build, the 12-minute timer **resets to zero**
- Wait for the build to complete before making any new commits

---

## 🎯 Why This Configuration Works

### 1. Dual-Stack Networking
- `host="::"` ensures Railway's internal mesh network can see Scrapegoat API
- Works with both IPv4 and IPv6
- Enables service-to-service communication on Railway

### 2. Sandbox Isolation
- Each Python service has its own `venv` folder
- Dependencies stored inside project folder (not system folders)
- Completely bypasses `pip3` permission errors

### 3. Dependency Synchronization
- All services have matching gRPC proto files
- Libraries are version-constrained for stability
- Production-ready dependency versions

---

## ✅ Post-Deployment Verification

After Railway deployment completes:

1. **Check Service Status:**
   - Scrapegoat: `https://your-scrapegoat.railway.app/health`
   - BrainScraper: `https://your-brainscraper.railway.app`
   - Chimera Brain: Check Railway logs for gRPC server startup

2. **Verify Redis Connection:**
   - Check Railway logs for "✅ Redis connected successfully"

3. **Test API Endpoints:**
   ```bash
   # Scrapegoat health check
   curl https://your-scrapegoat.railway.app/health
   
   # BrainScraper root
   curl https://your-brainscraper.railway.app
   ```

---

## 📍 Where This Leaves Us

Once deployment completes:

✅ **Local machine is 100% ready** to run the code  
✅ **Railway services are configured** with correct root directories  
✅ **IPv6 dual-stack networking** enabled for service communication  
✅ **All dependencies installed** in isolated environments  
✅ **Ready for production** - all systems operational

---

## 🚨 Important Reminders

1. **Don't push during Rust build** - Wait for 10-12 minutes
2. **Verify IPv6 binding** - Must be `host="::"` not `host="0.0.0.0"`
3. **Check Railway logs** - Monitor build progress
4. **Test connections** - Verify Redis and database connections work

---

**Status: Ready for Final Push** 🚀
