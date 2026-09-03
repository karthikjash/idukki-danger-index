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

PROJECT_DIR="/home/homie/Projects/SSR_system"

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Please run this script from the SSR_system directory:"
    echo "   cd /home/homie/Projects/SSR_system"
    echo "   ./quick-start.sh"
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
if python3 -c "import pandas, folium, streamlit, fastapi" 2>/dev/null; then
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
echo "1. Run Resident Web App (Streamlit) — Interactive UI for checking risk"
echo "2. Run API Server (FastAPI) — REST API for government integration"
echo "3. Run Demo — Show system capabilities (no server)"
echo "4. View Documentation"
echo "5. View Interactive Map"
echo "6. Exit"
echo

read -p "Enter your choice (1-6): " choice

case $choice in
    1)
        echo
        echo -e "${GREEN}Starting Streamlit Web App...${NC}"
        echo "Opening at: http://localhost:8501"
        echo
        echo "📍 Select your panchayat (Kumily, Peermedu, etc.)"
        echo "⚠️  View current Danger Level and guidance"
        echo
        sleep 2
        python3 -m streamlit run frontend/app.py
        ;;
    
    2)
        echo
        echo -e "${GREEN}Starting FastAPI Server...${NC}"
        echo "API available at: http://localhost:8000"
        echo
        echo "Interactive Docs: http://localhost:8000/docs"
        echo "API Endpoints:"
        echo "  • GET /index — All Danger Indices"
        echo "  • GET /index/{locality} — Single locality"
        echo "  • GET /map — Interactive map"
        echo "  • GET /incidents — Historical incidents"
        echo "  • GET /summary — Statistics"
        echo
        sleep 2
        python3 api/server.py
        ;;
    
    3)
        echo
        echo -e "${GREEN}Running End-to-End Demo...${NC}"
        echo
        python3 demo.py
        ;;
    
    4)
        echo
        echo -e "${BLUE}📚 Documentation Files:${NC}"
        echo
        echo "1. README.md"
        echo "   Quick start guide, feature overview, directory structure"
        echo
        echo "2. docs/METHODOLOGY.md"
        echo "   Complete danger index formulas, data sources, rationale"
        echo
        echo "3. docs/API_REFERENCE.md"
        echo "   REST API endpoint documentation with examples"
        echo
        read -p "Open README.md? (y/n): " open_readme
        if [ "$open_readme" = "y" ] || [ "$open_readme" = "Y" ]; then
            if command -v cat &> /dev/null; then
                less README.md
            else
                echo "Run: cat README.md"
            fi
        fi
        ;;
    
    5)
        echo
        echo -e "${GREEN}Generating Interactive Map...${NC}"
        python3 -c "
import sys
sys.path.insert(0, '.')
from data.fetcher import fetch_all_data_for_locality, LOCALITIES
from index.calculator import compute_index_for_locality
from index.map_generator import generate_danger_map
import pandas as pd

all_indices = {}
all_incidents = pd.DataFrame()

for locality in LOCALITIES.keys():
    data = fetch_all_data_for_locality(locality)
    rainfall_df = data['rainfall_forecast']
    current_rainfall = rainfall_df['rainfall_mm'].iloc[-1] if not rainfall_df.empty else 100
    
    weather = {
        'rainfall_mm': current_rainfall,
        'wind_mps': data['wind_data']['wind_speed_mps'],
        'humidity_pct': data['humidity_data']['relative_humidity_pct'],
        'cloud_cover_pct': data['cloud_cover']['cloud_cover_pct']
    }
    
    result = compute_index_for_locality(locality, weather)
    all_indices[locality] = result
    
    if all_incidents.empty:
        all_incidents = data['historical_incidents']

generate_danger_map(all_indices, all_incidents, 'idukki_danger_map.html')
print('Map saved to: idukki_danger_map.html')
" 2>&1 | grep -v "^INFO:"
        echo
        echo "✓ Map generated!"
        echo "Open in browser: file://$(pwd)/idukki_danger_map.html"
        ;;
    
    6)
        echo "Goodbye!"
        exit 0
        ;;
    
    *)
        echo "Invalid choice. Please try again."
        ;;
esac
