#!/bin/bash
# Idukki Monsoon Danger Index — Quick Start Script

set -e

echo "🌧️  Idukki Monsoon Danger Index — Quick Start"
echo "=============================================="
echo

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Resolve the project root from this script's own location, so it works no
# matter where the repository is checked out or invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Could not find requirements.txt next to quick-start.sh"
    echo "   Make sure the script stays inside the project root."
    exit 1
fi

echo -e "${BLUE}Step 1: Checking Python and dependencies${NC}"
echo

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION found"

# Check if dependencies are installed
if python3 -c "import pandas, folium, fastapi" 2>/dev/null; then
    echo "✓ All dependencies installed"
else
    echo "⚠️  Installing dependencies..."
    pip install -q -r requirements.txt
    echo "✓ Dependencies installed"
fi

echo

# Menu
echo -e "${BLUE}What would you like to do?${NC}"
echo
echo "1. Run the Dashboard + API  — opens http://localhost:8000 (recommended)"
echo "2. Run Demo                 — show system capabilities (no server)"
echo "3. View Documentation"
echo "4. Generate Map File (HTML)"
echo "5. Exit"
echo

read -p "Enter your choice (1-5): " choice

case $choice in
    1)
        echo
        echo -e "${GREEN}Starting the web server...${NC}"
        echo "🌐 Dashboard: http://localhost:8000"
        echo "📚 API docs:   http://localhost:8000/docs"
        echo
        echo "The dashboard shows the district overview, per-locality risk,"
        echo "plain-language guidance, the 7-day rainfall outlook, and the"
        echo "interactive danger map."
        echo
        sleep 2
        python3 api/server.py
        ;;

    2)
        echo
        echo -e "${GREEN}Running End-to-End Demo...${NC}"
        echo
        python3 demo.py
        ;;

    3)
        echo
        echo -e "${BLUE}📚 Documentation Files:${NC}"
        echo
        echo "1. README.md — quick start, features, methodology overview"
        echo "2. docs/METHODOLOGY.md — danger index formulas, seasonality"
        echo "3. docs/API_REFERENCE.md — REST endpoints with examples"
        echo "4. docs/DATA_SOURCES.md — live data feeds and setup"
        echo
        read -p "Open README.md? (y/n): " open_readme
        if [ "$open_readme" = "y" ] || [ "$open_readme" = "Y" ]; then
            less README.md 2>/dev/null || cat README.md
        fi
        ;;

    4)
        echo
        echo -e "${GREEN}Generating Interactive Map...${NC}"
        python3 - <<'PY' 2>&1 | grep -v "^INFO:"
from index.calculator import compute_all_locality_indices
from index.map_generator import generate_danger_map
import pandas as pd

indices, incidents = compute_all_locality_indices()
if incidents is None:
    incidents = pd.DataFrame()

generate_danger_map(indices, incidents, 'idukki_danger_map.html')
print('Map saved to: idukki_danger_map.html')
PY
        echo
        echo -e "✓ Map generated!"
        echo "Open in browser: file://$(pwd)/idukki_danger_map.html"
        ;;

    5)
        echo "Goodbye!"
        exit 0
        ;;

    *)
        echo "Invalid choice. Please try again."
        ;;
esac
