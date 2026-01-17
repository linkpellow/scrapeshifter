#!/bin/bash
# Permission-Proof Installation Script
# Installs all dependencies for the Triple-Vessel Stealth Extraction Engine

set -e  # Exit on any error

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "🚀 Starting installation from: $PROJECT_ROOT"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Triple-Vessel Stealth Extraction Engine${NC}"
echo -e "${BLUE}  Dependency Installation${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ============================================================================
# 1. SCRAPEGOAT (The Scraper)
# ============================================================================
echo -e "${GREEN}[1/3] Installing Scrapegoat (The Scraper)${NC}"
echo "─────────────────────────────────────────────────────────────"

cd "$PROJECT_ROOT/scrapegoat"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip --quiet

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright Chromium..."
playwright install chromium

echo -e "${GREEN}✅ Scrapegoat installation complete!${NC}"
echo ""

# ============================================================================
# 2. CHIMERA BRAIN (The AI)
# ============================================================================
echo -e "${GREEN}[2/3] Installing Chimera Brain (The AI)${NC}"
echo "─────────────────────────────────────────────────────────────"

cd "$PROJECT_ROOT/chimera_brain"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip --quiet

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Making generate_proto.sh executable..."
chmod +x generate_proto.sh

echo "Generating gRPC proto files..."
if [ -f "generate_proto.sh" ]; then
    ./generate_proto.sh
else
    echo -e "${YELLOW}⚠️  generate_proto.sh not found, skipping proto generation${NC}"
fi

echo -e "${GREEN}✅ Chimera Brain installation complete!${NC}"
echo ""

# ============================================================================
# 3. BRAINSCRAPER (The UI)
# ============================================================================
echo -e "${GREEN}[3/3] Installing BrainScraper (The UI)${NC}"
echo "─────────────────────────────────────────────────────────────"

cd "$PROJECT_ROOT/brainscraper"

if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install --legacy-peer-deps
else
    echo "Node modules already exist, skipping..."
fi

echo -e "${GREEN}✅ BrainScraper installation complete!${NC}"
echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 All dependencies installed successfully!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Activate Scrapegoat venv: cd scrapegoat && source venv/bin/activate"
echo "  2. Activate Chimera Brain venv: cd chimera_brain && source venv/bin/activate"
echo "  3. Start BrainScraper: cd brainscraper && npm run dev"
echo ""
echo "For Railway deployment, all services are ready!"
echo ""
