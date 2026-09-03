"""
Historical daily rainfall dataset builder for the ML prediction engine.

Source : Open-Meteo Archive API (https://archive-api.open-meteo.com) - ERA5
         reanalysis daily precipitation, free, no API key required.
Cache  : historical ranges are immutable, so closed date spans are cached
         forever; only the trailing (open-ended) span is refreshed.
Output : per-locality CSV of daily rainfall plus engineered features and a
         binary 'heavy day' label used to train the hazard classifier.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

HIST_CACHE_DIR = Path('/tmp/ssr_cache/historical')
HIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_YEAR = 2012

HEAVY_MM = 64.5   # hazard label threshold: IMD "very heavy rain" band (64.5-115 mm/day)
# (100 mm/day is too rare at these grid points - 2 positives in 8 training
# years - for any classifier to learn from; 64.5 mm is still firmly in the
# flood/landslide-triggering band and yields a usable class balance)
MAX_RAIN = 400.0  # clamp for outliers (ERA5 rarely exceeds this over 24h here)
SPAN_MAX_YEARS = 4  # biggest single archive request we make


def _span_cache_path(lat: float, lon: float, start: int, end: int) -> Path:
    return HIST_CACHE_DIR / f"hist_{lat:.2f}_{lon:.2f}_{start}-{end}.json"


def _fetch_archive_range(lat: float, lon: float, start_date: str, end_date: str,
                         attempts: int = 3):
    """Fetch daily precipitation_sum for a date range (one API call).

    The archive API occasionally 502s or stalls on slow links, so the call is
    retried with a short backoff before the caller falls back.
    """
    import time
    params = {
        'latitude': lat,
        'longitude': lon,
        'start_date': start_date,
        'end_date': end_date,
        'daily': 'precipitation_sum',
        'timezone': 'Asia/Kolkata',
    }
    last_exc = None
    for attempt in range(attempts):
        try:
            response = requests.get(ARCHIVE_URL, params=params, timeout=45)
            response.raise_for_status()
            daily = response.json().get('daily', {})
            return pd.DataFrame({
                'date': pd.to_datetime(daily.get('time', [])),
                'rainfall_mm': [min(float(v or 0.0), MAX_RAIN)
                                for v in daily.get('precipitation_sum', [])],
            })
        except Exception as exc:  # noqa: BLE001 - retryable network/server errors
            last_exc = exc
            time.sleep(2.5 * (attempt + 1))
    raise last_exc


def _span_info(lat: float, lon: float):
    """Yield (start_year, end_year, is_trailing, path) for cached spans."""
    import re
    prefix = f"hist_{lat:.2f}_{lon:.2f}_"
    for path in sorted(HIST_CACHE_DIR.glob(prefix + "*.json")):
        m = re.match(prefix + r"(\d{4})-(\d{4})\.json$", path.name)
        if not m:
            continue
        yield int(m.group(1)), int(m.group(2)), path


def _ensure_range(lat: float, lon: float, start: int, end: int,
                  today: datetime.date, refresh_trailing: bool):
    """Fetch years [start..end] if not cached; split into halves on failure."""
    cache_path = _span_cache_path(lat, lon, start, end)
    is_trailing = end >= today.year
    cached = _read_span_cache(cache_path, is_trailing, refresh_trailing)
    if cached is not None:
        return cached

    end_date = (today - timedelta(days=1)) if is_trailing else f"{end}-12-31"
    try:
        df = _fetch_archive_range(lat, lon, f"{start}-01-01", str(end_date))
    except Exception as exc:  # noqa: BLE001 - slow links stall on big payloads
        logger.warning(f"Archive fetch failed ({lat:.2f},{lon:.2f}) "
                       f"{start}-{end}: {exc} - retrying in halves")
        if start == end:
            return None
        mid = (start + end) // 2
        left = _ensure_range(lat, lon, start, mid, today, refresh_trailing)
        right = _ensure_range(lat, lon, mid + 1, end, today, refresh_trailing)
        if left is None and right is None:
            return None
        return pd.concat([f for f in (left, right) if f is not None], ignore_index=True)

    if not df.empty:
        _write_span_cache(cache_path, df)
    return df if not df.empty else None


def load_daily_rainfall(lat: float, lon: float, refresh_trailing: bool = True) -> pd.DataFrame:
    """Concatenated daily rainfall for one location, cached on disk.

    Coverage-based: cached span files are inventoried and only the missing
    years are fetched (in <=SPAN_MAX_YEARS chunks, split in half again on
    failure), so interrupted runs simply resume where they stopped.
    """
    today = datetime.now().date()
    cur_year = today.year

    covered = set()
    frames = []
    for s, e, path in _span_info(lat, lon):
        is_trailing = e >= cur_year
        if is_trailing and refresh_trailing:
            stale = _read_span_cache(path, True, True) is None
            if stale:
                try:
                    path.unlink()  # trailing span too old - refetch below
                except OSError:
                    pass
                continue
        covered.update(range(s, e + 1))
        frames.append(_read_span_cache(path, is_trailing, False))

    missing = [y for y in range(START_YEAR, cur_year + 1) if y not in covered]
    if missing:
        # group consecutive missing years into <=SPAN_MAX_YEARS chunks
        chunks, start = [], missing[0]
        prev = missing[0]
        for y in missing[1:]:
            if y - prev > 1 or y - start >= SPAN_MAX_YEARS:
                chunks.append((start, prev))
                start = y
            prev = y
        chunks.append((start, prev))

        for s, e in chunks:
            df = _ensure_range(lat, lon, s, e, today, refresh_trailing)
            if df is not None:
                frames.append(df)

    if not frames:
        return pd.DataFrame(columns=['date', 'rainfall_mm'])
    full = pd.concat(frames, ignore_index=True)
    return full.drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)


def _read_span_cache(path: Path, is_trailing: bool, refresh: bool):
    """Cache hit -> DataFrame. Trailing spans expire after 24h when refresh=True."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if is_trailing and refresh:
            age = datetime.now() - datetime.fromisoformat(data['fetched_at'])
            if age > timedelta(hours=24):
                return None
        df = pd.DataFrame(data['rows'])
        df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Historical cache read error {path.name}: {exc}")
        return None


def _write_span_cache(path: Path, df: pd.DataFrame):
    try:
        with open(path, 'w') as f:
            json.dump({
                'fetched_at': datetime.now().isoformat(),
                'rows': df.to_dict(orient='records'),
            }, f, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Historical cache write error {path.name}: {exc}")


# ------------------------------------------------------------------ features
def build_features(rainfall: pd.Series) -> pd.DataFrame:
    """Feature engineering over the daily rainfall series.

    Each feature is derived from past values only (no look-ahead), so rows
    can be fed to models as a chronological stream.
    """
    rain = rainfall.clip(lower=0.0)
    out = pd.DataFrame(index=rain.index)

    out['rainfall_mm'] = rain
    out['accum_1d'] = rain
    for window in (3, 7, 15, 30):
        out[f'accum_{window}d'] = rain.rolling(window, min_periods=1).sum()
    # trailing mean (exclude today) as local climatology anchor
    out['clim_30d'] = rain.shift(1).rolling(30, min_periods=1).mean().fillna(rain.mean())
    out['rain_over_clim'] = out['accum_1d'] / (out['clim_30d'] + 2.0)
    # wet-day streak (consecutive days with measurable rain)
    wet = (rain > 0.5).astype(int)
    grp = (wet != wet.shift()).cumsum()
    out['wet_streak'] = wet.groupby(grp).cumsum()
    # number of dry days in the previous 7 (prior values only)
    prior_wet = wet.shift(1).rolling(7, min_periods=1).sum()
    prior_n = wet.shift(1).rolling(7, min_periods=1).count()
    out['dry_days_7'] = (prior_n - prior_wet).fillna(0).astype(int)

    # calendar seasonality (Idukki: SW monsoon peaks Jun-Sep, NE Oct-Nov)
    idx = pd.DatetimeIndex(rain.index)
    doy = idx.dayofyear.to_numpy() / 365.25 * 2 * np.pi
    out['doy_sin'] = np.sin(doy)
    out['doy_cos'] = np.cos(doy)
    out['month'] = idx.month
    out['is_monsoon'] = idx.month.isin([6, 7, 8, 9]).astype(int)
    out['is_transition'] = idx.month.isin([5, 10]).astype(int)

    # forecast targets (always use the future, so they are never part of the
    # feature columns consumed by the models)
    out['rain_tomorrow'] = rain.shift(-1)
    # Hazard label: a very-heavy day within the NEXT 3 days. A 1-day horizon
    # is genuinely hard for daily totals (a convective burst often follows an
    # unremarkable day), while multi-day accumulation windows are predictable
    # and are what flood/landslide watches are issued on.
    out['heavy_soon'] = (rain.shift(-1).rolling(3, min_periods=1).max() >= HEAVY_MM).astype(float)
    return out


def labelled_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Daily rainfall frame -> feature/label frame with NaNs dropped."""
    feats = build_features(df.set_index('date')['rainfall_mm'])
    feats = feats.dropna()
    return feats.reset_index()


def observed_store_frame(lat: float, lon: float) -> pd.DataFrame:
    """Measured rows recorded by the project's live-history store.

    The running server closes each fully-measured IST day into the store
    (data/observed.py), so with every day of operation the models gain a
    genuinely observed (not reanalysis) tail to train on.
    """
    try:
        from data.observed import LiveHistoryStore
        s = LiveHistoryStore().recent(lat, lon, limit=120)
        if s is None or s.empty:
            return pd.DataFrame(columns=['date', 'rainfall_mm'])
        return s[['date', 'rainfall_mm']].rename(columns={'rainfall_mm': 'rain_mm'})
    except Exception:  # noqa: BLE001 - observed history is an enhancement
        return pd.DataFrame(columns=['date', 'rainfall_mm'])


def load_daily_rainfall_observed(lat: float, lon: float,
                                 refresh_trailing: bool = True) -> pd.DataFrame:
    """ERA5 archive spliced with the measured observed-history store.

    The archive supplies the deep 2012+ record; measured store rows (which
    are real observations from the live weather feed, not reanalysis) win on
    any date overlap. Empty store rows leave the archive untouched.
    """
    frame = load_daily_rainfall(lat, lon, refresh_trailing=refresh_trailing)
    obs = observed_store_frame(lat, lon)
    if obs.empty or frame.empty:
        return frame
    obs = obs.rename(columns={'rain_mm': 'rainfall_mm'})
    merged = pd.concat([frame, obs], ignore_index=True)
    merged = merged.drop_duplicates(subset='date', keep='last')
    return merged.sort_values('date').reset_index(drop=True)
