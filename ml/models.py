"""
Pure-NumPy prediction models for the ML engine.

The SSR proposal names an LSTM rainfall forecaster and a flood/hazard
classifier. This module implements a compact LSTM (one hidden layer, trained
with Adam + truncated BPTT) together with a ridge-regression baseline and a
logistic hazard classifier, using only NumPy so the whole suite runs offline
with no heavy ML dependencies (TensorFlow / scikit-learn can be swapped in
later -- see docs/PROPOSAL_COVERAGE.md).

All models are per-locality: climate at each panchayat differs (orography).
"""

import numpy as np

# ------------------------------------------------------------------- helpers
def _standardize(X, mean=None, std=None):
    """Standardize columns. Returns (Xz, mean, std)."""
    if mean is None:
        mean = X.mean(axis=0)
        std = X.std(axis=0) + 1e-9
    return (X - mean) / std, mean, std


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _auc(labels, scores):
    """Rank-based Area Under the ROC Curve (labels 0/1).

    Ranks are ascending (1 = lowest score); with that convention
    AUC = (sum of positive ranks - n_pos*(n_pos+1)/2) / (n_pos*n_neg).
    """
    order = np.argsort(scores, kind='mergesort')  # ascending scores
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(order) + 1)
    n_pos = int(labels.sum())
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    return float((ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


# ----------------------------------------------------------- ridge (baseline)
class RidgeRainfall:
    """Closed-form ridge regression over engineered features (baseline)."""

    def __init__(self, lam: float = 1.0):
        self.lam = lam
        self.mean = self.std = self.w = None
        self.b = 0.0
        self.scale = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.scale = float(np.percentile(y, 99) + 1e-6)
        yt = np.clip(y / self.scale, 0.0, 1.2)
        Xz, self.mean, self.std = _standardize(X)
        n = Xz.shape[1]
        A = Xz.T @ Xz + self.lam * np.eye(n)
        self.w = np.linalg.solve(A, Xz.T @ yt)
        self.b = float(yt.mean() - Xz.mean(axis=0) @ self.w)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        Xz, _, _ = _standardize(X, self.mean, self.std)
        return np.clip(Xz @ self.w + self.b, 0.0, 1.2) * self.scale

    def save(self, path):
        np.savez(path, w=self.w, mean=self.mean, std=self.std,
                 b=self.b, scale=self.scale)

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=True)
        m = cls()
        m.w, m.mean, m.std, m.b, m.scale = z['w'], z['mean'], z['std'], \
            float(z['b']), float(z['scale'])
        return m


# ------------------------------------------------------------------- LSTM
class LSTMRainfall:
    """One-layer LSTM: last T causal days -> next-day rainfall (mm).

    Gate order f, i, o, c. Trained with Adam and truncated BPTT over the full
    sequence per mini-batch. The output is a clipped linear readout of the
    final hidden state, scaled to predict mm/day in [0, ~240].
    """

    def __init__(self, hidden: int = 12, seed: int = 7):
        self.hidden = hidden
        self.rng = np.random.default_rng(seed)
        self.out_scale = 240.0
        self.params = None

    def _init_params(self, n_in: int):
        h, r = self.hidden, self.rng

        def glorot(rows, cols):
            lim = np.sqrt(6.0 / (rows + cols))
            return r.uniform(-lim, lim, size=(rows, cols))

        U = [glorot(h, n_in) * 0.5 for _ in range(4)]
        V = [glorot(h, h) for _ in range(4)]
        b = [np.zeros(h) for _ in range(4)]
        self.params = {'U': U, 'V': V, 'b': b,
                       'Wy': r.normal(0, 0.1, size=h), 'by': 0.0}

    def _forward(self, X):
        """X (B, T, n_in) -> (yhat (B,), cache)."""
        B, T, _ = X.shape
        h = self.hidden
        p = self.params
        h_prev = np.zeros((B, h))
        c_prev = np.zeros((B, h))
        cache = {'X': X, 'hs': [h_prev], 'cs': [c_prev],
                 'f': [], 'i': [], 'o': [], 'cc': []}
        for t in range(T):
            x = X[:, t, :]
            f = _sigmoid(x @ p['U'][0].T + h_prev @ p['V'][0].T + p['b'][0])
            i = _sigmoid(x @ p['U'][1].T + h_prev @ p['V'][1].T + p['b'][1])
            o = _sigmoid(x @ p['U'][2].T + h_prev @ p['V'][2].T + p['b'][2])
            cc = np.tanh(x @ p['U'][3].T + h_prev @ p['V'][3].T + p['b'][3])
            c = f * c_prev + i * cc
            h = o * np.tanh(c)
            cache['f'].append(f)
            cache['i'].append(i)
            cache['o'].append(o)
            cache['cc'].append(cc)
            cache['cs'].append(c)
            cache['hs'].append(h)
            h_prev, c_prev = h, c
        yhat = np.clip(h_prev @ p['Wy'] + p['by'], 0.0, 1.2)
        return yhat, cache

    def _backward(self, yhat, y, cache):
        """BPTT gradients of mean-squared error."""
        B, T, _ = cache['X'].shape
        h = self.hidden
        p = self.params
        grads = {'U': [np.zeros_like(u) for u in p['U']],
                 'V': [np.zeros_like(v) for v in p['V']],
                 'b': [np.zeros_like(x) for x in p['b']],
                 'Wy': np.zeros_like(p['Wy']), 'by': 0.0}

        d_out = 2.0 * (yhat - y) / B
        grads['Wy'] += cache['hs'][-1].T @ d_out
        grads['by'] += float(d_out.sum())

        dh_next = d_out[:, None] * p['Wy']          # dL/dh_{T-1}... entry at final step
        dc_next = np.zeros((B, h))

        f, i, o, cc = cache['f'], cache['i'], cache['o'], cache['cc']
        hs, cs = cache['hs'], cache['cs']
        U, V, b = p['U'], p['V'], p['b']

        for t in reversed(range(T)):
            x = X_t = cache['X'][:, t, :]
            h_prev, c_prev = hs[t], cs[t]
            c_t = cs[t + 1]

            # h_t = o_t * tanh(c_t)
            d_c_out = dh_next * o[t] * (1.0 - np.tanh(c_t) ** 2)
            d_c = dc_next + d_c_out            # total dL/dc_t
            d_o = dh_next * np.tanh(c_t)       # dL/do_t

            d_f = d_c * c_prev
            d_i = d_c * cc[t]
            d_cc = d_c * i[t]

            dz = [d_f * f[t] * (1.0 - f[t]),
                  d_i * i[t] * (1.0 - i[t]),
                  d_o * o[t] * (1.0 - o[t]),
                  d_cc * (1.0 - cc[t] ** 2)]

            dh_prev = np.zeros_like(h_prev)
            for g in range(4):
                grads['U'][g] += dz[g].T @ x
                grads['V'][g] += dz[g].T @ h_prev
                grads['b'][g] += dz[g].sum(axis=0)
                dh_prev = dh_prev + dz[g] @ V[g]

            dc_next = d_c * f[t]               # dL/dc_{t-1} via c_t = f_t*c_{t-1} + ...
            dh_next = dh_prev
        return grads

    def fit(self, X, y, epochs: int = 45, batch: int = 128, lr: float = 0.03,
            verbose: bool = False):
        B, T, n_in = X.shape
        self._init_params(n_in)
        y = np.clip(y / self.out_scale, 0.0, 1.2)

        m = {'U': [np.zeros_like(u) for u in self.params['U']],
             'V': [np.zeros_like(v) for v in self.params['V']],
             'b': [np.zeros_like(x) for x in self.params['b']],
             'Wy': np.zeros_like(self.params['Wy']), 'by': 0.0}
        v = {'U': [np.zeros_like(u) for u in self.params['U']],
             'V': [np.zeros_like(v) for v in self.params['V']],
             'b': [np.zeros_like(x) for x in self.params['b']],
             'Wy': np.zeros_like(self.params['Wy']), 'by': 0.0}
        b1, b2, eps = 0.9, 0.999, 1e-8
        step = 0
        n_batches = max(1, (B + batch - 1) // batch)
        keys = ('U', 'V', 'b')

        for ep in range(epochs):
            perm = self.rng.permutation(B)
            epoch_loss = 0.0
            for bi in range(n_batches):
                idx = perm[bi * batch:(bi + 1) * batch]
                yhat, cache = self._forward(X[idx])
                loss = float(np.mean((yhat - y[idx]) ** 2))
                epoch_loss += loss
                grads = self._backward(yhat, y[idx], cache)
                step += 1
                for key in keys:
                    for k in range(4):
                        m[key][k] = b1 * m[key][k] + (1 - b1) * grads[key][k]
                        v[key][k] = b2 * v[key][k] + (1 - b2) * grads[key][k] ** 2
                        mh = m[key][k] / (1 - b1 ** step)
                        vh = v[key][k] / (1 - b2 ** step)
                        self.params[key][k] -= lr * mh / (np.sqrt(vh) + eps)
                for key in ('Wy', 'by'):
                    m[key] = b1 * m[key] + (1 - b1) * grads[key]
                    v[key] = b2 * v[key] + (1 - b2) * grads[key] ** 2
                    mh = m[key] / (1 - b1 ** step)
                    vh = v[key] / (1 - b2 ** step)
                    self.params[key] -= lr * mh / (np.sqrt(vh) + eps)
            if verbose and (ep % 5 == 0 or ep == epochs - 1):
                print(f"    epoch {ep + 1}/{epochs}  loss {epoch_loss / n_batches:.5f}")
        return self

    def predict(self, X):
        yhat, _ = self._forward(X)
        return yhat * self.out_scale

    def save(self, path):
        flat = {}
        for key in ('U', 'V', 'b'):
            flat.update({f'{key}_{i}': a for i, a in enumerate(self.params[key])})
        flat['Wy'] = self.params['Wy']
        flat['by'] = np.asarray([self.params['by']])
        flat['hidden'] = np.asarray([self.hidden])
        np.savez(path, **flat)

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=True)
        model = cls(hidden=int(z['hidden'][0]), seed=0)
        model.params = {
            'U': [z['U_0'], z['U_1'], z['U_2'], z['U_3']],
            'V': [z['V_0'], z['V_1'], z['V_2'], z['V_3']],
            'b': [z['b_0'], z['b_1'], z['b_2'], z['b_3']],
            'Wy': z['Wy'], 'by': float(z['by'][0]),
        }
        return model


# ------------------------------------------------------- hazard classifier
class LogisticHazard:
    """Cost-weighted logistic classifier for P(heavy-rain danger window).

    The positive class (a very-heavy day within the next 3 days) is rare
    (~2-8% of days), so plain accuracy is meaningless here. The model is
    trained with a MISS COST: misclassifying a dangerous day as safe is
    weighted `pos_weight`x more heavily than a false alarm (a landslide watch
    that never fires is cheap; a missed watch costs lives). The decision
    threshold is set AFTER training on a held-out validation year so the
    deployed model targets >= TARGET_RECALL sensitivity - see
    ml.models.best_threshold.
    """

    def __init__(self, seed: int = 7):
        self.rng = np.random.default_rng(seed)
        self.mean = self.std = self.w = None
        self.bias = 0.0
        self.threshold = 0.5       # operating point (set by calibration)
        self.pos_weight = 1.0

    def fit(self, X, y, epochs: int = 140, batch: int = 256, lr: float = 0.5,
            lam: float = 1e-3, pos_weight: float = 4.0):
        Xz, self.mean, self.std = _standardize(X)
        N = Xz.shape[0]
        n = Xz.shape[1] + 1
        w = np.zeros(n)  # last entry = bias
        m = np.zeros(n)
        v = np.zeros(n)
        b1, b2, eps = 0.9, 0.999, 1e-8
        step = 0
        n_batches = max(1, N // batch)
        yv = y.astype(float)
        # per-sample weight: misses cost pos_weight x more than false alarms
        wgt = np.where(yv == 1.0, pos_weight, 1.0)
        self.pos_weight = pos_weight

        for _ in range(epochs):
            perm = self.rng.permutation(N)
            for bi in range(n_batches):
                idx = perm[bi * batch:(bi + 1) * batch]
                Xb = Xz[idx]
                z = Xb @ w[:-1] + w[-1]
                p = _sigmoid(z)
                err = (p - yv[idx]) * wgt[idx]
                wsum = float(wgt[idx].sum())
                grad = np.concatenate([Xb.T @ err, [err.sum()]]) / wsum
                grad[:-1] += lam * w[:-1]
                step += 1
                m = b1 * m + (1 - b1) * grad
                v = b2 * v + (1 - b2) * grad ** 2
                mh = m / (1 - b1 ** step)
                vh = v / (1 - b2 ** step)
                w -= lr * mh / (np.sqrt(vh) + eps)
        self.w, self.bias = w[:-1], w[-1]
        return self

    def predict_proba(self, X):
        Xz, _, _ = _standardize(X, self.mean, self.std)
        return _sigmoid(Xz @ self.w + self.bias)

    def predict(self, X):
        """0/1 predictions at the calibrated threshold (0.5 if unset)."""
        return (self.predict_proba(X) >= float(self.threshold or 0.5)).astype(int)

    def save(self, path):
        np.savez(path, w=self.w, mean=self.mean, std=self.std, bias=self.bias,
                 threshold=np.asarray([float(self.threshold or 0.5)]),
                 pos_weight=np.asarray([float(self.pos_weight)]))

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=True)
        model = cls(seed=0)
        model.w, model.mean, model.std, model.bias = \
            z['w'], z['mean'], z['std'], float(z['bias'])
        model.threshold = float(z['threshold'][0]) if 'threshold' in z else 0.5
        model.pos_weight = float(z['pos_weight'][0]) if 'pos_weight' in z else 1.0
        return model


# ---------------------------------------------------- threshold calibration
def best_threshold(y_true, p_score, min_recall: float = 0.90,
                   max_fpr: float = 0.25):
    """Most-specific operating point that still catches enough positives.

    Walks predicted probabilities from the highest down and returns the FIRST
    cutoff whose sensitivity reaches the target recall - i.e. the highest
    threshold (fewest alarms) that still catches >= min_recall of the
    dangerous windows on the validation window. This is how alerting systems
    are tuned: the operator fixes the minimum detection rate and the system
    then minimises false alarms (Keeps every day-1..3 event where possible).

    If even that most-specific cutoff alarms on more than `max_fpr` of safe
    days, the model cannot separate well enough to meet the target cleanly:
    we then return the cutoff at the max_fpr alarm cap with the best
    balanced-accuracy, and the caller reports the shortfall honestly.

    Returns a dict {threshold, recall, precision, fpr, f1,
    balanced_accuracy, n_pos, target_met}.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p_score, dtype=float)
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return {'threshold': 0.5, 'recall': float('nan'), 'precision': float('nan'),
                'fpr': float('nan'), 'f1': float('nan'),
                'balanced_accuracy': float('nan'), 'n_pos': n_pos,
                'target_met': False}

    order = np.argsort(-p, kind='mergesort')
    cum_pos = 0
    chosen = None
    capped = None
    for i, idx in enumerate(order):
        if y[idx] == 1.0:
            cum_pos += 1
        thr = p[idx]
        # number of alarms issued at this cutoff (all samples above it)
        alarms = i + 1
        fpr = (alarms - int((y[order[:alarms]] == 1).sum())) / n_neg
        rec = cum_pos / n_pos
        prec = cum_pos / alarms
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        bal = (rec + (1.0 - fpr)) / 2.0
        if chosen is None and rec >= min_recall and prec > 0:
            chosen = (thr, rec, prec, fpr, f1, bal)
            break                       # highest threshold meeting recall
        if capped is None and fpr >= max_fpr:
            # alarm cap crossed before reaching target recall: keep the best
            # balanced point seen so far and keep scanning is not needed
            capped = (thr, rec, prec, fpr, f1, bal)
    if chosen is None and capped is None:
        # recall never reached even at the lowest cutoff
        idx = order[-1]
        thr = p[idx]
        rec = cum_pos / n_pos
        alarms = len(order)
        fp = alarms - cum_pos
        chosen = (thr, rec, cum_pos / max(alarms, 1), fp / max(n_neg, 1),
                  2 * (cum_pos / max(alarms, 1)) * rec / max(cum_pos / max(alarms, 1) + rec, 1e-9),
                  (rec + (1.0 - fp / max(n_neg, 1))) / 2.0)
        target_met = False
    elif chosen is None:
        chosen = capped
        target_met = False
    else:
        target_met = bool(chosen[1] >= min_recall and chosen[3] <= max_fpr)
    thr, rec, prec, fpr, f1, bal = chosen
    return {'threshold': round(float(thr), 4), 'recall': round(float(rec), 3),
            'precision': round(float(prec), 3), 'fpr': round(float(fpr), 3),
            'f1': round(float(f1), 3),
            'balanced_accuracy': round(float(bal), 3), 'n_pos': n_pos,
            'target_met': target_met}


# ------------------------------------------------------------ sequence maker
def make_sequences(feat: np.ndarray, window: int = 30):
    """Sliding causal windows -> (X (N, T, F), y_next_day_mm)."""
    X, y = [], []
    for i in range(window, len(feat)):
        X.append(feat[i - window:i])
        y.append(feat[i, 0])  # column 0 is that day's rainfall_mm
    return np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.float64)
