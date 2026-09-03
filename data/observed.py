"""
Measured (observed) recent weather + per-locality trends assembly.

Why this module exists
----------------------
OpenWeatherMap's free tier exposes NO historical weather, and IMD gridded
data needs registration, so the project's *measured* recent record comes from
Open-Meteo's free `past_days` feed (measured daily/hourly values, updated
hourly). This module provides:

  1. observed_daily(lat, lon, days)  - measured daily rain/wind/humidity for
     the last N days (one cached API call, ~30 days requested by default).
  2. LiveHistoryStore - the project's own accumulating daily record per
     locality (JSON under /tmp/ssr_cache/live_history). Each day the running
     server closes the previous (fully measured) day. The store feeds the
     soil-saturation score and future ML retrains with genuinely observed
     values - so the models keep learning from real weather the longer the
     system runs.
  3. build_trends(locality, lat, lon) - the three chart series the drawer
     renders. Provider is tagged per series so the UI never mislabels:
       * rain_outlook : OpenWeatherMap 5-day/3h (when key set) else Open-Meteo 7-day
       * observed_30d : Open-Meteo measured past_days
       * hourly_48h   : OpenWeatherMap 3h steps (when key set) else Open-Meteo hourly
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

CACHE_DIR = Path('/tmp/ssr_cache')
LIVE_HISTORY_DIR = CACHE_DIR / 'live_history'
LIVE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

OPEN_METEO_FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
STORE_LIMIT_DAYS = 120   # keep ~4 months of observed history per locality
TRENDS_TTL_HOURS = 3     # OWM forecast refreshes ~every 3 h


# ------------------------------------------------------------------ caching
def _read_cache(path: Path, ttl_hours: float) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        age = datetime.now() - datetime.fromisoformat(data['timestamp'])
        if age < timedelta(hours=ttl_hours):
            return data.get('data')
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'cache read error {path.name}: {exc}')
    return None


def _write_cache(path: Path, data) -> None:
    try:
        with open(path, 'w') as f:
            json.dump({'timestamp': datetime.now().isoformat(), 'data': data},
                      f, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'cache write error {path.name}: {exc}')


# ------------------------------------------------------------- observed feed
def observed_daily(lat: float, lon: float, days: int = 30,
                   refresh: bool = False) -> Optional[pd.DataFrame]:
    """Measured daily rain/wind/humidity for the last `days` full days.

    One Open-Meteo call with past_days=N (measured values; today excluded
    because the IST day is not complete until midnight). Cached for 6 h.
    Returns a DataFrame with date/rain_mm/wind_max_mps/humidity_mean_pct and
    df.attrs['provider'] = 'open-meteo measured'.
    """
    cache_path = CACHE_DIR / f'obs_{lat:.2f}_{lon:.2f}_{days}d_cache.json'
    cached = _read_cache(cache_path, ttl_hours=6) if not refresh else None
    if cached is not None:
        df = pd.DataFrame(cached['rows'])
        df['date'] = pd.to_datetime(df['date'])
        df.attrs['provider'] = cached.get('provider', 'open-meteo measured')
        return df

    params = {
        'latitude': lat, 'longitude': lon,
        'daily': 'precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,'
                 'relative_humidity_2m_mean',
        'past_days': days, 'forecast_days': 1,
        'wind_speed_unit': 'ms', 'precipitation_unit': 'mm',
        'timezone': 'Asia/Kolkata',
    }
    try:
        r = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=20)
        r.raise_for_status()
        daily = r.json().get('daily', {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'observed fetch failed ({lat:.2f},{lon:.2f}): {exc}')
        return None

    times = pd.to_datetime(daily.get('time', []))
    rain = [float(v or 0.0) for v in daily.get('precipitation_sum', [])]
    wind = [float(v or 0.0) for v in daily.get('wind_speed_10m_max', [])]
    gust = [float(v or 0.0) for v in daily.get('wind_gusts_10m_max', [])]
    hum = [float(v or 0.0) for v in daily.get('relative_humidity_2m_mean', [])]
    today = pd.Timestamp.now(IST).date()
    rows = [{'date': d, 'rain_mm': r_, 'wind_max_mps': w_, 'gust_max_mps': g_,
             'humidity_mean_pct': h_}
            for d, r_, w_, g_, h_ in zip(times, rain, wind, gust, hum)
            if d.date() < today]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df.attrs['provider'] = 'open-meteo measured'
    _write_cache(cache_path, {'provider': df.attrs['provider'],
                              'rows': df.to_dict(orient='records')})
    return df


# ------------------------------------------------------- observed history store
class LiveHistoryStore:
    """Rolling day-by-day observed record per locality.

    The store closes each IST day once it is complete (i.e. when we next run,
    we persist *yesterday's* measured rain/wind/humidity from the past_days
    feed). Rows are tagged with the provider that supplied them so retrains
    and charts stay honest. The file lives under /tmp (ephemeral scratch);
    point STORE_DIR at a persistent volume for long-running deployments.
    """

    def __init__(self, store_dir: Path = LIVE_HISTORY_DIR):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, lat: float, lon: float) -> Path:
        return self.store_dir / f'live_{lat:.2f}_{lon:.2f}.json'

    def _load(self, lat: float, lon: float) -> list:
        path = self._path(lat, lon)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text()).get('rows', [])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f'live history read error {path.name}: {exc}')
            return []

    def _save(self, lat: float, lon: float, rows: list) -> None:
        rows = rows[-STORE_LIMIT_DAYS:]
        try:
            self._path(lat, lon).write_text(json.dumps(
                {'rows': rows}, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f'live history write error: {exc}')

    def record_today(self, lat: float, lon: float) -> None:
        """Persist yesterday's measured day (skip if already recorded)."""
        today = datetime.now(IST).date()
        rows = self._load(lat, lon)
        dates = {r['date'] for r in rows}
        y_iso = (today - timedelta(days=1)).isoformat()
        if y_iso in dates:
            return
        obs = observed_daily(lat, lon, days=3, refresh=False)
        if obs is None or obs.empty:
            return
        y = obs[obs['date'].dt.date == today - timedelta(days=1)]
        if y.empty:
            return
        row = y.iloc[0]
        rows.append({
            'date': y_iso,
            'rain_mm': round(float(row['rain_mm']), 1),
            'wind_max_mps': round(float(row['wind_max_mps']), 1),
            'humidity_mean_pct': round(float(row['humidity_mean_pct']), 1),
            'provider': obs.attrs.get('provider', 'open-meteo measured'),
            'recorded_at': datetime.now(IST).isoformat(),
        })
        self._save(lat, lon, rows)

    def recent(self, lat: float, lon: float, limit: int = 30) -> pd.DataFrame:
        """Recent recorded rows (oldest first), empty frame if none yet."""
        rows = self._load(lat, lon)[-limit:]
        if not rows:
            return pd.DataFrame(columns=['date', 'rain_mm', 'wind_max_mps',
                                         'humidity_mean_pct', 'provider'])
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        return df.reset_index(drop=True)


# ------------------------------------------------------------ trends builder
def _om_rain_outlook(lat: float, lon: float, days: int = 7) -> Optional[pd.DataFrame]:
    """Open-Meteo 7-day daily rainfall outlook (used when no OWM key)."""
    params = {
        'latitude': lat, 'longitude': lon,
        'daily': 'precipitation_sum,precipitation_probability_max',
        'forecast_days': days, 'precipitation_unit': 'mm',
        'timezone': 'Asia/Kolkata',
    }
    try:
        r = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=20)
        r.raise_for_status()
        daily = r.json().get('daily', {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'rain outlook fetch failed: {exc}')
        return None
    dates = pd.to_datetime(daily.get('time', []))
    rain = [float(v or 0.0) for v in daily.get('precipitation_sum', [])]
    pops = daily.get('precipitation_probability_max')
    pops = [None if p is None else float(p) for p in (pops or [])]
    df = pd.DataFrame({'date': dates, 'rain_mm': rain, 'pop_pct': pops})
    df.attrs['provider'] = 'open-meteo'
    return df


def _om_hourly(lat: float, lon: float, hours: int = 48) -> Optional[pd.DataFrame]:
    """Open-Meteo hourly temperature/humidity/wind for the next `hours`."""
    params = {
        'latitude': lat, 'longitude': lon,
        'hourly': 'temperature_2m,relative_humidity_2m,wind_speed_10m,'
                  'wind_gusts_10m,precipitation_probability',
        'forecast_days': 3, 'wind_speed_unit': 'ms',
        'timezone': 'Asia/Kolkata',
    }
    try:
        r = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=20)
        r.raise_for_status()
        h = r.json().get('hourly', {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f'hourly fetch failed: {exc}')
        return None
    times = pd.to_datetime(h.get('time', []))
    n = min(hours, len(times))
    out = pd.DataFrame({
        'time': times[:n],
        'temp_c': [float(v or 0.0) for v in h.get('temperature_2m', [])[:n]],
        'humidity_pct': [float(v or 0.0) for v in h.get('relative_humidity_2m', [])[:n]],
        'wind_mps': [float(v or 0.0) for v in h.get('wind_speed_10m', [])[:n]],
        'gust_mps': [float(v or 0.0) for v in h.get('wind_gusts_10m', [])[:n]],
        'pop_pct': [float(v or 0.0) for v in h.get('precipitation_probability', [])[:n]],
    })
    return out if not out.empty else None


def build_trends(locality: str, lat: float, lon: float,
                 current_provider: str = 'synthetic') -> dict:
    """Assemble the drawer's three chart series with per-series provider tags.

    Network work is cached for TRENDS_TTL_HOURS (3 h) - the first call for a
    locality pays 1-3 upstream requests; subsequent opens are instant.
    """
    cache_path = CACHE_DIR / f'trends_{lat:.2f}_{lon:.2f}_cache.json'
    cached = _read_cache(cache_path, ttl_hours=TRENDS_TTL_HOURS)
    if cached is not None:
        cached['locality'] = locality
        cached['cached'] = True
        return cached

    from data.openweather import OpenWeatherClient
    owm = OpenWeatherClient()

    # 1) rainfall outlook - OWM 5-day/3h when key present, else OM 7-day
    rain_outlook = None
    if owm.enabled:
        df = owm.daily_forecast(lat, lon, days=5)
        if df is not None:
            today_partial = True   # day-0 bucket covers only the forecast span
            rain_outlook = {
                'provider': 'openweathermap',
                'today_partial': today_partial,
                'days': [{'date': str(d.date()),
                          'rain_mm': round(float(r), 1),
                          'pop_pct': None if p is None else round(float(p), 0)}
                         for d, r, p in zip(df['date'], df['rain_mm'], df['pop_pct'])],
            }
    if rain_outlook is None:
        df = _om_rain_outlook(lat, lon, days=7)
        if df is not None:
            rain_outlook = {
                'provider': 'open-meteo',
                'today_partial': False,
                'days': [{'date': str(d.date()),
                          'rain_mm': round(float(r), 1),
                          'pop_pct': None if p is None else round(float(p), 0)}
                         for d, r, p in zip(df['date'], df['rain_mm'], df['pop_pct'])],
            }

    # 2) observed 30-day monsoon pattern (measured)
    obs = observed_daily(lat, lon, days=30)
    observed_30d = None
    if obs is not None:
        observed_30d = {
            'provider': obs.attrs.get('provider', 'open-meteo measured'),
            'days': [{'date': str(d.date()),
                      'rain_mm': round(float(r), 1),
                      'wind_max_mps': round(float(w), 1),
                      'humidity_mean_pct': round(float(h), 1)}
                     for d, r, w, h in zip(obs['date'], obs['rain_mm'],
                                           obs['wind_max_mps'],
                                           obs['humidity_mean_pct'])],
        }

    # 3) hourly wind/humidity/temperature for the next 48 h
    hourly = None
    if owm.enabled:
        hf = owm.hourly_series(lat, lon, hours=48)
        if hf is not None:
            hourly = {'provider': 'openweathermap',
                      'step_hours': 3,
                      'hours': hf.to_dict(orient='records')}
    if hourly is None:
        hf = _om_hourly(lat, lon, hours=48)
        if hf is not None:
            hourly = {'provider': 'open-meteo', 'step_hours': 1,
                      'hours': [{'time': str(t), 'temp_c': round(r, 1),
                                 'humidity_pct': round(h, 1),
                                 'wind_mps': round(w, 1),
                                 'gust_mps': round(g, 1),
                                 'pop_pct': round(p, 0)}
                                for t, r, h, w, g, p in zip(
                                    hf['time'], hf['temp_c'], hf['humidity_pct'],
                                    hf['wind_mps'], hf['gust_mps'], hf['pop_pct'])]}

    trends = {
        'locality': locality,
        'generated_at': datetime.now(IST).isoformat(),
        'cached': False,
        'providers': {
            'current': current_provider,
            'rain_outlook': (rain_outlook or {}).get('provider', 'none'),
            'observed_30d': (observed_30d or {}).get('provider', 'none'),
            'hourly_48h': (hourly or {}).get('provider', 'none'),
        },
        'rain_outlook': rain_outlook,
        'observed_30d': observed_30d,
        'hourly_48h': hourly,
    }
    if any((rain_outlook, observed_30d, hourly)):
        _write_cache(cache_path, trends)
    return trends
