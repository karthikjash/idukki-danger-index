# SSR Proposal → Codebase Coverage

Tracks the 2026-27 SSR project proposal
(*AI-Based Localized Seasonal Climate Intelligence & Monsoon Risk Prediction
System for Kerala*) against what is implemented in this repository.

Status legend: ✅ done · 🟡 partial/substituted · ❌ not built

## Module 1 — Multi-source data collection

| Proposal | Status | Where / note |
|---|---|---|
| IMD gridded rainfall/wind/humidity | 🟡 | IMD enters as rainfall *category thresholds*; live values come from OpenWeatherMap (when `OPENWEATHERMAP_API_KEY` is set) or Open-Meteo (`data/openweather.py`, `data/fetcher.py`) |
| Accurate live weather (rainfall/wind) | ✅ | OpenWeatherMap current-weather provider is the primary live source when a key is present; honest `conditions_provider` labels on every record/card |
| NASA EarthData MODIS / GPM / SRTM | 🟡 | `NASADataFetcher` is a stub reusing the shared live feed; terrain slope is a static table, not SRTM |
| KSDMA incident records 2004–present | 🟡 | 15 hand-compiled sample incidents (`data/fetcher.py`) — swap in the real register to upgrade; incident influence is now *derived from the register* (see Module 4) |
| Census ward-level population | 🟡 | Ward structures + incident-sensitivity micro-zones added (`index/wards.py`, `data/static/wards.json`). Kumily carries the real LSG-Kerala Election-2020 ward table; other panchayats ship modelled defaults. Census-2011 ward population tables drop in via `wards_overrides.csv` |
| OpenStreetMap roads / relief camps | ❌ | folium basemap only |
| NOAA CPC ONI (ENSO) | ✅ | `outlook/enso.py` + vendored `data/static/oni.txt` |

## Module 2 — Data engineering & features

| Proposal | Status | Where / note |
|---|---|---|
| Historical rainfall series (ERA5 via Open-Meteo archive) | ✅ | `ml/dataset.py` — 2012→today per locality, cached |
| Measured recent history | ✅ | Open-Meteo measured `past_days` feed + the project's own day-by-day observed store (`data/observed.py`) that feeds soil saturation and future retrains |
| Missing-value handling / season-aware fallback | ✅ | `data/fetcher.py` fallbacks, clearly flagged |
| Rainfall accumulation / seasonal features | ✅ | `ml/dataset.py::build_features` |
| Wind-vector decomposition, cloud trajectories, ENSO correlation features | ❌ | not used as model inputs |
| GeoPandas spatial joins | ❌ | no geodataframe pipeline |

## Module 3 — AI/ML prediction engine

| Proposal | Status | Where / note |
|---|---|---|
| LSTM rainfall intensity prediction | ✅ | pure-NumPy LSTM, per locality (`ml/models.py`, trained by `ml/train.py`) |
| Flood/hazard classification | 🟡 | cost-weighted logistic hazard classifier (pure NumPy — sklearn/XGB swap path documented), threshold **calibrated per locality for ≥90% detection of heavy-rain windows** on a held-out validation period; out-of-sample test metrics (recall/precision/false-alarm/F1) reported in `ml/models/eval.json` and `/ml` |
| False-negative control | ✅ | misses cost 4× a false alarm in training (`COST_RATIO`), decision thresholds chosen by *most-specific cutoff that still catches ≥90% of dangerous windows*, model alert surfaced in the UI |
| Landslide risk scoring (slope, soil, rainfall thresholds) | ✅ | rainfall-gated rule model in `index/calculator.py`, rebalanced to a documented NDMA/BIS-style scheme; soil saturation now sharpened by measured recent rain |
| Lightning heatmap | 🟡 | climatological day-of-year risk per locality (`outlook/lightning.py`); no live strike feed |
| Anomaly detection | ❌ | not built |

## Module 4 — Geographic risk analysis

| Proposal | Status | Where / note |
|---|---|---|
| Terrain slope / elevation layers | 🟡 | static per-locality slope constants |
| Flood inundation modelling (DEM + catchment) | ❌ | not built |
| Road-accessibility graph with flood-based closures | ❌ | not built (evacuation difficulty is only a scoring constant) |
| Ward-level vulnerability scoring | 🟡 | **new**: ward micro-zones per panchayat (`/wards/{locality}`, drawer panel) — score = panchayat danger lifted by each ward's recorded-incident history; populations apportioned from authoritative totals (modelled until Census table drops in) |
| Relief-camp capacity / assignment | ❌ | not built |

## Module 5 — Dashboard & reporting

| Proposal | Status | Where / note |
|---|---|---|
| Interactive web dashboard | ✅ | FastAPI + zero-build JS UI (`frontend/static/`) — monsoon-grove greenery theme |
| Risk overlays & time-series charts | ✅ | Folium map, 7-day danger outlook, plus **3 trend charts per locality**: rainfall outlook, 30-day measured monsoon pattern, 48 h wind/humidity/temperature (`/trends/{locality}`) — each series provider-tagged |
| Seasonal risk report (PDF/Word) | ✅ | `reporting/report.py`, endpoints `/report?format=pdf\|docx` |
| Post-event accuracy feedback dashboard | 🟡 | static evaluation in `ml/models/eval.json` + `/ml`; no live event tracking UI |

## Objectives & outcomes quick check

- ✅ Hyperlocal seasonal engine for Idukki (selected district, one of the
  proposal's two "Extreme High" candidates)
- ✅ Live data + honest source labelling (provider shown per series)
- ✅ OpenWeatherMap integration (key-gated, `.env`) for accurate current data
- ✅ AI rainfall/hazard predictions per locality with calibrated alerts (`/ml`)
- ✅ ENSO seasonal context + lightning advisories (`/outlook`)
- ✅ Ward-level exposure micro-zones + correct authoritative populations
- ✅ GIS risk map + incident layer + PDF/DOCX admin reports
- ❌ Isolation-aware evacuation routing, relief-camp planning, real
  IMD/NASA/KSDMA registers, live lightning feed, post-event tracking UI

## How to extend (in rough priority)

1. **OpenWeather live** → `export OPENWEATHERMAP_API_KEY=...` (or `.env`) and
   restart; cards/drawers flip to `OpenWeatherMap` automatically.
2. **Real incident register** → replace the sample frame in
   `KSDMADataFetcher.get_historical_incidents` with an authoritative export;
   scoring factors and ward sensitivity follow automatically.
3. **Real ward tables** → add `data/static/wards_overrides.csv`
   (`locality,ward_no,ward_name,population,source`) or edit `wards.json`.
4. **Stronger ML** → swap `ml/models.py` implementations for
   sklearn/XGBoost/TF versions (interfaces already fit `fit/predict/save/load`);
   retrain with `python3 ml/train.py`.
5. **Live lightning feed** → new provider behind the `outlook.lightning` API.
6. **Road access & camps** → OSM/Overpass fetch + graph module feeding an
   isolation-risk view (the biggest remaining Module 4 item).
