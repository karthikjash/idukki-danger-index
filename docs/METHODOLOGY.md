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

The **Composite Danger Index** combines three sub-scores:

| Sub-Score | Weight | Definition | Range |
|-----------|--------|------------|-------|
| **Environmental Severity** | 60% | Rainfall (IMD 24h categories), wind, humidity, cloud cover | 0–1 |
| **Structural Risk** | 25% | Terrain, soil saturation, historical patterns — **rainfall-gated** | 0–1 |
| **Human Threat Level** | 15% | Population exposure, rainfall-driven danger, evacuation | 0–1 |

### Calculation Formula

```
Composite Score = (0.60 × Env. Severity) + (0.25 × Struct. Risk) + (0.15 × Human Threat)

Tier Assignment:
  Score < 0.25   →  "Low"
  0.25 ≤ Score < 0.50  →  "Moderate"
  0.50 ≤ Score < 0.70  →  "High"
  Score ≥ 0.70   →  "Extreme"
```

### Seasonality (v1.1) — why most of Idukki shows LOW most of the year

The district's real danger window is the **south-west monsoon (June–September)**.
To reflect that:

1. **Rainfall is scored against the IMD 24-hour categories** (light / moderate /
   rather heavy / heavy / very heavy / extremely heavy), not against a single
   observed day's value.
2. **Season scaling** — rainfall-driven danger is multiplied by a monthly
   factor (1.0 during the monsoon, ~0.6 in May/October transition months,
   0.25–0.35 in the dry season). The same 40 mm day is therefore a "Moderate"
   monsoon day but a non-event in January.
3. **Structural risk is rainfall-gated.** Terrain steepness, soil saturation
   and historical incident density only contribute while rain is actually
   falling (`activation = min(rainfall / 150 mm, 1)`). Past incidents alone can
   never raise the tier — they amplify risk only during wet weather.

This removes the earlier over-fit in which scoring was calibrated to a single
observed day and localities looked at risk purely because incidents had
happened there in past monsoons.

> Authoritative constants live at the top of `index/calculator.py`
> (`RAIN_KNOTS`, `SEASON_SCALE`, `W_ENV`/`W_STRUCT`/`W_HUMAN`,
> `T_LOW`/`T_MOD`/`T_HIGH`, `RAIN_ACTIVATION_MM`). Sub-score details below
> describe the design and may lag minor value changes.

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
/idukki-danger-index/
├── /data/
│   └── fetcher.py              # IMD, NASA, KSDMA data ingestion
├── /index/
│   ├── calculator.py           # Danger Index computation
│   └── map_generator.py        # Folium-based map rendering
├── /api/
│   └── server.py               # FastAPI REST backend
├── /frontend/
│   └── /static/                # Dashboard UI (HTML/CSS/JS)
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
- 🟠 Moderate: `#f5a623`
- 🔴 High: `#ff5252`
- 🔴 Extreme: `#b0102e`

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

#### 5. Dashboard UI (`frontend/static/`)
**Purpose:** HTML/CSS/JS dashboard served by the API at `/`

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

1. **Open the app:** `python3 api/server.py` and visit http://localhost:8000
2. **See the district overview**, then tap any locality card
3. **Read the current Danger Level** in plain language
4. **Check the sub-scores** to understand drivers (weather, terrain, people)
5. **Follow the "What to do" guidance** for your tier
6. **Check nearby past incidents** to understand local hazards
7. **View the map** tab to see risk across inner Idukki
8. **Call for help** if you see an emergency: **112** or **1077**

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
- **FastAPI Documentation:** https://fastapi.tiangolo.com

---

## ML Prediction Engine & Seasonal Outlook (v1.2)

### ML suite (`ml/`, pure NumPy)

Every locality gets its own small models, trained on the Open-Meteo/ERA5
historical rainfall record (2012 → yesterday, ~5,300 days per locality):

- **LSTM rainfall forecaster** — one hidden layer (10 units), 30-day causal
  input window of [rain, 3/7-day accumulation, day-of-year sine/cosine],
  Adam + truncated BPTT, predicts next-day rainfall (mm).
- **Ridge baseline** — closed-form ridge regression over the same engineered
  features (rolling accumulations 3/7/15/30-day, wet-streak, dryness count,
  seasonal dummies) for comparison.
- **Hazard classifier** — logistic regression (L2, mini-batch GD) over the
  features predicting P(rain ≥ 100 mm tomorrow), evaluated by ROC-AUC and
  top-decile precision rather than accuracy (positive class ≈ 1–3% of days).

Training is **chronologically split**: 2012–2019 train, 2020+ held out — so
the evaluation window overlaps the 2020–25 recorded incident era and the
metrics in `ml/models/eval.json` are honest out-of-sample numbers.

> Why pure NumPy? So the entire AI suite installs and runs with only
> `numpy + pandas`. The proposal's TensorFlow/scikit-learn stack can replace
> `ml/models.py` without changing any caller (same `fit/predict/save/load`
> surface).

### Seasonal outlook (`outlook/`)

- **ENSO (El Niño/La Niña)** — parsed from the vendored NOAA CPC Oceanic Niño
  Index table; surfaced as season-level context (weaker SW monsoon during El
  Niño, stronger NE monsoon during La Niña). Advisory only — ENSO is not a
  direct input to the daily Danger Index.
- **Lightning** — climatological risk per locality from Kerala's monthly
  strike curve (pre-monsoon Apr–May peak, NE-monsoon Oct–Nov secondary),
  scaled by highland exposure. Clearly labelled as a climatology model;
  a live strike feed can be added behind the same API shape.

### Administrator reports (`reporting/`)

`GET /report` renders the district or per-locality risk position — headline
tier, sub-scores, weather, drivers, incidents and seasonal context — as a
printable PDF (fpdf2) or DOCX (stdlib OOXML writer, no lxml dependency), for
submission to the District Collector / KSDMA.

### 7-day danger outlook (`GET /danger-forecast/{locality}`)

The live Danger Index answers "what is the risk NOW". The outlook answers
"is danger coming this week": the SAME scoring model (60/25/15 weights,
IMD rainfall bands, rainfall-gated structural risk, season scale) is run once
per forecast day on that day's Open-Meteo rainfall and chance-of-rain
probability. A day that reaches Moderate/High/Extreme is therefore visible
3–5 days before it arrives, along with its drivers (e.g. "heavy rain on
historically sensitive terrain"). Wind/humidity/cloud for future days follow
the latest observation, since those are not predictable a week out — rainfall
is the dominant input and gates landslide risk, so this is a conservative,
documented assumption rather than a silent one.

# v1.3 — calibration, weighting and hyperlocal layers

## Structural-risk weighting (government/industry framing)

Past-landslide/flood records now *validate* rather than drive the index, in
the spirit of NDMA / BIS IS-14496-style susceptibility zonation. The
structural channel (rainfall-gated) uses:

| Factor | Weight | Source of value |
|---|---|---|
| Terrain / slope | 40% | per-locality slope table (SRTM-derived when added) |
| Soil saturation | 25% | monsoon baseline **sharpened by measured 3-day rain** (`data/observed.py` store) when available |
| Population exposure | 20% | authoritative panchayat totals ÷ district max |
| Incident history | 15% | **derived from the register**: incidents within 20 km, severity × recency-decay (1/(years+1)), capped at 0.30 |

The old hand-set `HISTORICAL_INCIDENT_FACTOR` constants are gone — the factor
is computed from the actual incident record every run, so swapping in the
real KSDMA register changes behaviour automatically. Historical risk can only
express itself through the rainfall gate (never in dry weather).

## Ward-level micro-zonation

Each panchayat is split into its LSG ward structure (`data/static/wards.json`;
Kumily = real LSG Election-2020 wards). Every ward gets a deterministic
geometric centre inside the panchayat, and a **sensitivity** score from the
recorded incidents within ~5 km (severity- and recency-weighted). The ward
danger score = panchayat composite danger × (1 + 1.6 × sensitivity), so
wards escalate in the right order during heavy rain while staying calm when
the panchayat is calm. Populations are apportioned from the authoritative
panchayat totals (equal share until a Census-2011 ward table is supplied via
`wards_overrides.csv`).

## ML alert calibration — what "90-95%" means here

A literal 90-95% "accuracy" on next-day millimetres is not achievable (daily
rainfall is high-variance; even top operational models report R² ~0.3-0.5).
The industry-standard equivalent for an alerting system is **detection of the
dangerous windows**, which this suite is tuned for:

- **Label**: a day within the next 3 days with ≥64.5 mm rain (IMD very-heavy
  band) — the windows landslide/flood watches are issued on.
- **Training cost**: missing a dangerous window costs 4× a false alarm
  (`COST_RATIO`), so the model is biased conservative on purpose.
- **Split**: train 2012-2017 · validate 2018-2019 (threshold selection) ·
  test 2020+ (out-of-sample report) — strictly chronological.
- **Threshold**: per locality, the *most-specific* cutoff that still catches
  ≥90% of dangerous windows on validation (max false-alarm cap 25%), stored
  in each `*_hazard.npz` and used live as the `heavy_alert` flag.

Out-of-sample test results (2020+, from `ml/models/eval.json`):

| Locality | AUC | Test recall | Test precision | False-alarm rate |
|---|---|---|---|---|
| Kumily | 0.94 | 0.92 | 0.11 | 0.19 |
| Peermedu | 0.94 | 0.88 | 0.11 | 0.17 |
| Idukki | 0.97 | 0.94 | 0.19 | 0.14 |
| Adimali | 0.94 | 0.93 | 0.18 | 0.18 |
| Kattappana | 0.97 | 0.93 | 0.16 | 0.18 |
| Munnar | 0.94 | 0.79 | 0.34 | 0.08 |
| Nedumkandam | 0.97 | 0.96 | 0.16 | 0.18 |

Median detection ≈93% (AUC 0.94-0.97). Munnar's recall shortfall is real and
reported, not hidden — its calibration window is noisier; per-locality tuning
is the documented extension path. Precision is low because dangerous days are
~2-5% of days; that is the honest price of high recall (many watches, few
misses), and why every alert is shown as a *probability*, never a certainty.

## Data providers

OpenWeatherMap is the primary current-conditions provider when
`OPENWEATHERMAP_API_KEY` is set; Open-Meteo covers the 7-day outlook and
measured history; every series is tagged with its true provider in `/trends`
and on the cards/drawer (see `docs/DATA_SOURCES.md`).

---

**Document Version:** 1.3  
**Last Updated:** September 2026  
**Author:** Idukki Monsoon Danger Index Team
