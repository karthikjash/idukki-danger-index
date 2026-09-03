# Idukki Monsoon Danger Index

**A hyperlocal monsoon-risk early-warning system for inner Idukki district, Kerala.**

The system turns live weather data into a plain-language, colour-coded danger
level for each of the seven main panchayats of inner Idukki — **Kumily,
Peermedu, Idukki, Adimali, Nedumkandam, Kattappana, Munnar** — tells people
*why* an area is dangerous and *what to do*, forecasts the danger up to seven
days ahead, flags heavy-rain danger windows with a machine-learning model
trained on the 2012–2025 local rainfall record, and delivers SMS alerts to
registered residents.

It is a working prototype of the *Climate Intelligence for Kerala* SSR
proposal: a full data → index → ML → GIS → dashboard → report → alert stack
that runs end-to-end on a normal machine. **It is a forecast tool, not a
guarantee** — it always defers to official KSDMA / IMD / district warnings.

Full documentation booklet: [`docs/PROJECT_DOCUMENTATION.pdf`](docs/PROJECT_DOCUMENTATION.pdf) (regenerate with
`python3 docs/generate_project_doc.py`).

---

## Features

**For residents**
- Live **4-tier danger index** (Low / Moderate / High / Extreme) per panchayat,
  with the plain-language *reason* and *what to do / what to avoid*
  guidance.
- **7-day danger outlook** — the same danger model run on each forecast day,
  so a rising tier is visible days before the rain arrives.
- **Ward-level exposure** — risk micro-zones per panchayat (real LSG
  Election-2020 wards for Kumily), with incident-weighted scoring.
- **AI 24-hour outlook** — next-day rainfall plus a heavy-rain alert from
  models calibrated per locality to catch ≥90% of dangerous windows
  (out-of-sample AUC 0.94–0.97 — see [Machine learning](#machine-learning)).
- **Three trend charts** per area: rainfall outlook, 30-day measured monsoon
  pattern, and 48 h wind/humidity/temperature — every series tagged with the
  real provider that supplied it.
- **Seasonal context** — ENSO phase (NOAA CPC ONI) and lightning-risk
  advisories.
- **English ⇄ മലയാളം** — the entire UI, guidance and SMS messages translate;
  English is the default and the choice is remembered per browser.
- **SMS alerts** — register a mobile number and choose areas, language,
  threshold and schedule (danger / daily / weekly) — see
  [SMS alerts](#sms-alerts).

**For officials / administrators**
- REST API for every layer (`/index`, `/danger-forecast`,
  `/trends`, `/wards`, `/ml`, `/outlook`, `/report`, `/notify/*`).
- **Seasonal risk reports** — a PDF *and* a DOCX per panchayat or for the
  whole district.
- Interactive **danger map** with historical incident overlay.
- Summary + health endpoints for integration and monitoring.

---

## Quick start

Requires Python 3.9+. No database, no heavy ML stack — the ML engine is pure
NumPy and everything ships in `requirements.txt`.

```bash
git clone https://github.com/karthikjash/idukki-danger-index
cd idukki-danger-index

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python api/server.py
```

Open **http://localhost:8000** (API docs at `/docs`). On first boot the
server, in the background and without blocking the UI:

- trains the per-panchayat ML models from the ERA5 rainfall archive
  (`ml/models/`, usually ~1 min per area),
- starts the SMS alert scheduler,
- closes measured-weather history into the local store.

### Optional configuration — `.env`

```bash
cp .env.example .env    # then fill in the keys you want
```

| Key | Effect |
| --- | --- |
| `OPENWEATHERMAP_API_KEY` | Current conditions + 5-day/3-h outlook become the **primary live provider** (otherwise Open-Meteo covers everything, always labelled) |
| `FAST2SMS_API_KEY` | SMS alerts go out through Fast2SMS (register a DLT sender/template for transactional SMS in India) |
| `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_FROM` | Alternative SMS gateway with full Unicode/Malayalam support |

Without a gateway key the SMS service runs in **demo mode** — every message
is previewed in the UI and logged to `data/notifications/outbox.jsonl`, so
the whole flow is verifiable before a key is added.

---

## How the danger index is computed

For each panchayat, live weather (rainfall, wind, humidity, cloud) is fetched,
and a composite score (0–1) is built from four documented components under a
government-style weighting scheme — **terrain 40% · soil 25% · exposure
(population/wards) 20% · incident history 15%** — where rainfall *gates* the
structural risk: without rain the score cannot rise, no matter the terrain.
Incident history is derived from the register with proximity + severity +
recency decay (no hand-set constants). The score maps to IMD rain bands
(heavy ≥64.5 mm, very heavy ≥115.5 mm) and to tier-specific guidance.
Methodology: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Machine learning

Daily rainfall per panchayat (2012–2025) trains, in pure NumPy: an **LSTM**
forecaster (the proposal's named architecture), a **ridge** next-day baseline
and a **logistic hazard classifier** for ≥64.5 mm within 3 days. Misses cost
4× a false alarm; each threshold is calibrated on the 2018–2019 validation
years to ≥90% recall, then measured honestly **out-of-sample on 2020–2026**
data the models never saw — `ml/models/eval.json` holds full confusion
matrices. Median detection ≈93%, AUC 0.94–0.97, ridge MAE ≈7.0 mm (σ ≈15
mm). See [`docs/ACCURACY_IMPROVEMENT_REPORT.md`](docs/ACCURACY_IMPROVEMENT_REPORT.md).

## SMS alerts

Click **SMS Alerts** in the header (or *SMS alerts for this area* inside any
panchayat's panel), enter a mobile number, and pick:

1. **Danger alerts** — instant SMS when a watched area crosses your threshold
   (High or Extreme), at most once per area per day.
2. **Daily briefing** — every day at 07:00 IST: today's level and rain, plus
   tomorrow's forecast, per watched area.
3. **Weekly outlook** — every Monday at 08:00 IST: the week's worst day per
   area from the 7-day danger outlook.

Messages are sent in English or Malayalam as chosen. Subscriptions live in
`data/subscriptions.json` (git-ignored). Endpoints: `GET/POST/DELETE
/notify/subscribe`, `POST /notify/test`, `GET /notify/messages`, `GET
/notify/status`.

---

## REST API (summary)

| Endpoint | Purpose |
| --- | --- |
| `GET /health`, `/summary` | Health and district summary |
| `GET /index` · `/index/{locality}` | Danger index, all or one panchayat |
| `GET /danger-forecast/{locality}` | 7-day danger outlook (tier/day, probability, worst day) |
| `GET /trends/{locality}` | Chart series (outlook / measured 30 d / 48 h) |
| `GET /wards/{locality}` | Ward micro-zones |
| `GET /ml` | AI outlook + evaluation data |
| `GET /outlook` | ENSO + lightning |
| `GET /report?locality=&format=pdf\|docx` | Seasonal report download |
| `GET /incidents`, `GET /map` | Historical events, interactive map |
| `/notify/*` | SMS subscriptions, tests, outbox |

Full reference with examples: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).

---

## Project layout

```
api/server.py            FastAPI app: dashboard + REST API + background threads
data/                    Live providers (openweather / open-meteo / observed),
                         static ward tables (data/static/wards.json)
index/                   Danger-index calculator, 7-day outlook, ward zoning, map
ml/                      Dataset, NumPy models, training + per-locality eval
notify/                  SMS subscriptions, EN/ML composer, scheduler, gateways
outlook/                 ENSO phase + lightning climatology
reporting/               Seasonal report PDF/DOCX generation
frontend/static/         Dashboard (vanilla JS, no build step, EN/ML)
docs/                    Methodology, API reference, data sources, proposal
                         coverage, accuracy report, this booklet (PDF)
```

## Documentation

| Document | Contents |
| --- | --- |
| `docs/PROJECT_DOCUMENTATION.pdf` | Full project booklet (this readme's big sibling) |
| `docs/METHODOLOGY.md` | Scoring, weighting, ML protocol in detail |
| `docs/API_REFERENCE.md` | Every endpoint with examples |
| `docs/DATA_SOURCES.md` | Providers, keys, accuracy notes |
| `docs/PROPOSAL_COVERAGE.md` | Proposal item → status map (incl. what is *not* built) |
| `docs/ACCURACY_IMPROVEMENT_REPORT.md` | Retraining, calibration and evaluation results |

## Reproducibility

- `python3 ml/train.py` — retrain all models and rewrite `ml/models/eval.json`
  (deterministic split: train 2012–2017 → calibrate 2018–2019 → test 2020+).
- `python3 docs/generate_project_doc.py` — regenerate the documentation PDF.
- No automated test suite yet — the ML metrics in `eval.json` and the live
  endpoint checks in the documentation PDF act as the current regression
  evidence.

## Honest limitations

- The incident register is a small sample; terrain is a per-locality constant
  (not SRTM DEM). Live weather is Open-Meteo/ERA5 until an IMD key is
  available, and OpenWeatherMap when configured.
- Ward structures for six panchayats are LSG-typical models (Kumily is real)
  until Census ward tables are dropped in via
  `data/static/wards_overrides.csv`.
- The ML models are validated on rainfall; validating them against actual
  2018–2020 landslide/flood outcomes is the recommended next step (a backtest
  of the alert engine).
- Not affiliated with or endorsed by KSDMA, IMD or any government body.

*An SSR / college-demo project by students — built openly so reviewers can
read every formula, number and limitation.*
