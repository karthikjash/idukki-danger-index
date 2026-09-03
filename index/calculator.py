"""
Composite Danger Index Calculation
Combines Environmental Severity, Structural Risk, and Human Threat Level
into a 4-tier index: Low / Moderate / High / Extreme.

Design notes (see also docs/METHODOLOGY.md):

* Rainfall is scored against the IMD 24h rainfall categories (light, moderate,
  rather heavy, heavy, very heavy, extremely heavy), NOT against a single
  observed day. This avoids the previous over-fit where the scoring was
  calibrated to one specific date's conditions.
* The index is season-aware. Idukki's danger window is the south-west monsoon
  (June-September). Outside that window the same rainfall drives a much lower
  risk, which reflects reality: most of the district is genuinely safe for most
  of the year.
* Historical incidents and terrain only express themselves through the
  structural-risk channel, which is *gated by rainfall*. Past incidents alone
  can never raise the tier - they only amplify risk when heavy rain is
  actually present. This fixes the earlier behaviour where localities showed
  elevated risk purely because incidents had happened there before.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authoritative panchayat/municipality population totals (project owner,
# Census-2011-derived). Used for population-exposure scoring AND for
# apportioning the ward-level population model (index/wards.py).
LOCALITY_POPULATION = {
    'Kumily': 33722,
    'Peermedu': 22213,
    'Idukki': 21724,
    'Adimali': 40484,
    'Kattappana': 42646,
    'Munnar': 32039,
    'Nedumkandam': 41980
}

# Terrain slope risk factors (approximate for inner Idukki)
TERRAIN_SLOPE_RISK = {
    'Kumily': 0.8,      # Very steep
    'Peermedu': 0.85,   # Extremely steep
    'Idukki': 0.75,     # Very steep
    'Adimali': 0.90,    # Extremely steep
    'Kattappana': 0.70, # Very steep
    'Munnar': 0.80,     # Very steep
    'Nedumkandam': 0.65 # Steep
}

# ---------------------------------------------------------------------------
# Incident-history influence (data-derived, not hand-set)
# ---------------------------------------------------------------------------
# Industry framing (NDMA / BIS-IS14496 landslide-zonation practice): a
# landslide/flood INVENTORY validates a susceptibility model; it does not
# dominate it. So recorded incidents feed only the rainfall-gated structural
# channel at a low, capped weight, and the per-locality factor below is
# COMPUTED from the actual register - proximity-weighted, severity-weighted
# and recency-decayed (a 2004 event weighs a fraction of a 2024 one).
# Hand-tuned constants are gone; when the real KSDMA register replaces the
# sample, the same function keeps working unchanged.
_INCIDENT_FACTOR_CACHE: Dict[str, float] = {}
_INCIDENT_SEVERITY_WT = {'extreme': 1.4, 'high': 1.0, 'moderate': 0.6, 'low': 0.3}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math as _m
    r = 6371.0
    p1, p2 = _m.radians(lat1), _m.radians(lat2)
    dp = _m.radians(lat2 - lat1)
    dl = _m.radians(lon2 - lon1)
    a = (_m.sin(dp / 2) ** 2 +
         _m.cos(p1) * _m.cos(p2) * _m.sin(dl / 2) ** 2)
    return 2 * r * _m.asin(_m.sqrt(a))


def incident_history_factors(incidents_df=None) -> Dict[str, float]:
    """Recency/severity-decayed incident influence per locality (0 .. ~0.3).

    Sums, for every recorded incident within 20 km of the panchayat centre,
    severity_weight / (years since + 1) and caps the total. Only ever used
    through the rainfall-gated structural channel at a 15% sub-weight, so the
    register can never manufacture danger by itself.
    """
    if incidents_df is None and _INCIDENT_FACTOR_CACHE:
        return dict(_INCIDENT_FACTOR_CACHE)
    if incidents_df is None:
        try:
            from data.fetcher import IDUKKI_INNER_BOUNDS, KSDMADataFetcher
            incidents_df = KSDMADataFetcher().get_historical_incidents(IDUKKI_INNER_BOUNDS)
        except Exception:  # noqa: BLE001 - factor defaults to a small constant
            logger.warning('Incident register unavailable - using default factors')
            return {}

    try:
        from data.fetcher import LOCALITIES
    except Exception:  # noqa: BLE001
        return {}

    now_year = datetime.now().year
    factors: Dict[str, float] = {}
    for name, loc in LOCALITIES.items():
        total = 0.0
        for _, row in incidents_df.iterrows():
            d = _haversine_km(loc['lat'], loc['lon'],
                              float(row['latitude']), float(row['longitude']))
            if d > 20.0:
                continue
            recency = 1.0 / max(1.0, now_year - int(row['year']) + 1)
            sev = _INCIDENT_SEVERITY_WT.get(
                str(row.get('severity', 'high')).lower(), 1.0)
            total += sev * recency
        factors[name] = round(min(0.30, 0.10 * total), 3)
    _INCIDENT_FACTOR_CACHE.update(factors)
    return factors


def _observed_recent_rain_3d(locality: str, today_mm: float) -> Optional[float]:
    """Measured rain accumulated over the last ~3 days (incl. today).

    Uses the observed-history store (data/observed.py) which closes each
    fully-measured day; returns None when no observed record exists yet.
    """
    try:
        from data.fetcher import LOCALITIES
        from data.observed import LiveHistoryStore
        loc = LOCALITIES.get(locality)
        if loc is None:
            return None
        store = LiveHistoryStore().recent(loc['lat'], loc['lon'], limit=6)
        if store is None or store.empty:
            return None
        today = datetime.now().date()
        cutoff = today - timedelta(days=3)
        recent = store[store['date'].dt.date >= cutoff]
        measured = float(recent['rain_mm'].sum()) if not recent.empty else 0.0
        return round(measured + max(0.0, float(today_mm or 0.0)), 1)
    except Exception as exc:  # noqa: BLE001 - never let history block scoring
        logger.debug(f'recent-rain lookup failed for {locality}: {exc}')
        return None

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

# IMD 24-hour rainfall categories (mm/day), used as score knots:
#   0-7.5 light · 7.5-35.5 moderate · 35.5-64.5 rather heavy · 64.5-115.5 heavy
#   115.5-204.5 very heavy · >204.5 extremely heavy
RAIN_KNOTS = (
    (0.0, 0.00),
    (7.5, 0.05),
    (35.5, 0.32),
    (64.5, 0.55),
    (115.5, 0.72),
    (204.5, 0.90),
    (250.0, 1.00),
)

# Monthly season scale for rainfall-driven danger. 1.0 = monsoon peak.
# May and October are transition months; the rest of the year is dry.
SEASON_SCALE = {
    1: 0.25, 2: 0.25, 3: 0.25, 4: 0.35, 5: 0.60,
    6: 1.00, 7: 1.00, 8: 1.00, 9: 1.00,
    10: 0.60, 11: 0.35, 12: 0.25,
}
MONSOON_MONTHS = (6, 7, 8, 9)

# Rainfall that fully "activates" structural vulnerability (mm/day).
# Chosen so that IMD 'very heavy' rainfall (~115 mm/day) mostly activates it.
RAIN_ACTIVATION_MM = 150.0

# Composite weights (must sum to 1.0)
W_ENV = 0.60       # Environmental severity (weather is the main driver)
W_STRUCT = 0.25    # Structural risk (rainfall-gated vulnerability)
W_HUMAN = 0.15     # Human threat level

# Tier thresholds
T_LOW, T_MOD, T_HIGH = 0.25, 0.50, 0.70


def get_season_info(month: Optional[int] = None) -> Tuple[str, float]:
    """Return (season_label, season_scale) for a month (default: now)."""
    if month is None:
        month = datetime.now().month
    label = 'monsoon' if month in MONSOON_MONTHS else 'dry'
    return label, SEASON_SCALE.get(month, 0.25)


def _rainfall_score(rainfall_mm: float) -> float:
    """Map daily rainfall to a 0-1 severity using the IMD category knots."""
    x = max(0.0, rainfall_mm)
    prev_x, prev_y = RAIN_KNOTS[0]
    for knot_x, knot_y in RAIN_KNOTS[1:]:
        if x <= knot_x:
            if knot_x == prev_x:
                return knot_y
            frac = (x - prev_x) / (knot_x - prev_x)
            return prev_y + frac * (knot_y - prev_y)
        prev_x, prev_y = knot_x, knot_y
    return prev_y


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class DangerIndexCalculator:
    """Compute Danger Index from environmental and structural factors"""

    def __init__(self, locality: str):
        self.locality = locality
        self.population = LOCALITY_POPULATION.get(locality, 30000)
        self.terrain_risk = TERRAIN_SLOPE_RISK.get(locality, 0.7)
        # data-derived (recency/severity-decayed register), capped ~0.30
        self.historical_factor = incident_history_factors().get(locality, 0.10)

    # ------------------------------------------------------------- sub-scores
    def calculate_environmental_severity(self, rainfall_mm: float, wind_mps: float,
                                         humidity_pct: float, cloud_cover_pct: float,
                                         month: Optional[int] = None) -> float:
        """
        Environmental severity (0-1): how severe is the weather right now?

        Rainfall is dominant (78%) and is scored against IMD daily categories,
        scaled by season (dry-season rain is far less dangerous in Idukki).
        Wind, humidity and cloud act only as small amplifiers.

        Returns: Score 0-1 (0=benign weather, 1=catastrophic weather)
        """
        _, season_scale = get_season_info(month)

        rain_score = _rainfall_score(rainfall_mm)
        rain_effective = rain_score * season_scale

        wind_score = _clip(wind_mps / 15.0)          # ~gale-warning threshold
        humidity_score = _clip((humidity_pct - 50.0) / 50.0)  # normal in monsoon
        cloud_score = _clip(cloud_cover_pct / 100.0)

        severity = (
            0.78 * rain_effective +
            0.12 * wind_score +
            0.06 * humidity_score +
            0.04 * cloud_score
        )

        logger.info(f"{self.locality} - Environmental: rain={rain_score:.2f}"
                    f"(x{season_scale:.2f} season), wind={wind_score:.2f}, "
                    f"hum={humidity_score:.2f}, cloud={cloud_score:.2f} "
                    f"→ {severity:.2f}")
        return _clip(severity)

    def calculate_structural_risk(self, rainfall_mm: Optional[float] = None,
                                  month: Optional[int] = None,
                                  recent_rain_3d: Optional[float] = None) -> float:
        """
        Structural risk (0-1): vulnerability of buildings/roads/land to failure.

        This channel is *gated by rainfall*: terrain steepness, soil saturation
        and the locality's documented incident history only matter while rain is
        actually falling. In calm weather the score collapses towards zero, so
        past incidents can never create danger on their own.

        Weighting scheme (documented in docs/METHODOLOGY.md), aligned with
        NDMA/BIS-style susceptibility zonation where rainfall history and the
        landslide inventory validate rather than dominate:
            terrain/slope         40%
            soil saturation       25%   (seasonal + measured recent rain)
            population exposure   20%
            incident history      15%   (decayed register, capped ~0.30)

        Returns: Score 0-1 (0=no active structural risk, 1=extreme risk)
        """
        rainfall_mm = rainfall_mm if rainfall_mm is not None else 0.0
        month = month or datetime.now().month

        # Rainfall gate: how much of the locality's vulnerability is "live"?
        activation = _clip(rainfall_mm / RAIN_ACTIVATION_MM)

        # Soil saturation: monsoon baseline, sharpened by MEASURED recent rain
        # when the observed-history store has data (dry months stay dry even
        # inside the monsoon window after a 3-day break).
        if recent_rain_3d is not None:
            if month in MONSOON_MONTHS:
                soil_saturation = _clip(max(0.55, recent_rain_3d / 80.0))
            else:
                soil_saturation = _clip(min(0.45, recent_rain_3d / 120.0))
        else:
            soil_saturation = 0.9 if month in MONSOON_MONTHS else 0.35

        max_population = max(LOCALITY_POPULATION.values())
        infra_exposure = _clip(self.population / max_population)

        raw_vulnerability = (
            0.40 * self.terrain_risk +
            0.25 * soil_saturation +
            0.20 * infra_exposure +
            0.15 * self.historical_factor   # incidents amplify, never trigger
        )

        risk = raw_vulnerability * activation

        logger.info(f"{self.locality} - Structural: vulnerability={raw_vulnerability:.2f} "
                    f"x activation={activation:.2f} (hist={self.historical_factor:.2f}, "
                    f"soil={soil_saturation:.2f}) → {risk:.2f}")
        return _clip(risk)

    def calculate_human_threat_level(self, rainfall_mm: float,
                                     population: Optional[int] = None,
                                     month: Optional[int] = None) -> float:
        """
        Human threat level (0-1): danger to life and evacuation difficulty.

        Rainfall-driven threat dominates (50%) and is season-scaled. Population
        exposure (35%) and terrain-based evacuation difficulty (15%) provide a
        modest, weather-independent floor so densely populated steep areas are
        never shown as fully risk-free.

        Returns: Score 0-1 (0=low threat, 1=extreme threat to life)
        """
        pop = population or self.population
        max_population = max(LOCALITY_POPULATION.values())
        _, season_scale = get_season_info(month)

        rain_threat = _rainfall_score(rainfall_mm) * season_scale
        population_score = _clip(pop / max_population)
        evacuation_difficulty = self.terrain_risk

        threat = (
            0.50 * rain_threat +
            0.35 * population_score +
            0.15 * evacuation_difficulty
        )

        logger.info(f"{self.locality} - Human Threat: rain={rain_threat:.2f}, "
                    f"pop={population_score:.2f}, evac={evacuation_difficulty:.2f} "
                    f"→ {threat:.2f}")
        return _clip(threat)

    def calculate_composite_index(self, environmental_severity: float,
                                  structural_risk: float,
                                  human_threat_level: float) -> Tuple[str, float]:
        """
        Combine the three sub-scores into the final 4-tier Danger Index.

        Environmental severity carries the most weight because weather is the
        primary driver of monsoon danger in inner Idukki; structural risk and
        human threat modulate it.

        Tier thresholds:
            < 0.25  Low · < 0.50 Moderate · < 0.70 High · >= 0.70 Extreme

        Returns: (tier, score)
        """
        composite_score = (
            W_ENV * environmental_severity +
            W_STRUCT * structural_risk +
            W_HUMAN * human_threat_level
        )

        if composite_score < T_LOW:
            tier = 'Low'
        elif composite_score < T_MOD:
            tier = 'Moderate'
        elif composite_score < T_HIGH:
            tier = 'High'
        else:
            tier = 'Extreme'

        logger.info(f"{self.locality} - COMPOSITE INDEX: {tier} ({composite_score:.2f}) "
                    f"[E={environmental_severity:.2f}, S={structural_risk:.2f}, "
                    f"H={human_threat_level:.2f}]")
        return tier, composite_score

    # --------------------------------------------------------------- helpers
    @staticmethod
    def get_tier_color(tier: str) -> str:
        """Return hex color for map rendering"""
        colors = {
            'Low': '#2ecc71',       # Green
            'Moderate': '#f5a623',  # Orange
            'High': '#ff5252',      # Red
            'Extreme': '#b0102e'    # Deep red
        }
        return colors.get(tier, '#8a93a6')

    @staticmethod
    def get_tier_description(tier: str) -> str:
        """Return plain-language description for residents"""
        descriptions = {
            'Low': 'Current risk is LOW. Weather is calm for the season and '
                   'normal activity is safe. Stay alert during monsoon season.',
            'Moderate': 'Current risk is MODERATE. Rainfall is building and '
                        'some roads may turn slippery. Avoid unnecessary travel '
                        'during heavy downpours.',
            'High': 'Current risk is HIGH. Heavy rain is falling or expected. '
                    'Landslides and flash floods are possible on steep terrain. '
                    'Stay indoors and avoid non-essential travel.',
            'Extreme': 'Current risk is EXTREME. Very heavy rain poses an '
                       'immediate threat to life and property. STAY INDOORS, '
                       'follow evacuation orders and call 112 / 1077 if in danger.'
        }
        return descriptions.get(tier, 'Unknown risk level')


# ---------------------------------------------------------------------------
# Public pipeline functions
# ---------------------------------------------------------------------------

def _build_drivers(locality: str, rainfall_mm: float, season: str,
                   source: str, rainfall_score: float) -> List[str]:
    """Short, plain-language reasons shown in the UI ('why is it this level')."""
    drivers: List[str] = []

    if rainfall_mm >= 115.5:
        drivers.append('Very heavy rain (>115 mm/day) — slope & stream hazards active')
    elif rainfall_mm >= 64.5:
        drivers.append('Heavy rain (>64 mm/day) — IMD "heavy rain" category')
    elif rainfall_mm >= 35.5 and season == 'monsoon':
        drivers.append('Sustained monsoon rain in the forecast')
    elif rainfall_mm >= 35.5:
        drivers.append('Unseasonal rain — treat with monsoon-level caution')
    elif season != 'monsoon':
        drivers.append('Dry season — danger only from outlier storms')
    else:
        drivers.append('Monsoon in progress — monitor daily updates')

    if season == 'monsoon' and TERRAIN_SLOPE_RISK.get(locality, 0) >= 0.75:
        drivers.append('Steep terrain + wet soils raise landslide potential')
    elif rainfall_score >= 0.5:
        drivers.append('Heavy rain on historically sensitive terrain')

    if source == 'synthetic':
        drivers.append('Showing modelled data — live feed unavailable')

    return drivers[:3]


def _evaluate_weather(locality: str, rainfall_mm: float, wind_mps: float,
                      humidity_pct: float, cloud_cover_pct: float,
                      source: str, observed_at=None) -> Dict:
    """Core scoring shared by the live index and the 7-day danger outlook."""
    calc = DangerIndexCalculator(locality)
    season, _ = get_season_info()

    # Live scores use measured recent rain for soil saturation; forecast-day
    # scoring keeps the seasonal baseline (rainfall days ahead are not yet
    # measured, so the outlook behaves exactly as before).
    recent_3d = (_observed_recent_rain_3d(locality, rainfall_mm)
                 if source != 'forecast' else None)

    env_severity = calc.calculate_environmental_severity(
        rainfall_mm, wind_mps, humidity_pct, cloud_cover_pct)
    struct_risk = calc.calculate_structural_risk(
        rainfall_mm, recent_rain_3d=recent_3d)
    human_threat = calc.calculate_human_threat_level(rainfall_mm)
    tier, score = calc.calculate_composite_index(env_severity, struct_risk, human_threat)
    rain_score = _rainfall_score(rainfall_mm)

    return {
        'locality': locality,
        'tier': tier,
        'composite_score': round(score, 2),
        'environmental_severity': round(env_severity, 2),
        'structural_risk': round(struct_risk, 2),
        'human_threat': round(human_threat, 2),
        'color': DangerIndexCalculator.get_tier_color(tier),
        'description': DangerIndexCalculator.get_tier_description(tier),
        'drivers': _build_drivers(locality, rainfall_mm, season, source, rain_score),
        'season': season,
        'data_source': source,
        'observed_at': observed_at,
        'weather': {
            'rainfall_mm': round(float(rainfall_mm), 1),
            'wind_mps': round(float(wind_mps), 1),
            'humidity_pct': round(float(humidity_pct), 1),
            'cloud_cover_pct': round(float(cloud_cover_pct), 1),
        },
        'timestamp': pd.Timestamp.now().isoformat()
    }


def compute_index_for_locality(locality: str, weather_data: Dict) -> Dict:
    """
    End-to-end calculation: current weather data → today's Danger Index.

    Args:
        locality: Locality name
        weather_data: Dict with rainfall_mm, wind_mps, humidity_pct,
                      cloud_cover_pct (plus optional source/observed_at)

    Returns:
        Dict with tier, score, sub-scores, drivers, season, data source,
        description and color.
    """
    rainfall_mm = weather_data.get('rainfall_mm', 0.0)
    wind_mps = weather_data.get('wind_mps', 0.0)
    humidity_pct = weather_data.get('humidity_pct', 60.0)
    cloud_cover_pct = weather_data.get('cloud_cover_pct', 40.0)
    source = weather_data.get('source', 'synthetic')
    observed_at = weather_data.get('observed_at')
    res = _evaluate_weather(locality, rainfall_mm, wind_mps, humidity_pct,
                            cloud_cover_pct, source, observed_at)

    # metadata consumed by the API/UI (not part of the risk maths)
    res['conditions_provider'] = weather_data.get('conditions_provider', 'synthetic')
    res['population'] = LOCALITY_POPULATION.get(locality, 0)
    try:
        from index.wards import _load_structure
        res['ward_count'] = len(_load_structure().get(locality, {}).get('wards', []))
    except Exception:  # noqa: BLE001 - cosmetic metadata only
        res['ward_count'] = 0
    temp = weather_data.get('temperature_c')
    if temp is not None:
        res['weather']['temperature_c'] = round(float(temp), 1)
    return res


def compute_forecast_outlook(locality: str, forecast_df, days: int = 7,
                             context_weather: Optional[Dict] = None) -> Dict:
    """
    7-day-ahead danger forecast for a locality.

    Runs the SAME danger-index model as the live feed, once per forecast day,
    using that day's forecast rainfall (Open-Meteo). Wind/humidity/cloud are
    not predictable a week out, so future days reuse the latest observation
    (or season-typical values) - rainfall dominates the score anyway, and it
    gates structural (landslide) risk.

    Returns:
        {"locality", "source", "season", "note", "days": [...]}
        where each day has date, day_offset, rainfall_mm, probability_pct,
        tier, composite_score, color, description, drivers.
    """
    ctx = context_weather or {}
    wind = ctx.get('wind_mps', 0.0)
    humidity = ctx.get('humidity_pct', 60.0)
    cloud = ctx.get('cloud_cover_pct', 40.0)

    season, _ = get_season_info()
    days_out: List[Dict] = []
    worst = None
    worst_score = -1.0

    df = forecast_df.head(days)
    for offset, (_, row) in enumerate(df.iterrows()):
        rain = float(row.get('rainfall_mm', 0.0) or 0.0)
        prob = row.get('probability_pct')
        prob = None if prob is None or pd.isna(prob) else float(prob)

        res = _evaluate_weather(locality, rain, wind, humidity, cloud,
                                source='forecast', observed_at=None)
        drivers = res['drivers']
        if prob is not None and prob >= 55.0:
            drivers.append(f'~{int(round(prob))}% chance of rain this day')

        day = {
            'date': pd.Timestamp(row['date']).strftime('%Y-%m-%d'),
            'day_offset': offset,
            'rainfall_mm': round(rain, 1),
            'probability_pct': prob,
            'tier': res['tier'],
            'composite_score': res['composite_score'],
            'color': res['color'],
            'description': res['description'],
            'drivers': drivers[:4],
            'environmental_severity': res['environmental_severity'],
            'structural_risk': res['structural_risk'],
            'human_threat': res['human_threat'],
        }
        days_out.append(day)
        if res['composite_score'] > worst_score:
            worst, worst_score = day, res['composite_score']

    return {
        'locality': locality,
        'source': forecast_df.attrs.get('source', 'forecast') if hasattr(forecast_df, 'attrs') else 'forecast',
        'season': season,
        'note': 'Danger tier per day from the 7-day rainfall forecast. '
                'Wind/humidity/cloud follow the latest observation.',
        'worst_day': worst,
        'days': days_out,
    }


def compute_all_locality_indices() -> Tuple[Dict, Optional[pd.DataFrame]]:
    """
    Fetch data and compute the Danger Index for every monitored locality.

    Single shared entry point used by the API server, the map view and other
    callers, so the fetch -> extract -> compute pipeline is defined exactly
    once.

    Returns:
        (indices, incidents_df): dict of {locality: index_result} plus the
        historical-incidents DataFrame (from the first locality's data). The
        DataFrame is None if no locality could be fetched at all.
    """
    from data.fetcher import LOCALITIES, fetch_all_data_for_locality, extract_current_weather

    indices: Dict[str, Dict] = {}
    incidents_df: Optional[pd.DataFrame] = None

    for locality in LOCALITIES.keys():
        try:
            data = fetch_all_data_for_locality(locality)
            weather_data = extract_current_weather(data)
            result = compute_index_for_locality(locality, weather_data)
            result['latitude'] = LOCALITIES[locality]['lat']
            result['longitude'] = LOCALITIES[locality]['lon']
            indices[locality] = result

            if incidents_df is None and data.get('historical_incidents') is not None:
                incidents_df = data['historical_incidents']

        except Exception as e:
            logger.error(f"Error computing index for {locality}: {e}")
            # Safe default so one bad locality never takes down the whole map/API
            indices[locality] = {
                'locality': locality,
                'tier': 'Moderate',
                'composite_score': 0.45,
                'environmental_severity': 0.4,
                'structural_risk': 0.45,
                'human_threat': 0.45,
                'color': '#f5a623',
                'description': 'Unable to fetch data; showing default risk level.',
                'drivers': ['Data temporarily unavailable — default level shown'],
                'season': get_season_info()[0],
                'data_source': 'synthetic',
                'conditions_provider': 'synthetic',
                'population': LOCALITY_POPULATION.get(locality, 0),
                'ward_count': 0,
                'observed_at': None,
                'weather': {
                    'rainfall_mm': None,
                    'wind_mps': None,
                    'humidity_pct': None,
                    'cloud_cover_pct': None,
                    'temperature_c': None,
                },
                'timestamp': pd.Timestamp.now().isoformat(),
                'latitude': LOCALITIES[locality]['lat'],
                'longitude': LOCALITIES[locality]['lon'],
            }

    return indices, incidents_df


if __name__ == '__main__':
    # Test with representative scenarios (monsoon month = August)
    scenarios = [
        ('Dry-season calm', {'rainfall_mm': 2, 'wind_mps': 3, 'humidity_pct': 55, 'cloud_cover_pct': 20}),
        ('Monsoon light', {'rainfall_mm': 15, 'wind_mps': 4, 'humidity_pct': 80, 'cloud_cover_pct': 70}),
        ('Monsoon moderate', {'rainfall_mm': 45, 'wind_mps': 6, 'humidity_pct': 88, 'cloud_cover_pct': 90}),
        ('Monsoon heavy', {'rainfall_mm': 100, 'wind_mps': 8, 'humidity_pct': 92, 'cloud_cover_pct': 95}),
        ('Very heavy', {'rainfall_mm': 180, 'wind_mps': 11, 'humidity_pct': 95, 'cloud_cover_pct': 100}),
        ('Catastrophic', {'rainfall_mm': 280, 'wind_mps': 14, 'humidity_pct': 98, 'cloud_cover_pct': 100}),
    ]

    for label, w in scenarios:
        result = compute_index_for_locality('Kumily', w)
        print(f"{label:20} → {result['tier']:9} score={result['composite_score']:.2f} "
              f"[E={result['environmental_severity']:.2f} S={result['structural_risk']:.2f} "
              f"H={result['human_threat']:.2f}]")
