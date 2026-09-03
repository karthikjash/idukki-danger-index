"""Background scheduler.

A daemon thread started with the API server evaluates subscriptions every 60 s:

  * danger plan — recompute the district snapshot every 10 min (only while a
    danger subscription exists) and alert when a watched panchayat crosses the
    chosen threshold, at most once per area per day.
  * daily plan   — 07:00 IST briefing: today's reading + tomorrow's forecast.
  * weekly plan  — Monday 08:00 IST outlook: the week's worst day per area.

Delivery state lives in the subscription record (store.update_state), so a
restart never double-sends. If a send fails, the state is NOT advanced and a
retry is attempted on the next tick (rate-limited to every 15 min per sub).
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import sms as _sms
from . import store as _store
from . import messages as _messages

logger = logging.getLogger(__name__)

IST = ZoneInfo('Asia/Kolkata')

_TICK_SECONDS = 60
_SNAPSHOT_REFRESH = 600       # recompute district danger snapshot
_RETRY_COOLDOWN = 900         # per-sub retry backoff after a failed send

_TIER_RANK = {'Low': 1, 'Moderate': 2, 'High': 3, 'Extreme': 4}


def _now() -> datetime:
    return datetime.now(IST)


def _today() -> str:
    return _now().date().isoformat()


def _monday_of(d: datetime) -> str:
    return (d - timedelta(days=d.weekday())).date().isoformat()


# --------------------------------------------------------------------------
# district snapshot (current danger index per locality)
# --------------------------------------------------------------------------
def _compute_snapshot() -> dict:
    try:
        from index.calculator import compute_all_locality_indices
        indices, _ = compute_all_locality_indices()
        return indices or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"notify: district snapshot failed: {exc}")
        return {}


def _snapshot_age_hint() -> None:
    pass  # placeholder kept minimal: refresh logic lives in the loop


# --------------------------------------------------------------------------
# forecast / outlook fetches (one locality at a time, network-light)
# --------------------------------------------------------------------------
def _forecast_day1(locality: str, lat: float, lon: float):
    """Tomorrow's rain (mm) from the live provider; None on failure."""
    try:
        from data.fetcher import IMDDataFetcher
        df = IMDDataFetcher().get_rainfall_forecast(lat, lon, 1)
        if df is not None and len(df):
            v = df.iloc[0].get('rainfall_mm')
            return None if v is None else float(v)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"notify: day-1 forecast for {locality}: {exc}")
    return None


def _weekly_outlook(locality: str, lat: float, lon: float, index: dict):
    """Worst-day summary from the shared 7-day danger outlook engine."""
    try:
        from data.fetcher import IMDDataFetcher
        from index.calculator import compute_forecast_outlook
        ctx = (index or {}).get('weather') or {}
        df = IMDDataFetcher().get_rainfall_forecast(lat, lon, 7)
        if df is None or not len(df):
            return None
        outlook = compute_forecast_outlook(locality, df, days=7,
                                           context_weather=ctx)
        return (outlook or {}).get('worst_day')
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"notify: weekly outlook for {locality}: {exc}")
    return None


def _localities_meta(snapshot: dict) -> dict:
    """locality -> {'lat': .., 'lon': .., 'index': ..} for message builders."""
    try:
        from data.fetcher import LOCALITIES
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for name in LOCALITIES:
        info = LOCALITIES.get(name) or {}
        out[name] = {
            'lat': info.get('lat'), 'lon': info.get('lon'),
            'index': snapshot.get(name) or {},
        }
    return out


# --------------------------------------------------------------------------
# per-subscription evaluation
# --------------------------------------------------------------------------
def _evaluate(sub: dict, meta: dict) -> None:
    plans = set(sub.get('plans', []))
    if not plans:
        return
    lang = sub.get('lang') or 'en'
    phone = sub.get('phone')
    now = _now()
    today = _today()

    def get_state():
        rec = _store.get(phone)
        return rec.get('state') or {} if rec else {}

    def set_state(state):
        _store.update_state(phone, lambda _old: state)

    # ----- danger alerts -----
    if 'danger' in plans:
        threshold = _TIER_RANK.get(sub.get('threshold') or 'High', 3)
        st = get_state()
        sent = dict(st.get('danger_sent') or {})
        for loc in sub.get('localities', []):
            if sent.get(loc) == today:
                continue
            meta_loc = meta.get(loc)
            if not meta_loc:
                continue
            idx = meta_loc.get('index') or {}
            tier = idx.get('tier')
            if tier and _TIER_RANK.get(tier, 0) >= threshold:
                texts = _messages.compose(sub, 'danger',
                                          {'locality': loc, 'index': idx})
                sent_ok = all(_deliver(sub, text)['ok'] for text in texts)
                if sent_ok:
                    sent[loc] = today
                    set_state({**st, 'danger_sent': sent})
                    logger.info(f"notify: danger alert -> {phone} for {loc} ({tier})")

    # ----- daily briefing (07:00 IST) -----
    if 'daily' in plans:
        st = get_state()
        if (st.get('last_daily') != today
                and (now.hour, now.minute) >= (7, 0)
                and _cooldown_ok(st, 'daily')):
            rows = []
            failed = False
            for loc in sub.get('localities', []):
                meta_loc = meta.get(loc)
                if not meta_loc:
                    continue
                idx = meta_loc.get('index') or {}
                tmrw = _forecast_day1(loc, meta_loc.get('lat'),
                                      meta_loc.get('lon'))
                rows.append({
                    'locality': loc,
                    'tier': idx.get('tier') or '—',
                    'rain_mm': (idx.get('weather') or {}).get('rainfall_mm'),
                    'tomorrow_mm': tmrw,
                })
                if tmrw is None and not (idx.get('weather') or {}).get('rainfall_mm'):
                    failed = True
            if not failed:
                texts = _messages.compose(
                    sub, 'daily', {'date': today, 'rows': rows})
                ok = all(_deliver(sub, t)['ok'] for t in texts)
                if ok:
                    set_state({**st, 'last_daily': today,
                               'daily_retry_after': None})
                    logger.info(f"notify: daily briefing -> {phone}")

    # ----- weekly outlook (Monday 08:00 IST) -----
    if 'weekly' in plans:
        st = get_state()
        monday = _monday_of(now)
        if (st.get('last_weekly') != monday
                and now.weekday() == 0
                and (now.hour, now.minute) >= (8, 0)
                and _cooldown_ok(st, 'weekly')):
            rows = []
            failed = False
            for loc in sub.get('localities', []):
                meta_loc = meta.get(loc)
                if not meta_loc:
                    continue
                worst = _weekly_outlook(loc, meta_loc.get('lat'),
                                        meta_loc.get('lon'),
                                        meta_loc.get('index') or {})
                rows.append({'locality': loc, 'worst': worst})
                if worst is None:
                    failed = True
            if not failed:
                texts = _messages.compose(
                    sub, 'weekly', {'week': monday, 'rows': rows})
                ok = all(_deliver(sub, t)['ok'] for t in texts)
                if ok:
                    set_state({**st, 'last_weekly': monday,
                               'weekly_retry_after': None})
                    logger.info(f"notify: weekly outlook -> {phone}")


def _cooldown_ok(st: dict, kind: str) -> bool:
    key = f'{kind}_retry_after'
    retry = st.get(key)
    if not retry:
        return True
    try:
        return datetime.fromisoformat(retry) <= _now()
    except ValueError:
        return True


def _deliver(sub: dict, text: str) -> dict:
    res = _sms.send_sms(sub.get('phone'), text, sub.get('lang') or 'en',
                        _reason='scheduled')
    if not res['ok'] and not res['demo']:
        logger.warning(f"notify: SMS delivery failed: {res.get('error')}")
    return res


# --------------------------------------------------------------------------
# main loop
# --------------------------------------------------------------------------
def run() -> None:
    snapshot: dict = {}
    last_snapshot = 0.0
    while True:
        started = time.time()
        try:
            subs = _store.all()
            if subs:
                need_snapshot = any('danger' in (s.get('plans') or [])
                                    for s in subs)
                if need_snapshot and started - last_snapshot >= _SNAPSHOT_REFRESH:
                    snapshot = _compute_snapshot()
                    last_snapshot = started
                meta = _localities_meta(snapshot)
                for sub in subs:
                    try:
                        _evaluate(sub, meta)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"notify: subscription eval failed "
                                       f"({sub.get('phone')}): {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"notify: scheduler tick failed: {exc}")
        elapsed = time.time() - started
        time.sleep(max(5, _TICK_SECONDS - elapsed))


def start() -> None:
    threading.Thread(target=run, daemon=True,
                     name='notify-scheduler').start()
    logger.info("SMS notification scheduler started (tick 60 s)")
