"""
Data fetcher for Idukki Monsoon Danger Index

Retrieves rainfall, wind, humidity and cloud data from public sources.

Provider strategy (see docs/DATA_SOURCES.md):

* Current conditions (wind / humidity / cloud / temperature / live rain):
  OpenWeatherMap is the PRIMARY provider whenever OPENWEATHERMAP_API_KEY is
  set (its current-weather endpoint refreshes every ~10 minutes); Open-Meteo
  is the automatic fallback.
* Daily rainfall outlook (today + next 7 days, with rain probability):
  Open-Meteo, which offers a full 7-day daily forecast for free (OpenWeather's
  free tier is limited to 5 days / 3-hour steps; that data is aggregated to
  IST days and served through /trends as the OpenWeatherMap outlook chart).
* Measured history (past days): Open-Meteo `past_days` feed + the project's
  own day-by-day observed store (data/observed.py) - OWM free tier has no
  history endpoint.
* Fallback: realistic, season-aware synthetic data clearly flagged with
  source='synthetic' so consumers (and the UI) can always tell live data
  from modelled data.

Every returned object carries a source/provider key so the UI can label the
true origin of every number.
"""

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import hashlib
import logging
import json
import os
from pathlib import Path

# Load project .env (OPENWEATHERMAP_API_KEY lives there) before anything reads it.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:  # noqa: BLE001 - dotenv is optional
    pass

from data.openweather import OpenWeatherClient  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path('/tmp/ssr_cache')
CACHE_DIR.mkdir(exist_ok=True)
CACHE_VALIDITY_HOURS = 6

# Live weather source
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Idukki district bounds (inner areas: Peermedu, Kumily, Adimali panchayats)
IDUKKI_INNER_BOUNDS = {
    'north': 9.75,
    'south': 9.40,
    'east': 76.95,
    'west': 76.55
}

# Locality coordinates (taluk/panchayat level)
LOCALITIES = {
    'Kumily': {'lat': 9.655, 'lon': 76.775},
    'Peermedu': {'lat': 9.545, 'lon': 76.615},
    'Idukki': {'lat': 9.725, 'lon': 76.805},
    'Adimali': {'lat': 9.575, 'lon': 76.895},
    'Kattappana': {'lat': 9.650, 'lon': 76.925},
    'Munnar': {'lat': 10.089, 'lon': 76.766},
    'Nedumkandam': {'lat': 9.800, 'lon': 76.868}
}

# Kerala monsoon months (south-west monsoon, June-September). October/May are
# transition months with lighter rain, the rest of the year is generally dry.
MONSOON_MONTHS = (6, 7, 8, 9)
TRANSITION_MONTHS = (5, 10)


def _daily_seed(lat: float, lon: float, salt: str = "") -> int:
    """Deterministic per-locality, per-day RNG seed (stable across processes).

    Python's built-in `hash()` is salted per process (PYTHONHASHSEED), so it
    cannot be used to generate reproducible values. Using an MD5 digest of the
    location + date key means every process that runs on the same day gets the
    same generated values, without relying on the on-disk cache.
    """
    key = f"{lat:.2f}_{lon:.2f}_{datetime.now().strftime('%Y-%m-%d')}_{salt}"
    return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16) % (2 ** 32)


def _season_band() -> str:
    """Return 'monsoon', 'transition' or 'dry' for today's date."""
    month = datetime.now().month
    if month in MONSOON_MONTHS:
        return 'monsoon'
    if month in TRANSITION_MONTHS:
        return 'transition'
    return 'dry'


def _read_cache(cache_path: Path):
    """Read cache payload if present and still valid, else None."""
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r') as f:
            data = json.load(f)
            cached_time = datetime.fromisoformat(data.get('timestamp', ''))
            if (datetime.now() - cached_time).total_seconds() < CACHE_VALIDITY_HOURS * 3600:
                logger.info(f"Using cached data from {cache_path.name}")
                return data.get('data')
    except Exception as e:
        logger.warning(f"Cache read error: {e}")

    return None


def _write_cache(cache_path: Path, data) -> None:
    """Write JSON-serialisable payload to cache."""
    try:
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, default=str)
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


class IMDDataFetcher:
    """Fetch gridded data from Open-Meteo (primary) / OpenWeatherMap (optional).

    Every returned object carries a `source` key:
        'open-meteo' -> live public forecast/observation
        'synthetic'  -> season-aware modelled fallback (offline / API failure)
    """

    def __init__(self):
        # OpenWeatherMap client (enabled only when a key is present).
        self.owm = OpenWeatherClient()
        self.owm_api_key = self.owm.api_key

    # ------------------------------------------------------------------ cache
    def _get_cache_path(self, locality: str, data_type: str) -> Path:
        """Get cache file path for locality data"""
        return CACHE_DIR / f"{locality}_{data_type}_cache.json"

    # -------------------------------------------------------------- Open-Meteo
    def _fetch_open_meteo_current(self, lat: float, lon: float):
        """Fetch current observations from Open-Meteo (no API key needed).

        Returns a dict with wind/humidity/cloud/precipitation, or None.
        """
        params = {
            'latitude': lat,
            'longitude': lon,
            'current': ('precipitation,relative_humidity_2m,'
                        'wind_speed_10m,wind_direction_10m,cloud_cover,'
                        'temperature_2m,surface_pressure'),
            'wind_speed_unit': 'ms',      # metres per second
            'precipitation_unit': 'mm',
            'timezone': 'Asia/Kolkata',
        }
        try:
            response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=8)
            response.raise_for_status()
            current = response.json().get('current')
            if not current:
                return None
            return {
                'latitude': lat,
                'longitude': lon,
                'precipitation_mm': float(current.get('precipitation', 0.0) or 0.0),
                'relative_humidity_pct': float(current.get('relative_humidity_2m', 0.0) or 0.0),
                'wind_speed_mps': float(current.get('wind_speed_10m', 0.0) or 0.0),
                'wind_direction_deg': float(current.get('wind_direction_10m', 0.0) or 0.0),
                'cloud_cover_pct': float(current.get('cloud_cover', 0.0) or 0.0),
                'temperature_c': float(current.get('temperature_2m', 0.0) or 0.0),
                'pressure_hpa': float(current.get('surface_pressure', 0.0) or 0.0),
                'observed_at': current.get('time'),
                'timestamp': datetime.now().isoformat(),
                'source': 'open-meteo',
            }
        except Exception as e:
            logger.warning(f"Open-Meteo current fetch failed ({lat:.2f},{lon:.2f}): {e}")
            return None

    def _fetch_open_meteo_forecast(self, lat: float, lon: float, days: int = 7):
        """Fetch a daily rainfall forecast from Open-Meteo.

        Returns a DataFrame with date/rainfall_mm columns and df.attrs['source']
        set, or None.
        """
        params = {
            'latitude': lat,
            'longitude': lon,
            'daily': 'precipitation_sum,precipitation_probability_max',
            'forecast_days': days,
            'precipitation_unit': 'mm',
            'timezone': 'Asia/Kolkata',
        }
        try:
            response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=8)
            response.raise_for_status()
            daily = response.json().get('daily')
            if not daily:
                return None

            dates = pd.to_datetime(daily.get('time', []))
            rain = [min(float(v or 0.0), 500.0) for v in daily.get('precipitation_sum', [])]
            probs = daily.get('precipitation_probability_max')
            if probs is None:
                probs = [None] * len(rain)

            df = pd.DataFrame({
                'date': dates,
                'rainfall_mm': rain,
                'probability_pct': probs,
                'latitude': lat,
                'longitude': lon,
            })
            df.attrs['source'] = 'open-meteo'
            return df
        except Exception as e:
            logger.warning(f"Open-Meteo forecast fetch failed ({lat:.2f},{lon:.2f}): {e}")
            return None

    def _fetch_owm_current(self, lat: float, lon: float):
        """OpenWeatherMap current weather (only if API key is set)."""
        data = self.owm.current(lat, lon)
        if data is None:
            return None
        # consumers read .get('source'); the client reports 'provider'
        data['source'] = data.get('provider', 'openweathermap')
        return data

    # ----------------------------------------------------------------- current
    def get_current_weather(self, lat: float, lon: float) -> dict:
        """Combined current weather (wind/humidity/cloud/precipitation).

        Provider order: OpenWeatherMap (when a key is set - freshest,
        ~10-minute updates) first, Open-Meteo second. Cached for
        CACHE_VALIDITY_HOURS, with a season-aware synthetic fallback.
        """
        cache_path = CACHE_DIR / f"current_{lat:.2f}_{lon:.2f}_cache.json"

        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

        current = self._fetch_owm_current(lat, lon) if self.owm.enabled else None
        if current is None:
            current = self._fetch_open_meteo_current(lat, lon)

        if current is not None:
            # unify provider naming: downstream reads .get('source')
            if 'source' not in current and current.get('provider'):
                current['source'] = current['provider']
            _write_cache(cache_path, current)
            return current

        # Offline / unavailable: season-aware modelled fallback, clearly flagged
        band = _season_band()
        np.random.seed(_daily_seed(lat, lon, 'current'))
        wind_ms = {'monsoon': (3.0, 9.0), 'transition': (2.0, 7.0), 'dry': (1.0, 5.0)}[band]
        humidity = {'monsoon': (72, 96), 'transition': (60, 90), 'dry': (40, 75)}[band]
        cloud = {'monsoon': (60, 98), 'transition': (40, 85), 'dry': (15, 60)}[band]

        return {
            'latitude': lat,
            'longitude': lon,
            'precipitation_mm': 0.0,  # current instant precip unknown without live feed
            'relative_humidity_pct': float(np.clip(np.random.uniform(*humidity), 20, 100)),
            'wind_speed_mps': float(np.clip(np.random.uniform(*wind_ms), 0.5, 20.0)),
            'wind_direction_deg': float(np.random.uniform(0, 360)),
            'cloud_cover_pct': float(np.clip(np.random.uniform(*cloud), 0, 100)),
            'observed_at': datetime.now().isoformat(),
            'timestamp': datetime.now().isoformat(),
            'source': 'synthetic',
        }

    def get_wind_data(self, lat: float, lon: float) -> dict:
        """Get wind speed and direction for a location."""
        current = self.get_current_weather(lat, lon)
        return {
            'latitude': lat,
            'longitude': lon,
            'wind_speed_mps': current['wind_speed_mps'],
            'wind_direction_deg': current['wind_direction_deg'],
            'timestamp': current['timestamp'],
            'source': current['source'],
        }

    def get_humidity_data(self, lat: float, lon: float) -> dict:
        """Get relative humidity for a location."""
        current = self.get_current_weather(lat, lon)
        return {
            'latitude': lat,
            'longitude': lon,
            'relative_humidity_pct': current['relative_humidity_pct'],
            'timestamp': current['timestamp'],
            'source': current['source'],
        }

    # --------------------------------------------------------------- rainfall
    def get_rainfall_forecast(self, lat: float, lon: float, days: int = 7):
        """Daily rainfall forecast (live, cached) with synthetic fallback.

        Returns a DataFrame with columns [date, rainfall_mm, latitude, longitude]
        and df.attrs['source'] set to 'open-meteo' or 'synthetic'.
        """
        cache_path = CACHE_DIR / f"rainfall_{lat:.2f}_{lon:.2f}_cache.json"

        cached = _read_cache(cache_path)
        if cached is not None:
            src = cached.get('source', 'synthetic')  # legacy caches -> synthetic
            rows = cached.get('rows', cached if isinstance(cached, list) else [])
            df = pd.DataFrame(rows)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                # caches written before probability existed: try an in-place
                # upgrade once; on failure keep the cache but with a NaN
                # column so we never stall every subsequent request on the
                # network again (the 6h TTL will refresh it later anyway).
                if 'probability_pct' not in df.columns:
                    live = self._fetch_open_meteo_forecast(lat, lon, days)
                    if live is not None:
                        _write_cache(cache_path, {
                            'source': 'open-meteo',
                            'rows': live.to_dict(orient='records'),
                        })
                        return live
                    df['probability_pct'] = np.nan
                    _write_cache(cache_path, {'source': src,
                                              'rows': df.to_dict(orient='records')})
                df.attrs['source'] = src
                return df

        df = self._fetch_open_meteo_forecast(lat, lon, days)
        if df is None:
            df = self._generate_sample_rainfall(lat, lon, days)
        else:
            _write_cache(cache_path, {
                'source': 'open-meteo',
                'rows': df.to_dict(orient='records'),
            })
        return df

    # --------------------------------------------------------------- fallback
    @staticmethod
    def _generate_sample_rainfall(lat: float, lon: float, days: int):
        """Season-aware modelled rainfall for offline/fallback use.

        Distribution follows the broad climatology of inner Idukki (altitude
        700-1600 m, west-facing slopes): monsoon months carry 10-60 mm/day with
        occasional bursts, transition months are lighter, dry months are calm.
        Values are deterministic per day and location.
        """
        np.random.seed(_daily_seed(lat, lon, 'rainfall'))
        band = _season_band()

        if band == 'monsoon':
            low, high = 6.0, 55.0
            burst_p = 0.12
            burst_extra = (40.0, 90.0)
        elif band == 'transition':
            low, high = 1.5, 20.0
            burst_p = 0.05
            burst_extra = (20.0, 45.0)
        else:
            low, high = 0.0, 6.0
            burst_p = 0.0
            burst_extra = (0.0, 0.0)

        rainfall_mm = np.random.uniform(low=low, high=high, size=days)
        if burst_p > 0:
            bursts = np.random.uniform(size=days) < burst_p
            rainfall_mm[bursts] += np.random.uniform(*burst_extra, size=bursts.sum())
        rainfall_mm = np.maximum(rainfall_mm, 0.0)

        dates = [datetime.now() + timedelta(days=i) for i in range(days)]
        df = pd.DataFrame({
            'date': dates,
            'rainfall_mm': rainfall_mm,
            'latitude': lat,
            'longitude': lon,
        })
        df.attrs['source'] = 'synthetic'
        return df


class NASADataFetcher:
    """Cloud/precipitation helper backed by the shared Open-Meteo current feed.

    A dedicated NASA MODIS/GPM ingestion (EarthData bearer token) can be added
    later; until then this class reuses the same live current-weather feed and
    flags the source honestly.
    """

    def __init__(self):
        self.modis_url = "https://earthdata.nasa.gov"

    def get_cloud_cover(self, lat: float, lon: float) -> dict:
        """Get cloud cover (live where possible, else modelled fallback)."""
        cache_path = CACHE_DIR / f"cloud_{lat:.2f}_{lon:.2f}_cache.json"

        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

        # Reuse the shared Open-Meteo current feed (same source of truth as
        # wind/humidity so the metrics are internally consistent).
        current_cache = CACHE_DIR / f"current_{lat:.2f}_{lon:.2f}_cache.json"
        current = _read_cache(current_cache)
        if current is not None:
            cloud_data = {
                'latitude': lat,
                'longitude': lon,
                'cloud_cover_pct': current['cloud_cover_pct'],
                'timestamp': current['timestamp'],
                'source': current['source'],
            }
            _write_cache(cache_path, cloud_data)
            return cloud_data

        np.random.seed(_daily_seed(lat, lon, 'cloud'))
        band = _season_band()
        cloud = {'monsoon': (60, 98), 'transition': (40, 85), 'dry': (15, 60)}[band]
        cloud_data = {
            'latitude': lat,
            'longitude': lon,
            'cloud_cover_pct': float(np.clip(np.random.uniform(*cloud), 0, 100)),
            'timestamp': datetime.now().isoformat(),
            'source': 'synthetic',
        }
        _write_cache(cache_path, cloud_data)
        return cloud_data

    def get_precipitation_gpm(self, lat: float, lon: float) -> dict:
        """Get precipitation estimate (GPM IMERG later; shared feed for now)."""
        cache_path = CACHE_DIR / f"precip_{lat:.2f}_{lon:.2f}_cache.json"

        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

        current_cache = CACHE_DIR / f"current_{lat:.2f}_{lon:.2f}_cache.json"
        current = _read_cache(current_cache)
        if current is not None:
            precip_data = {
                'latitude': lat,
                'longitude': lon,
                'precipitation_mm': current['precipitation_mm'],
                'timestamp': current['timestamp'],
                'source': current['source'],
            }
            _write_cache(cache_path, precip_data)
            return precip_data

        np.random.seed(_daily_seed(lat, lon, 'precip'))
        precip_data = {
            'latitude': lat,
            'longitude': lon,
            'precipitation_mm': float(np.clip(np.random.normal(loc=30, scale=25), 0, 200)),
            'timestamp': datetime.now().isoformat(),
            'source': 'synthetic',
        }
        _write_cache(cache_path, precip_data)
        return precip_data


class KSDMADataFetcher:
    """Historical calamity records (KSDMA / district records, sample dataset).

    The rows below are a hand-compiled sample of documented landslide/flood
    events in inner Idukki (2004-2025) for development and demonstration.
    To use authoritative records, export the KSDMA register to CSV and load it
    here (see docs/DATA_SOURCES.md).
    """

    def __init__(self):
        self.incidents = []  # Load from CSV/database

    def get_historical_incidents(self, bbox: dict, start_year: int = 2004):
        """Get landslides, floods and dam incidents in the bounding box."""
        return pd.DataFrame({
            'latitude': [
                9.655, 9.545, 9.575, 9.725, 9.650,  # 2018-2020
                9.615, 9.680, 9.560, 9.700, 9.620,  # 2021-2023
                9.665, 9.540, 9.710, 9.595, 9.670   # 2024-2025
            ],
            'longitude': [
                76.775, 76.615, 76.895, 76.805, 76.925,  # 2018-2020
                76.745, 76.835, 76.655, 76.785, 76.915,  # 2021-2023
                76.765, 76.625, 76.815, 76.885, 76.955   # 2024-2025
            ],
            'incident_type': [
                'landslide', 'flood', 'landslide', 'flood', 'landslide',
                'mudslide', 'flash_flood', 'landslide', 'debris_flow', 'flood',
                'landslide', 'flash_flood', 'flood', 'mudslide', 'landslide'
            ],
            'year': [
                2018, 2019, 2018, 2019, 2020,
                2021, 2022, 2021, 2022, 2023,
                2024, 2024, 2025, 2025, 2025
            ],
            'severity': [
                'high', 'extreme', 'moderate', 'high', 'high',
                'high', 'high', 'moderate', 'moderate', 'extreme',
                'high', 'high', 'moderate', 'high', 'high'
            ],
            'location': [
                'Near Kumily', 'Peermedu Region', 'Adimali', 'Idukki Dam Area', 'Kattappana',
                'Munnar Hills', 'Peermedu Valley', 'Kumily Slope', 'Nedumkandam', 'Kottayam Border',
                'High Wavy Road', 'Peermedu Low Region', 'Idukki Valley', 'Adimali Slope', 'Kumily Teaplantation'
            ],
            'description': [
                'Landslide during heavy monsoon (2018)',
                'Flash floods in Peermedu panchayat (July 2019)',
                'Debris flow in hillside near tea plantations (2018)',
                'Dam spillway overflow during peak monsoon (2019)',
                'Landslide near tea plantation (May 2020)',
                'Mudslide on Munnar-Kochi road (2021)',
                'Flash flood in tributary streams (August 2022)',
                'Landslide affecting 5 households (2021)',
                'Debris flow blocking road access (September 2022)',
                'Extreme flooding in low-lying areas (2023)',
                'Road collapse due to landslide (April 2024)',
                'Flash flood in mountain streams (July 2024)',
                'Flooding in residential areas (June 2025)',
                'Mudslide affecting plantation area (August 2025)',
                'Landslide near Kumily town (September 2025)'
            ]
        })


def record_observed_history() -> int:
    """Close yesterday's fully-measured day for every locality (idempotent).

    Called once per server boot so the observed-history store (data/observed.py)
    keeps accumulating real measured rows that feed soil saturation and future
    ML retrains. Returns the number of localities recorded.
    """
    from data.observed import LiveHistoryStore
    store = LiveHistoryStore()
    recorded = 0
    for name, loc in LOCALITIES.items():
        try:
            before = len(store.recent(loc['lat'], loc['lon']))
            store.record_today(loc['lat'], loc['lon'])
            if len(store.recent(loc['lat'], loc['lon'])) > before:
                recorded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Observed history close failed for {name}: {exc}")
    return recorded


def fetch_all_data_for_locality(locality_name: str):
    """Fetch all relevant data for a single locality."""
    if locality_name not in LOCALITIES:
        raise ValueError(f"Locality {locality_name} not found")

    loc = LOCALITIES[locality_name]
    lat, lon = loc['lat'], loc['lon']

    imd = IMDDataFetcher()
    nasa = NASADataFetcher()
    ksdma = KSDMADataFetcher()

    # close yesterday's measured day for this locality (cheap when already done)
    try:
        from data.observed import LiveHistoryStore
        LiveHistoryStore().record_today(lat, lon)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Observed history close failed for {locality_name}: {exc}")

    data = {
        'locality': locality_name,
        'coordinates': {'lat': lat, 'lon': lon},
        'current_conditions': imd.get_current_weather(lat, lon),
        'rainfall_forecast': imd.get_rainfall_forecast(lat, lon),
        'wind_data': imd.get_wind_data(lat, lon),
        'humidity_data': imd.get_humidity_data(lat, lon),
        'cloud_cover': nasa.get_cloud_cover(lat, lon),
        'precipitation_gpm': nasa.get_precipitation_gpm(lat, lon),
        'historical_incidents': ksdma.get_historical_incidents(IDUKKI_INNER_BOUNDS)
    }

    return data


def extract_current_weather(locality_data: dict) -> dict:
    """Build the 'current conditions' dict used for Danger Index computation.

    IMPORTANT: uses the NEAREST available day of the rainfall forecast
    (row 0), because the last row is several days in the future and is not
    representative of current conditions.

    Returns:
        Dict with rainfall_mm, wind_mps, humidity_pct, cloud_cover_pct plus
        `source` and `observed_at`.

    Source rule: a locality is only flagged 'live' when its RAINFALL forecast
    is live. Rainfall is the dominant Danger Index input (highest weight and it
    gates structural risk), so if rain fell back to modelled data the whole
    feed is reported as synthetic -- even when wind/humidity arrived live.
    Otherwise the UI would claim a LIVE feed while the number driving the
    score was generated.
    """
    rainfall_df = locality_data.get('rainfall_forecast')
    if rainfall_df is not None and not rainfall_df.empty:
        rainfall_mm = float(rainfall_df['rainfall_mm'].iloc[0])
        rain_source = rainfall_df.attrs.get('source', 'synthetic')
    else:
        rainfall_mm = 100.0  # Conservative default when no forecast is available
        rain_source = 'synthetic'

    wind = locality_data.get('wind_data', {})
    humidity = locality_data.get('humidity_data', {})
    cloud = locality_data.get('cloud_cover', {})
    current = locality_data.get('current_conditions', {}) or {}

    return {
        'rainfall_mm': rainfall_mm,
        'wind_mps': wind.get('wind_speed_mps', 8),
        'humidity_pct': humidity.get('relative_humidity_pct', 85),
        'cloud_cover_pct': cloud.get('cloud_cover_pct', 80),
        'temperature_c': current.get('temperature_c'),
        'pressure_hpa': current.get('pressure_hpa'),
        'precip_now_mm': current.get('precipitation_mm'),
        'source': 'live' if rain_source != 'synthetic' else 'synthetic',
        'conditions_provider': current.get('source')
                               or wind.get('source')
                               or 'synthetic',
        'observed_at': current.get('observed_at') or wind.get('timestamp')
                       or humidity.get('timestamp')
                       or datetime.now().isoformat(),
    }


if __name__ == '__main__':
    # Test data fetcher
    locality_data = fetch_all_data_for_locality('Kumily')
    print(f"Fetched data for {locality_data['locality']}")
    print(f"Rainfall forecast:\n{locality_data['rainfall_forecast']}")
    print(f"Wind data: {locality_data['wind_data']}")
