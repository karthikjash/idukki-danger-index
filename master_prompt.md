# Master Prompt — Hyperlocal Monsoon Danger Index for Idukki

Build a web application called **Idukki Monsoon Danger Index** that forecasts seasonal monsoon severity for the inner areas of Idukki district, Kerala, and communicates it to non-technical residents through a colour-coded map and a plain-language interface.

## What to build

**1. Forecast Engine**
Ingest gridded rainfall, wind-vector, humidity, and cloud-movement data (IMD gridded data, NASA EarthData MODIS/GPM) and produce a short-to-seasonal monsoon outlook per locality (taluk/panchayat level) in inner Idukki — not district-wide.

**2. Composite Danger Index**
For each locality, compute three sub-scores and combine them into one index (Low / Moderate / High / Extreme):
- **Environmental Severity** — rainfall intensity, terrain saturation potential
- **Structural Risk** — likelihood of damage to buildings/roads/property (slope, soil, historical damage patterns)
- **Human Threat Level** — danger to life, weighted by population exposure (Census ward data) and proximity to known hazard zones

Keep the weighting formula simple and documented (e.g. normalized 0–1 sub-scores, weighted sum → 4-tier bucket) so it's explainable, not a black box.

**3. Colour-Coded Forecast Map**
Interactive map of inner Idukki, zones shaded by current Danger Index (cool = low risk, warm/red = high risk), rendered from live forecast output — not hand-drawn.

**4. Historical Calamity Overlay**
Plot documented past landslides/floods/dam-related incidents (KSDMA records, 2004–present) as markers on the same map, toggleable against the forecast layer.

**5. Resident-Facing Interface**
User selects or taps a locality → sees: current Danger Index, the three contributing sub-scores in plain language, the forecast driving it, and nearby historical incidents. No jargon, no technical charts required to understand the headline risk.

## Data constraint (hard rule)
Only use data confirmed publicly accessible: IMD (mausam.imd.gov.in), NASA EarthData, KSDMA incident records, OpenStreetMap/ISRO Bhuvan, Census of India. Do not design any feature around data that isn't already available — if a feature needs data access we don't have this week, cut it rather than build a placeholder.

## Tech stack
- **Forecast/ML:** Python, Pandas, NumPy, Scikit-learn
- **Geospatial:** GeoPandas, Folium or Leaflet.js
- **Backend:** Flask or FastAPI
- **Frontend:** React.js or Streamlit
- **Repo:** GitHub, single repo, clear module boundaries (`/data`, `/forecast`, `/index`, `/api`, `/frontend`)

## Priorities given the 1-week deadline
1. Get one working end-to-end slice first: one locality → real data → Danger Index number → shown on a map. Prove the pipeline before scaling to all inner-Idukki zones.
2. UI/UX clarity matters as much as model accuracy — a resident must understand the output in seconds.
3. Document data sources and index methodology as you go (needed for the SSR report regardless of what ships in code).
4. No feature that can't be demoed with real data by the deadline — cut scope, don't fake data.

## Deliverable
A running web app (local or deployed) showing the map, index, and historical overlay for at least the inner-Idukki localities with usable data, plus a short README covering data sources and the index formula.
