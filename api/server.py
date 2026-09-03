"""
FastAPI Backend for Idukki Monsoon Danger Index
Serves forecast data, Danger Index, and map generation
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
import pandas as pd
import logging
from datetime import datetime
import os
import sys
import json
from pathlib import Path

# Add project paths
sys.path.insert(0, '/home/homie/Projects/SSR_system')

from data.fetcher import fetch_all_data_for_locality, LOCALITIES
from index.calculator import compute_index_for_locality
from index.map_generator import generate_danger_map

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Idukki Monsoon Danger Index API",
    description="Hyperlocal monsoon severity forecasting for inner Idukki",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for API responses
class SubScores(BaseModel):
    environmental_severity: float
    structural_risk: float
    human_threat_level: float

class DangerIndexResponse(BaseModel):
    locality: str
    tier: str
    composite_score: float
    sub_scores: SubScores
    color: str
    description: str
    timestamp: str
    latitude: float
    longitude: float

class HistoricalIncident(BaseModel):
    latitude: float
    longitude: float
    incident_type: str
    year: int
    severity: str
    location: str
    description: str

class LocalityListResponse(BaseModel):
    localities: List[str]
    count: int


# In-memory cache for forecast data (6-hour refresh interval)
_cache = {
    'indices': {},
    'incidents': None,
    'last_update': None,
    'cache_file': '/tmp/ssr_cache/indices_cache.json'
}

def _load_cached_indices() -> Dict[str, Dict]:
    """Load indices from persistent cache file"""
    cache_file = Path(_cache['cache_file'])
    
    if not cache_file.exists():
        return {}
    
    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
            # Check cache validity (6 hours)
            cached_time = datetime.fromisoformat(data.get('timestamp', ''))
            if (datetime.now() - cached_time).total_seconds() < 6 * 3600:
                logger.info(f"Loaded cached indices from {cache_file}")
                return data.get('indices', {})
    except Exception as e:
        logger.warning(f"Failed to load cached indices: {e}")
    
    return {}

def _save_cached_indices(indices: Dict[str, Dict]):
    """Save indices to persistent cache file"""
    try:
        cache_file = Path(_cache['cache_file'])
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'indices': indices
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2, default=str)
        
        logger.info(f"Saved indices to cache: {cache_file}")
    except Exception as e:
        logger.warning(f"Failed to save indices to cache: {e}")


def compute_all_indices() -> Dict[str, Dict]:
    """Compute Danger Index for all inner-Idukki localities"""
    
    indices = {}
    
    for locality in LOCALITIES.keys():
        try:
            # Fetch data
            data = fetch_all_data_for_locality(locality)
            
            # Extract weather metrics
            rainfall_df = data['rainfall_forecast']
            current_rainfall = rainfall_df['rainfall_mm'].iloc[-1] if not rainfall_df.empty else 100
            
            weather_data = {
                'rainfall_mm': current_rainfall,
                'wind_mps': data['wind_data']['wind_speed_mps'],
                'humidity_pct': data['humidity_data']['relative_humidity_pct'],
                'cloud_cover_pct': data['cloud_cover']['cloud_cover_pct']
            }
            
            # Compute index
            result = compute_index_for_locality(locality, weather_data)
            result['latitude'] = LOCALITIES[locality]['lat']
            result['longitude'] = LOCALITIES[locality]['lon']
            indices[locality] = result
            
        except Exception as e:
            logger.error(f"Error computing index for {locality}: {e}")
            # Return safe defaults
            indices[locality] = {
                'locality': locality,
                'tier': 'Moderate',
                'composite_score': 0.45,
                'environmental_severity': 0.4,
                'structural_risk': 0.45,
                'human_threat': 0.45,
                'color': '#f39c12',
                'description': 'Unable to fetch data; showing default risk level.',
                'timestamp': datetime.now().isoformat(),
                'latitude': LOCALITIES[locality]['lat'],
                'longitude': LOCALITIES[locality]['lon']
            }
    
    return indices


def get_historical_incidents() -> pd.DataFrame:
    """Get historical incidents (cached)"""
    if _cache['incidents'] is None:
        from data.fetcher import KSDMADataFetcher
        fetcher = KSDMADataFetcher()
        _cache['incidents'] = fetcher.get_historical_incidents(
            {'north': 9.75, 'south': 9.40, 'east': 76.95, 'west': 76.55}
        )
    return _cache['incidents']


@app.on_event("startup")
async def startup_event():
    """Compute indices on startup, using cache if valid"""
    logger.info("Initializing Danger Index...")
    
    # Try to load from cache first
    _cache['indices'] = _load_cached_indices()
    
    # If cache is empty or invalid, compute fresh indices
    if not _cache['indices']:
        logger.info("Cache empty or invalid, computing fresh indices...")
        _cache['indices'] = compute_all_indices()
        _save_cached_indices(_cache['indices'])
    
    _cache['incidents'] = get_historical_incidents()
    _cache['last_update'] = datetime.now()
    logger.info("Ready to serve requests")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with info"""
    return """
    <html>
        <head>
            <title>Idukki Monsoon Danger Index API</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                h1 { color: #2c3e50; }
                code { background: #ecf0f1; padding: 2px 6px; border-radius: 3px; }
                ul { line-height: 1.8; }
            </style>
        </head>
        <body>
            <h1>🌧️ Idukki Monsoon Danger Index API</h1>
            <p>Hyperlocal monsoon severity forecasting for inner Idukki district, Kerala</p>
            
            <h2>API Endpoints</h2>
            <ul>
                <li><code>GET /localities</code> — List all monitored localities</li>
                <li><code>GET /index</code> — Get Danger Index for all localities</li>
                <li><code>GET /index/{locality}</code> — Get Danger Index for one locality</li>
                <li><code>GET /map</code> — Interactive map (HTML)</li>
                <li><code>GET /incidents</code> — Historical incidents (2004-present)</li>
                <li><code>GET /health</code> — Health check</li>
                <li><code>GET /docs</code> — API documentation (Swagger UI)</li>
            </ul>
            
            <h2>Quick Start</h2>
            <pre>
# Get all indices
curl http://localhost:8000/index

# Get index for Kumily
curl http://localhost:8000/index/Kumily

# View interactive map
open http://localhost:8000/map
            </pre>
            
            <h2>Data Sources</h2>
            <ul>
                <li><strong>Rainfall/Weather:</strong> IMD (mausam.imd.gov.in), OpenWeatherMap</li>
                <li><strong>Cloud/Precipitation:</strong> NASA MODIS, GPM IMERG</li>
                <li><strong>Historical Incidents:</strong> KSDMA (2004-present)</li>
                <li><strong>Geography:</strong> OpenStreetMap, Census India</li>
            </ul>
        </body>
    </html>
    """


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "last_update": _cache['last_update'],
        "localities_computed": len(_cache['indices']),
        "incidents_loaded": len(_cache['incidents']) if _cache['incidents'] is not None else 0
    }


@app.get("/localities", response_model=LocalityListResponse)
async def get_localities():
    """List all monitored localities"""
    locality_list = list(LOCALITIES.keys())
    return {
        "localities": sorted(locality_list),
        "count": len(locality_list)
    }


@app.get("/index", response_model=List[DangerIndexResponse])
async def get_all_indices():
    """Get Danger Index for all localities (from cache)"""
    
    if not _cache['indices']:
        # Try to load from cache
        _cache['indices'] = _load_cached_indices()
        
        # If still empty, compute fresh
        if not _cache['indices']:
            logger.warning("No cached indices, computing fresh...")
            _cache['indices'] = compute_all_indices()
            _save_cached_indices(_cache['indices'])
    
    results = []
    for locality, index_data in _cache['indices'].items():
        results.append(DangerIndexResponse(
            locality=index_data['locality'],
            tier=index_data['tier'],
            composite_score=index_data['composite_score'],
            sub_scores=SubScores(
                environmental_severity=index_data['environmental_severity'],
                structural_risk=index_data['structural_risk'],
                human_threat_level=index_data['human_threat']
            ),
            color=index_data['color'],
            description=index_data['description'],
            timestamp=index_data['timestamp'],
            latitude=index_data['latitude'],
            longitude=index_data['longitude']
        ))
    
    return results


@app.get("/index/{locality}", response_model=DangerIndexResponse)
async def get_locality_index(locality: str):
    """Get Danger Index for specific locality"""
    
    if locality not in LOCALITIES:
        raise HTTPException(status_code=404, detail=f"Locality '{locality}' not found")
    
    if not _cache['indices']:
        _cache['indices'] = compute_all_indices()
    
    if locality not in _cache['indices']:
        raise HTTPException(status_code=500, detail=f"Failed to compute index for {locality}")
    
    index_data = _cache['indices'][locality]
    
    return DangerIndexResponse(
        locality=index_data['locality'],
        tier=index_data['tier'],
        composite_score=index_data['composite_score'],
        sub_scores=SubScores(
            environmental_severity=index_data['environmental_severity'],
            structural_risk=index_data['structural_risk'],
            human_threat_level=index_data['human_threat']
        ),
        color=index_data['color'],
        description=index_data['description'],
        timestamp=index_data['timestamp'],
        latitude=index_data['latitude'],
        longitude=index_data['longitude']
    )


@app.get("/incidents", response_model=List[HistoricalIncident])
async def get_incidents():
    """Get historical incidents (2004-present) in inner Idukki"""
    
    incidents_df = get_historical_incidents()
    
    results = []
    for _, row in incidents_df.iterrows():
        results.append(HistoricalIncident(
            latitude=row['latitude'],
            longitude=row['longitude'],
            incident_type=row['incident_type'],
            year=row['year'],
            severity=row['severity'],
            location=row['location'],
            description=row['description']
        ))
    
    return results


@app.get("/map", response_class=HTMLResponse)
async def get_map():
    """Generate and serve interactive danger map"""
    
    map_file = "/tmp/idukki_danger_map.html"
    
    # Generate map with current indices and incidents
    indices = _cache['indices'] or compute_all_indices()
    incidents = get_historical_incidents()
    
    generate_danger_map(indices, incidents, map_file)
    
    # Read and return HTML
    with open(map_file, 'r') as f:
        return f.read()


@app.get("/summary")
async def get_summary():
    """Get summary statistics for all localities"""
    
    indices = _cache['indices'] or compute_all_indices()
    
    tier_counts = {}
    avg_score = 0
    
    for locality, data in indices.items():
        tier = data['tier']
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        avg_score += data['composite_score']
    
    avg_score /= len(indices) if indices else 1
    
    return {
        "total_localities": len(indices),
        "tier_breakdown": tier_counts,
        "average_danger_score": round(avg_score, 2),
        "last_computed": _cache['last_update'],
        "status": "OK"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
