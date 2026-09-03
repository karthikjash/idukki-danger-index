"""Seasonal outlook package: ENSO context + lightning-risk climatology.

Built as advisory layers on top of the live danger index: ENSO phase gives
season-level context for Idukki's rainfall, and lightning risk is a
climatological day-of-year model (no live strike feed is wired yet).
"""

from datetime import datetime

from outlook.enso import ensn_state, monsoon_outlook
from outlook.lightning import lightning_risk_today


def build_outlook() -> dict:
    """District seasonal outlook for today."""
    ensn = ensn_state()
    lit = {name: lightning_risk_today(name) for name in _localities()}
    return {
        'generated_at': datetime.now().isoformat(),
        'enso': ensn,
        'monsoon_outlook': monsoon_outlook(ensn),
        'lightning': lit,
    }


def _localities():
    from data.fetcher import LOCALITIES
    return list(LOCALITIES.keys())
