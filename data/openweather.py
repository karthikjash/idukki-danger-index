"""
OpenWeatherMap client — primary current-conditions provider.

Used by data/fetcher.py whenever OPENWEATHERMAP_API_KEY is set (the free tier
is sufficient: current weather + the 5-day / 3-hour forecast endpoint for all
7 localities).

Division of labour between providers (documented in docs/DATA_SOURCES.md):

* OpenWeatherMap (when key present)
    - current conditions: temperature, humidity, wind, gust, clouds, pressure
      and the live rain measurement (rain.1h / rain.3h when raining).
    - its own 5-day/3-hour forecast, aggregated to IST calendar days, served
      through /trends as the "OpenWeatherMap rainfall outlook" chart.
* Open-Meteo (always available, no key)
    - the 7-day daily rainfall forecast that drives the danger outlook and
      today's rain figure (a 7-day horizon is needed; OWM's free forecast is
      only 5 days), plus measured past_days for the observed 30-day series.

Honesty note: OWM's free plan exposes NO historical weather, so every
"observed" number in the project (30-day monsoon-pattern chart, yesterday's
measured rain, model retrain rows) still comes from Open-Meteo's measured
past_days feed — or from the project's own day-by-day observed history
accumulator (data/live_history.py) — and is labelled with its real provider.

Every returned object carries a `provider` key so the UI can always label
the true source of each number.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Load project .env (idempotent) so `export OPENWEATHERMAP_API_KEY=...` and a
# checked-in .env file both work from any launch directory.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:  # noqa: BLE001 - dotenv is optional
    pass

BASE_URL = 'https://api.openweathermap.org/data/2.5'
TIMEOUT_S = 8


class OpenWeatherClient:
    """Thin, resilient client over the OpenWeatherMap current/forecast APIs."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or os.getenv('OPENWEATHERMAP_API_KEY', '')).strip()
        self.enabled = bool(self.api_key)

    # ------------------------------------------------------------ HTTP core
    def _get(self, path: str, params: dict, attempts: int = 2):
        if not self.enabled:
            return None
        params = dict(params, appid=self.api_key, units='metric')
        last_exc = None
        for i in range(attempts):
            try:
                r = requests.get(f'{BASE_URL}/{path}', params=params,
                                 timeout=TIMEOUT_S)
                r.raise_for_status()
                return r.json()
            except Exception as exc:  # noqa: BLE001 - network/5xx retried
                last_exc = exc
                import time
                time.sleep(1.5 * (i + 1))
        logger.warning(f'OpenWeatherMap {path} failed: {last_exc}')
        return None

    # ------------------------------------------------------------ current
    def current(self, lat: float, lon: float) -> Optional[dict]:
        """Current observed conditions, shaped like the Open-Meteo current feed.

        Extra keys carried for the UI/graphs: temperature_c, pressure_hpa,
        feels_like_c, weather_desc, is_raining.
        """
        if not self.enabled:
            return None
        data = self._get('weather', {'lat': lat, 'lon': lon})
        if not data:
            return None
        try:
            main = data.get('main', {})
            wind = data.get('wind', {})
            clouds = data.get('clouds', {})
            rain = data.get('rain', {}) or {}
            rain_1h = float(rain.get('1h', 0.0) or 0.0)
            rain_3h = float(rain.get('3h', 0.0) or 0.0)
            # prefer the finer 1h window; scale 3h back to a per-hour rate
            precip_now = rain_1h if rain_1h > 0 else (rain_3h / 3.0)
            dt = int(data.get('dt', 0))
            return {
                'latitude': lat,
                'longitude': lon,
                'precipitation_mm': float(precip_now),
                'relative_humidity_pct': float(main.get('humidity', 0.0) or 0.0),
                'wind_speed_mps': float(wind.get('speed', 0.0) or 0.0),
                'wind_direction_deg': float(wind.get('deg', 0.0) or 0.0),
                'cloud_cover_pct': float(clouds.get('all', 0.0) or 0.0),
                'temperature_c': float(main.get('temp', 0.0) or 0.0),
                'feels_like_c': float(main.get('feels_like', 0.0) or 0.0),
                'pressure_hpa': float(main.get('pressure', 0.0) or 0.0),
                'weather_desc': (data.get('weather') or [{}])[0].get('description', ''),
                'is_raining': bool(precip_now > 0),
                'observed_at': (datetime.fromtimestamp(dt, tz=IST)
                                .isoformat() if dt else datetime.now(IST).isoformat()),
                'timestamp': datetime.now(IST).isoformat(),
                'provider': 'openweathermap',
            }
        except Exception as exc:  # noqa: BLE001 - tolerate odd payloads
            logger.warning(f'OpenWeatherMap current parse error: {exc}')
            return None

    # ------------------------------------------------------------ forecast
    def forecast_steps(self, lat: float, lon: float) -> Optional[pd.DataFrame]:
        """Raw 5-day / 3-hour forecast as a tidy DataFrame (UTC timestamps)."""
        if not self.enabled:
            return None
        data = self._get('forecast', {'lat': lat, 'lon': lon, 'cnt': 40})
        if not data:
            return None
        rows = []
        try:
            for item in data.get('list', []):
                wind = item.get('wind', {}) or {}
                rain = item.get('rain', {}) or {}
                rows.append({
                    'utc': datetime.fromtimestamp(int(item['dt']), tz=timezone.utc),
                    'temp_c': float((item.get('main') or {}).get('temp', 0.0) or 0.0),
                    'humidity_pct': float((item.get('main') or {}).get('humidity', 0.0) or 0.0),
                    'pressure_hpa': float((item.get('main') or {}).get('pressure', 0.0) or 0.0),
                    'wind_mps': float(wind.get('speed', 0.0) or 0.0),
                    'wind_gust_mps': float(wind.get('gust', 0.0) or 0.0),
                    'cloud_pct': float((item.get('clouds') or {}).get('all', 0.0) or 0.0),
                    'pop': float(item.get('pop', 0.0) or 0.0),
                    'rain_mm': float((rain.get('3h', 0.0) or 0.0)),
                    'desc': (item.get('weather') or [{}])[0].get('description', ''),
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning(f'OpenWeatherMap forecast parse error: {exc}')
            return None
        df = pd.DataFrame(rows)
        return df if not df.empty else None

    def daily_forecast(self, lat: float, lon: float, days: int = 5) -> Optional[pd.DataFrame]:
        """3-hour steps aggregated into IST calendar days.

        Columns: date (IST), rain_mm (sum of 3h buckets), pop_pct (max),
        wind_max_mps, wind_gust_max_mps, humidity_mean_pct, temp_min_c,
        temp_max_c, steps (count of 3h buckets that day). The day-0 bucket is
        partial (the forecast starts a few hours ahead), which the UI marks.
        """
        steps = self.forecast_steps(lat, lon)
        if steps is None or steps.empty:
            return None
        steps['ist'] = steps['utc'].dt.tz_convert(IST)
        steps['date'] = steps['ist'].dt.date
        g = steps.groupby('date').agg(
            rain_mm=('rain_mm', 'sum'),
            pop_pct=('pop', 'max'),
            wind_max_mps=('wind_mps', 'max'),
            wind_gust_max_mps=('wind_gust_mps', 'max'),
            humidity_mean_pct=('humidity_pct', 'mean'),
            temp_min_c=('temp_c', 'min'),
            temp_max_c=('temp_c', 'max'),
            steps=('rain_mm', 'size'),
        ).reset_index()
        g['date'] = pd.to_datetime(g['date'])
        g = g.sort_values('date').head(days).reset_index(drop=True)
        g.attrs['provider'] = 'openweathermap'
        return g

    def hourly_series(self, lat: float, lon: float, hours: int = 48) -> Optional[pd.DataFrame]:
        """3-hour forecast steps for the next `hours`, as the hourly_48h chart
        series (every 3 h). Columns: time (IST iso), temp_c, humidity_pct,
        wind_mps, gust_mps, pop_pct, cloud_pct, desc."""
        steps = self.forecast_steps(lat, lon)
        if steps is None or steps.empty:
            return None
        steps['ist'] = steps['utc'].dt.tz_convert(IST)
        n = min(hours // 3, len(steps))
        s = steps.head(n).copy()
        return pd.DataFrame({
            'time': s['ist'].dt.strftime('%Y-%m-%dT%H:%M'),
            'temp_c': s['temp_c'],
            'humidity_pct': s['humidity_pct'],
            'wind_mps': s['wind_mps'],
            'gust_mps': s['wind_gust_mps'],
            'pop_pct': (s['pop'] * 100.0),
            'cloud_pct': s['cloud_pct'],
            'desc': s['desc'],
        })
