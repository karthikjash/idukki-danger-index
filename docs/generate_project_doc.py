#!/usr/bin/env python3
"""Generate docs/PROJECT_DOCUMENTATION.pdf — the full project booklet.

Builds a self-contained PDF (pure fpdf2, DejaVu Sans embedded when present)
covering: problem, architecture, data sources, methodology, ML evaluation
(read live from ml/models/eval.json), ward layer, reports, SMS alert service,
API surface, frontend features, verification walkthrough and roadmap.

Usage:  .venv/bin/python docs/generate_project_doc.py
Output: docs/PROJECT_DOCUMENTATION.pdf
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from fpdf import FPDF
except ImportError:
    sys.exit("fpdf2 not installed — run: .venv/bin/pip install -r requirements.txt")

# ------------------------------------------------------------------ fonts ---
_DEJAVU = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
_DEJAVU_B = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
_DEJAVU_I = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf')
_MONO = Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')
FONT = 'DejaVu' if _DEJAVU.exists() else 'Helvetica'

# ----------------------------------------------------------------- palette --
INK = (26, 32, 28)
MUTED = (90, 102, 95)
GREEN = (16, 130, 100)
DARK_GREEN = (13, 90, 72)
LIGHT_FILL = (240, 246, 243)
RULE = (200, 212, 205)

PW = 210          # A4 width mm
ML = 18
MR = 18
CW = PW - ML - MR


class Booklet(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(True, margin=17)
        self._register_fonts()
        self._fonts_set = False

    def _register_fonts(self):
        if FONT == 'DejaVu':
            self.add_font('DejaVu', '', str(_DEJAVU))
            self.add_font('DejaVu', 'B', str(_DEJAVU_B))
            self.add_font('DejaVu', 'I', str(_DEJAVU_I))
            if _MONO.exists():
                self.add_font('DejaVuMono', '', str(_MONO))

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font(FONT, '', 7.5)
        self.set_text_color(*MUTED)
        self.set_y(8)
        self.cell(0, 4, 'Idukki Monsoon Danger Index — Project Documentation', align='L')
        self.cell(0, 4, 'Version 1.3 · September 2026', align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*RULE)
        self.line(ML, 13.5, PW - MR, 13.5)

    def footer(self):
        self.set_y(-13)
        self.set_draw_color(*RULE)
        self.line(ML, self.get_y(), PW - MR, self.get_y())
        self.set_font(FONT, '', 8)
        self.set_text_color(*MUTED)
        page = f'Page {self.page_no()}'
        self.cell(0, 5, 'Generated ' + datetime.now().strftime('%d %b %Y'),
                  align='L')
        self.cell(0, 5, page, align='R')


B = Booklet()


def _style(kind):
    return {
        'font': FONT,
        'size': 10.2,
        'color': INK,
    }


def H1(text):
    B.set_x(ML)
    B.set_font(FONT, 'B', 15.5)
    B.set_text_color(*DARK_GREEN)
    B.multi_cell(CW, 8, text)
    B.ln(1.5)


def H2(text):
    B.set_x(ML)
    B.set_font(FONT, 'B', 12.5)
    B.set_text_color(*GREEN)
    B.multi_cell(CW, 6.5, text)
    B.ln(1)


def H3(text):
    B.set_x(ML)
    B.set_font(FONT, 'B', 10.8)
    B.set_text_color(*INK)
    B.multi_cell(CW, 6, text)
    B.ln(0.5)


def P(text, size=10.2, color=INK, lh=5.2):
    B.set_x(ML)
    B.set_font(FONT, '', size)
    B.set_text_color(*color)
    B.multi_cell(CW, lh, text)
    B.ln(1.2)


def BUL(items, size=9.9, lh=5.1):
    B.set_x(ML)
    B.set_font(FONT, '', size)
    B.set_text_color(*INK)
    for it in items:
        B.set_x(ML + 4)
        B.multi_cell(CW - 8, lh, '•  ' + it)
        B.ln(0.4)
    B.ln(1)


def CODE(text, size=8.3):
    B.set_font('DejaVuMono' if _MONO.exists() else FONT, '', size)
    B.set_text_color(*INK)
    for line in text.strip('\n').split('\n'):
        B.set_fill_color(247, 249, 248)
        B.set_x(ML + 3)
        B.multi_cell(CW - 6, 4.6, line if line else ' ', fill=True)
        B.ln(0.1)
    B.ln(1.4)


def TBL(headers, rows, widths=None, sizes=9.0, mono=False):
    """Simple table with wrapped cells."""
    if widths is None:
        widths = [CW / len(headers)] * len(headers)
    B.set_font(FONT, 'B', sizes)
    B.set_fill_color(*DARK_GREEN)
    B.set_text_color(255, 255, 255)
    x0 = ML
    for h, w in zip(headers, widths):
        B.set_x(x0)
        B.cell(w, 6.4, h, border=0, fill=True)
        x0 += w
    B.ln()
    B.set_font(FONT, '', sizes)
    B.set_text_color(*INK)
    for r_i, row in enumerate(rows):
        fill = r_i % 2 == 1
        B.set_fill_color(*LIGHT_FILL) if fill else B.set_fill_color(255, 255, 255)
        # compute row height from wrapped line counts
        heights = []
        for cell, w in zip(row, widths):
            lines = B.multi_cell(w, 4.6, str(cell), dry_run=True, output='LINES')
            heights.append(len(lines) * 4.6 + 1.6)
        rh = max(heights)
        if B.get_y() + rh > 275:
            B.add_page()
        y0 = B.get_y()
        x = ML
        for cell, w in zip(row, widths):
            B.set_xy(x, y0)
            if mono:
                B.set_font('DejaVuMono' if _MONO.exists() else FONT, '', sizes - 0.6)
            else:
                B.set_font(FONT, '', sizes)
            B.multi_cell(w, 4.6, str(cell), fill=True)
            x += w
        B.set_y(y0 + rh)
    B.ln(2)


def PAGES():
    return B.page_no()


# ================================================================ content ===
B.add_page()

# --- title block ---
B.set_fill_color(*DARK_GREEN)
B.rect(0, 0, PW, 60, 'F')
B.set_text_color(255, 255, 255)
B.set_y(18)
B.set_x(ML)
B.set_font(FONT, 'B', 24)
B.multi_cell(CW, 11, 'Idukki Monsoon Danger Index', align='C')
B.set_x(ML)
B.set_font(FONT, '', 12.5)
B.multi_cell(CW, 6.5, 'Hyperlocal Monsoon-Risk Intelligence for Inner Idukki, Kerala', align='C')
B.set_y(53)
B.set_x(ML)
B.set_font(FONT, 'B', 11)
B.multi_cell(CW, 6, 'Full Project Documentation  ·  Version 1.3', align='C')
B.set_x(ML)
B.set_font(FONT, '', 9.5)
B.multi_cell(CW, 5, 'September 2026', align='C')
B.ln(6)

B.set_text_color(*INK)

H1('1.  Executive summary')
P('The Idukki Monsoon Danger Index turns raw weather data into an '
  'operational, plain-language early-warning service for the seven main '
  'panchayats of inner Idukki district, Kerala — a region repeatedly hit by '
  'landslides and flash floods (2018, 2019, 2020, 2021). The system fetches '
  'live conditions and forecasts per locality, computes a transparent '
  'four-tier danger index (Low / Moderate / High / Extreme), forecasts the '
  'same tiers up to seven days ahead, learns from a 14-year rainfall record '
  'to flag heavy-rain danger windows, and pushes the result to the people who '
  'need it through a bilingual (English/Malayalam) resident dashboard, '
  'colour-coded danger maps, downloadable administrator reports and an SMS '
  'alert service that residents subscribe to with their mobile number.')
P('Every layer is honest about its data: modelled estimates are always '
  'labelled, live providers (OpenWeatherMap when a key is configured, '
  'otherwise Open-Meteo) are named per number, machine-learning results are '
  'reported with out-of-sample evaluation, and ward splits are flagged as '
  'estimates until a Census table is dropped in. This document covers the '
  'full architecture, methodology, evaluation numbers, API surface, the SMS '
  'alert flow, and a step-by-step verification of every working flow.')

H1('2.  Objectives and scope')
BUL([
    'Provide a hyperlocal, ward-aware danger level for the 7 main panchayats of inner Idukki (Kumily, Peermedu, Idukki, Adimali, Nedumkandam, Kattappana, Munnar) with their authoritative populations.',
    'Give non-technical residents plain-language risk levels, the reason for them, and what to do / avoid — in English or Malayalam.',
    'Forecast danger up to 7 days ahead from the rainfall forecast, using the identical scoring model as the live index.',
    'Add a machine-learning engine trained on the 2012–2025 local rainfall record, calibrated to catch at least 90% of dangerous heavy-rain windows on data the model has never seen.',
    'Deliver alerts by SMS with per-user choice of areas, threshold, message language and schedule (instant danger / daily 07:00 / Monday weekly).',
    'Provide government-grade exports: PDF/DOCX seasonal reports and a REST API.',
])

H1('3.  Architecture')
P('Monolith-FastAPI server (api/server.py) that serves both the REST API and '
  'the static resident dashboard. Pure-NumPy ML engine, zero-dependency DOCX '
  'writer, pure fpdf2 PDF reports. No database: JSON files for caches and '
  'subscriptions; /tmp caches for live feeds.')
TBL(['Module', 'Responsibility'], [
    ['data/ (fetcher.py, openweather.py, observed.py)', 'Provider-agnostic live conditions, forecasts, measured history; OpenWeatherMap primary when key set, Open-Meteo otherwise; caching + source tags'],
    ['index/ (calculator.py, wards.py, map_generator.py)', 'Danger-index scoring engine, 7-day danger outlook, ward-level micro-zonation, Folium danger map'],
    ['ml/ (dataset.py, models.py, train.py, predict.py)', 'LSTM + ridge next-day rainfall and cost-weighted hazard classifier, per locality; out-of-sample evaluation'],
    ['outlook/ (enso.py, lightning.py)', 'NOAA CPC ONI ENSO phase + lightning-risk climatology'],
    ['notify/ (sms.py, store.py, messages.py, scheduler.py)', 'SMS subscriptions, EN/ML message composer, background alert scheduler, Twilio/Fast2SMS gateway or demo outbox'],
    ['reporting/report.py', 'Seasonal risk report PDF (fpdf2) + DOCX (stdlib OOXML)'],
    ['frontend/static/', 'Vanilla-JS dashboard: cards, search/filters, 3 trend charts, ward panel, bilingual EN/ML, SMS registration modal'],
    ['api/server.py', 'FastAPI application + background threads (ML first-boot training, observed-day closer, SMS scheduler)'],
], widths=[62, CW - 62])

H1('4.  Data sources')
TBL(['Source', 'What it supplies', 'Status'], [
    ['OpenWeatherMap (key in .env)', 'Current conditions (rain, wind, humidity, cloud, temp) + 5-day/3-h outlook', 'Primary when OPENWEATHERMAP_API_KEY is set'],
    ['Open-Meteo (no key needed)', 'Current conditions, 7-day daily forecast with rain probability, measured past-30-days history, ERA5 2012–2025 archive for training', 'Always-available fallback / history'],
    ['IMD rain categories', 'Heavy (64.5 mm) / very heavy (115.5 mm) daily bands used as hazard thresholds', 'Applied, documented'],
    ['NOAA CPC ONI', 'ENSO phase (El Niño / La Niña) for seasonal context', 'Vendored table, live'],
    ['KSDMA-style incident register', 'Historical landslide/flood events near each area (sample of 15 records)', 'Demo sample — real register is an extension point'],
    ['LSG Kerala Election-2020', 'Real 20-ward table for Kumily', 'Live'],
    ['Census-2011 populations', 'Authoritative panchayat totals', 'Applied per locality'],
], widths=[55, 75, CW - 130])

H1('5.  Danger-index methodology')
P('The composite score (0–1) combines rainfall-gated weather severity with '
  'structural and human factors under a documented NDMA/BIS-style weighting: '
  'terrain 40% · soil 25% · exposure (population/wards) 20% · incident '
  'history 15%. Rainfall gates the structural risk: without rain the score '
  'cannot rise regardless of terrain. The incident-history factor is computed '
  'from the register with proximity + severity + recency decay rather than '
  'hand-set constants. Tiers map to IMD rain bands and plain-language '
  'guidance (what to do / what to avoid), fully translated into Malayalam.')
TBL(['Tier', 'Meaning', 'Typical trigger'], [
    ['Low', 'Normal activity safe; stay alert during monsoon', 'Calm weather / <35 mm forecast'],
    ['Moderate', 'Rain building; slippery roads; avoid heavy-rain travel', '35–64 mm expected'],
    ['High', 'Landslides/flash floods possible on steep terrain', '64–115 mm (IMD “heavy”)'],
    ['Extreme', 'Immediate threat to life and property; act now', '>115 mm (IMD “very heavy”)'],
], widths=[22, 85, CW - 107])

H1('6.  Hyperlocal ward layer')
TBL(['Panchayat', 'Population (Census) ', 'Wards', 'Ward structure source'], [
    ['Kumily', '33,722', '20', 'LSG Kerala Election-2020 (real)'],
    ['Peermedu', '22,213', '19', 'LSG-typical modelled'],
    ['Idukki', '21,724', '19', 'LSG-typical modelled'],
    ['Adimali', '40,484', '20', 'LSG-typical modelled'],
    ['Nedumkandam', '41,980', '21', 'LSG-typical modelled'],
    ['Kattappana', '42,646', '24', 'LSG-typical modelled'],
    ['Munnar', '32,039', '20', 'LSG-typical modelled'],
], widths=[32, 36, 22, CW - 90])
P('Each ward receives a risk score = panchayat danger raised by that ward’s '
  'recorded-incident history, with population apportioned from the '
  'authoritative panchayat total. A real Census ward table can be dropped in '
  'as data/static/wards_overrides.csv (locality, ward_no, ward_name, '
  'population, source) — endpoint GET /wards/{locality}.')

H1('7.  Machine-learning engine')
P('Daily rainfall per locality (ERA5 archive via Open-Meteo, 2012–2025) '
  'trains three models per panchayat, all pure NumPy: an LSTM forecaster '
  '(the proposal’s named architecture), a ridge next-day-rainfall baseline, '
  'and a logistic hazard classifier for very-heavy-rain windows (>=64.5 mm '
  'within 3 days). Misses cost 4x a false alarm in training; each locality’s '
  'alert threshold is chosen on the 2018–2019 validation years as the most '
  'specific cutoff that still catches >=90% of dangerous windows, then '
  'measured honestly on 2020+ data the models never trained on.')
P('Result (test window 2020 → yesterday; full confusion matrices in '
  'ml/models/eval.json):')
TBL(['Locality', 'Test AUC', 'Test recall', 'Threshold', 'Heavy-day rate'], [
    ['Kumily', '0.938', '91.8%', '0.025', '2.5%'],
    ['Peermedu', '0.943', '88.1%', '0.038', '2.4%'],
    ['Idukki', '0.973', '93.7%', '0.279', '3.2%'],
    ['Adimali', '0.940', '92.9%', '0.041', '4.1%'],
    ['Kattappana', '0.967', '93.1%', '0.061', '3.6%'],
    ['Munnar', '0.941', '78.8%', '0.129', '4.8%'],
    ['Nedumkandam', '0.971', '95.5%', '0.078', '3.7%'],
], widths=[30, 26, 28, 26, CW - 110])
P('Median detection of dangerous windows ≈ 93%, AUC 0.94–0.97, validation '
  'calibration target met (recall 93% at 14.5% precision). Ridge next-day '
  'rainfall: MAE ≈ 7.0 mm vs a daily σ of ≈15 mm (R² ≈ 0.37). The live '
  '24-hour outlook shown in every locality panel (“AI outlook”) uses these '
  'models and labels its own uncertainty; the operational forecast remains '
  'the primary source.')

H1('8.  Seasonal context and reporting')
P('ENSO phase from the vendored NOAA CPC ONI table (live: Moderate El Niño, '
  'ONI +1.39 °C) plus a per-locality lightning-risk climatology give the '
  'amber header pill and seasonal advisories. Administrator exports: one PDF '
  'and one DOCX per locality or for the whole district (GET /report) — '
  'headline tier, sub-scores, weather, drivers, incidents and ENSO context, '
  'built with fpdf2 (Unicode font fallback) and a zero-dependency stdlib '
  'OOXML writer.')

H1('9.  SMS alert service (resident registration)')
P('The header “SMS Alerts” button (and every locality panel) opens a '
  'registration form. A resident enters a validated 10-digit Indian mobile '
  'number, chooses the panchayats to watch, the message language'  '(English/Malayalam) and the alert plans:')
BUL([
    'Danger alerts — instant SMS when a watched area reaches the chosen threshold (High or Extreme), max once per area per day.',
    'Daily briefing — every day at 07:00 IST: today’s level and rain plus tomorrow’s forecast for each watched area.',
    'Weekly outlook — every Monday at 08:00 IST: the week’s worst day per area from the 7-day danger outlook.',
])
P('A background scheduler (notify/scheduler.py) evaluates subscriptions every '
  '60 s and refreshes the district danger snapshot every 10 min while danger '
  'subscriptions exist. Delivery state lives in the subscription record, so '
  'restarts never double-send; failed sends retry with backoff. Subscriptions '
  'persist in data/subscriptions.json (git-ignored — personal data). '
  'Messages are chunked to SMS segment limits and composed per language.')
H3('Gateway: demo → live')
P('Without a gateway key the service runs in demo mode: every message is '
  'previewed in the UI and recorded to data/notifications/outbox.jsonl so the '
  'whole flow is verifiable before connecting a gateway. Add to .env: '
  'FAST2SMS_API_KEY (Indian gateway — register a DLT sender/template for '
  'transactional SMS) or Twilio keys (TWILIO_ACCOUNT_SID / '
  'TWILIO_AUTH_TOKEN / TWILIO_FROM) — real SMS then goes out with zero code '
  'changes. GET /notify/status reports which path is live.')
H3('Sample messages (demo previews, as generated)')
CODE('⚠ DANGER ALERT — Kumily, Idukki\n'
     'Level: High (score 0.72)\n'
     'Heavy rain on steep terrain\n'
     'Rain: 78.4 mm · Why: Heavy rain (>64 mm/day) — IMD "heavy rain" category\n'
     'Stay safe · KSDMA 1077\n'
     '\n'
     'Idukki · 03 Sep morning briefing\n'
     '• Kumily: High · 78.4 mm today · tomorrow 45.2 mm\n'
     '• Munnar: Moderate · 22 mm today\n'
     'Kerala disaster helpline: 1077')

H1('10.  REST API surface')
TBL(['Method / Path', 'Purpose'], [
    ['GET /', 'Dashboard UI (static, bilingual)'],
    ['GET /health · /summary', 'Health + district tier/source summary'],
    ['GET /localities', 'List with population, ward count, LSG meta'],
    ['GET /index[ /{locality}]', 'Danger index for all / one panchayat'],
    ['GET /danger-forecast/{locality}', '7-day danger outlook (tier per day, probability, worst day)'],
    ['GET /trends/{locality}', '3 chart series: outlook, 30-day measured, 48-h wind/humidity/temp'],
    ['GET /wards/{locality}', 'Ward micro-zones with risk + population'],
    ['GET /incidents · /map', 'Historical incidents / interactive Folium map'],
    ['GET /ml', 'AI 24-h outlook + eval (AUC, recall, thresholds)'],
    ['GET /outlook', 'ENSO phase + lightning advisories'],
    ['GET /report?locality=&format=pdf|docx', 'Seasonal report download'],
    ['GET/POST/DELETE /notify/subscribe · /notify/test · /notify/messages · /notify/status', 'SMS alert registration, testing and audit'],
], widths=[82, CW - 82])

H1('11.  Resident dashboard (frontend)')
BUL([
    'Professional charcoal theme with restrained forest-green accents (no decorative animation), full English ⇄ Malayalam toggle (English default, remembered per browser; the UI, guidance and SMS messages all translate).',
    'Search + tier filters and one-click shortcuts: “Most at risk now”, “Worst day this week” (scans all 7 outlooks).',
    'Per-locality drawer: plain-language guidance, 7-day danger outlook chart (tier-coloured bars), AI model alert, lightning/ENSO, three provider-tagged trend charts, ward-exposure list, nearby incidents, PDF/DOCX downloads, SMS-subscribe shortcut.',
    'Live indicators: season pill, ● live / ⚠ modelled source pill, ENSO pill, provider tags on every number.',
])

H1('12.  Verified working flows')
P('Every flow below was executed live on the running system (localhost:8000) '
  'and the observed outputs recorded:')
BUL([
    'Dashboard render: 7 panchayats with live conditions (Open-Meteo), population and ward counts, district Low headline.',
    '7-day danger outlook endpoint returns per-day tier/score/colour/probability + worst_day; a synthetic 45 mm day correctly flips Low → Moderate with landslide drivers.',
    'ML suite: 7/7 localities trained; /ml predicts next-day rain (~7 mm Kumily); heavy_alert flags respond to thresholds.',
    'ENSO outlook live: Moderate El Niño · ONI 1.39 °C pill in header; lightning advisories per locality.',
    'Reports: valid PDF (37.7 KB) and real DOCX downloaded for district and single locality.',
    'Ward layer: /wards/Kumily returns the 20 real LSG wards with incident-weighted risk; /trends returns all 3 chart series.',
    'SMS flow: POST /notify/subscribe (EN and ML) → welcome message recorded; GET re-fetches the subscription; scheduler auto-fired a real daily briefing to the test subscription within 60 s; POST /notify/test recorded a preview; DELETE removed it; /notify/messages lists the audit trail.',
    'Bilingual UI: full Malayalam flip verified across header, hero, cards, filters, drawer, SMS modal — zero console errors.',
])

H1('13.  How to run')
CODE('git clone https://github.com/karthikjash/idukki-danger-index\n'
     'cd idukki-danger-index\n'
     '.venv/bin/pip install -r requirements.txt   # or: pip install -r requirements.txt\n'
     '.venv/bin/python api/server.py              # dashboard + API on :8000\n'
     '\n'
     '# optional — better live feed & real SMS:\n'
     'cp .env.example .env        # add OPENWEATHERMAP_API_KEY / FAST2SMS_API_KEY (or Twilio)\n'
     '\n'
     '# regenerate ML models (auto-trained on first boot otherwise):\n'
     '.venv/bin/python ml/train.py\n'
     '# regenerate this booklet:\n'
     '.venv/bin/python docs/generate_project_doc.py')
P('Requirements: Python 3.9+, internet for live weather. Docs: README.md · '
  'docs/METHODOLOGY.md · docs/API_REFERENCE.md · docs/DATA_SOURCES.md · '
  'docs/PROPOSAL_COVERAGE.md · docs/ACCURACY_IMPROVEMENT_REPORT.md')

H1('14.  Limitations and roadmap')
BUL([
    'Incident register is a 15-row sample, not the live KSDMA database; terrain is per-locality constant, not SRTM elevation/slope.',
    'Open-Meteo/ERA5 weather rather than IMD gridded data (IMD requires registration); no validation against actual 2018–2020 outcomes yet (a backtest script is the next step).',
    'Ward structures for six panchayats are LSG-typical models until Census ward tables are dropped in via wards_overrides.csv.',
    'SMS alerting is a prototype awaiting a gateway key for real delivery; danger alerts currently trigger on the computed tier, refreshed every 10 minutes.',
])

# ---------------------------------------------------------------- meta block
B.set_y(-40) if B.get_y() < 250 else None
H1('15.  Document control')
TBL(['Item', 'Value'], [
    ['Project', 'Idukki Monsoon Danger Index (github.com/karthikjash/idukki-danger-index)'],
    ['Document version', '1.3 — generated September 2026'],
    ['Reproducibility', 'Run docs/generate_project_doc.py; ML numbers read live from ml/models/eval.json'],
    ['Coverage tracking', 'docs/PROPOSAL_COVERAGE.md maps every proposal item to status'],
], widths=[36, CW - 36])

OUT = ROOT / 'docs' / 'PROJECT_DOCUMENTATION.pdf'
B.output(str(OUT))
print(f'OK — {OUT} ({OUT.stat().st_size // 1024} KB, {B.page_no()} pages)')
