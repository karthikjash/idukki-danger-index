"""Subscription store — one JSON file, thread-safe, atomic writes.

File: data/subscriptions.json   (git-ignored: contains personal phone numbers)

A subscription record:
  {
    "phone": "+919876543210",        # E.164 key
    "name": "",                      # optional display name
    "lang": "en" | "ml",             # message language
    "localities": ["Kumily", ...],
    "threshold": "High" | "Extreme", # danger-alert level
    "plans": ["danger", "daily", "weekly"],   # what the user opted into
    "created_at": ..., "updated_at": ...,
    "state": {
        "danger_sent": {"Kumily": "2026-09-03"},  # one alert per area per day
        "last_daily": "2026-09-03",               # day the 07:00 brief went out
        "last_weekly": "2026-08-31",              # Monday the outlook went out
    }
  }
"""
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
STORE_FILE = DATA_DIR / 'subscriptions.json'

VALID_PLANS = ('danger', 'daily', 'weekly')
VALID_THRESHOLDS = ('High', 'Extreme')
VALID_LANGS = ('en', 'ml')

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def normalize_phone(raw) -> str:
    """Accept '9876543210', '+91 98765 43210', '09876543210' -> '+91...'."""
    digits = re.sub(r'\D', '', str(raw or ''))
    if digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    elif digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and re.match(r'[6-9]\d{9}$', digits):
        return '+91' + digits
    raise ValueError('Enter a valid 10-digit Indian mobile number '
                     '(e.g. 98765 43210).')


def validate_payload(payload: dict, valid_localities, normalize: bool = True) -> dict:
    """Validate + clean an incoming subscription payload.

    Returns the cleaned record body (without state/timestamps). Raises
    ValueError with a user-facing message on any problem.
    """
    phone = normalize_phone(payload.get('phone')) if normalize else \
        str(payload.get('phone') or '').strip()
    lang = payload.get('lang') if payload.get('lang') in VALID_LANGS else 'en'
    name = str(payload.get('name') or '').strip()[:60]
    name = name if name not in ('', '+') else ''

    localities = []
    for raw in (payload.get('localities') or []):
        loc = str(raw).strip()
        if loc in valid_localities and loc not in localities:
            localities.append(loc)
    if not localities:
        raise ValueError('Choose at least one locality to watch.')

    plans = []
    for raw in (payload.get('plans') or []):
        plan = str(raw).strip()
        if plan in VALID_PLANS and plan not in plans:
            plans.append(plan)
    if not plans:
        raise ValueError('Choose at least one type of alert '
                         '(danger, daily or weekly).')

    threshold = payload.get('threshold') or 'High'
    if threshold not in VALID_THRESHOLDS:
        threshold = 'High'

    return {
        'phone': phone, 'name': name, 'lang': lang,
        'localities': localities, 'threshold': threshold, 'plans': plans,
    }


# --------------------------------------------------------------------------
# low-level persistence
# --------------------------------------------------------------------------
def _read() -> dict:
    try:
        with open(STORE_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE_FILE)


def _subs() -> dict:
    return _read().setdefault('subscriptions', {})


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def upsert(body: dict) -> dict:
    """Create or fully replace a subscription (keeps delivery state)."""
    with _lock:
        subs = _subs()
        existing = subs.get(body['phone'], {})
        state = existing.get('state', {}) if isinstance(existing, dict) else {}
        now = _now_iso()
        record = dict(body)
        record['created_at'] = existing.get('created_at', now) \
            if isinstance(existing, dict) else now
        record['updated_at'] = now
        record['state'] = {
            'danger_sent': state.get('danger_sent', {}),
            'last_daily': state.get('last_daily'),
            'last_weekly': state.get('last_weekly'),
        }
        subs[body['phone']] = record
        _write({'subscriptions': subs})
        return record


def all() -> list:
    with _lock:
        return list(_subs().values())


def get(phone: str):
    try:
        phone = normalize_phone(phone)
    except ValueError:
        return None
    with _lock:
        rec = _subs().get(phone)
        return rec.copy() if rec else None


def delete(phone: str) -> bool:
    try:
        phone = normalize_phone(phone)
    except ValueError:
        return False
    with _lock:
        subs = _subs()
        existed = phone in subs
        if existed:
            del subs[phone]
            _write({'subscriptions': subs})
        return existed


def update_state(phone: str, fn) -> None:
    """Apply fn(state) -> new state for one subscription (thread-safe)."""
    with _lock:
        subs = _subs()
        rec = subs.get(phone)
        if not rec:
            return
        rec['state'] = fn(dict(rec.get('state') or {}))
        rec['updated_at'] = _now_iso()
        _write({'subscriptions': subs})
