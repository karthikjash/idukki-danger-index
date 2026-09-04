"""
Inference for the per-locality ML outlook ("AI outlook").

predict_tomorrow(locality) builds the causal feature vector ending TODAY
(live rainfall spliced onto the historical series) and returns the trained
models' next-day rainfall estimate and heavy-rain probability.
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from ml.dataset import build_features, load_daily_rainfall  # noqa: E402
from ml.models import (LSTMRainfall, LogisticHazard, RidgeRainfall,  # noqa: E402
                       make_sequences)
from ml.train import (CLS_FEATURES, LSTM_WINDOW, MODEL_DIR,  # noqa: E402
                      SEQ_FEATURES)


def _latest_window_and_row(locality: str, today_mm: float):
    """Causal features ending today: (LSTM window, classifier row, n_days)."""
    loc = _localities()[locality]
    # Inference must never trigger archive downloads: use only what is
    # already cached on disk (training/`build dataset` populates it).
    hist = load_daily_rainfall(loc['lat'], loc['lon'],
                               refresh_trailing=False, fetch_missing=False)
    if hist.empty:
        return None

    # splice today's live reading onto the historical series
    today = pd.Timestamp(datetime.now().date())
    hist = hist[hist['date'] < today]
    if today_mm is not None:
        hist = pd.concat([hist, pd.DataFrame({'date': [today],
                                              'rainfall_mm': [max(0.0, float(today_mm))]})],
                         ignore_index=True)
    feats = build_features(hist.set_index('date')['rainfall_mm'])
    feats = feats.drop(columns=['accum_1d'], errors='ignore')

    cols = [c for c in CLS_FEATURES if c in feats.columns]
    if len(feats) < LSTM_WINDOW + 1:
        return None
    seq_idx = [cols.index(c) for c in SEQ_FEATURES]
    arr = feats[cols].to_numpy(dtype=np.float64)
    window = arr[-LSTM_WINDOW:, seq_idx][None, :, :]   # (1, T, F)
    return {'window': window, 'row': arr[-1:, :], 'days': len(feats),
            'last_date': str(feats.index[-1].date())}


def predict_tomorrow(locality: str, today_mm: float) -> dict:
    """Combined AI outlook for the next 24h at a locality."""
    out = {'locality': locality, 'status': 'unavailable',
           'trained_at': None, 'generated_at': datetime.now().isoformat()}
    lstm_path = MODEL_DIR / f"{locality}_lstm.npz"
    ridge_path = MODEL_DIR / f"{locality}_ridge.npz"
    hazard_path = MODEL_DIR / f"{locality}_hazard.npz"
    if not (lstm_path.exists() or ridge_path.exists() or hazard_path.exists()):
        return out

    ctx = _latest_window_and_row(locality, today_mm)
    if ctx is None:
        return out

    try:
        if lstm_path.exists():
            lstm = LSTMRainfall.load(lstm_path)
            out['lstm_mm'] = round(float(lstm.predict(ctx['window'])[0]), 1)
        if ridge_path.exists():
            ridge = RidgeRainfall.load(ridge_path)
            out['ridge_mm'] = round(float(ridge.predict(ctx['row'])[0]), 1)
        if hazard_path.exists():
            clf = LogisticHazard.load(hazard_path)
            prob = float(clf.predict_proba(ctx['row'])[0])
            thr = float(getattr(clf, 'threshold', None) or 0.5)
            out['heavy_rain_pct'] = round(prob * 100.0, 1)
            # model alert = probability above the calibrated operating point
            # (threshold chosen so >=90% of dangerous windows are caught on
            # the 2019 validation year - see ml/train.py / eval.json)
            out['heavy_alert'] = bool(prob >= thr)
            out['threshold'] = thr
        # consensus next-day rainfall: mean of available regressors
        est = [v for k, v in out.items() if k.endswith('_mm')]
        out['ml_rain_mm'] = round(float(np.mean(est)), 1) if est else None
        from ml.dataset import HEAVY_MM
        out['heavy_mm'] = HEAVY_MM
        out['status'] = 'ready'
        # plain-language framing for the UI: trained to minimise missed days
        out['recall_note'] = ('Hazard model threshold calibrated for >=90% '
                              'recall of heavy-rain windows on the 2019 '
                              'validation year (a miss costs more than a '
                              'false alarm).')
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"ML predict failed for {locality}: {exc}")
        out['status'] = 'error'
    return out


def _localities():
    from data.fetcher import LOCALITIES
    return LOCALITIES


def train_if_missing(epochs: int = 40) -> bool:
    """Train the whole suite when artifacts are absent. Returns True if trained."""
    eval_path = MODEL_DIR / "eval.json"
    if eval_path.exists():
        return False
    logger.info("ML artifacts missing - training model suite (background)...")
    from ml.train import train_all
    train_all(epochs=epochs, verbose=False)
    return True
