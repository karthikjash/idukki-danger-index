"""
Train the per-locality ML model suite.

Usage:
    python3 ml/train.py                 # train every locality
    python3 ml/train.py --locality Kumily
    python3 ml/train.py --fetch-only    # only download/cache historical data

Evaluation protocol (chronological, no look-ahead):
    train      2012-01-01 .. 2017-12-31   (fits the models)
    validate   2018-01-01 .. 2019-12-31   (chooses the hazard threshold)
    test       2020-01-01 .. yesterday     (final out-of-sample report)

The hazard model is trained cost-weighted (a missed dangerous window is
weighted COST_RATIO x a false alarm) and its decision threshold is calibrated
on the two validation years to catch at least TARGET_RECALL of real dangerous
windows while firing the fewest possible alarms. The test window then shows
the honest recall/precision trade-off - this is how an alerting system is
tuned in practice, because on very rare events plain "accuracy" is
meaningless (a model that never alerts scores 95%+ "accuracy" and protects
nobody).
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetcher import LOCALITIES  # noqa: E402

from ml.dataset import (HEAVY_MM, labelled_frame,  # noqa: E402
                        load_daily_rainfall_observed)
from ml.models import (LSTMRainfall, LogisticHazard, RidgeRainfall,  # noqa: E402
                       _auc, best_threshold, make_sequences)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger("ml.train")

MODEL_DIR = Path(__file__).resolve().parent / "models"
VAL_START = date(2018, 1, 1)     # threshold-calibration window starts
EVAL_CUTOFF = date(2020, 1, 1)   # test window starts

# Cost/alerting configuration (documented in docs/METHODOLOGY.md)
COST_RATIO = 4.0        # a missed dangerous window costs 4x a false alarm
TARGET_RECALL = 0.90    # must catch >=90% of dangerous windows (validated)
MIN_RECALL = 0.85       # floor if the 90% point cannot be reached

SEQ_FEATURES = ['rainfall_mm', 'accum_3d', 'accum_7d', 'doy_sin', 'doy_cos']
CLS_FEATURES = ['rainfall_mm', 'accum_3d', 'accum_7d', 'accum_15d', 'accum_30d',
                'clim_30d', 'rain_over_clim', 'wet_streak', 'dry_days_7',
                'doy_sin', 'doy_cos', 'month', 'is_monsoon', 'is_transition']
LSTM_WINDOW = 30


def _prepare(locality: str):
    """Historical rainfall (ERA5 archive + measured live-history tail)."""
    loc = LOCALITIES[locality]
    frame = load_daily_rainfall_observed(loc['lat'], loc['lon'])
    if frame.empty:
        return None
    feats = labelled_frame(frame)
    feats = feats.drop(columns=['accum_1d'], errors='ignore')
    return feats


def _metrics(y_true, y_pred):
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        'mae_mm': round(float(np.mean(np.abs(y_true - y_pred))), 2),
        'r2': round(1.0 - ss_res / ss_tot if ss_tot > 0 else float('nan'), 3),
        'bias_mm': round(float(np.mean(y_pred - y_true)), 2),
    }


def _confusion(y_true, pred):
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    return {'tp': tp, 'fn': fn, 'fp': fp, 'tn': tn}


def _alert_metrics(y_true, pred):
    """Operating-point metrics: recall, precision, false-alarm rate, F1."""
    c = _confusion(y_true, pred)
    denom_r = c['tp'] + c['fn']
    denom_p = c['tp'] + c['fp']
    recall = c['tp'] / denom_r if denom_r else float('nan')
    precision = c['tp'] / denom_p if denom_p else 0.0
    fpr = c['fp'] / (c['fp'] + c['tn']) if (c['fp'] + c['tn']) else float('nan')
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        'recall': round(recall, 3),
        'precision': round(precision, 3),
        'false_alarm_rate': round(fpr, 3),
        'f1': round(f1, 3),
        'balanced_accuracy': round((recall + (1.0 - fpr)) / 2.0, 3)
        if not (np.isnan(recall) or np.isnan(fpr)) else float('nan'),
        'confusion': c,
    }


def train_locality(locality: str, epochs: int = 45, verbose: bool = False) -> dict:
    feats = _prepare(locality)
    if feats is None:
        logger.warning(f"{locality}: no historical data - skipped")
        return {}

    feat_cols = [c for c in CLS_FEATURES if c in feats.columns]
    dates = pd.to_datetime(feats['date'])
    is_train = dates < pd.Timestamp(VAL_START)
    is_val = (dates >= pd.Timestamp(VAL_START)) & (dates < pd.Timestamp(EVAL_CUTOFF))
    is_test = dates >= pd.Timestamp(EVAL_CUTOFF)

    X_all = feats[feat_cols].to_numpy(dtype=np.float64)
    y_heavy_all = feats['heavy_soon'].to_numpy(dtype=np.float64)

    summary = {'locality': locality, 'days': int(len(feats)),
               'train_days': int(is_train.sum()),
               'val_days': int(is_val.sum()),
               'test_days': int(is_test.sum()),
               'window': LSTM_WINDOW, 'features': feat_cols,
               'seq_features': SEQ_FEATURES, 'heavy_mm': HEAVY_MM,
               'hazard_label': f'very-heavy day (>= {HEAVY_MM} mm) within next 3 days',
               'cost_ratio_miss_vs_false_alarm': COST_RATIO,
               'target_recall': TARGET_RECALL,
               'trained_at': pd.Timestamp.now().isoformat()}

    # ---- hazard classifier (cost-weighted, threshold-calibrated on 2019)
    if is_train.sum() > 100 and is_val.sum() > 40 and is_test.sum() > 60:
        clf = LogisticHazard(seed=7).fit(
            X_all[is_train], y_heavy_all[is_train],
            epochs=epochs, pos_weight=COST_RATIO)
        p_train = clf.predict_proba(X_all[is_train])
        p_val = clf.predict_proba(X_all[is_val])
        p_test = clf.predict_proba(X_all[is_test])

        # calibration: most-specific operating point that still catches the
        # target fraction of dangerous windows on the validation years
        cal = best_threshold(y_heavy_all[is_val], p_val,
                             min_recall=TARGET_RECALL)
        if not cal.get('target_met', True):
            cal = best_threshold(y_heavy_all[is_val], p_val,
                                 min_recall=MIN_RECALL)
        clf.threshold = cal['threshold']

        # honest out-of-sample metrics at the calibrated threshold
        pred_test = (p_test >= cal['threshold']).astype(int)
        test_metrics = _alert_metrics(y_heavy_all[is_test], pred_test)
        val_metrics = _alert_metrics(y_heavy_all[is_val],
                                     (p_val >= cal['threshold']).astype(int))

        summary['hazard'] = {
            'auc_train': round(_auc(y_heavy_all[is_train], p_train), 3),
            'auc_val': round(_auc(y_heavy_all[is_val], p_val), 3),
            'auc_test': round(_auc(y_heavy_all[is_test], p_test), 3),
            'threshold': cal['threshold'],
            'calibration': {
                'window': '2018-2019 validation years',
                'target_met': cal.get('target_met', True),
                'chosen_recall': cal['recall'],
                'chosen_precision': cal['precision'],
                'chosen_fpr': cal['fpr'],
                'val_metrics': val_metrics,
            },
            'test_metrics': test_metrics,      # 2020+ at calibrated threshold
            'positive_rate_test': round(float(y_heavy_all[is_test].mean()), 4),
        }
        clf.save(MODEL_DIR / f"{locality}_hazard.npz")

    # ---- regressors (target: NEXT-day rainfall mm), train < 2019 / test 2020+
    y_next_all = feats['rain_tomorrow'].to_numpy(dtype=np.float64)
    y_next_train = y_next_all[is_train]
    y_next_test = y_next_all[is_test]

    ridge = RidgeRainfall(lam=1.0).fit(X_all[is_train], y_next_train)
    pred_ridge = ridge.predict(X_all[is_test])
    summary['ridge'] = _metrics(y_next_test, pred_ridge)
    ridge.save(MODEL_DIR / f"{locality}_ridge.npz")

    seq_idx = [feat_cols.index(c) for c in SEQ_FEATURES]
    Xs, ys = make_sequences(X_all[:, seq_idx], LSTM_WINDOW)
    y_dates = dates.iloc[LSTM_WINDOW:].to_numpy()
    s_train = y_dates < pd.Timestamp(VAL_START)
    s_test = y_dates >= pd.Timestamp(EVAL_CUTOFF)

    if s_train.sum() > 200 and s_test.sum() > 100:
        lstm = LSTMRainfall(hidden=12, seed=7)
        if verbose:
            print(f"  [{locality}] training LSTM "
                  f"({s_train.sum()} windows)...")
        lstm.fit(Xs[s_train], ys[s_train], epochs=epochs, verbose=verbose)
        pred_lstm = lstm.predict(Xs[s_test])
        summary['lstm'] = _metrics(ys[s_test], pred_lstm)
        lstm.save(MODEL_DIR / f"{locality}_lstm.npz")

    logger.info(f"{locality}: hazard AUC(test) "
                f"{summary.get('hazard', {}).get('auc_test', 'n/a')} | "
                f"test recall {summary.get('hazard', {}).get('test_metrics', {}).get('recall', 'n/a')} "
                f"@ thr {summary.get('hazard', {}).get('threshold', 'n/a')} | "
                f"ridge MAE {summary.get('ridge', {}).get('mae_mm', 'n/a')} mm | "
                f"LSTM MAE {summary.get('lstm', {}).get('mae_mm', 'n/a')} mm")
    return summary


def train_all(epochs: int = 45, verbose: bool = False,
              names: list = None) -> list:
    """Train the whole suite (or given localities) and write eval.json."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    names = names or list(LOCALITIES.keys())
    results = [train_locality(n, epochs=epochs, verbose=verbose) for n in names]
    results = [r for r in results if r]
    with open(MODEL_DIR / "eval.json", "w") as f:
        json.dump({
            'trained_at': datetime.now().isoformat(),
            'train_window': '2012-01-01 .. 2018-12-31',
            'val_window': '2019 (hazard threshold calibration)',
            'test_window': '2020-01-01 .. yesterday',
            'data_note': 'ERA5 archive (Open-Meteo) + measured live-history '
                         'store tail; see docs/METHODOLOGY.md',
            'target_recall': TARGET_RECALL,
            'cost_ratio': COST_RATIO,
            'models': results,
        }, f, indent=2, default=str)
    return results


def main():
    parser = argparse.ArgumentParser(description="Train Idukki ML model suite")
    parser.add_argument("--locality", default=None, help="train a single locality")
    parser.add_argument("--epochs", type=int, default=45)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--fetch-only", action="store_true",
                        help="download/cache historical data and exit")
    args = parser.parse_args()

    if args.fetch_only:
        names = [args.locality] if args.locality else list(LOCALITIES.keys())
        for n in names:
            loc = LOCALITIES[n]
            frame = load_daily_rainfall_observed(loc['lat'], loc['lon'])
            if frame.empty:
                logger.warning(f"{n}: no historical data fetched")
            else:
                logger.info(f"{n}: {len(frame)} days "
                            f"({frame['date'].min().date()} - {frame['date'].max().date()})")
        return

    results = train_all(epochs=args.epochs, verbose=args.verbose,
                        names=[args.locality] if args.locality else None)
    print(f"\nSaved models + evaluation to {MODEL_DIR} "
          f"({len(results)} localities)")


if __name__ == '__main__':
    main()
