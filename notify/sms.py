"""SMS delivery layer.

Three states, never guessed:
  * Twilio configured  (TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM)
  * Fast2SMS configured (FAST2SMS_API_KEY)  - Indian gateway, DLT route needed
                                               for transactional SMS in India
  * demo               - no key: every "send" is recorded to
                         data/notifications/outbox.jsonl and reported as demo,
                         so the whole feature is verifiable before any gateway
                         is connected.

Every attempt (demo or real) is appended to the outbox for audit.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')  # idempotent
except Exception:  # noqa: BLE001 - dotenv is optional
    pass

logger = logging.getLogger(__name__)

OUTBOX_DIR = Path(__file__).resolve().parent.parent / 'data' / 'notifications'
OUTBOX_FILE = OUTBOX_DIR / 'outbox.jsonl'

_lock = threading.RLock()


def _record(entry: dict) -> None:
    """Append one outbox entry (thread-safe, tolerant of missing dir)."""
    try:
        with _lock:
            OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
            with open(OUTBOX_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not write SMS outbox entry: {exc}")


def outbox(phone: str = None, limit: int = 15) -> list:
    """Most recent outbox entries (optionally for one phone), newest first."""
    rows = []
    try:
        with open(OUTBOX_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    if phone:
        rows = [r for r in rows if r.get('phone') == phone]
    return list(reversed(rows[-max(1, limit) * 3:]))[:max(1, limit)]


def provider_status() -> dict:
    """Which delivery path is live and whether it is real or demo."""
    tw = (os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN')
          and os.getenv('TWILIO_FROM'))
    fs = os.getenv('FAST2SMS_API_KEY')
    if tw:
        return {
            'provider': 'twilio',
            'demo': False,
            'note': 'Twilio gateway configured — alerts go out as real SMS.',
        }
    if fs:
        return {
            'provider': 'fast2sms',
            'demo': False,
            'note': 'Fast2SMS gateway configured — alerts go out as real SMS '
                    '(register a DLT sender/template for transactional SMS in India).',
        }
    return {
        'provider': 'demo',
        'demo': True,
        'note': 'No SMS gateway key configured — messages are recorded to the demo '
                'outbox and shown on this page instead of being sent. Add '
                'FAST2SMS_API_KEY (or Twilio keys) to .env to go live.',
    }


def _has_unicode(text: str) -> bool:
    return any(ord(ch) > 127 for ch in text)


def _send_twilio(phone: str, text: str) -> tuple:
    import requests
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    frm = os.getenv('TWILIO_FROM')
    resp = requests.post(
        f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
        data={'To': phone, 'From': frm, 'Body': text},
        auth=(sid, token), timeout=20,
    )
    if resp.status_code in (200, 201):
        return True, None
    return False, f"Twilio HTTP {resp.status_code}: {resp.text[:200]}"


def _send_fast2sms(phone: str, text: str) -> tuple:
    import requests
    key = os.getenv('FAST2SMS_API_KEY').strip()
    digits = phone.lstrip('+')
    resp = requests.get(
        'https://www.fast2sms.com/dev/bulkV2',
        params={
            'authorization': key,
            'route': 'q',
            'message': text,
            'language': 'unicode' if _has_unicode(text) else 'english',
            'flash': 0,
            'numbers': digits,
        }, timeout=20,
    )
    try:
        data = resp.json()
        ok = bool(data.get('return') is True or data.get('return') == 'true'
                  or data.get('code') == 1)
    except ValueError:
        ok = False
        data = {}
    if ok:
        return True, None
    return False, f"Fast2SMS error: {str(data)[:200]}"


def send_sms(phone: str, text: str, lang: str = 'en', _reason: str = '') -> dict:
    """Deliver one message. Always recorded; returns the full outcome.

    Never raises: a failure is reported in the result dict so callers can
    decide whether to retry later.
    """
    entry = {
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'phone': phone, 'lang': lang, 'text': text,
        'provider': 'demo', 'delivered': False, 'demo': True,
        'error': None, 'reason': _reason or '',
    }
    st = provider_status()
    entry['provider'] = st['provider']
    entry['demo'] = st['demo']
    try:
        if st['demo']:
            entry['delivered'] = True  # recorded to outbox, not sent
        elif st['provider'] == 'twilio':
            ok, err = _send_twilio(phone, text)
            entry['delivered'], entry['error'] = ok, err
        elif st['provider'] == 'fast2sms':
            ok, err = _send_fast2sms(phone, text)
            entry['delivered'], entry['error'] = ok, err
    except Exception as exc:  # noqa: BLE001
        entry['error'] = str(exc)[:300]
    _record(entry)
    return {
        'ok': entry['delivered'],
        'delivered': entry['delivered'],
        'provider': entry['provider'],
        'demo': entry['demo'],
        'preview': text,
        'error': entry['error'],
        'note': st['note'],
    }
