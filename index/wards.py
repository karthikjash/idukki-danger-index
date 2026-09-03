"""
Ward-level micro-zonation for the monitored panchayats.

What is real and what is modelled (kept explicit everywhere):

* Ward STRUCTURE comes from data/static/wards.json. Kumily's table is the
  real LSG Kerala Election-2020 ward list; the other panchayats ship a
  clearly-flagged modelled default until their real LSG / Census ward tables
  are dropped in. Two drop-in paths:
      1. edit data/static/wards.json, or
      2. add a data/static/wards_overrides.csv with columns
         locality,ward_no,ward_name,population,source  (takes precedence).
* Panchayat POPULATION totals are the authoritative figures supplied by the
  project owner (see index/calculator.py LOCALITY_POPULATION). Per-ward
  population is apportioned in equal shares from the panchayat total until a
  Census-2011 ward table is supplied - flagged as modelled.
* Ward GEOMETRY (centres) is a deterministic geometric proxy (disc layout
  around the panchayat centre) until real ward polygons are loaded. It is
  only used to measure each ward's proximity to the REAL recorded incidents,
  which is what differentiates the wards.
* Ward SENSITIVITY is data-derived: recorded landslide/flood incidents within
  ~5 km of a ward centre, severity- and recency-weighted (recent + severe
  events count more; a 2004 event weighs less than a 2024 one).

The ward score is the panchayat's live danger score lifted by that ward's
incident sensitivity - so on a calm day every ward is calm (rainfall still
gates everything), while during heavy rain the historically-touched wards
escalate first. This mirrors how district officers actually triage wards.
"""

import hashlib
import json
import logging
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'static'
WARDS_JSON = DATA_DIR / 'wards.json'
OVERRIDE_CSV = DATA_DIR / 'wards_overrides.csv'

# tier knots mirror index/calculator.py so micro-zones use the same language
T_LOW, T_MOD, T_HIGH = 0.25, 0.50, 0.70
TIER_COLOURS = {'Low': '#2ecc71', 'Moderate': '#f5a623',
                'High': '#ff5252', 'Extreme': '#ff2e5f'}
SEVERITY_WEIGHT = {'extreme': 1.6, 'high': 1.0, 'moderate': 0.55,
                   'low': 0.3}
PROXIMITY_M = 5000.0


def _stable_seed(text: str) -> int:
    """Deterministic seed that is identical across processes."""
    return int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16) % (2 ** 32)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ loading
def _load_structure() -> dict:
    """Panchayat -> meta + wards list (JSON, optionally overridden by CSV)."""
    raw = json.loads(WARDS_JSON.read_text())['panchayats']
    if OVERRIDE_CSV.exists():
        try:
            df = pd.read_csv(OVERRIDE_CSV)
            for locality, g in df.groupby('locality'):
                wards = [{'no': int(r['ward_no']), 'name': str(r['ward_name'])}
                         for _, r in g.iterrows()]
                meta = raw.setdefault(locality, {})
                meta['wards'] = wards
                meta['structure_source'] = 'wards_overrides.csv (authoritative)'
                if 'population' in g.columns and pd.notna(g['population']).any():
                    meta['ward_populations'] = {
                        int(r['ward_no']): float(r['population'])
                        for _, r in g.iterrows() if pd.notna(r.get('population'))}
            logger.info('wards_overrides.csv applied')
        except Exception as exc:  # noqa: BLE001
            logger.warning(f'wards_overrides.csv failed: {exc}')
    return raw


def _ward_centres(locality: str, n: int, lat: float, lon: float) -> list:
    """Deterministic disc-layout proxy centres inside the panchayat radius."""
    from index.map_generator import LOCALITY_COORDS
    radius = LOCALITY_COORDS.get(locality, {}).get('radius', 7000)
    rng = np.random.default_rng(_stable_seed(f'wardgeo::{locality}'))
    centres = []
    for i in range(n):
        # golden-angle disc packing: even spread, jittered deterministically
        angle = i * 2.399963 + rng.uniform(-0.08, 0.08)
        rr = max(250.0, radius * math.sqrt(max(0.05, (i + 0.5) / n)) *
                 rng.uniform(0.82, 1.05))
        dy = rr * math.cos(angle)
        dx = rr * math.sin(angle)
        centres.append((lat + dy / 111000.0,
                        lon + dx / (111000.0 * math.cos(math.radians(lat)))))
    return centres


# ------------------------------------------------------------------ scoring
def ward_risk(locality: str, composite_score: float = 0.0,
              incidents=None) -> dict:
    """Ward-level exposure for one panchayat.

    Args:
        locality: panchayat name
        composite_score: the panchayat's live composite danger score (0-1)
        incidents: DataFrame of recorded incidents (latitude/longitude/year/
                   severity) - the shared register from data/fetcher.py
    """
    from data.fetcher import LOCALITIES
    from index.calculator import LOCALITY_POPULATION

    structure = _load_structure().get(locality)
    if not structure:
        return {'locality': locality, 'available': False}
    loc = LOCALITIES.get(locality)
    if not loc:
        return {'locality': locality, 'available': False}

    wards = structure['wards']
    n = len(wards)
    pop_total = int(LOCALITY_POPULATION.get(locality, 0))
    centres = _ward_centres(locality, n, loc['lat'], loc['lon'])
    now_year = datetime.now().year
    # per-ward population: authoritative census table when provided, else an
    # equal apportionment of the panchayat total (modelled, flagged).
    ward_pops = structure.get('ward_populations')
    base_share = pop_total / max(n, 1)
    pops = []
    for w in wards:
        if ward_pops and w['no'] in ward_pops:
            pops.append(float(ward_pops[w['no']]))
        else:
            pops.append(base_share)
    # absorb rounding drift into the last ward
    drift = pop_total - sum(pops)
    pops[-1] = max(0.0, pops[-1] + drift)
    pops = [round(p) for p in pops]

    # per-ward sensitivity from the real incident record
    sensitivity = []
    hits = []
    inc = incidents if incidents is not None else pd.DataFrame(
        columns=['latitude', 'longitude', 'year', 'severity'])
    for (wlat, wlon) in centres:
        score_hits = 0
        count = 0
        if not inc.empty:
            for _, row in inc.iterrows():
                d = _haversine_m(wlat, wlon, float(row['latitude']),
                                 float(row['longitude']))
                if d <= PROXIMITY_M:
                    count += 1
                    recency = 1.0 / max(1.0, now_year - int(row['year']) + 1)
                    sev = SEVERITY_WEIGHT.get(
                        str(row.get('severity', 'high')).lower(), 1.0)
                    score_hits += recency * sev
        sensitivity.append(min(0.35, 0.05 * score_hits))
        hits.append(count)

    rows = []
    for i, w in enumerate(wards):
        score = min(1.0, max(0.0, composite_score * (1.0 + 1.6 * sensitivity[i])
                             + 0.02 * sensitivity[i]))
        tier = ('Extreme' if score >= T_HIGH else
                'High' if score >= T_MOD else
                'Moderate' if score >= T_LOW else 'Low')
        rows.append({
            'ward_no': w['no'],
            'ward_name': w['name'],
            'population': pops[i],
            'population_share_pct': round(100.0 * pops[i] / max(pop_total, 1), 1),
            'latitude': round(centres[i][0], 5),
            'longitude': round(centres[i][1], 5),
            'incidents_nearby': hits[i],
            'sensitivity': round(sensitivity[i], 3),
            'score': round(score, 3),
            'tier': tier,
            'color': TIER_COLOURS[tier],
        })

    rows.sort(key=lambda r: (-r['score'], -r['incidents_nearby']))
    return {
        'locality': locality,
        'available': True,
        'panchayat_population': pop_total,
        'panchayat_score': round(composite_score, 3),
        'ward_count': n,
        'structure_source': structure.get('structure_source', 'unknown'),
        'population_model': ('census ward table' if ward_pops else
                             'apportioned estimate (equal share)'),
        'top_ward': rows[0],
        'wards': rows,
    }


def all_ward_risk(indices: dict, incidents=None) -> dict:
    """Ward micro-zonation for every locality in the indices dict."""
    return {name: ward_risk(name,
                            float(data.get('composite_score', 0.0) or 0.0),
                            incidents)
            for name, data in indices.items()}
