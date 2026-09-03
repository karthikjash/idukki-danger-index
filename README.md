# Idukki Monsoon Danger Index

🌧️ **A hyperlocal monsoon severity forecaster for inner Idukki district, Kerala**

Communicates real-time danger levels to non-technical residents through colour-coded maps, plain-language summaries, and actionable guidance — no jargon, no charts.

---

## 🎯 What It Does

**For Residents:**
- Select your panchayat (Kumily, Peermedu, Idukki, Adimali, Kattappana, Munnar, Nedumkandam)
- Get a 4-tier **Danger Index** (Low / Moderate / High / Extreme)
- Understand *why* it's dangerous (rainfall, terrain, population at risk)
- See plain-language **"what to do"** guidance (no jargon)
- View past incidents nearby (to understand local hazards)
- Interactive map showing all zones and historical events

**For Officials:**
- REST API for integration with government alert systems
- Real-time Danger Index for all inner-Idukki localities
- Historical incident overlay for situational awareness
- Exportable map and summary statistics

---

## ⚡ Quick Start

### Prerequisites
- Python 3.9+
- `pip` or `conda`

### 1. Install Dependencies

```bash
cd /home/homie/Projects/SSR_system
pip install -r requirements.txt
```

### 2. Run the Resident App

```bash
streamlit run frontend/app.py
```

Opens in browser at `http://localhost:8501`

**Features:**
- 📍 Select your locality
- ⚠️ See current Danger Index (colour-coded)
- 📊 View sub-scores and weather data
- 📅 7-day rainfall forecast
- 📍 Past incidents in your area
- 🗺️ Interactive map of all zones

### 3. Run the API Server (Optional)

```bash
python api/server.py
```

Starts FastAPI at `http://localhost:8000`

**Endpoints:**
- `GET /` — API info page
- `GET /localities` — List all monitored areas
- `GET /index` — All Danger Indices
- `GET /index/{locality}` — Single locality
- `GET /map` — Interactive map (HTML)
- `GET /incidents` — Historical incidents
- `GET /docs` — Interactive Swagger UI

---

## 📊 How It Works

### 1. Data Sources (All Public)

| Data | Source | Frequency |
|------|--------|-----------|
| **Rainfall** | IMD (mausam.imd.gov.in), NASA GPM IMERG | 6-hourly / 30-min |
| **Wind, Humidity** | IMD gridded forecasts | 6-hourly |
| **Cloud Cover** | NASA MODIS satellite | Daily |
| **Past Incidents** | KSDMA records (2004–present) | Static |
| **Population** | Census of India 2021 | Static |
| **Terrain** | OpenStreetMap, ISRO Bhuvan | Static |

### 2. Composite Danger Index

Three sub-scores (each 0–1) are combined:

```
40% Environmental Severity
   ├─ Rainfall intensity (primary monsoon driver)
   ├─ Wind speed
   ├─ Humidity
   └─ Cloud cover

35% Structural Risk
   ├─ Terrain slope (steep = more landslide risk)
   ├─ Historical incident frequency
   ├─ Infrastructure exposure (population proxy)
   └─ Soil saturation

25% Human Threat Level
   ├─ Population exposure
   ├─ Rainfall-driven danger to life
   └─ Evacuation difficulty
```

**Final Index:** Weighted sum → 4-tier assignment

```
Score < 0.25        → 🟢 LOW
0.25 ≤ Score < 0.50 → 🟠 MODERATE
0.50 ≤ Score < 0.75 → 🔴 HIGH
Score ≥ 0.75        → 🔴 EXTREME
```

### 3. Visual Output

- **Streamlit UI** — Locality selector, current index, sub-scores, forecast, guidance, incidents
- **Interactive Map** — Folium-based, colour-coded zones, toggleable incident layer
- **REST API** — JSON responses for government integration

---

## 🗂️ Directory Structure

```
/SSR_system/
├── /data/
│   └── fetcher.py              # IMD, NASA, KSDMA data ingestion
│
├── /index/
│   ├── calculator.py           # Danger Index computation & formulas
│   └── map_generator.py        # Folium interactive map
│
├── /api/
│   └── server.py               # FastAPI REST backend
│
├── /frontend/
│   └── app.py                  # Streamlit resident web app
│
├── /docs/
│   ├── METHODOLOGY.md          # Detailed methodology & formulas
│   ├── DATA_SOURCES.md         # How to fetch IMD, NASA, KSDMA data
│   └── API_REFERENCE.md        # API endpoint details
│
├── requirements.txt            # Python packages
└── README.md                   # This file
```

---

## 🌍 Monitored Localities (Inner Idukki)

| Panchayat | Coordinates | Terrain Risk | Population |
|-----------|-------------|--------------|------------|
| **Kumily** | 9.655°N, 76.775°E | Very Steep | ~45,000 |
| **Peermedu** | 9.545°N, 76.615°E | Extremely Steep | ~32,000 |
| **Idukki** | 9.725°N, 76.805°E | Very Steep | ~28,000 |
| **Adimali** | 9.575°N, 76.895°E | Extremely Steep | ~22,000 |
| **Kattappana** | 9.650°N, 76.925°E | Very Steep | ~38,000 |
| **Munnar** | 10.089°N, 76.766°E | Very Steep | ~35,000 |
| **Nedumkandam** | 9.800°N, 76.868°E | Steep | ~18,000 |

---

## 🎓 Danger Index Tiers — What They Mean

### 🟢 LOW (Score < 0.25)
**Safe.** Normal activity OK. Monitor daily.  
✅ Schools, markets, offices open  
✅ Travel, work as usual  
⚠️ Stay alert during monsoon season

### 🟠 MODERATE (Score 0.25–0.50)
**Caution.** Heavy rainfall; avoid unnecessary travel.  
⚠️ Stay indoors during heavy rain  
⚠️ Avoid hilly areas  
⚠️ Keep children indoors

### 🔴 HIGH (Score 0.50–0.75)
**Danger.** Landslides/floods possible. Stay indoors.  
🚨 **STAY INDOORS**  
🚨 Avoid all non-essential travel  
🚨 Prepare to evacuate (pack go-bag with documents, medicines, water)

### 🔴 EXTREME (Score ≥ 0.75)
**SEVERE DANGER.** Evacuate if ordered.  
🚨 **EVACUATE IMMEDIATELY** if told by authorities  
🚨 Go to panchayat-designated shelter  
🚨 Avoid rivers, dams, slopes  
📞 **Call: 112 (national) or 1077 (Kerala Disaster)**

---

## 🔧 Configuration & Customization

### Adjust Weighting

Edit `index/calculator.py`:

```python
# In calculate_composite_index():
composite_score = (
    0.40 * environmental_severity +  # Adjust these percentages
    0.35 * structural_risk +         # (must sum to 1.0)
    0.25 * human_threat_level
)
```

### Add/Remove Localities

Edit `data/fetcher.py`:

```python
LOCALITIES = {
    'Locality_Name': {'lat': 9.XXX, 'lon': 76.XXX},
    # Add your locality...
}
```

### Adjust Tier Thresholds

Edit `index/calculator.py`:

```python
if composite_score < 0.25:      # Adjust these thresholds
    tier = 'Low'
elif composite_score < 0.50:
    tier = 'Moderate'
# etc.
```

---

## 📡 API Usage Examples

### Get all Danger Indices

```bash
curl http://localhost:8000/index | jq
```

### Get Kumily index

```bash
curl http://localhost:8000/index/Kumily | jq
```

### Get incidents

```bash
curl http://localhost:8000/incidents | jq
```

### Get summary

```bash
curl http://localhost:8000/summary | jq
```

### View map

```bash
open http://localhost:8000/map
```

---

## 🚀 Deployment

### Local Development
```bash
streamlit run frontend/app.py
```

### Server (Docker Optional)

```dockerfile
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["streamlit", "run", "frontend/app.py", "--server.port=8501"]
```

```bash
docker build -t idukki-danger-index .
docker run -p 8501:8501 idukki-danger-index
```

### Production Integration

- Run `api/server.py` as a daemon (systemd, supervisor, etc.)
- Set up cron to refresh data 2× daily (6 AM, 6 PM IST)
- Expose `/index`, `/map`, `/incidents` to government SMS/email alert systems
- Log all alerts for audit/improvement

---

## 📚 Documentation

- **[METHODOLOGY.md](docs/METHODOLOGY.md)** — Detailed formulas, sub-score definitions, data rationale
- **[DATA_SOURCES.md](docs/DATA_SOURCES.md)** — How to fetch IMD, NASA, KSDMA data (in progress)
- **[API_REFERENCE.md](docs/API_REFERENCE.md)** — Complete API endpoint reference (in progress)

---

## ⚠️ Important Notes

1. **This is a forecast tool, not a guarantee.** Always follow official warnings and evacuation orders.
2. **Data latency:** Forecasts updated 2× daily. Real-time hazards may emerge between updates.
3. **Locality resolution:** Index computed at panchayat level. Micro-variations (e.g., a specific slope) not captured.
4. **Emergency:** If in doubt or seeing weather deteriorate, **call 112 or 1077 immediately.**

---

## 🤝 Contributing

To improve the system:

1. Report inaccurate incident records or missing data sources
2. Suggest UI/UX improvements for non-technical residents
3. Test with actual residents and provide feedback
4. Help integrate with government alert systems

---

## 📜 License

[To be determined by project governance]

---

## 📞 Support

- **App Issues:** Open an issue in the repository
- **Data Questions:** Contact KSDMA or IMD directly
- **Emergency:** **112 (national) or 1077 (Kerala Disaster Helpline)**

---

## 🎯 Project Goals (1-Week Deadline)

- ✅ Forecast engine ingesting IMD, NASA, KSDMA public data
- ✅ Composite Danger Index (3 sub-scores → 4-tier output)
- ✅ Colour-coded interactive map (Folium)
- ✅ Resident-facing Streamlit app (plain-language, no jargon)
- ✅ REST API for government integration
- ✅ Historical incident overlay
- ✅ Documentation of methodology

---

**Version:** 1.0  
**Last Updated:** September 2026  
**Author:** Idukki Monsoon Danger Index Team
