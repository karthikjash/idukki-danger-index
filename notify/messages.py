"""SMS text composers (English + മലയാളം).

Each composer returns a list of SMS texts (multi-locality messages are
chunked so nothing is silently truncated by a 160/70 character limit).
Numbers, dates and tier words come from the live index / outlook payloads.
"""

TIER_ML = {
    'Low': 'കുറഞ്ഞ അപകടം',
    'Moderate': 'ഇടത്തരം',
    'High': 'ഉയർന്ന അപകടം',
    'Extreme': 'അത്യധികം അപകടം',
}
TIER_EN = {'Low': 'Low', 'Moderate': 'Moderate', 'High': 'High', 'Extreme': 'Extreme'}

UNIT_MM = {'en': 'mm', 'ml': 'mm'}
# Malayalam (unicode) SMS segments are 70 chars; English GSM-7 is 160.
_LIMIT = {'en': 155, 'ml': 68}


def tier_word(lang: str, tier: str) -> str:
    return (TIER_ML if lang == 'ml' else TIER_EN).get(tier, tier or '—')


def _mm(v) -> str:
    if v is None:
        return '—'
    return f"{float(v):.1f}".rstrip('0').rstrip('.')


def _fmt_date(d, lang: str) -> str:
    """'2026-09-07' -> '07 Sep' (or Malayalam-flavoured Gregorian)."""
    try:
        from datetime import datetime
        dt = datetime.strptime(str(d)[:10], '%Y-%m-%d')
        if lang == 'ml':
            # Keep Gregorian numerals/days short and unambiguous.
            return dt.strftime('%d %b')
        return dt.strftime('%a %d %b')
    except Exception:  # noqa: BLE001
        return str(d)[:10]


def chunk(text: str, lang: str) -> list:
    """Split a long message on line boundaries to respect SMS limits."""
    limit = _LIMIT.get(lang, 150)
    if len(text) <= limit:
        return [text]
    out, cur = [], ''
    for line in text.split('\n'):
        if not line:
            continue
        if cur and len(cur) + 1 + len(line) > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def compose(sub: dict, kind: str, payload: dict) -> list:
    """Top-level entry: sub -> list of SMS texts for the given kind.

    kind: welcome | test | danger | daily | weekly
    """
    lang = sub.get('lang') or 'en'
    builder = _BUILDERS.get(kind)
    if not builder:
        return []
    return chunk(builder(sub, payload, lang), lang)


def _welcome(sub, payload, lang):
    demo = bool(payload.get('demo'))
    plans = [p for p in sub.get('plans', []) if p in ('danger', 'daily', 'weekly')]
    th = sub.get('threshold') or 'High'
    if lang == 'ml':
        area = ' | '.join(sub.get('localities', []))
        kinds = ' | '.join({
            'danger': 'അപകട അലേർട്ട്',
            'daily': 'പ്രതിദിന റിപ്പോർട്ട്',
            'weekly': 'ആഴ്ച പ്രവചനം',
        }.get(p, p) for p in plans)
        txt = (f"ഇടുക്കി അപകട സൂചിക — SMS അലേർട്ട് സജീവമായി ✅\n"
               f"മേഖല: {area}\nതരം: {kinds}")
        if 'danger' in plans:
            txt += f"\n{th}-ൽ കൂടുതൽ അപകടമുണ്ടെങ്കിൽ ഉടൻ അറിയിക്കും"
        if demo:
            txt += "\n(ഡെമോ മോഡ് — ഇത് അയച്ചതല്ല)"
        return txt
    area = ' | '.join(sub.get('localities', []))
    kinds = ' | '.join({
        'danger': 'danger alerts', 'daily': 'daily briefing',
        'weekly': 'weekly outlook',
    }.get(p, p) for p in plans)
    txt = (f"Idukki Danger Index — SMS alerts active ✓\n"
           f"Watching: {area}\nSending: {kinds}")
    if 'danger' in plans:
        txt += f"\nYou will be alerted the moment risk reaches {th} or above."
    if demo:
        txt += "\n(Demo mode — this was not actually sent.)"
    return txt


def _test(sub, payload, lang):
    live = not bool(payload.get('demo'))
    if lang == 'ml':
        txt = (f"ഇടുക്കി അപകട സൂചിക — ടെസ്റ്റ് SMS ✅\n"
               f"നിങ്ങളുടെ രജിസ്ട്രേഷൻ പ്രവർത്തിക്കുന്നു. "
               f"അപകട സാധ്യതയുള്ളപ്പോൾ ഇത്തരം മുന്നറിയിപ്പുകൾ ലഭിക്കും.\n"
               f"സഹായം: 1077 (KSDMA)")
        if not live:
            txt += "\n(ഡെമോ മോഡ് — ഇത് അയച്ചതല്ല.)"
        return txt
    txt = ("Idukki Danger Index — test SMS ✓\n"
           "Your registration is working. You will receive alerts like this "
           "when risk rises. Help: 1077 (KSDMA disaster line)")
    if not live:
        txt += "\n(Demo mode — this was not actually sent.)"
    return txt


def _danger(sub, payload, lang):
    idx = payload.get('index') or {}
    loc = payload.get('locality') or sub.get('localities', ['?'])[0]
    tier = idx.get('tier') or 'Moderate'
    score = idx.get('composite_score')
    rain = (idx.get('weather') or {}).get('rainfall_mm')
    desc = idx.get('description') or ''
    drivers = idx.get('drivers') or []
    # very-short per-message limit: one SMS per locality
    if lang == 'ml':
        txt = (f"⚠ അപകട മുന്നറിയിപ്പ് — {loc}, ഇടുക്കി\n"
               f"നില: {tier_word(lang, tier)}"
               + (f" (സ്കോർ {score:.2f})" if score is not None else '')
               + "\n" + desc)
        if rain is not None:
            txt += f"\nമഴ: {_mm(rain)} mm"
        if drivers:
            txt += "\nകാരണം: " + ' · '.join(str(d) for d in drivers[:2])
        txt += "\nസുരക്ഷിതരായിരിക്കുക · KSDMA 1077"
        return txt
    txt = (f"⚠ DANGER ALERT — {loc}, Idukki\n"
           f"Level: {tier}"
           + (f" (score {score:.2f})" if score is not None else '')
           + "\n" + desc)
    if rain is not None:
        txt += f"\nRain: {_mm(rain)} mm"
    if drivers:
        txt += "\nWhy: " + ' · '.join(str(d) for d in drivers[:2])
    txt += "\nStay safe · KSDMA 1077"
    return txt


def _daily(sub, payload, lang):
    today = payload.get('date') or ''
    rows = payload.get('rows') or []   # per-locality dicts
    if lang == 'ml':
        head = f"ഇടുക്കി · {_fmt_date(today, lang)} രാവിലെ റിപ്പോർട്ട്"
        lines = []
        for r in rows:
            line = f"• {r['locality']}: {tier_word(lang, r['tier'])}"
            if r.get('rain_mm') is not None:
                line += f" · {_mm(r['rain_mm'])} mm ഇന്ന്"
            if r.get('tomorrow_mm') is not None:
                line += f" · നാളെ {_mm(r['tomorrow_mm'])} mm"
            lines.append(line)
        foot = "\nകേരള ദുരന്ത ഹെൽപ്പ്ലൈൻ: 1077"
        return head + '\n' + '\n'.join(lines) + foot
    head = f"Idukki · {_fmt_date(today, lang)} morning briefing"
    lines = []
    for r in rows:
        line = f"• {r['locality']}: {tier_word(lang, r['tier'])}"
        if r.get('rain_mm') is not None:
            line += f" · {_mm(r['rain_mm'])} mm today"
        if r.get('tomorrow_mm') is not None:
            line += f" · tomorrow {_mm(r['tomorrow_mm'])} mm"
        lines.append(line)
    foot = "\nKerala disaster helpline: 1077"
    return head + '\n' + '\n'.join(lines) + foot


def _weekly(sub, payload, lang):
    week = payload.get('week') or ''
    rows = payload.get('rows') or []  # per-locality {locality, worst:{...}|None}
    if lang == 'ml':
        head = f"ഇടുക്കി · {_fmt_date(week, lang)} ആഴ്ച പ്രവചനം"
        lines = []
        for r in rows:
            w = r.get('worst')
            if not w:
                lines.append(f"• {r['locality']}: ഡാറ്റ ലഭ്യമല്ല")
                continue
            line = (f"• {r['locality']}: ഏറ്റവും അപകടം {_fmt_date(w['date'], lang)} — "
                    f"{tier_word(lang, w['tier'])} · {_mm(w.get('rainfall_mm'))} mm")
            lines.append(line)
        return head + '\n' + '\n'.join(lines) + \
            "\n1077 (KSDMA) · മുന്നറിയിപ്പുകൾ ശ്രദ്ധിക്കുക"
    head = f"Idukki · outlook for week of {_fmt_date(week, lang)}"
    lines = []
    for r in rows:
        w = r.get('worst')
        if not w:
            lines.append(f"• {r['locality']}: outlook unavailable")
            continue
        line = (f"• {r['locality']}: worst {_fmt_date(w['date'], lang)} — "
                f"{tier_word(lang, w['tier'])} · {_mm(w.get('rainfall_mm'))} mm")
        lines.append(line)
    return head + '\n' + '\n'.join(lines) + \
        "\nOfficial warnings always override this outlook · KSDMA 1077"


_BUILDERS = {
    'welcome': _welcome,
    'test': _test,
    'danger': _danger,
    'daily': _daily,
    'weekly': _weekly,
}
