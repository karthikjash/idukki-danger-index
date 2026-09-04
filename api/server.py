"""
FastAPI Backend for Idukki Monsoon Danger Index
Serves the resident dashboard (static UI) and the REST API for government
integration: forecast data, Danger Index, map generation.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import pandas as pd
import logging
import threading
from datetime import datetime
import os
import sys
import json
from pathlib import Path

# Ensure the project root is importable no matter where this file is run from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetcher import LOCALITIES
from index.calculator import compute_all_locality_indices, get_season_info
from index.map_generator import generate_danger_map

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Idukki Monsoon Danger Index API",
    description="Hyperlocal monsoon severity forecasting for inner Idukki",
    version="1.3.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Static dashboard UI
# --------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, 'frontend', 'static')

try:
    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
except Exception as e:
    logger.warning(f"Static UI not mounted (frontend/static missing?): {e}")

# Pydantic models for API responses
class WeatherInfo(BaseModel):
    rainfall_mm: Optional[float] = None
    wind_mps: Optional[float] = None
    humidity_pct: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    temperature_c: Optional[float] = None
    observed_at: Optional[str] = None

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
    weather: Optional[WeatherInfo] = None
    data_source: str = 'synthetic'
    conditions_provider: Optional[str] = None
    population: Optional[int] = None
    ward_count: Optional[int] = None
    season: str = 'dry'
    drivers: List[str] = []

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
    meta: Optional[Dict[str, Dict]] = None

class DailyRainfall(BaseModel):
    date: str
    rainfall_mm: float

class ForecastResponse(BaseModel):
    locality: str
    source: str
    season: str
    daily: List[DailyRainfall]


class NotifySubscribeRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    lang: str = 'en'
    localities: List[str]
    threshold: str = 'High'
    plans: List[str]


class NotifyUnsubscribeRequest(BaseModel):
    phone: str


class NotifyTestRequest(BaseModel):
    phone: str
    lang: str = 'en'


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
    indices, _ = compute_all_locality_indices()
    return indices


def _force_live_refresh() -> None:
    """Drop stale weather/index caches and recompute from the live feed.

    Backs the UI's 'Retry live feed' action - a genuine re-fetch, not a
    cache re-read. Guarded with a short cooldown so parallel
    /summary?refresh=1 + /index?refresh=1 calls only compute once.
    """
    now = datetime.now()
    last = _cache.get('last_refresh')
    if last and (now - last).total_seconds() < 60:
        return
    _cache['last_refresh'] = now
    cache_dir = Path('/tmp/ssr_cache')
    if cache_dir.exists():
        for p in cache_dir.glob('*.json'):
            try:
                p.unlink()
            except OSError:
                pass
    _cache['indices'] = {}
    logger.info("Forced live refresh: recomputing indices from the live feed...")
    _cache['indices'] = compute_all_indices()
    _save_cached_indices(_cache['indices'])
    logger.info("Forced live refresh complete.")


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
def startup_event():
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

    # Train the ML suite in the background on first boot (no artifacts yet),
    # so the dashboard never blocks on model training.
    def _maybe_train_ml():
        try:
            from ml.predict import train_if_missing
            if train_if_missing():
                logger.info("ML model suite trained on first boot")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Background ML training failed: {exc}")

    # Close yesterday's fully-measured day into the observed-history store
    # (feeds soil saturation + future model retrains with real observations).
    def _close_observed_days():
        try:
            from data.fetcher import record_observed_history
            n = record_observed_history()
            if n:
                logger.info(f"Observed history: closed {n} day(s) into the store")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Observed-history close failed: {exc}")

    # SMS alert scheduler (danger alerts / daily briefs / weekly outlooks).
    def _start_notify():
        try:
            from notify.scheduler import start as start_notify
            start_notify()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"SMS scheduler failed to start: {exc}")

    threading.Thread(target=_maybe_train_ml, daemon=True).start()
    threading.Thread(target=_close_observed_days, daemon=True).start()
    threading.Thread(target=_start_notify, daemon=True).start()
    logger.info("Ready to serve requests")


def _to_response(index_data: dict) -> DangerIndexResponse:
    """Build the API response object from an index result dict."""
    weather = index_data.get('weather') or {}
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
        longitude=index_data['longitude'],
        weather=WeatherInfo(
            rainfall_mm=weather.get('rainfall_mm'),
            wind_mps=weather.get('wind_mps'),
            humidity_pct=weather.get('humidity_pct'),
            cloud_cover_pct=weather.get('cloud_cover_pct'),
            temperature_c=weather.get('temperature_c'),
            observed_at=index_data.get('observed_at'),
        ),
        data_source=index_data.get('data_source', 'synthetic'),
        conditions_provider=index_data.get('conditions_provider'),
        population=index_data.get('population'),
        ward_count=index_data.get('ward_count'),
        season=index_data.get('season', 'dry'),
        drivers=index_data.get('drivers', []),
    )


# --------------------------------------------------------------------------
# UI routes
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the resident dashboard UI"""
    index_path = os.path.join(STATIC_DIR, 'index.html')
    if not os.path.exists(index_path):
        return HTMLResponse(
            "<h1>Idukki Monsoon Danger Index</h1>"
            "<p>Dashboard UI not found — check frontend/static/index.html</p>"
            "<p>API docs: <a href='/docs'>/docs</a></p>"
        )
    return FileResponse(index_path, media_type='text/html')


# --------------------------------------------------------------------------
# API routes
# --------------------------------------------------------------------------
@app.get("/health")
def health_check():
    """Health check endpoint"""
    season, _ = get_season_info()
    return {
        "status": "healthy",
        "season": season,
        "last_update": _cache['last_update'],
        "localities_computed": len(_cache['indices']),
        "incidents_loaded": len(_cache['incidents']) if _cache['incidents'] is not None else 0
    }


@app.get("/localities", response_model=LocalityListResponse)
def get_localities():
    """List all monitored localities (+ population and ward structure meta)"""
    locality_list = sorted(LOCALITIES.keys())
    from index.calculator import LOCALITY_POPULATION
    from index.wards import _load_structure
    structure = _load_structure()
    meta = {}
    for name in locality_list:
        info = structure.get(name, {})
        meta[name] = {
            'population': LOCALITY_POPULATION.get(name, 0),
            'ward_count': len(info.get('wards', [])),
            'lsg': info.get('lsg', ''),
            'structure_source': info.get('structure_source', ''),
            'coordinates': {'lat': LOCALITIES[name]['lat'],
                            'lon': LOCALITIES[name]['lon']},
        }
    return {
        "localities": locality_list,
        "count": len(locality_list),
        "meta": meta
    }


@app.get("/index", response_model=List[DangerIndexResponse])
def get_all_indices(refresh: bool = False):
    """Get Danger Index for all localities (from cache)

    ?refresh=1 drops stale caches and recomputes from the live weather
    feed before returning (used by the UI's 'Retry live feed').
    """

    if refresh:
        _force_live_refresh()

    if not _cache['indices']:
        # Try to load from cache
        _cache['indices'] = _load_cached_indices()

        # If still empty, compute fresh
        if not _cache['indices']:
            logger.warning("No cached indices, computing fresh...")
            _cache['indices'] = compute_all_indices()
            _save_cached_indices(_cache['indices'])

    return [_to_response(index_data) for index_data in _cache['indices'].values()]


@app.get("/index/{locality}", response_model=DangerIndexResponse)
def get_locality_index(locality: str):
    """Get Danger Index for specific locality"""

    if locality not in LOCALITIES:
        raise HTTPException(status_code=404, detail=f"Locality '{locality}' not found")

    if not _cache['indices']:
        _cache['indices'] = compute_all_indices()

    if locality not in _cache['indices']:
        raise HTTPException(status_code=500, detail=f"Failed to compute index for {locality}")

    return _to_response(_cache['indices'][locality])


@app.get("/forecast/{locality}", response_model=ForecastResponse)
def get_forecast(locality: str, days: int = 7):
    """Get the daily rainfall forecast for a locality (1-7 days)."""

    if locality not in LOCALITIES:
        raise HTTPException(status_code=404, detail=f"Locality '{locality}' not found")

    days = max(1, min(days, 7))
    loc = LOCALITIES[locality]

    try:
        from data.fetcher import IMDDataFetcher
        df = IMDDataFetcher().get_rainfall_forecast(loc['lat'], loc['lon'], days)
        daily = [
            DailyRainfall(
                date=pd.Timestamp(row['date']).strftime('%Y-%m-%d'),
                rainfall_mm=round(float(row['rainfall_mm']), 1)
            )
            for _, row in df.head(days).iterrows()
        ]
        source = df.attrs.get('source', 'synthetic')
    except Exception as e:
        logger.error(f"Forecast failed for {locality}: {e}")
        raise HTTPException(status_code=500, detail=f"Forecast unavailable for {locality}")

    season, _ = get_season_info()
    return ForecastResponse(
        locality=locality,
        source=source,
        season=season,
        daily=daily
    )


@app.get("/danger-forecast/{locality}")
def get_danger_forecast(locality: str):
    """7-day-ahead danger outlook: per-day tier from the rainfall forecast.

    Each day is scored with the SAME model used for today's index, so a
    rising tier on, say, day 4 is visible days before the rain arrives.
    """
    if locality not in LOCALITIES:
        raise HTTPException(status_code=404, detail=f"Locality '{locality}' not found")

    indices = _cache['indices'] or compute_all_indices()
    index = indices.get(locality)
    context = (index or {}).get('weather') or {}

    try:
        from data.fetcher import IMDDataFetcher
        from index.calculator import compute_forecast_outlook
        loc = LOCALITIES[locality]
        df = IMDDataFetcher().get_rainfall_forecast(loc['lat'], loc['lon'], 7)
        outlook = compute_forecast_outlook(locality, df, days=7, context_weather=context)
        return outlook
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Danger forecast failed for {locality}: {exc}")
        raise HTTPException(status_code=500,
                            detail=f"7-day danger outlook unavailable for {locality}: {exc}")


@app.get("/incidents", response_model=List[HistoricalIncident])
def get_incidents():
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
def get_map():
    """Generate and serve interactive danger map"""

    map_file = "/tmp/idukki_danger_map.html"

    # Generate map with current indices and incidents
    indices = _cache['indices'] or compute_all_indices()
    incidents = get_historical_incidents()

    generate_danger_map(indices, incidents, map_file)

    # Read and return HTML
    with open(map_file, 'r') as f:
        return f.read()


@app.get("/report")
def download_report(locality: str = "all", format: str = "pdf"):
    """Seasonal risk report as PDF or DOCX for one locality or the whole district."""
    fmt = format.lower().strip()
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status_code=400,
                            detail="format must be 'pdf' or 'docx'")

    indices = _cache['indices'] or compute_all_indices()
    if locality != 'all' and locality not in indices:
        raise HTTPException(status_code=404,
                            detail=f"Locality '{locality}' not found")
    selected = indices if locality == 'all' else {locality: indices[locality]}

    try:
        from reporting.report import generate
        from outlook import build_outlook
        outlook = build_outlook()
        content = generate(locality, fmt, selected,
                           incidents=get_historical_incidents(),
                           outlook=outlook)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Report generation failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Report failed: {exc}")

    name = 'district' if locality == 'all' else locality.lower().replace(' ', '_')
    filename = f"idukki_{name}_monsoon_report_{datetime.now():%Y%m%d}.{fmt}"
    media = 'application/pdf' if fmt == 'pdf' else \
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return Response(content=content, media_type=media,
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get("/wards/{locality}")
def get_wards(locality: str):
    """Ward-level micro-zonation for one panchayat (LSG ward structure +
    incident-derived sensitivity + apportioned population)."""
    if locality not in LOCALITIES:
        raise HTTPException(status_code=404, detail=f"Locality '{locality}' not found")
    indices = _cache['indices'] or compute_all_indices()
    index = indices.get(locality, {})
    try:
        from index.wards import ward_risk
        return ward_risk(locality, float(index.get('composite_score', 0.0) or 0.0),
                         incidents=get_historical_incidents())
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Ward risk failed for {locality}: {exc}")
        raise HTTPException(status_code=500, detail=f"Ward data unavailable: {exc}")


@app.get("/trends/{locality}")
def get_trends(locality: str):
    """Chart series for a locality: 7-day rainfall outlook (provider-tagged),
    30-day measured monsoon pattern, and 48h wind/humidity/temperature."""
    if locality not in LOCALITIES:
        raise HTTPException(status_code=404, detail=f"Locality '{locality}' not found")
    loc = LOCALITIES[locality]
    indices = _cache['indices'] or compute_all_indices()
    provider = (indices.get(locality, {}).get('conditions_provider')
                or 'synthetic')
    try:
        from data.observed import build_trends
        return build_trends(locality, loc['lat'], loc['lon'],
                            current_provider=provider)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Trends failed for {locality}: {exc}")
        raise HTTPException(status_code=500, detail=f"Trends unavailable: {exc}")


@app.get("/outlook")
def seasonal_outlook():
    """Seasonal outlook: ENSO phase context + per-locality lightning risk."""
    try:
        from outlook import build_outlook
        return build_outlook()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Outlook failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Outlook unavailable: {exc}")


# --------------------------------------------------------------------------
# SMS alert subscriptions
# --------------------------------------------------------------------------
@app.get("/notify/status")
def notify_status():
    """Which SMS path is live (Twilio / Fast2SMS / demo outbox) + counts."""
    from notify.sms import provider_status, outbox
    from notify import store
    st = provider_status()
    subs = store.all()
    plan_counts = {'danger': 0, 'daily': 0, 'weekly': 0}
    for s in subs:
        for p in s.get('plans', []):
            plan_counts[p] = plan_counts.get(p, 0) + 1
    return {
        'status': 'ok',
        'demo': st['demo'],
        'provider': st['provider'],
        'note': st['note'],
        'subscriptions': len(subs),
        'plan_counts': plan_counts,
        'messages_sent': len(outbox()),
    }


@app.post("/notify/subscribe", response_model=None)
def notify_subscribe(req: NotifySubscribeRequest):
    """Register a mobile number for SMS alerts.

    Body: {phone, name?, lang: en|ml, localities: [...],
           threshold: High|Extreme, plans: [danger, daily, weekly]}
    A welcome SMS confirms the subscription (demo mode if no gateway key).
    """
    from notify.sms import provider_status
    from notify import store, messages
    try:
        body = store.validate_payload(req.dict(), set(LOCALITIES.keys()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sub = store.upsert(body)
    st = provider_status()
    welcome_previews = []
    welcome_delivered = True
    try:
        for text in messages.compose(sub, 'welcome', {'demo': st['demo']}):
            res = send_notify_text(sub, text)
            welcome_delivered = welcome_delivered and bool(res.get('delivered'))
            if res.get('preview'):
                welcome_previews.append(res['preview'])
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Welcome SMS failed: {exc}")
    welcome_res = {
        'delivered': welcome_delivered,
        'preview': '\n— next SMS —\n'.join(welcome_previews),
    }
    return {
        'ok': True,
        'phone': sub['phone'],
        'lang': sub['lang'],
        'localities': sub['localities'],
        'threshold': sub['threshold'],
        'plans': sub['plans'],
        'demo': st['demo'],
        'provider': st['provider'],
        'welcome': welcome_res.get('preview', ''),
        'welcome_delivered': welcome_res.get('delivered', False),
        'note': st['note'],
    }


def send_notify_text(sub: dict, text: str) -> dict:
    from notify.sms import send_sms
    return send_sms(sub.get('phone'), text, sub.get('lang') or 'en')


@app.get("/notify/subscribe")
def notify_get_subscription(phone: str):
    """Fetch the current subscription for a phone number (for pre-fill)."""
    from notify import store
    rec = store.get(phone)
    if not rec:
        raise HTTPException(status_code=404, detail="No subscription for that number.")
    rec.pop('state', None)
    return rec


@app.delete("/notify/subscribe")
def notify_unsubscribe(req: NotifyUnsubscribeRequest):
    """Remove the subscription for a phone number."""
    from notify import store
    removed = store.delete(req.phone)
    if not removed:
        raise HTTPException(status_code=404, detail="No subscription for that number.")
    return {'ok': True, 'removed': removed}


@app.post("/notify/test")
def notify_test(req: NotifyTestRequest):
    """Send a test SMS to a phone right now (demo mode returns the preview)."""
    from notify.sms import provider_status
    from notify import store, messages
    try:
        phone = store.normalize_phone(req.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    lang = req.lang if req.lang in ('en', 'ml') else 'en'
    sub = {'phone': phone, 'lang': lang, 'localities': ['Kumily'],
           'threshold': 'High', 'plans': ['danger']}
    st = provider_status()
    previews, delivered = [], True
    for text in messages.compose(sub, 'test', {'demo': st['demo']}):
        r = send_notify_text(sub, text)
        delivered = delivered and bool(r.get('delivered'))
        if r.get('preview'):
            previews.append(r['preview'])
    return {
        'ok': delivered, 'delivered': delivered,
        'preview': '\n— next SMS —\n'.join(previews),
        'demo': st['demo'], 'provider': st['provider'],
        'note': st['note'],
    }


@app.get("/notify/messages")
def notify_messages(phone: Optional[str] = None, limit: int = 15):
    """Recent SMS outbox entries — audit trail; in demo mode these show exactly
    what would have been sent to each number."""
    from notify.sms import outbox
    from notify import store
    limit = max(1, min(limit, 100))
    norm = None
    if phone:
        try:
            norm = store.normalize_phone(phone)
        except ValueError:
            norm = None
    return {'messages': outbox(phone=norm, limit=limit)}


@app.get("/ml")
def ml_outlook():
    """AI outlook: trained-model next-day rainfall + heavy-rain probability."""
    from pathlib import Path as _P
    eval_path = _P(__file__).resolve().parent.parent / "ml" / "models" / "eval.json"
    eval_data = None
    if eval_path.exists():
        with open(eval_path) as f:
            eval_data = json.load(f)

    indices = _cache['indices'] or compute_all_indices()
    try:
        from ml.predict import predict_tomorrow
        from data.fetcher import LOCALITIES as _LOC
        models = []
        for name in _LOC.keys():
            rain = (indices.get(name, {}).get('weather') or {}).get('rainfall_mm')
            pred = predict_tomorrow(name, rain)
            if pred.get('status') == 'ready':
                models.append(pred)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"ML outlook failed: {exc}")
        raise HTTPException(status_code=500, detail=f"ML outlook unavailable: {exc}")

    return {
        'status': 'ready' if (models and eval_data) else 'training',
        'note': 'Trained on 2012-2025 Open-Meteo/ERA5 daily rainfall; '
                'evaluation window 2020+ (see eval.json)',
        'evaluation': eval_data,
        'models': models,
    }


@app.get("/summary")
def get_summary(refresh: bool = False):
    """Get summary statistics for all localities.

    ?refresh=1 forces a live re-fetch first (see /index).
    """

    if refresh:
        _force_live_refresh()

    indices = _cache['indices'] or compute_all_indices()

    tier_counts = {}
    avg_score = 0
    synthetic_count = 0

    for locality, data in indices.items():
        tier = data['tier']
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        avg_score += data['composite_score']
        if data.get('data_source', 'synthetic') != 'live':
            synthetic_count += 1

    avg_score /= len(indices) if indices else 1
    season, _ = get_season_info()

    # District headline = most severe tier with at least one locality
    headline_tier, headline_count = 'Low', 0
    for tier in ['Extreme', 'High', 'Moderate', 'Low']:
        if tier_counts.get(tier, 0) > 0:
            headline_tier, headline_count = tier, tier_counts[tier]
            break

    return {
        "total_localities": len(indices),
        "tier_breakdown": tier_counts,
        "average_danger_score": round(avg_score, 2),
        "headline": {"tier": headline_tier, "count": headline_count},
        "season": season,
        "data_source": 'live' if synthetic_count == 0 else 'synthetic',
        "localities_on_synthetic": synthetic_count,
        "last_computed": _cache['last_update'],
        "status": "OK"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
