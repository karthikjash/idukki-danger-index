# Data Sources — How to Access IMD, NASA, KSDMA Data

## Overview

The Idukki Monsoon Danger Index integrates data from publicly accessible sources. This document explains how each source is accessed and how to set up live data fetching in production.

## Provider strategy (current build)

Every number on the dashboard is provider-tagged, and the provider mix is
keyed off one environment variable:

| Role | Provider when key set | Provider otherwise | Where |
|---|---|---|---|
| Current conditions (wind/humidity/cloud/temp/pressure/live rain) | **OpenWeatherMap** (`OPENWEATHERMAP_API_KEY` in `.env`) — refresh ~10 min | Open-Meteo | `data/openweather.py`, `data/fetcher.py` |
| Today's rain + 7-day danger outlook | Open-Meteo (OWM free forecast is only 5 days) | Open-Meteo | `data/fetcher.py` |
| Rainfall-outlook chart | **OpenWeatherMap** 5-day/3-hour (aggregated to IST days) | Open-Meteo 7-day | `data/observed.py::build_trends` |
| 30-day monsoon-pattern chart (measured) | Open-Meteo measured `past_days` (OWM free tier has **no history API**) | Open-Meteo measured | `data/observed.py` |
| 48 h wind/humidity/temperature chart | **OpenWeatherMap** 3-hour steps | Open-Meteo hourly | `data/observed.py` |
| Observed history store (soil saturation + ML retrains) | the project's own daily accumulator, seeded from Open-Meteo measured | same | `data/observed.py::LiveHistoryStore` |

Measured history constraint is fundamental to the free tiers: OpenWeatherMap
sells history (One-Call/History plans); it is not free. The project therefore
accumulates its own observed record day by day (each server boot closes the
previous fully-measured IST day), and retraining (`ml/train.py`) splices that
record onto the ERA5 archive.

Panchayat populations are authoritative (project owner, Census-2011 derived).
Ward structures live in `data/static/wards.json` (Kumily = real LSG Kerala
Election-2020 wards; others = modelled LSG-typical defaults). Ward populations
are apportioned equal shares until a Census-2011 ward table is supplied via
`data/static/wards_overrides.csv` (`locality,ward_no,ward_name,population,source`).

---

## 1. IMD (Indian Meteorological Department)

### Source
**Website:** https://mausam.imd.gov.in  
**Data:** Gridded rainfall forecasts, wind, humidity, pressure

### Current Access
- **Status:** Accessible via public web portal
- **Resolution:** 0.5° × 0.5° (~50 km)
- **Update Frequency:** 4× daily (00:00, 06:00, 12:00, 18:00 UTC)
- **Monsoon Season:** June 1 — September 30

### How to Fetch Live Data

#### Option 1: Manual Download (Development)
1. Visit https://mausam.imd.gov.in
2. Navigate to "Gridded Data"
3. Select region (latitude 9.4–9.75°N, longitude 76.55–76.95°E for inner Idukki)
4. Download GRIB or NetCDF format
5. Parse with Python: `rasterio` or `netCDF4`

#### Option 2: Public API (If Available)
IMD occasionally provides API access. Check:
```bash
curl https://api.weatherapi.com/weather.json
```

**Note:** As of Sept 2026, IMD does not have a documented public API. The system currently uses placeholder realistic data for development.

#### Option 3: Third-Party Weather API (Production)
For immediate deployment, use:

**OpenWeatherMap API:**
```bash
curl "https://api.openweathermap.org/data/2.5/forecast?lat=9.655&lon=76.775&appid=YOUR_API_KEY"
```

**Setup in code:**
```python
# data/fetcher.py
API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
def get_rainfall_forecast(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={API_KEY}"
    response = requests.get(url)
    return response.json()
```

---

## 2. NASA EarthData

### Source
**Website:** https://earthdata.nasa.gov  
**Data:** MODIS cloud cover, GPM IMERG precipitation

### Current Access

#### MODIS Cloud Cover
- **Product:** MOD06_L2 (Cloud Properties)
- **Resolution:** 250 m — 1 km
- **Update:** Daily
- **Access:** NASA EarthData (requires free account)

**Steps to Access:**
1. Register at https://earthdata.nasa.gov
2. Download MODIS data via:
   - Web portal: https://ladsweb.modaps.eosdis.nasa.gov
   - Python: `requests` + bearer token

**Example Python Code:**
```python
import requests

BEARER_TOKEN = os.getenv('NASA_BEARER_TOKEN')
headers = {'Authorization': f'Bearer {BEARER_TOKEN}'}

# Query MODIS for cloud cover
url = "https://api.nasa.gov/planetary/earth/imagery?"
params = {
    'lon': 76.775,
    'lat': 9.655,
    'dim': 0.15,  # 15 km
    'api_key': os.getenv('NASA_API_KEY')
}
response = requests.get(url, params=params, headers=headers)
```

#### GPM IMERG Precipitation
- **Product:** IMERG (Integrated Multi-satellitE Retrievals for GPM)
- **Resolution:** 11 km
- **Update:** 30 minutes (3-hour latency)
- **Access:** Google Earth Engine (simplest)

**Simplest Method: Google Earth Engine**

```python
import ee

ee.Authenticate()
ee.Initialize()

# Collection: NASA/GPM_L3/IMERG_V06
image = ee.ImageCollection('NASA/GPM_L3/IMERG_V06')\
    .filterDate('2026-09-01', '2026-09-02')\
    .first()

# Extract precipitation at Kumily
point = ee.Geometry.Point([76.775, 9.655])
value = image.sample(point, 11000).first().getInfo()
print(f"Precipitation: {value['precipitationCal']} mm")
```

---

## 3. KSDMA (Kerala State Disaster Management Authority)

### Source
**Website:** https://sdma.kerala.gov.in  
**Data:** Historical landslides, floods, dam incidents (2004–present)

### Current Access

#### Official Records
- **Format:** PDF reports, incident registers
- **Request:** Contact KSDMA directly
  - Email: info@sdma.kerala.gov.in
  - Phone: +91-471-2301234

#### Data We Use (Pre-loaded)
For development, we've pre-loaded sample incident data (5 incidents 2018–2020):

```python
# data/fetcher.py — KSDMADataFetcher.get_historical_incidents()
# Returns DataFrame with:
# - latitude, longitude, incident_type, year, severity, location, description
```

**To Update with Real Data:**
1. Request incident records from KSDMA
2. Georeferenced data (latitude/longitude)
3. Convert to CSV → Load into `data/incidents.csv`
4. Modify fetcher to read from CSV:

```python
def get_historical_incidents(self, bbox):
    df = pd.read_csv('data/incidents.csv')
    # Filter by bbox
    return df
```

---

## 4. Census of India (Population)

### Source
**Website:** https://censusindia.gov.in  
**Data:** Ward-level population (2021 Census)

### Current Access

#### Official Download
1. Visit https://censusindia.gov.in
2. Select "Kerala" → "Idukki District"
3. Download ward-level data (Excel)

#### Data Used
Pre-loaded in `index/calculator.py`:
```python
LOCALITY_POPULATION = {
    'Kumily': 45000,
    'Peermedu': 32000,
    'Idukki': 28000,
    # ... etc
}
```

**To Update:**
1. Download latest Census data
2. Parse CSV
3. Update LOCALITY_POPULATION dict

---

## 5. OpenStreetMap / ISRO Bhuvan (Terrain)

### Source
**OpenStreetMap:** https://www.openstreetmap.org  
**ISRO Bhuvan:** https://bhuvan.nrsc.gov.in

### Data Used
- Panchayat boundaries (GeoJSON)
- DEM (Digital Elevation Model) for terrain slope
- Road network

### How to Fetch

#### OpenStreetMap (Simplest)
```python
import requests

# Get panchayat boundary (GeoJSON)
url = "https://nominatim.openstreetmap.org/search"
params = {
    'q': 'Kumily panchayat, Idukki, Kerala',
    'format': 'geojson'
}
response = requests.get(url, params=params)
boundary = response.json()
```

#### ISRO Bhuvan
1. Visit https://bhuvan.nrsc.gov.in
2. Select "Idukki District"
3. Download DEM (GeoTIFF)
4. Process with `rasterio`:

```python
import rasterio
import numpy as np

with rasterio.open('dem_idukki.tif') as src:
    dem = src.read(1)  # Elevation data
    
    # Calculate slope
    from scipy.ndimage import gradient
    slope = np.gradient(dem)
```

---

## Production Setup

### Environment Variables

Create `.env` file:
```bash
# IMD/Weather
OPENWEATHERMAP_API_KEY=your_api_key_here

# NASA EarthData
NASA_BEARER_TOKEN=your_token_here
NASA_API_KEY=your_api_key_here

# Database (if using persistent storage)
DATABASE_URL=postgresql://user:pass@localhost/idukki_danger
```

### Data Refresh Cron Jobs

Add to crontab:

```bash
# Refresh every 6 hours
0 */6 * * * /usr/bin/python3 <PROJECT_ROOT>/data/refresh.py

# Refresh every 30 minutes (GPM IMERG)
*/30 * * * * /usr/bin/python3 <PROJECT_ROOT>/data/refresh_imerg.py
```

### Monitoring Data Freshness

```python
# api/server.py — Add endpoint
@app.get("/data-freshness")
async def get_data_freshness():
    return {
        "last_imd_update": _cache.get('imd_timestamp'),
        "last_nasa_update": _cache.get('nasa_timestamp'),
        "last_ksdma_update": _cache.get('ksdma_timestamp'),
        "data_age_minutes": (datetime.now() - _cache['last_update']).total_seconds() / 60
    }
```

---

## Data Quality & Limitations

### IMD
- ✅ Most reliable for rainfall forecasts
- ⚠️ 0.5° resolution (50 km) — may miss local variations
- ⚠️ Forecast skill reduces beyond 5 days

### NASA
- ✅ Global coverage, satellite-derived (objective)
- ⚠️ 11 km resolution for GPM — may miss microcells
- ⚠️ 3-hour latency on IMERG data

### KSDMA
- ✅ Official incident records
- ⚠️ May have reporting delays (weeks–months)
- ⚠️ Historical data may be incomplete pre-2010

### Census
- ✅ Authoritative population data
- ⚠️ Only updated every 10 years (next: 2031)
- ⚠️ May not reflect urban migration post-2021

---

## Testing Data Fetchers

```bash
# Test IMD fetcher
python3 -c "from data.fetcher import IMDDataFetcher; print(IMDDataFetcher().get_rainfall_forecast(9.655, 76.775))"

# Test NASA fetcher
python3 -c "from data.fetcher import NASADataFetcher; print(NASADataFetcher().get_cloud_cover(9.655, 76.775))"

# Test KSDMA fetcher
python3 -c "from data.fetcher import KSDMADataFetcher; print(KSDMADataFetcher().get_historical_incidents({}))"
```

---

## Troubleshooting

### "No data available" Error
1. Check internet connectivity
2. Verify API keys in `.env`
3. Check data source website status
4. Review rate limits (API calls/day)

### Stale Data
1. Check last update timestamp in `/health` endpoint
2. Verify cron job is running: `crontab -l`
3. Check logs: `tail /var/log/idukki_danger/*.log`

### Coordinate System Issues
- All coordinates use **WGS84 (EPSG:4326)**
- Format: latitude (9–10°N), longitude (76–77°E)
- Do NOT use other projections without conversion

---

## API Keys Required for Production

| Source | Key | Free Tier | Cost |
|--------|-----|-----------|------|
| OpenWeatherMap | API Key | Yes (60 calls/min) | $39/month (professional) |
| NASA EarthData | Bearer Token | Yes (unlimited) | Free |
| Google Earth Engine | API Key | Yes | Free (up to limits) |

---

## References

- **IMD Gridded Data:** https://mausam.imd.gov.in/mausam/en/Home
- **NASA EarthData Search:** https://search.earthdata.nasa.gov
- **Google Earth Engine:** https://earthengine.google.com
- **KSDMA:** https://sdma.kerala.gov.in
- **Census of India:** https://censusindia.gov.in
- **Bhuvan (ISRO):** https://bhuvan.nrsc.gov.in

---

**Document Version:** 1.0  
**Last Updated:** September 2026
