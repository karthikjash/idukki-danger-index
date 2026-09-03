# Idukki Monsoon Danger Index — Documentation

## Overview

The **Idukki Monsoon Danger Index** is a hyperlocal forecasting system that communicates seasonal monsoon severity to non-technical residents of inner Idukki district, Kerala, through a colour-coded map and plain-language interface.

The system aggregates gridded rainfall, wind, humidity, and cloud data from public sources (IMD, NASA EarthData, KSDMA) and produces a real-time **4-tier Danger Index** (Low / Moderate / High / Extreme) for each locality (taluk/panchayat level) in inner Idukki.

---

## Data Sources (Public, Confirmed Accessible)

### 1. **Rainfall & Weather Data**
- **IMD (Indian Meteorological Department):** `mausam.imd.gov.in`
  - Gridded forecasts (0.5°×0.5° resolution)
  - Monsoon outlooks
  - Wind & humidity data
- **Alternative:** OpenWeatherMap API (free tier available)
  - Supplementary rainfall and wind data for cross-validation

### 2. **Cloud & Precipitation Data**
- **NASA EarthData:**
  - MODIS cloud cover (250m resolution, daily)
  - GPM IMERG precipitation radar (11km resolution, 30-min updates)
  - Access: Direct download or Google Earth Engine

### 3. **Historical Calamity Records**
- **KSDMA (Kerala State Disaster Management Authority):**
  - Documented landslides (2004–present)
  - Flood events (2004–present)
  - Dam-related incidents
  - Incident type, date, location, severity classification

### 4. **Geospatial & Population Data**
- **OpenStreetMap / ISRO Bhuvan:** Administrative boundaries, terrain, roads
- **Census of India (2021):** Ward-level population density for inner Idukki

---

## Danger Index Methodology

### Index Composition

The **Composite Danger Index** combines three independent sub-scores:

| Sub-Score | Weight | Definition | Range |
|-----------|--------|------------|-------|
| **Environmental Severity** | 40% | Rainfall intensity, wind speed, humidity, cloud cover | 0–1 |
| **Structural Risk** | 35% | Terrain slope, soil saturation, historical damage patterns | 0–1 |
| **Human Threat Level** | 25% | Population exposure, evacuation difficulty | 0–1 |

### Calculation Formula

```
Composite Score = (0.40 × Env. Severity) + (0.35 × Struct. Risk) + (0.25 × Human Threat)

Tier Assignment:
  Score < 0.25   →  "Low"
  0.25 ≤ Score < 0.50  →  "Moderate"
  0.50 ≤ Score < 0.75  →  "High"
  Score ≥ 0.75   →  "Extreme"
```

### Sub-Score Definitions

#### 1. Environmental Severity (40% weight)
**Indicators:**
- **Rainfall intensity** (45% of sub-score): Normalized 0–1 at 200 mm/day (extreme monsoon)
- **Wind speed** (25% of sub-score): Normalized 0–1 at 15 m/s
- **Humidity** (15% of sub-score): Normalized 0–1 above 95%
- **Cloud cover** (15% of sub-score): Normalized 0–1 at 100%

**Rationale:** During SW monsoon (June–September), rainfall is the primary driver of hazards in inner Idukki. Wind and humidity amplify instability.

#### 2. Structural Risk (35% weight)
**Indicators:**
- **Terrain slope** (50% of sub-score): Inner Idukki ranges 65°–90°; risk increases with slope
- **Historical incident frequency** (20% of sub-score): Normalized count of past incidents by locality (2004–present)
- **Infrastructure exposure** (15% of sub-score): Population as proxy for buildings/roads at risk
- **Soil saturation** (15% of sub-score): ~0.85 (fixed, high during monsoon)

**Rationale:** Steep slopes + saturated soils + past patterns = structural failure probability. Population acts as a proxy for infrastructure density.

#### 3. Human Threat Level (25% weight)
**Indicators:**
- **Population exposure** (35% of sub-score): Census ward-level population normalized by max in inner Idukki
- **Rainfall-driven threat** (45% of sub-score): Direct danger to life (normalized at 150 mm/day)
- **Evacuation difficulty** (20% of sub-score): Terrain-based accessibility; steep areas harder to evacuate

**Rationale:** More people in hilly areas without easy roads = higher threat. Rainfall > 150 mm/day poses acute danger to life.

---

## Architecture

### Directory Structure

```
/SSR_system/
├── /data/
│   └── fetcher.py              # IMD, NASA, KSDMA data ingestion
├── /index/
│   ├── calculator.py           # Danger Index computation
│   └── map_generator.py        # Folium-based map rendering
├── /api/
│   └── server.py               # FastAPI REST backend
├── /frontend/
│   └── app.py                  # Streamlit resident UI
├── requirements.txt            # Python dependencies
├── README.md                   # Quick start guide
└── /docs/
    ├── METHODOLOGY.md          # This file
    ├── DATA_SOURCES.md         # Detailed data access
    └── API_REFERENCE.md        # API endpoint documentation
```

### Core Modules

#### 1. `data/fetcher.py`
**Purpose:** Ingest and aggregate gridded weather and historical incident data

**Key Classes:**
- `IMDDataFetcher()` — Rainfall, wind, humidity (6-hourly forecasts)
- `NASADataFetcher()` — Cloud cover, precipitation (satellite-derived)
- `KSDMADataFetcher()` — Historical incidents (2004–present)

**Example:**
```python
from data.fetcher import fetch_all_data_for_locality
data = fetch_all_data_for_locality('Kumily')
# Returns: rainfall_forecast, wind_data, humidity_data, cloud_cover, incidents
```

#### 2. `index/calculator.py`
**Purpose:** Compute Danger Index sub-scores and composite tier

**Key Class:** `DangerIndexCalculator(locality)`
- `calculate_environmental_severity(rainfall, wind, humidity, cloud_cover)` → 0–1
- `calculate_structural_risk()` → 0–1
- `calculate_human_threat_level(rainfall)` → 0–1
- `calculate_composite_index()` → (tier, score)

**Tier Colors:**
- 🟢 Low: `#2ecc71`
- 🟠 Moderate: `#f39c12`
- 🔴 High: `#e74c3c`
- 🔴 Extreme: `#8b0000`

#### 3. `index/map_generator.py`
**Purpose:** Generate interactive Folium map with zones and incident overlay

**Key Function:**
```python
generate_danger_map(
    locality_indices: {locality: index_result},
    historical_incidents: DataFrame,
    output_file: str
) → filepath
```

**Features:**
- Circle zones per locality, color-coded by tier
- Toggleable incident layer (landslides, floods, dam events)
- Legend and layer controls
- Popup descriptions (plain-language risk)

#### 4. `api/server.py`
**Purpose:** REST API serving forecasts, indices, and maps

**Key Endpoints:**
- `GET /index` — All localities' Danger Index
- `GET /index/{locality}` — Single locality
- `GET /map` — Interactive HTML map
- `GET /incidents` — Historical incidents (GeoJSON-ready)
- `GET /summary` — Tier breakdown statistics

#### 5. `frontend/app.py`
**Purpose:** Streamlit web app for resident-facing interface

**Features:**
- Locality selector (dropdown)
- Plain-language current risk (no jargon)
- Three sub-scores displayed as metrics
- 7-day rainfall forecast chart
- What-to-do guidance (tier-specific, plain language)
- Recent incidents overlay
- Embedded interactive map toggle

---

## Danger Index Tiers — Interpretation Guide

### 🟢 LOW (Score < 0.25)
**Meaning:** Safe conditions. Normal activity is safe.

**Indicators:**
- Rainfall < 75 mm/day
- Wind < 7 m/s
- Low humidity and cloud cover

**Resident Guidance:**
- ✅ Normal work and travel is safe
- ✅ Schools, markets, offices open as usual
- ⚠️ Stay alert; monitor updates daily

**Official Action:** None; continue normal operations.

---

### 🟠 MODERATE (Score 0.25–0.50)
**Meaning:** Caution. Heavy rainfall likely; avoid unnecessary travel.

**Indicators:**
- Rainfall 75–150 mm/day
- Wind 7–10 m/s
- Moderate humidity and cloud cover

**Resident Guidance:**
- ⚠️ Avoid non-essential travel, especially to hilly areas
- ⚠️ Keep children and elderly indoors during heavy downpours
- ⚠️ Avoid crossing flooded/muddy roads
- ✅ Continue essential work with care

**Official Action:** Heightened monitoring; panchayats on alert.

---

### 🔴 HIGH (Score 0.50–0.75)
**Meaning:** Danger. Very heavy rainfall and strong winds. Landslides/flooding possible.

**Indicators:**
- Rainfall 150–200 mm/day
- Wind 10–15 m/s
- High humidity and cloud cover
- Close to historical incident zones

**Resident Guidance:**
- 🚨 **STAY INDOORS.** Avoid all non-essential travel.
- 🚨 Keep go-bags packed (documents, valuables, water, medicines)
- 🚨 Avoid stepping near streams, rivers, and slopes
- ✅ Only go out for critical medical/grocery needs with adult supervision

**Official Action:** Evacuation alert issued. Schools and offices may close. Shelters prepared.

---

### 🔴 EXTREME (Score ≥ 0.75)
**Meaning:** **SEVERE DANGER.** Life-threatening conditions. Evacuate if ordered.

**Indicators:**
- Rainfall > 200 mm/day
- Wind > 15 m/s
- Very high humidity and cloud cover
- Potential dam spillway events, catastrophic landslides

**Resident Guidance:**
- 🚨 **EVACUATE IMMEDIATELY if told by authorities.**
- 🚨 Go to panchayat-designated shelter with essential items.
- 🚨 **STAY AWAY** from rivers, dams, slopes, landslide-prone areas.
- 🚨 Do NOT wait for reminders; leave early if warned.
- 📞 **Emergency: 112 (national) or 1077 (Kerala Disaster)**

**Official Action:** Evacuation orders issued. All non-essential services close. Emergency response activated.

---

## Limitations & Caveats

1. **Data Quality:** Forecast depends on IMD/NASA data quality. Real-time updates subject to satellite overpass frequency.

2. **Locality Resolution:** Index computed at panchayat level (~7–8 km²). Micro-scale variations within a panchayat not captured.

3. **Model Simplicity:** Composite index uses weighted sum, not machine learning. Explainability is prioritized over black-box accuracy.

4. **Historical Bias:** Index relies on 2004–present incident records from KSDMA. Pre-2004 patterns not included; emerging hazards not yet in data.

5. **Update Frequency:** Computed 2× daily (6 AM, 6 PM IST). Real-time intra-day changes may not be captured immediately.

6. **Population Proxy:** Uses Census 2021. Urban growth/migration not yet reflected.

---

## How to Use (Residents)

1. **Open the app:** `streamlit run frontend/app.py`
2. **Select your panchayat** from the dropdown
3. **Read the current Danger Level** in plain language
4. **Check the sub-scores** to understand drivers (rainfall, terrain, people)
5. **Follow the "What to do" guidance** for your tier
6. **Check nearby past incidents** to understand local hazards
7. **View the map** to see risk across inner Idukki
8. **Call for help** if you see emergency: **112** or **1077**

---

## How to Integrate with Government Systems

1. **SMS Alerts:** Trigger SMS warnings to registered phone numbers when tier ≥ High
2. **Radio/TV:** Broadcast tier summary (e.g., "Kumily: Extreme Risk")
3. **Panchayat Dashboards:** Display real-time index on public displays
4. **Warning Sirens:** Auto-trigger evacuation sirens at Extreme tier
5. **ERP Integration:** Link to state ERP for supply chain, school closures, etc.

---

## References

- **IMD:** https://mausam.imd.gov.in
- **KSDMA:** https://sdma.kerala.gov.in
- **NASA EarthData:** https://earthdata.nasa.gov
- **Census of India 2021:** https://censusindia.gov.in
- **Folium Documentation:** https://python-visualization.github.io/folium
- **Streamlit Documentation:** https://docs.streamlit.io

---

**Document Version:** 1.0  
**Last Updated:** September 2026  
**Author:** Idukki Monsoon Danger Index Team
