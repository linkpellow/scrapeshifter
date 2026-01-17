# 🛠️ Permission-Proof Installation Guide

Complete installation guide for the Triple-Vessel Stealth Extraction Engine.

## 🚀 Quick Install (Recommended)

Run the automated installation script:

```bash
cd ~/Desktop/my-lead-engine
./install-dependencies.sh
```

This script will:
- ✅ Create virtual environments for Python services
- ✅ Install all dependencies automatically
- ✅ Set up Playwright for browser automation
- ✅ Generate gRPC proto files
- ✅ Install Node.js dependencies

---

## 📋 Manual Installation (Step-by-Step)

If you prefer to install manually or the script fails, follow these steps:

### 1. Scrapegoat (The Scraper)

```bash
cd ~/Desktop/my-lead-engine/scrapegoat

# Create and activate a clean environment
python3 -m venv venv
source venv/bin/activate

# Install with NO permission issues
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

**Verify installation:**
```bash
python3 -c "import fastapi, redis, playwright; print('✅ Scrapegoat dependencies OK')"
```

---

### 2. Chimera Brain (The AI)

```bash
cd ~/Desktop/my-lead-engine/chimera_brain

# Create and activate a clean environment
python3 -m venv venv
source venv/bin/activate

# Install and generate gRPC files
pip install --upgrade pip
pip install -r requirements.txt
chmod +x generate_proto.sh
./generate_proto.sh
```

**Verify installation:**
```bash
python3 -c "import grpc, torch, transformers; print('✅ Chimera Brain dependencies OK')"
```

---

### 3. BrainScraper (The UI)

```bash
cd ~/Desktop/my-lead-engine/brainscraper
npm install --legacy-peer-deps
```

**Verify installation:**
```bash
npm run build
```

---

## ⚠️ Troubleshooting

### Permission Denied on macOS

If you get permission errors, fix folder ownership:

```bash
sudo chown -R $(whoami) ~/Desktop/my-lead-engine
```

(This will ask for your Mac password. It ensures you have full ownership of the project folder.)

### Python3 Not Found

If `python3` is not found, install Python via Homebrew:

```bash
brew install python3
```

### pip3 Permission Errors

Use `--user` flag or virtual environment:

```bash
# Option 1: Use --user flag
pip3 install --user -r requirements.txt

# Option 2: Use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Node.js Not Found

Install Node.js via Homebrew:

```bash
brew install node
```

Or download from [nodejs.org](https://nodejs.org/)

---

## ✅ Verification Checklist

After installation, verify everything works:

- [ ] **Scrapegoat**: `cd scrapegoat && source venv/bin/activate && python3 -c "import fastapi; print('OK')"`
- [ ] **Chimera Brain**: `cd chimera_brain && source venv/bin/activate && python3 -c "import grpc; print('OK')"`
- [ ] **BrainScraper**: `cd brainscraper && npm run build`

---

## 📍 Where This Leaves Us

Once installation completes:

✅ **Local machine is 100% ready** to run the code  
✅ **All dependencies installed** in isolated virtual environments  
✅ **Code changes** (the `[::]` bindings) are already in the files  
✅ **Ready for Railway deployment** - all services configured

---

## 🚀 Next Steps

1. **Test locally:**
   ```bash
   # Terminal 1: Scrapegoat
   cd scrapegoat && source venv/bin/activate && python main.py
   
   # Terminal 2: Chimera Brain
   cd chimera_brain && source venv/bin/activate && python server.py
   
   # Terminal 3: BrainScraper
   cd brainscraper && npm run dev
   ```

2. **Deploy to Railway:**
   - All services are configured with correct root directories
   - Environment variables are set via Railway shared variables
   - Build commands are configured in `railway.toml` files

---

## 📝 Notes

- Each Python service uses its own virtual environment (isolated dependencies)
- Node.js dependencies are installed globally in `brainscraper/node_modules`
- Playwright browsers are installed in user directory (no sudo needed)
- gRPC proto files are generated automatically for Chimera Brain

---

**Status: Ready for Production** 🎯
