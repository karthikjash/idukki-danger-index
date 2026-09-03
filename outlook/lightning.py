"""
Lightning risk layer for inner Idukki.

Kerala lightning climatology: strikes peak sharply in the pre-monsoon
(Apr-May, when daytime heating meets moist westerlies), with a weaker
secondary peak in Oct-Nov (NE monsoon). Highlands such as Idukki see
elevated strike exposure relative to the coast.

This module scores each locality from (a) a day-of-year climatology curve
and (b) a fixed terrain/elevation factor, and labels the result as a
climatological model. A live strike feed (e.g. Blitzortung/lightningmaps
data or IMD lightning records) can replace the climatology later - the API
shape will not change.
"""

from datetime import datetime
from pathlib import Path

import numpy as np

# Fixed per-locality exposure: highland + west-facing = higher strike exposure.
_LOCAL_EXPOSURE = {
    'Kumily': 1.15, 'Peermedu': 1.10, 'Idukki': 1.10, 'Adimali': 1.15,
    'Kattappana': 1.05, 'Munnar': 1.20, 'Nedumkandam': 1.10,
}

# Monthly relative strike activity for Kerala (Jan..Dec), normalised.
# Pre-monsoon peak (Apr-May), secondary NE-monsoon peak (Oct-Nov).
MONTHLY_WEIGHT = np.array([3, 4, 7, 16, 18, 8, 3, 3, 6, 9, 7, 3], dtype=float)


def _today_index() -> float:
    """Day-of-year climatology value in [0, 1]."""
    now = datetime.now()
    w = MONTHLY_WEIGHT[now.month - 1]
    # smooth within the month using day position
    day_frac = (now.day - 1) / 30.0
    return float(w * (1.0 + 0.1 * day_frac) / MONTHLY_WEIGHT.max())


def lightning_risk_today(locality: str) -> dict:
    """Per-locality lightning risk for today (climatological model)."""
    base = _today_index()
    exposure = _LOCAL_EXPOSURE.get(locality, 1.0)
    score = float(np.clip(base * exposure, 0.0, 1.0))

    if score >= 0.6:
        tier, colour, guidance = 'High', '#ef4444', (
            'Pre-monsoon thunderstorm season: avoid open fields, hilltops, '
            'isolated trees and water bodies during afternoon storms.')
    elif score >= 0.35:
        tier, colour, guidance = 'Moderate', '#f5a623', (
            'Thunderstorms possible. Move indoors when thunder follows '
            'lightning within 30 seconds; unplug sensitive appliances.')
    elif score >= 0.15:
        tier, colour, guidance = 'Low', '#2ecc71', (
            'Low strike likelihood today. Usual monsoon precautions apply.')
    else:
        tier, colour, guidance = 'Very Low', '#27ae60', (
            'Minimal lightning activity expected. Keep a general weather '
            'awareness during evening showers.')

    return {
        'locality': locality,
        'tier': tier,
        'score': round(score, 2),
        'colour': colour,
        'model': 'climatological (Kerala monthly strike climatology)',
        'source': 'climatology',
        'peak_months': 'April-May (pre-monsoon) and October-November',
        'guidance': guidance,
    }
