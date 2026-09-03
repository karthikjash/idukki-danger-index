"""
ENSO state from the NOAA CPC Oceanic Nino Index (ONI).

The ONI is the 3-month running mean of Niño 3.4 SST anomalies. It is fetched
at build time from NOAA CPC (see data/static/oni.txt) and parsed here.
Phases follow the standard NOAA thresholds: |anomaly| >= 0.5 °C.

Kerala relevance (from IMD/climate literature, encoded as plain-language
advisories, not as a hard model input):
  * El Niño during the SW monsoon (Jun-Sep) is associated with weaker,
    drier monsoon spells over much of India - including fewer extreme
    rainfall days but also heat stress and patchy rains.
  * La Niña (especially a mature La Niña into Oct-Dec) tends to strengthen
    the NE monsoon over southern Kerala - the Oct-Dec rains that saturate
    Idukki's slopes after the SW monsoon.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ONI_FILE = Path(__file__).resolve().parent.parent / "data" / "static" / "oni.txt"
ROW_RE = re.compile(r'^\s*([A-Z]{3})\s+(\d{4})\s+[\d.]+\s+(-?[\d.]+)\s*$')
SEASON_MONTH = {'DJF': 1, 'JFM': 2, 'FMA': 3, 'MAM': 4, 'AMJ': 5, 'MJJ': 6,
                'JJA': 7, 'JAS': 8, 'ASO': 9, 'SON': 10, 'OND': 11, 'NDJ': 12}

STRONG = 1.5
MODERATE = 1.0


def _load_oni():
    rows = []
    if not ONI_FILE.exists():
        logger.warning(f"ONI file missing: {ONI_FILE}")
        return rows
    for line in ONI_FILE.read_text().splitlines():
        m = ROW_RE.match(line)
        if m:
            rows.append({'season': m.group(1),
                         'year': int(m.group(2)),
                         'oni': float(m.group(3))})
    return rows


def ensn_state() -> dict:
    """Most recent completed ONI season + 4-season trend."""
    rows = _load_oni()
    if not rows:
        return {'available': False, 'source': 'noaa-cpc',
                'note': 'ONI table not available'}
    latest = rows[-1]

    def phase(oni):
        if oni >= STRONG:
            return 'Strong El Niño'
        if oni >= MODERATE:
            return 'Moderate El Niño'
        if oni >= 0.5:
            return 'Weak El Niño'
        if oni <= -STRONG:
            return 'Strong La Niña'
        if oni <= -MODERATE:
            return 'Moderate La Niña'
        if oni <= -0.5:
            return 'Weak La Niña'
        return 'ENSO-neutral'

    trend = [r['oni'] for r in rows[-4:]]
    return {
        'available': True,
        'source': 'NOAA CPC ONI (Niño 3.4)',
        'latest_season': f"{latest['season']} {latest['year']}",
        'oni': round(latest['oni'], 2),
        'phase': phase(latest['oni']),
        'trend_oni': [round(x, 2) for x in trend],
        'parsed_at': datetime.now().isoformat(),
    }


def monsoon_outlook(ensn: dict) -> dict:
    """Plain-language seasonal guidance for Kerala/Idukki given ENSO phase."""
    phase = ensn.get('phase', 'ENSO-neutral') if ensn.get('available') else 'unknown'
    oni = ensn.get('oni', 0.0)
    month = datetime.now().month

    if phase == 'unknown':
        text = ('ENSO data unavailable. Follow daily IMD/KSDMA updates for '
                'monsoon behaviour.')
    elif 'El Niño' in phase and month in (6, 7, 8, 9):
        text = (f'{phase} (ONI {oni:+.2f} °C). El Niño Junes-September often '
                'bring a weaker, patchier SW monsoon over Idukki - fewer '
                'prolonged heavy spells, but sudden intense bursts remain '
                'possible. Watch for dry-spell water stress too.')
    elif 'El Niño' in phase:
        text = (f'{phase} (ONI {oni:+.2f} °C). Typically suppresses the SW '
                'monsoon and can delay its onset. The NE monsoon (Oct-Dec) '
                'may still deliver normal to heavy rain - do not relax '
                'landslide vigilance.')
    elif 'La Niña' in phase and month in (10, 11, 12):
        text = (f'{phase} (ONI {oni:+.2f} °C). A mature La Niña tends to '
                'strengthen Kerala\'s NE monsoon (Oct-Dec) - expect more '
                'frequent rain over already-saturated Idukki slopes. '
                'Elevated landslide watch recommended through December.')
    elif 'La Niña' in phase:
        text = (f'{phase} (ONI {oni:+.2f} °C). Often signals an active '
                'monsoon season ahead for Kerala; monitor early-season '
                'outlooks for heavy-rain windows.')
    else:
        text = (f'{phase} (ONI {oni:+.2f} °C). No strong ENSO forcing '
                'expected - monsoon behaviour driven mainly by synoptic '
                'weather systems. Continue routine monitoring.')
    return {'phase': phase, 'oni': oni, 'text': text}
