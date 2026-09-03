/* ============================================================
   Idukki Danger Index — dashboard logic (vanilla JS, no build)
   ============================================================ */

'use strict';

/* ---------- tiny helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html !== undefined) node.innerHTML = html;
  return node;
};
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const num = (v, d = 1) => (v == null || isNaN(v)) ? '—' : Number(v).toFixed(d);
const fmtDay = (iso) => {
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
};

const TIER_ORDER = ['Extreme', 'High', 'Moderate', 'Low'];
// emoji intentionally empty: risk is conveyed by colour + label, not glyphs
const TIER_META = {
  Low:      { label: 'Low',      emoji: '', color: '#34d399' },
  Moderate: { label: 'Moderate', emoji: '', color: '#fbbf24' },
  High:     { label: 'High',     emoji: '', color: '#fb7185' },
  Extreme:  { label: 'Extreme',  emoji: '', color: '#f43f5e' },
};

const PROVIDER_LABEL = {
  openweathermap: 'OpenWeatherMap',
  'open-meteo': 'Open-Meteo',
  'open-meteo measured': 'Open-Meteo · measured',
  synthetic: 'modelled fallback',
};
const providerName = (p) => PROVIDER_LABEL[p] || p || 'modelled fallback';

/* ---------- weather glyph: only shown when it matches the current weather ---------- */
function weatherGlyph(w) {
  if (!w) return '';
  const r = Number(w.rainfall_mm) || 0;
  const c = Number(w.cloud_cover_pct) || 0;
  if (r >= 35.5) return '🌧️';
  if (r >= 7.5) return '🌦️';
  if (c >= 70) return '☁️';
  if (c >= 30) return '⛅';
  return '☀️';
}

/* ============================================================
   Language: English (default) ⇄ മലയാളം
   ============================================================
   The whole dashboard is translated by replacing known English phrases in
   the rendered DOM with their Malayalam equivalents (numbers, units and
   proper nouns are preserved). English strings come back automatically:
   choosing EN simply reloads the page, which re-renders from the original
   templates. Unknown / dynamic strings fall back to English rather than
   guessing — safety-critical text is never machine-translated.
   ============================================================ */
const I18N_KEY = 'idi-lang';
const I18N = [
  // --- chrome ---
  ['Hyperlocal monsoon watch · inner Idukki, Kerala', 'ഇടുക്കി ജില്ലയിലെ മഴക്കാല നിരീക്ഷണം'],
  ['Monsoon season · active', 'മഴക്കാലം · സജീവം'],
  ['Dry season · monsoon risk off-peak', 'വരണ്ട കാലം · മഴക്കാല അപകടം കുറവാണ്'],
  ['Live data', 'തത്സമയ ഡാറ്റ'],
  ['Live feed', 'തത്സമയ ഫീഡ്'],
  ['Modelled data', 'മോഡൽ ഡാറ്റ'],
  ['District status · now', 'ജില്ലാ നില · ഇപ്പോൾ'],
  ['district risk score', 'ജില്ലാ അപകട സ്കോർ'],
  ['District conditions are calm', 'ജില്ലയിലെ സ്ഥിതി ശാന്തമാണ്'],
  ['monitored panchayats are at Low risk. Normal activity is safe; stay alert during the monsoon.', 'നിരീക്ഷിക്കുന്ന പഞ്ചായത്തുകൾ കുറഞ്ഞ അപകടനിലയിലാണ്. സാധാരണ പ്രവർത്തനങ്ങൾ സുരക്ഷിതം; മഴക്കാലത്ത് ജാഗ്രത പാലിക്കുക.'],
  ['Elevated conditions in', 'ഉയർന്ന അപകടനിലയിലുള്ളത്'],
  ['Severe conditions in', 'ഗുരുതര അവസ്ഥയിലുള്ളത്'],
  ['of', 'എന്നിവയിൽ'],
  ['Follow the guidance for your area.', 'നിങ്ങളുടെ മേഖലയ്ക്കുള്ള നിർദേശങ്ങൾ പാലിക്കുക.'],
  ['monsoon', 'മഴക്കാലം'],
  ['Search panchayat, risk level, hazard…', 'പഞ്ചായത്ത്, അപകടനില, അപകടം തിരയുക…'],
  ['Most at risk now', 'ഇപ്പോൾ ഏറ്റവും അപകടസാധ്യത'],
  ['Worst day this week', 'ഈ ആഴ്ചയിലെ ഏറ്റവും അപകടകരമായ ദിനം'],
  ['Scanning all 7 areas…', '7 മേഖലകളും പരിശോധിക്കുന്നു…'],
  ['Most dangerous moment in the next 7 days:', 'അടുത്ത 7 ദിവസത്തെ ഏറ്റവും അപകടകരമായ നിമിഷം:'],
  ['Open details', 'വിശദാംശങ്ങൾ കാണുക'],
  ['Details', 'വിശദാംശങ്ങൾ'],
  ['Localities', 'പ്രദേശങ്ങൾ'],
  ['Danger map', 'അപകട ഭൂപടം'],
  ['Tap for guidance & outlook', 'മാർഗനിർദേശങ്ങൾക്കും പ്രവചനത്തിനും ടാപ്പ് ചെയ്യുക'],
  ['District conditions are calm — all 7 monitored panchayats are at Low risk. Normal activity is safe; stay alert during the monsoon.', 'ജില്ലയിലെ സ്ഥിതി ശാന്തമാണ് — 7 പഞ്ചായത്തുകളും കുറഞ്ഞ അപകടനിലയിലാണ്. സാധാരണ പ്രവർത്തനങ്ങൾ സുരക്ഷിതം; മഴക്കാലത്ത് ജാഗ്രത പാലിക്കുക.'],
  ['All', 'എല്ലാം'],
  ['Low', 'കുറഞ്ഞ അപകടം'],
  ['Moderate', 'ഇടത്തരം അപകടം'],
  ['High', 'ഉയർന്ന അപകടം'],
  ['Extreme', 'അത്യധിക അപകടം'],
  ['Tap a locality for plain-language guidance, the 7-day danger outlook (tier per day, days ahead) and nearby past incidents. Press', 'ഒരു പ്രദേശം തിരഞ്ഞെടുത്താൽ ലളിതമായ നിർദേശങ്ങൾ, 7 ദിവസത്തെ അപകട പ്രവചനം, സമീപ സംഭവങ്ങൾ എന്നിവ ലഭിക്കും.'],
  ['to search.', 'അമർത്തി തിരയാം.'],
  ['Loading localities…', 'ലോഡ് ചെയ്യുന്നു…'],
  ['Loading 7-day outlook…', '7 ദിവസത്തെ പ്രവചനം ലോഡ് ചെയ്യുന്നു…'],
  ['Loading incidents…', 'സംഭവങ്ങൾ ലോഡ് ചെയ്യുന്നു…'],
  ['Loading weather trends…', 'കാലാവസ്ഥ പ്രവണതകൾ ലോഡ് ചെയ്യുന്നു…'],
  ['Loading ward data…', 'വാർഡ് ഡാറ്റ ലോഡ് ചെയ്യുന്നു…'],
  ['Loading model outlook…', 'മോഡൽ പ്രവചനം ലോഡ് ചെയ്യുന്നു…'],
  ['No panchayats match your search/filter.', 'തിരയലുമായി പൊരുത്തപ്പെടുന്ന പഞ്ചായത്തുകളൊന്നുമില്ല.'],
  // --- weather labels ---
  ['Rain', 'മഴ'],
  ['Temp', 'താപനില'],
  ['Wind', 'കാറ്റ്'],
  ['Humidity', 'ഈർപ്പം'],
  ['Cloud', 'മേഘം'],
  ['Population', 'ജനസംഖ്യ'],
  ['Wards', 'വാർഡുകൾ'],
  ['Ward', 'വാർഡ്'],
  ['wards', 'വാർഡുകൾ'],
  ['ward', 'വാർഡ്'],
  ['people', 'ആളുകൾ'],
  ['incidents nearby', 'സമീപ സംഭവങ്ങൾ'],
  ['incident', 'സംഭവം'],
  ['Today', 'ഇന്ന്'],
  ['risk score', 'അപകട സ്കോർ'],
  ['pop', 'ജനസംഖ്യ'],
  ['chance of rain this day', 'ഈ ദിവസത്തെ മഴ സാധ്യത'],
  ['Watch', 'ശ്രദ്ധിക്കുക'],
  // --- drawer sections ---
  ['AI 24-hour outlook', 'AI 24-മണിക്കൂർ പ്രവചനം'],
  ['Seasonal outlook · lightning', 'സീസണൽ പ്രവചനം · മിന്നൽ'],
  ['Lightning risk today', 'ഇന്നത്തെ മിന്നൽ അപകടം'],
  ['ENSO phase (NOAA CPC)', 'ENSO ഘട്ടം (NOAA CPC)'],
  ['7-day danger outlook', '7 ദിവസത്തെ അപകട പ്രവചനം'],
  ['Rainfall trends · monsoon pattern', 'മഴ പ്രവണതകൾ · മഴക്കാല രീതി'],
  ['Ward-level exposure', 'വാർഡ് തല അപകടസാധ്യത'],
  ['micro-zones', 'മൈക്രോ സോണുകൾ'],
  ['Past incidents nearby (2004–2025)', 'സമീപകാല സംഭവങ്ങൾ (2004–2025)'],
  ['Why this level', 'എന്തുകൊണ്ട് ഈ നില'],
  ['What is driving the score', 'സ്കോറിനെ നിയന്ത്രിക്കുന്നത് എന്ത്'],
  ['What to do right now', 'ഇപ്പോൾ എന്തുചെയ്യണം'],
  ['What to do', 'ചെയ്യേണ്ടത്'],
  ['Avoid', 'ഒഴിവാക്കേണ്ടത്'],
  ['Environmental severity — weather', 'പാരിസ്ഥിതിക തീവ്രത — കാലാവസ്ഥ'],
  ['Structural risk — terrain, soil, history', 'ഘടനാപരമായ അപകടം — ഭൂപ്രദേശം, മണ്ണ്, ചരിത്രം'],
  ['Human threat — people & evacuation', 'മനുഷ്യ ഭീഷണി — ആളുകളും ഒഴിപ്പിക്കലും'],
  ['Download PDF report', 'PDF റിപ്പോർട്ട് ഡൗൺലോഡ് ചെയ്യുക'],
  ['Download DOCX report', 'DOCX റിപ്പോർട്ട് ഡൗൺലോഡ് ചെയ്യുക'],
  ['Observed by:', 'നിരീക്ഷണം:'],
  ['modelled fallback active', 'മോഡൽ ഫാൾബാക്ക് സജീവം'],
  // --- AI / model box ---
  ['Model alert:', 'മോഡൽ അലേർട്ട്:'],
  ['elevated chance of very heavy rain (≥', 'അതികനത്ത മഴയ്ക്കുള്ള സാധ്യത കൂടുതലാണ് (≥'],
  ['mm) within the next 3 days — treat forecast seriously.', 'mm) അടുത്ത 3 ദിവസത്തിനുള്ളിൽ — പ്രവചനം ഗൗരവമായി കാണുക.'],
  ['Model clear:', 'മോഡൽ നില വ്യക്തം:'],
  ['no strong heavy-rain signal in the next 3 days.', 'അടുത്ത 3 ദിവസത്തിനുള്ളിൽ കനത്ത മഴയ്ക്കുള്ള ശക്തമായ സൂചനയില്ല.'],
  ['Expected rain, next 24 h (trained models)', 'അടുത്ത 24 മണിക്കൂറിലെ പ്രതീക്ഷിക്കുന്ന മഴ (മോഡലുകൾ)'],
  ['Heavy-rain probability (≥', 'കനത്ത മഴയുടെ സാധ്യത (≥'],
  ['mm in 3 days)', 'mm — 3 ദിവസത്തിനുള്ളിൽ)'],
  ['in 3 days', '3 ദിവസത്തിനുള്ളിൽ'],
  ['LSTM / ridge next-day estimates', 'LSTM / ridge നാളത്തെ കണക്ക്'],
  ['within 3 days', '3 ദിവസത്തിനുള്ളിൽ'],
  ['within the next 3 days', 'അടുത്ത 3 ദിവസത്തിനുള്ളിൽ'],
  // --- drivers & guidance ---
  ['Very heavy rain (>115 mm/day) — slope & stream hazards active', 'അതികനത്ത മഴ (>115 mm/ദിവസം) — ചെരിവ്, അരുവി അപകടങ്ങൾ സജീവം'],
  ['Heavy rain (>64 mm/day) — IMD "heavy rain" category', 'കനത്ത മഴ (>64 mm/ദിവസം) — IMD "കനത്ത മഴ" വിഭാഗം'],
  ['Sustained monsoon rain in the forecast', 'പ്രവചനത്തിൽ തുടർച്ചയായ മഴക്കാല മഴ'],
  ['Unseasonal rain — treat with monsoon-level caution', 'അകാല മഴ — മഴക്കാല ജാഗ്രത പാലിക്കുക'],
  ['Dry season — danger only from outlier storms', 'വരണ്ട കാലം — വിരളമായ കൊടുങ്കാറ്റുകളിൽ മാത്രം അപകടം'],
  ['Monsoon in progress — monitor daily updates', 'മഴക്കാലം തുടരുന്നു — ദിവസേനയുള്ള അപ്ഡേറ്റുകൾ ശ്രദ്ധിക്കുക'],
  ['Steep terrain + wet soils raise landslide potential', 'കുത്തനെയുള്ള ഭൂപ്രദേശവും നനഞ്ഞ മണ്ണും ഉരുൾപൊട്ടൽ സാധ്യത വർധിപ്പിക്കുന്നു'],
  ['Heavy rain on historically sensitive terrain', 'ചരിത്രപരമായി അപകട സാധ്യതയുള്ള ഭൂപ്രദേശത്ത് കനത്ത മഴ'],
  ['Showing modelled data — live feed unavailable', 'മോഡൽ ഡാറ്റ കാണിക്കുന്നു — തത്സമയ ഫീഡ് ലഭ്യമല്ല'],
  ['Normal activities are safe — work and travel as usual', 'സാധാരണ പ്രവർത്തനങ്ങൾ സുരക്ഷിതം — പതിവുപോലെ ജോലിയും യാത്രയും തുടരാം'],
  ['Stay alert and monitor updates during monsoon season', 'മഴക്കാലത്ത് ജാഗ്രതയോടെ അപ്ഡേറ്റുകൾ ശ്രദ്ധിക്കുക'],
  ['Keep emergency numbers (112 / 1077) handy at home', 'എമർജൻസി നമ്പറുകൾ (112 / 1077) വീട്ടിൽ സൂക്ഷിക്കുക'],
  ['Avoid unnecessary travel, especially to hilly areas', 'അനാവശ്യ യാത്ര ഒഴിവാക്കുക, പ്രത്യേകിച്ച് മലമ്പ്രദേശങ്ങളിലേക്ക്'],
  ['Stay indoors during heavy downpours', 'കനത്ത മഴയിൽ വീടിനുള്ളിൽ കഴിയുക'],
  ['Keep children and the elderly indoors', 'കുട്ടികളെയും മുതിർന്നവരെയും വീടിനുള്ളിൽ നിർത്തുക'],
  ['Avoid crossing flooded or muddy roads', 'വെള്ളം കയറിയതോ ചെളി നിറഞ്ഞതോ ആയ റോഡുകൾ മുറിച്ചുകടക്കരുത്'],
  ['Don\u2019t venture near streams, rivers or steep slopes', 'തോടുകൾക്കും നദികൾക്കും കുത്തനെയുള്ള ചെരിവുകൾക്കും സമീപം പോകരുത്'],
  ['Don\u2019t ignore rainfall warnings from authorities', 'അധികാരികളുടെ മഴ മുന്നറിയിപ്പുകൾ അവഗണിക്കരുത്'],
  ['STAY INDOORS — avoid all non-essential travel', 'വീടിനുള്ളിൽ കഴിയുക — അനാവശ്യ യാത്ര പൂർണമായി ഒഴിവാക്കുക'],
  ['Keep a go-bag packed: documents, medicines, water, torch', 'ഒരു എമർജൻസി ബാഗ് തയ്യാറാക്കുക: രേഖകൾ, മരുന്നുകൾ, വെള്ളം, ടോർച്ച്'],
  ['Monitor local updates and panchayat announcements', 'പ്രാദേശിക അറിയിപ്പുകളും പഞ്ചായത്ത് പ്രഖ്യാപനങ്ങളും ശ്രദ്ധിക്കുക'],
  ['Don\u2019t travel on hilly roads', 'മലയോര റോഡുകളിൽ യാത്ര ചെയ്യരുത്'],
  ['Don\u2019t approach landslide-prone or flooded areas', 'ഉരുൾപൊട്ടൽ സാധ്യതയുള്ളതോ വെള്ളക്കെട്ടുള്ളതോ ആയ സ്ഥലങ്ങളെ സമീപിക്കരുത്'],
  ['Don\u2019t ignore evacuation orders if they are issued', 'ഒഴിപ്പിക്കൽ നിർദേശം ലഭിച്ചാൽ അവഗണിക്കരുത്'],
  ['EVACUATE IMMEDIATELY if ordered by authorities', 'അധികാരികൾ നിർദേശിച്ചാൽ ഉടൻ ഒഴിഞ്ഞുപോകുക'],
  ['Go to your panchayat-designated shelter with essentials', 'അവശ്യവസ്തുക്കളുമായി പഞ്ചായത്ത് നിശ്ചയിച്ച ഷെൽട്ടറിലേക്ക് പോകുക'],
  ['Stay away from rivers, streams, dams and slopes', 'നദികൾ, തോടുകൾ, അണക്കെട്ടുകൾ, ചെരിവുകൾ എന്നിവിടങ്ങളിൽ നിന്ന് അകന്നുനിൽക്കുക'],
  ['Call 112 (national) or 1077 (Kerala Disaster) if in danger', 'അപകടത്തിൽ 112 (ദേശീയ) അല്ലെങ്കിൽ 1077 (കേരള ഡിസാസ്റ്റർ) വിളിക്കുക'],
  ['Don\u2019t wait for reminders — leave early if warned', 'കാത്തിരിക്കരുത് — മുന്നറിയിപ്പ് കിട്ടിയാൽ നേരത്തെ പോകുക'],
  ['Don\u2019t stay at home in at-risk areas', 'അപകടസാധ്യതയുള്ള മേഖലകളിൽ വീട്ടിൽ കഴിയരുത്'],
  ['Current risk is LOW. Weather is calm for the season and normal activity is safe. Stay alert during monsoon season.', 'ഇപ്പോഴത്തെ അപകടം കുറവാണ്. കാലാവസ്ഥ ശാന്തം; സാധാരണ പ്രവർത്തനങ്ങൾ സുരക്ഷിതം. മഴക്കാലത്ത് ജാഗ്രത പാലിക്കുക.'],
  ['Current risk is MODERATE. Rainfall is building and some roads may turn slippery. Avoid unnecessary travel during heavy downpours.', 'ഇപ്പോഴത്തെ അപകടം ഇടത്തരം. മഴ ശക്തമാകുന്നു; ചില റോഡുകൾ വഴുക്കലായേക്കാം. കനത്ത മഴയിൽ അനാവശ്യ യാത്ര ഒഴിവാക്കുക.'],
  ['Current risk is HIGH. Heavy rain is falling or expected. Landslides and flash floods are possible on steep terrain. Stay indoors and avoid non-essential travel.', 'അപകടം ഉയർന്നതാണ്. കനത്ത മഴ പെയ്യുന്നു അല്ലെങ്കിൽ പ്രതീക്ഷിക്കുന്നു. ചെരിവുകളിൽ ഉരുൾപൊട്ടലും പെട്ടെന്നുള്ള വെള്ളപ്പൊക്കവും സാധ്യം. വീടിനുള്ളിൽ കഴിയുക; അനാവശ്യ യാത്ര ഒഴിവാക്കുക.'],
  ['Current risk is EXTREME. Very heavy rain poses an immediate threat to life and property. STAY INDOORS, follow evacuation orders and call 112 / 1077 if in danger.', 'അപകടം അത്യധികമാണ്. അതികനത്ത മഴ ജീവനും സ്വത്തിനും ഭീഷണിയാണ്. വീടിനുള്ളിൽ കഴിയുക; ഒഴിപ്പിക്കൽ നിർദേശം അനുസരിക്കുക; അപകടത്തിൽ 112 / 1077 വിളിക്കുക.'],
  // --- charts & notes ---
  ['Rainfall outlook', 'മഴ പ്രവചനം'],
  ['Monsoon pattern · last', 'മഴക്കാല രീതി · കഴിഞ്ഞ'],
  ['days (measured)', 'ദിവസങ്ങൾ (അളന്നത്)'],
  ['Rainfall outlook · last', 'മഴ പ്രവചനം · കഴിഞ്ഞ'],
  ['days', 'ദിവസങ്ങൾ'],
  ['Bar colour = danger tier for that day', 'ബാർ നിറം = ആ ദിവസത്തെ അപകട നില'],
  ['height = forecast rain (mm)', 'ഉയരം = പ്രവചിച്ച മഴ (mm)'],
  ['% = chance of rain.', '% = മഴ സാധ്യത.'],
  ['Bar = measured rain per IST day. Red/amber days are IMD very-heavy thresholds. Day-of-month labels at month starts.', 'ബാർ = ഓരോ IST ദിവസത്തെയും അളന്ന മഴ. ചുവപ്പ്/മഞ്ഞ ദിവസങ്ങൾ IMD അതികനത്ത മഴ പരിധിയാണ്.'],
  ['Danger tier per day from the 7-day rainfall forecast.', '7 ദിവസത്തെ മഴ പ്രവചനത്തിൽ നിന്നുള്ള പ്രതിദിന അപകട നില.'],
  ['Wind/humidity/cloud follow the latest observation.', 'കാറ്റ്/ഈർപ്പം/മേഘം ഏറ്റവും പുതിയ നിരീക്ഷണം പിന്തുടരുന്നു.'],
  // --- ENSO phases (full strings so tier words don't leak) ---
  ['Strong El Niño', 'ശക്തമായ എൽ നിനോ'],
  ['Moderate El Niño', 'മിതമായ എൽ നിനോ'],
  ['Weak El Niño', 'ദുർബലമായ എൽ നിനോ'],
  ['Strong La Niña', 'ശക്തമായ ലാ നിന'],
  ['Moderate La Niña', 'മിതമായ ലാ നിന'],
  ['Weak La Niña', 'ദുർബലമായ ലാ നിന'],
  ['ENSO-neutral', 'ENSO സാധാരണ നില'],
  // --- footer ---
  ['In an emergency', 'അടിയന്തരാവസ്ഥയിൽ'],
  ['National emergency', 'ദേശീയ എമർജൻസി'],
  ['Kerala disaster helpline', 'കേരള ദുരന്ത ഹെൽപ്പ്ലൈൻ'],
  // --- SMS alerts ---
  ['SMS Alerts', 'SMS മുന്നറിയിപ്പുകൾ'],
  ['SMS alerts for this area', 'ഈ മേഖലയ്ക്കുള്ള SMS മുന്നറിയിപ്പ്'],
  ['Free text alerts on your mobile — pick the areas and what to receive.', 'നിങ്ങളുടെ മൊബൈലിലേക്കുള്ള SMS മുന്നറിയിപ്പുകൾ — മേഖലകളും ആവശ്യമുള്ള അറിയിപ്പുകളും തിരഞ്ഞെടുക്കുക.'],
  ['Mobile number', 'മൊബൈൽ നമ്പർ'],
  ['98765 43210 (10-digit Indian)', '98765 43210 (10 അക്ക ഇന്ത്യൻ നമ്പർ)'],
  ['You will receive a confirmation SMS on this number.', 'ഈ നമ്പറിലേക്ക് സ്ഥിരീകരണ SMS ലഭിക്കും.'],
  ['Message language', 'സന്ദേശ ഭാഷ'],
  ['Localities to watch', 'നിരീക്ഷിക്കേണ്ട പ്രദേശങ്ങൾ'],
  ['Alert types', 'അലേർട്ട് തരങ്ങൾ'],
  ['Danger alerts', 'അപകട അലേർട്ടുകൾ'],
  ['Instant SMS when a watched area reaches the threshold below', 'തിരഞ്ഞെടുത്ത മേഖലയിലെ അപകടം താഴെയുള്ള പരിധി കടക്കുമ്പോൾ ഉടൻ SMS'],
  ['Alert when risk is at least', 'അപകടനില (കുറഞ്ഞത്)'],
  ['Daily briefing', 'പ്രതിദിന റിപ്പോർട്ട്'],
  ["Every morning at 7:00 — today's reading plus tomorrow's forecast", 'എല്ലാ ദിവസവും രാവിലെ 7:00 — ഇന്നത്തെ നിലയും നാളത്തെ പ്രവചനവും'],
  ['Weekly outlook', 'ആഴ്ച പ്രവചനം'],
  ["Every Monday at 8:00 — the week's worst day for each area", 'എല്ലാ തിങ്കളാഴ്ചയും 8:00 — ഓരോ മേഖലയിലെയും ആഴ്ചയിലെ ഏറ്റവും അപകടകരമായ ദിനം'],
  ['Save subscription', 'സബ്സ്ക്രിപ്ഷൻ സംരക്ഷിക്കുക'],
  ['Send test SMS', 'ടെസ്റ്റ് SMS അയയ്ക്കുക'],
  ['Unsubscribe', 'അൺസബ്സ്ക്രൈബ്'],
].sort((a, b) => b[0].length - a[0].length);

function translateText(txt) {
  let out = String(txt);
  for (const [en, ml] of I18N) {
    if (!en || out.indexOf(en) === -1) continue;
    // single tokens need word boundaries so 'rain' doesn't hit 'terrain'
    if (/^[\w'-]+$/.test(en)) {
      const re = new RegExp('\\b' + en.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'g');
      out = out.replace(re, ml);
    } else {
      out = out.split(en).join(ml);
    }
  }
  return out;
}

function translatePage() {
  if (state.lang !== 'ml') return;
  // attributes that carry user-facing words
  document.querySelectorAll('title, [title], [placeholder]').forEach((el) => {
    if (el.getAttribute('title')) el.setAttribute('title', translateText(el.getAttribute('title')));
    if (el.getAttribute('placeholder')) el.setAttribute('placeholder', translateText(el.getAttribute('placeholder')));
  });
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hits = [];
  while (walker.nextNode()) {
    const n = walker.currentNode;
    const p = n.parentNode;
    if (!p || !n.nodeValue) continue;
    const tag = p.nodeName || '';
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE') continue;
    if (p.closest && p.closest('[data-notr]')) continue;
    if (p.classList && p.classList.contains('clock')) continue;
    if (!/\p{L}/u.test(n.nodeValue)) continue;      // numbers/units only
    const t = translateText(n.nodeValue);
    if (t !== n.nodeValue) hits.push([n, t]);
  }
  hits.forEach(([n, t]) => { n.nodeValue = t; });
}

function initLangUI() {
  state.lang = (localStorage.getItem(I18N_KEY) === 'ml') ? 'ml' : 'en';
  document.documentElement.lang = state.lang === 'ml' ? 'ml' : 'en';
  const sync = () => {
    $('#lang-en').classList.toggle('is-active', state.lang === 'en');
    $('#lang-ml').classList.toggle('is-active', state.lang === 'ml');
  };
  sync();
  $('#lang-en').addEventListener('click', () => {
    if (state.lang === 'en') return;
    localStorage.setItem(I18N_KEY, 'en');
    location.reload();                       // English re-renders from templates
  });
  $('#lang-ml').addEventListener('click', () => {
    if (state.lang === 'ml') return;
    state.lang = 'ml';
    localStorage.setItem(I18N_KEY, 'ml');
    document.documentElement.lang = 'ml';
    sync();
    translatePage();
  });
  // re-translate any content that (re)renders while Malayalam is active
  new MutationObserver(() => {
    if (state.lang !== 'ml') return;
    clearTimeout(initLangUI._deb);
    initLangUI._deb = setTimeout(translatePage, 120);
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
}

const GUIDANCE = {
  Low: {
    do: [
      'Normal activities are safe — work and travel as usual',
      'Stay alert and monitor updates during monsoon season',
      'Keep emergency numbers (112 / 1077) handy at home',
    ],
    dont: [],
  },
  Moderate: {
    do: [
      'Avoid unnecessary travel, especially to hilly areas',
      'Stay indoors during heavy downpours',
      'Keep children and the elderly indoors',
      'Avoid crossing flooded or muddy roads',
    ],
    dont: [
      'Don\u2019t venture near streams, rivers or steep slopes',
      'Don\u2019t ignore rainfall warnings from authorities',
    ],
  },
  High: {
    do: [
      'STAY INDOORS — avoid all non-essential travel',
      'Keep a go-bag packed: documents, medicines, water, torch',
      'Monitor local updates and panchayat announcements',
    ],
    dont: [
      'Don\u2019t travel on hilly roads',
      'Don\u2019t approach landslide-prone or flooded areas',
      'Don\u2019t ignore evacuation orders if they are issued',
    ],
  },
  Extreme: {
    do: [
      'EVACUATE IMMEDIATELY if ordered by authorities',
      'Go to your panchayat-designated shelter with essentials',
      'Stay away from rivers, streams, dams and slopes',
      'Call 112 (national) or 1077 (Kerala Disaster) if in danger',
    ],
    dont: [
      'Don\u2019t wait for reminders — leave early if warned',
      'Don\u2019t stay at home in at-risk areas',
    ],
  },
};

/* ---------- state ---------- */
let state = {
  summary: null, indices: [], incidents: [], outlook: null, ml: null,
  filters: { q: '', tier: '' },
  lang: 'en',
};
const drawerOpenFor = { id: null, name: null };

/* ---------- search + filters ---------- */
function filteredLocalities() {
  const q = (state.filters.q || '').trim().toLowerCase();
  const tier = state.filters.tier;
  let list = [...state.indices];
  if (tier) list = list.filter((i) => i.tier === tier);
  if (q) {
    list = list.filter((i) => {
      const hay = [i.locality, i.tier, i.description || '', (i.drivers || []).join(' '),
                   String(i.weather && i.weather.rainfall_mm)].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }
  return list.sort((a, b) => b.composite_score - a.composite_score);
}

function applyFilters() {
  const list = filteredLocalities();
  renderCardList(list);
  $('#search-clear').classList.toggle('hidden', !state.filters.q);
}

function clearSearch() {
  state.filters.q = '';
  $('#search-input').value = '';
  applyFilters();
}

function bindSearch() {
  const input = $('#search-input');
  let debounce;
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.filters.q = input.value;
      applyFilters();
    }, 140);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = input.value.trim().toLowerCase();
      const hit = filteredLocalities().find((i) => i.locality.toLowerCase() === q)
        || (filteredLocalities().length === 1 ? filteredLocalities()[0] : null);
      if (hit) { openDrawer(hit); input.blur(); }
    }
  });
  $('#search-clear').addEventListener('click', () => { clearSearch(); input.focus(); });
  // '/' focuses search anywhere (except when already typing)
  document.addEventListener('keydown', (e) => {
    const tag = (document.activeElement || {}).tagName;
    if (e.key === '/' && !/INPUT|TEXTAREA/.test(tag)) {
      e.preventDefault();
      input.focus();
    }
  });
}

function bindTierFilters() {
  document.querySelectorAll('.tf').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tf').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      state.filters.tier = btn.dataset.tier || '';
      applyFilters();
    });
  });
}

/* ---------- seasonal outlook (ENSO + ML) ---------- */
function ensoMeta(enso) {
  if (!enso || !enso.available) return null;
  const phase = enso.phase || 'ENSO-neutral';
  const kind = /El Niño/.test(phase) ? 'el' : /La Niña/.test(phase) ? 'la' : 'neutral';
  return { kind, text: `${phase} · ONI ${enso.oni != null ? num(enso.oni, 2) : '—'}°C` };
}

async function loadOutlook() {
  try {
    const [outlook, ml] = await Promise.all([fetchJSON('/outlook'), fetchJSON('/ml')]);
    state.outlook = outlook;
    state.ml = ml;

    const meta = ensoMeta(outlook && outlook.enso);
    const pill = $('#enso-pill');
    if (meta) {
      pill.textContent = meta.text;
      pill.dataset.enso = meta.kind;
      const text = (outlook.monsoon_outlook && outlook.monsoon_outlook.text) || '';
      pill.title = `ENSO phase: ${text}`;
      pill.classList.remove('hidden');
    }
    if (drawerOpenFor.name) {
      fillDrawerMl(drawerOpenFor.name);
      fillDrawerSeasonal(drawerOpenFor.name);
    }
  } catch (e) {
    /* outlook is decorative — never block the dashboard on it */
  }
}

function lightningFor(name) {
  return (state.outlook && state.outlook.lightning && state.outlook.lightning[name]) || null;
}

function mlFor(name) {
  if (!state.ml || !Array.isArray(state.ml.models)) return null;
  return state.ml.models.find((m) => m.locality === name) || null;
}

/* ---------- fetch with timeout ---------- */
async function fetchJSON(url) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 20000);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(t);
  }
}

/* ---------- global chrome ---------- */
function tickClock() {
  const now = new Date();
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  $('#clock-date').textContent = ist.toLocaleDateString('en-IN', {
    weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
  });
  $('#clock-time').textContent = ist.toLocaleTimeString('en-IN', { hour12: false }) + ' IST';
}

function applyChrome(summary) {
  const seasonPill = $('#season-pill');
  seasonPill.dataset.season = summary.season;
  seasonPill.textContent = summary.season === 'monsoon'
    ? 'Monsoon season · active'
    : 'Dry season · monsoon risk off-peak';

  const live = summary.data_source === 'live' && summary.localities_on_synthetic === 0;
  const sourcePill = $('#source-pill');
  sourcePill.dataset.source = live ? 'live' : 'synthetic';
  sourcePill.textContent = live ? '● Live data' : '⚠ Modelled data';

  $('#synthetic-banner').classList.toggle('hidden', live);
}

/* ---------- hero + summary ---------- */
function renderSummary(s) {
  state.summary = s;
  applyChrome(s);

  const tier = s.headline.tier;
  const meta = TIER_META[tier] || TIER_META.Low;
  const countTxt = s.headline.count > 1
    ? `${s.headline.count} localities at ${tier}`
    : s.headline.count === 1
      ? `${tier} in 1 locality`
      : 'no localities above Low';

  const heroTier = $('#hero-tier');
  heroTier.dataset.tier = tier;
  heroTier.textContent = tier;

  $('#hero-sentence').textContent = s.headline.tier === 'Low' && s.total_localities > 0
    ? `District conditions are calm — all ${s.total_localities} monitored panchayats are at Low risk. Normal activity is safe; stay alert during the monsoon.`
    : `${s.headline.tier === 'Extreme' ? 'Severe conditions' : 'Elevated conditions'} in ${countTxt} of ${s.total_localities} monitored panchayats. Follow the guidance for your area.`;

  const avg = $('#hero-avg');
  avg.style.color = meta.color;
  avg.textContent = num(s.average_danger_score, 2);

  TIER_ORDER.forEach((t) => {
    $('#c-' + t).textContent = (s.tier_breakdown && s.tier_breakdown[t]) || 0;
  });
}

/* ---------- locality cards ---------- */
function tierBadge(tier) {
  const meta = TIER_META[tier] || TIER_META.Low;
  return `<span class="tier-badge" style="color:${meta.color};background:${meta.color}1f">${esc(tier)}</span>`;
}

function chip(label, value, unit) {
  return `<span class="chip">${esc(label)} <b>${value == null ? '—' : esc(value)}${unit ? esc(unit) : ''}</b></span>`;
}

function cardHTML(item) {
  const meta = TIER_META[item.tier] || TIER_META.Low;
  const w = item.weather || {};
  const drivers = (item.drivers || []).slice(0, 2);
  const live = item.data_source === 'live';
  const prov = providerName(item.conditions_provider || (live ? 'openweathermap' : 'synthetic'));
  return `
    <div class="card-top">
      <div>
        <h3 class="card-name">${esc(item.locality)}</h3>
        <div class="card-sub">
          <span class="card-source">${live ? '● Live feed' : '⚠ Modelled data'}${item.season === 'monsoon' ? ' · monsoon' : ''}</span>
          <span class="provider-chip">${esc(prov)}</span>
        </div>
      </div>
      ${tierBadge(item.tier)}
    </div>
    <div>
      <div class="scoreline"><b>${num(item.composite_score, 2)}</b><span>/ 1.0 risk score · pop ${item.population ? Number(item.population).toLocaleString('en-IN') : '—'}</span></div>
      <div class="scorebar"><i style="width:${Math.min(100, item.composite_score * 100)}%;background:${meta.color}"></i></div>
    </div>
    <div class="chips">
      ${weatherGlyph(w) ? `<span class="chip cond">${weatherGlyph(w)}</span>` : ''}
      ${chip('Rain', num(w.rainfall_mm, 1), ' mm')}
      ${w.temperature_c == null ? '' : chip('Temp', num(w.temperature_c, 0), '°C')}
      ${chip('Wind', num(w.wind_mps, 1), ' m/s')}
      ${chip('Humidity', w.humidity_pct == null ? null : Math.round(w.humidity_pct), ' %')}
      ${chip('Cloud', w.cloud_cover_pct == null ? null : Math.round(w.cloud_cover_pct), ' %')}
    </div>
    ${drivers.length ? `<ul class="drivers">${drivers.map((d) => `<li>${esc(d)}</li>`).join('')}</ul>` : ''}
    <div class="card-foot"><span>Tap for guidance &amp; outlook</span><span class="open-hint">Details →</span></div>
  `;
}

function renderCardList(list) {
  const grid = $('#cards');
  grid.innerHTML = '';
  if (!list.length) {
    grid.appendChild(el('div', 'card skeleton',
      (state.indices.length ? 'No panchayats match your search/filter.' : 'No locality data available — is the API running?')));
    return;
  }
  list.forEach((item) => {
    const btn = el('button', 'card');
    btn.type = 'button';
    btn.setAttribute('aria-label', `Open details for ${item.locality}`);
    btn.innerHTML = cardHTML(item);
    btn.addEventListener('click', () => openDrawer(item));
    grid.appendChild(btn);
  });
}

function renderCards() {
  renderCardList(filteredLocalities());
}

/* ---------- one-click shortcuts to the important info ---------- */
function bindShortcuts() {
  $('#btn-highest').addEventListener('click', () => {
    const top = [...state.indices].sort((a, b) => b.composite_score - a.composite_score)[0];
    if (top) openDrawer(top);
  });

  const btn = $('#btn-worst-week');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = 'Scanning all 7 areas…';
    const box = $('#week-scan');
    box.classList.remove('hidden');
    box.innerHTML = '<div class="chart-empty">Fetching 7-day danger outlooks…</div>';
    try {
      const results = await Promise.allSettled(
        state.indices.map((it) => fetchJSON(`/danger-forecast/${encodeURIComponent(it.locality)}`))
      );
      const scans = [];
      results.forEach((r, i) => {
        if (r.status === 'fulfilled' && r.value && r.value.worst_day) {
          scans.push({ locality: state.indices[i].locality, day: r.value.worst_day });
        }
      });
      scans.sort((a, b) => b.day.composite_score - a.day.composite_score);
      const top = scans[0];
      if (!top) throw new Error('no outlooks');
      const meta = TIER_META[top.day.tier] || TIER_META.Low;
      const fmtDay = (iso) => {
        const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
        return d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
      };
      box.innerHTML = `
        <h4>Most dangerous moment in the next 7 days: <span style="color:${top.day.color}">${esc(top.day.tier)}</span> — ${esc(top.locality)}, ${fmtDay(top.day.date)} (${num(top.day.rainfall_mm, 1)} mm ${top.day.probability_pct == null ? '' : `· ${Math.round(top.day.probability_pct)}% chance`})</h4>
        ${scans.slice(0, 3).map((s) => {
          const m = TIER_META[s.day.tier] || TIER_META.Low;
          return `<div class="ws-line"><span><b>${esc(s.locality)}</b> — ${fmtDay(s.day.date)} · ${esc(s.day.tier)} (${num(s.day.composite_score, 2)}) · ${num(s.day.rainfall_mm, 1)} mm</span>` +
            `<button class="ws-open" data-open="${esc(s.locality)}">Open details →</button></div>`;
        }).join('')}
      `;
      box.querySelectorAll('.ws-open').forEach((b) => {
        b.addEventListener('click', () => {
          const it = state.indices.find((x) => x.locality === b.dataset.open);
          if (it) openDrawer(it);
        });
      });
    } catch (e) {
      box.innerHTML = `<div class="chart-empty">⚠ Could not scan the week yet — live feeds may still be updating. ${esc(e.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Worst day this week';
    }
  });
}

/* ---------- drawer ---------- */
function subRow(label, value) {
  const meta = TIER_META.Low;
  const pct = Math.min(100, value * 100);
  return `
    <div class="sub-row">
      <span class="sub-label">${esc(label)}</span>
      <span class="sub-val">${num(value, 2)}</span>
    </div>
    <div class="scorebar"><i style="width:${pct}%;background:${meta.color}"></i></div>
  `;
}

function guidanceHTML(tier) {
  const g = GUIDANCE[tier] || GUIDANCE.Moderate;
  const doItems = g.do.map((t) => `<li><span class="g">✓</span>${esc(t)}</li>`).join('');
  const dontItems = g.dont.map((t) => `<li><span class="d">✕</span>${esc(t)}</li>`).join('');
  return `
    <div><span class="g">✓</span> <strong>What to do</strong></div>
    <ul class="guide-list">${doItems}</ul>
    ${dontItems ? `<div style="margin-top:10px"><span class="d">✕</span> <strong>Avoid</strong></div>
                  <ul class="guide-list">${dontItems}</ul>` : ''}
  `;
}

function openDrawer(item) {
  drawerOpenFor.id = item.locality;
  drawerOpenFor.name = item.locality;
  const meta = TIER_META[item.tier] || TIER_META.Low;
  const w = item.weather || {};
  const sub = item.sub_scores || {};
  const prov = providerName(item.conditions_provider);
  const pop = item.population ? Number(item.population).toLocaleString('en-IN') : null;

  $('#drawer-body').innerHTML = `
    <h2 id="drawer-title" style="margin:0;font-size:1.6rem">${esc(item.locality)}</h2>
    <span class="detail-tier" data-tier="${esc(item.tier)}">${meta.emoji} ${esc(item.tier)} · score ${num(item.composite_score, 2)}</span>
    <p class="detail-description">${esc(item.description)}</p>

    <div class="chips" style="margin-bottom:6px">
      ${weatherGlyph(w) ? `<span class="chip cond">${weatherGlyph(w)}</span>` : ''}
      ${chip('Rain', num(w.rainfall_mm, 1), ' mm')}
      ${w.temperature_c == null ? '' : chip('Temp', num(w.temperature_c, 0), '°C')}
      ${chip('Wind', num(w.wind_mps, 1), ' m/s')}
      ${chip('Humidity', w.humidity_pct == null ? null : Math.round(w.humidity_pct), ' %')}
      ${chip('Cloud', w.cloud_cover_pct == null ? null : Math.round(w.cloud_cover_pct), ' %')}
    </div>
    <div class="loc-meta">
      ${pop ? `<span class="chip">Population <b>${esc(pop)}</b></span>` : ''}
      ${item.ward_count ? `<span class="chip">Wards <b>${esc(item.ward_count)}</b></span>` : ''}
      <span class="provider-chip">Observed by: ${esc(prov)}</span>
      ${item.data_source !== 'live' ? '<span class="provider-chip" style="color:#fcd34d">⚠ modelled fallback active</span>' : ''}
    </div>
    <div class="card-source" style="font-size:0.76rem;color:var(--faint)">
      ${item.observed_at ? 'Observed ' + esc(String(item.observed_at).slice(0, 16).replace('T', ' ')) : ''}
    </div>

    <h4 class="section-title">Why this level</h4>
    <ul class="drivers">${(item.drivers || ['Forecast-based assessment']).map((d) => `<li>${esc(d)}</li>`).join('')}</ul>

    <h4 class="section-title">What is driving the score</h4>
    <div class="sub-block">
      <div class="sub-row"><span class="sub-label">Environmental severity — weather</span><span class="sub-val">${num(sub.environmental_severity, 2)}</span></div>
      <div class="scorebar"><i style="width:${Math.min(100, (sub.environmental_severity || 0) * 100)}%;background:${TIER_META.High.color}"></i></div>
      <div class="sub-row"><span class="sub-label">Structural risk — terrain, soil, history</span><span class="sub-val">${num(sub.structural_risk, 2)}</span></div>
      <div class="scorebar"><i style="width:${Math.min(100, (sub.structural_risk || 0) * 100)}%;background:${TIER_META.Moderate.color}"></i></div>
      <div class="sub-row"><span class="sub-label">Human threat — people &amp; evacuation</span><span class="sub-val">${num(sub.human_threat_level, 2)}</span></div>
      <div class="scorebar"><i style="width:${Math.min(100, (sub.human_threat_level || 0) * 100)}%;background:${TIER_META.Low.color}"></i></div>
    </div>

    <h4 class="section-title">What to do right now</h4>
    ${guidanceHTML(item.tier)}

    <h4 class="section-title">AI 24-hour outlook <span class="sub-tag">(ML)</span></h4>
    <div id="ml-box"><div class="chart-empty">Loading model outlook…</div></div>

    <h4 class="section-title">Seasonal outlook · lightning</h4>
    <div id="season-box"><div class="chart-empty">—</div></div>

    <h4 class="section-title">7-day danger outlook <span class="sub-tag">tier per day ahead</span></h4>
    <div id="forecast-box" class="chart"><div class="chart-empty">Loading 7-day outlook…</div></div>

    <h4 class="section-title">Rainfall trends · monsoon pattern <span class="sub-tag">measured &amp; forecast</span></h4>
    <div id="trends-box"><div class="chart-empty">Loading weather trends…</div></div>

    <h4 class="section-title">Ward-level exposure <span class="sub-tag">micro-zones</span></h4>
    <div id="wards-box"><div class="chart-empty">Loading ward data…</div></div>

    <h4 class="section-title">Past incidents nearby (2004–2025)</h4>
    <div id="incidents-box"><div class="chart-empty">Loading incidents…</div></div>

    <div class="report-row">
      <a class="btn-download" href="/report?locality=${encodeURIComponent(item.locality)}&amp;format=pdf">Download PDF report</a>
      <a class="btn-download" href="/report?locality=${encodeURIComponent(item.locality)}&amp;format=docx">Download DOCX report</a>
      <button type="button" class="btn-download drawer-notify">
        <svg class="notify-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          <path d="M8.5 9.5h7"/>
          <path d="M8.5 13h4.5"/>
        </svg>
        SMS alerts for this area
      </button>
    </div>
  `;

  $('#drawer').classList.add('open');
  $('#drawer').setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';

  loadDangerOutlook(item.locality);
  loadNearbyIncidents(item);
  loadTrends(item.locality);
  loadWards(item);
  fillDrawerMl(item.locality);
  fillDrawerSeasonal(item.locality);

  // per-area SMS subscription shortcut
  const dnb = drawerEl('.drawer-notify');
  if (dnb) dnb.addEventListener('click', () => {
    const name = item.locality;
    closeDrawer();
    openNotify(name);
  });
}

/* ---------- drawer: AI + seasonal blocks ---------- */
function fillDrawerMl(locality) {
  const box = drawerEl('#ml-box');
  if (!box) return;
  const m = mlFor(locality);
  if (!m || m.status !== 'ready') {
    box.innerHTML = '<div class="ml-note">Model outlook not ready — the ML suite trains on first boot (2012–25 local rainfall) and appears here automatically. <code>/ml</code> for status.</div>';
    return;
  }
  const pct = m.heavy_rain_pct == null ? null : m.heavy_rain_pct;
  const alertHTML = m.heavy_alert
    ? '<div class="model-alert">⚠ <b>Model alert:</b> elevated chance of very heavy rain (≥' + num(m.heavy_mm, 0) + ' mm) within the next 3 days — treat forecast seriously.</div>'
    : '<div class="model-alert clear">✓ <b>Model clear:</b> no strong heavy-rain signal in the next 3 days.</div>';
  box.innerHTML = `
    ${alertHTML}
    <div class="ml-row"><span>Expected rain, next 24 h (trained models)</span><b>${num(m.ml_rain_mm, 1)} mm</b></div>
    ${pct == null ? '' : `<div class="ml-row"><span>Heavy-rain probability (≥${num(m.heavy_mm, 0)} mm in 3 days)</span><b>${num(pct, 1)}%</b></div>`}
    <div class="ml-row"><span>LSTM / ridge next-day estimates</span><b>${num(m.lstm_mm, 1)} / ${num(m.ridge_mm, 1)} mm</b></div>
    <div class="ml-note">Trained per locality on 2012+ daily rainfall, evaluated out-of-sample on 2020+ (median detection of heavy-rain windows ~93%, AUC 0.94–0.97 — see <code>/ml</code>). Decision threshold ${m.threshold != null ? num(m.threshold, 3) : '—'} calibrated so misses cost more than false alarms. The live forecast above remains the primary source.</div>
  `;
}

function fillDrawerSeasonal(locality) {
  const box = drawerEl('#season-box');
  if (!box) return;
  const lit = lightningFor(locality);
  const ensn = state.outlook && state.outlook.enso;
  const ensoText = (state.outlook && state.outlook.monsoon_outlook && state.outlook.monsoon_outlook.text) || '';
  if (!lit) {
    box.innerHTML = '<div class="ml-note">Seasonal outlook loading…</div>';
    return;
  }
  box.innerHTML = `
    <div class="ml-row"><span>Lightning risk today</span><b style="color:${esc(lit.colour)}">${esc(lit.tier)}</b></div>
    ${ensn && ensn.available ? `<div class="ml-row"><span>ENSO phase (NOAA CPC)</span><b>${esc(ensn.phase)} · ONI ${num(ensn.oni, 2)} °C</b></div>` : ''}
    <div class="ml-note">${esc(lit.guidance)}</div>
    ${ensoText ? `<div class="ml-note" style="margin-top:4px">${esc(ensoText)}</div>` : ''}
  `;
}

function fillOpenDrawerSeasonal() {
  if (drawerOpenFor.name) fillDrawerSeasonal(drawerOpenFor.name);
}

/* ---------- drawer: rainfall trends + monsoon pattern + ward layer ---------- */
async function loadTrends(locality) {
  const box = drawerEl('#trends-box');
  if (!box) return;
  try {
    const t = await fetchJSON(`/trends/${encodeURIComponent(locality)}`);
    if (drawerOpenFor.id !== locality) return;
    box.innerHTML = '';
    const wrap = el('div');
    const p = t.providers || {};
    const have = (x) => x && (x.days || x.hours || []).length;
    if (have(t.rain_outlook)) wrap.appendChild(rainOutlookPanel(t.rain_outlook));
    if (have(t.observed_30d)) wrap.appendChild(observedPanel(t.observed_30d));
    if (have(t.hourly_48h)) wrap.appendChild(hourlyPanel(t.hourly_48h));
    wrap.appendChild(el('div', 'chart-note',
      `Providers — outlook: <b>${esc(providerName(t.rain_outlook && t.rain_outlook.provider))}</b>` +
      ` · observed 30 days: <b>${esc(providerName(t.observed_30d && t.observed_30d.provider))}</b>` +
      ` · wind/humidity 48 h: <b>${esc(providerName(t.hourly_48h && t.hourly_48h.provider))}</b>.<br>` +
      'OpenWeatherMap (when configured) feeds the outlook &amp; current conditions; measured history comes from Open-Meteo\'s observed past-days feed (OWM free tier has no history API).'));
    box.appendChild(wrap);
  } catch (e) {
    if (drawerOpenFor.id !== locality) return;
    box.innerHTML = `<div class="chart-empty">Trends unavailable right now: ${esc(e.message)}</div>`;
  }
}

function fmtShortDay(iso) {
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

function rainOutlookPanel(ro) {
  const days = ro.days || [];
  const width = Math.max(280, ($('#drawer-body').clientWidth || 500) - 60);
  const h = 150, padB = 22, padT = 16;
  const max = Math.max(8, ...days.map((d) => Number(d.rain_mm) || 0));
  const n = days.length;
  const bw = Math.min(42, (width - (n - 1) * 6) / n);
  const step = n > 1 ? (width - bw) / (n - 1) : 0;
  const colour = (v) => v >= 115.5 ? '#f43f5e' : v >= 64.5 ? '#fb7185'
    : v >= 35.5 ? '#fbbf24' : '#38bdf8';
  let bars = '';
  days.forEach((d, i) => {
    const v = Number(d.rain_mm) || 0;
    const x = n > 1 ? i * step : (width - bw) / 2;
    const bh = Math.max(1.5, (v / max) * (h - padB - padT));
    const first = i === 0 && ro.today_partial;
    bars += `
      <rect class="bar" x="${x.toFixed(1)}" y="${(h - padB - bh).toFixed(1)}" width="${bw.toFixed(1)}"
            height="${bh.toFixed(1)}" fill="${colour(v)}" opacity="0.92">
        <title>${first ? 'Today (partial)' : fmtShortDay(d.date)}: ${num(v, 1)} mm${d.pop_pct == null ? '' : ' · ' + Math.round(d.pop_pct) + '% rain chance'}</title>
      </rect>
      ${v >= 20 ? `<text class="chart-max" x="${(x + bw / 2).toFixed(1)}" y="${(h - padB - bh - 5).toFixed(1)}">${Math.round(v)}</text>` : ''}
      <text class="chart-label" x="${(x + bw / 2).toFixed(1)}" y="${h - 8}">${i === 0 ? (ro.today_partial ? 'Today*' : 'Today') : fmtShortDay(d.date)}</text>
    `;
  });
  const wrap = el('div', 'trend-panel');
  wrap.innerHTML = `
    <h5>Rainfall outlook <span class="provider-chip">${esc(providerName(ro.provider))}${ro.provider === 'openweathermap' ? ' · 5-day' : ' · 7-day'}</span></h5>
    <svg width="${width}" height="${h}" role="img" aria-label="Rainfall outlook">
      <line x1="0" y1="${h - padB}" x2="${width}" y2="${h - padB}" stroke="rgba(148,210,176,0.2)" stroke-width="1"/>
      ${bars}
    </svg>
    <div class="chart-legend">
      <span><i style="background:#38bdf8"></i>&lt;35 mm</span>
      <span><i style="background:#fbbf24"></i>35–64 mm</span>
      <span><i style="background:#fb7185"></i>64–115 mm</span>
      <span><i style="background:#f43f5e"></i>&gt;115 mm/day</span>
    </div>
    ${ro.today_partial ? '<div class="chart-note">* today\'s bucket covers only the hours since the 3-hour forecast started (partial day).</div>' : ''}
  `;
  return wrap;
}

function observedPanel(o) {
  const days = (o.days || []);  // backend returns chronological (oldest first)
  const width = Math.max(280, ($('#drawer-body').clientWidth || 500) - 60);
  const h = 120, padB = 20, padT = 12;
  const max = Math.max(8, ...days.map((d) => Number(d.rain_mm) || 0));
  const n = days.length;
  const bw = Math.max(2.2, Math.min(8, (width - 4) / Math.max(n, 1)));
  const colour = (v) => v >= 115.5 ? '#f43f5e' : v >= 64.5 ? '#fbbf24'
    : v >= 7.5 ? '#2fdd8f' : 'rgba(47,221,143,0.28)';
  let bars = '';
  days.forEach((d, i) => {
    const v = Number(d.rain_mm) || 0;
    const bh = Math.max(1, (v / max) * (h - padB - padT));
    const x = 2 + i * ((width - 4) / n);
    const date = new Date(String(d.date).slice(0, 10));
    bars += `
      <rect x="${x.toFixed(1)}" y="${(h - padB - bh).toFixed(1)}" width="${bw.toFixed(1)}"
            height="${bh.toFixed(1)}" fill="${colour(v)}" rx="1">
        <title>${fmtShortDay(d.date)}: ${num(v, 1)} mm (wind ${num(d.wind_max_mps, 1)} m/s · humidity ${Math.round(d.humidity_mean_pct)}%)</title>
      </rect>`;
    if (n > 1 && (date.getDate() === 1 || i === 0 || i === n - 1)) {
      bars += `<text class="chart-label" x="${(x + bw / 2).toFixed(1)}" y="${h - 6}" font-size="8">${date.getDate()}</text>`;
    }
  });
  const vals = days.map((d) => Number(d.rain_mm) || 0);
  const sum = vals.reduce((a, b) => a + b, 0);
  const wet = vals.filter((v) => v >= 7.5).length;
  const heavy = days.filter((d) => (Number(d.rain_mm) || 0) >= 64.5).length;
  const wettest = days.reduce((a, b) => ((Number(a.rain_mm) || 0) >= (Number(b.rain_mm) || 0)) ? a : b);
  const wrap = el('div', 'trend-panel');
  wrap.innerHTML = `
    <h5>Monsoon pattern · last ${days.length} days (measured) <span class="provider-chip">${esc(providerName(o.provider))}</span></h5>
    <svg width="${width}" height="${h}" role="img" aria-label="Observed rainfall over the last 30 days">
      <line x1="0" y1="${h - padB}" x2="${width}" y2="${h - padB}" stroke="rgba(148,210,176,0.2)" stroke-width="1"/>
      ${bars}
    </svg>
    <div class="mini-stats">
      <div><b>${num(sum, 0)} mm</b>30-day total</div>
      <div><b>${wet}</b>rainy days (≥7.5 mm)</div>
      <div><b>${heavy}</b>days ≥64.5 mm</div>
      <div><b>${num(Number(wettest.rain_mm) || 0, 0)} mm</b>wettest day (${fmtShortDay(wettest.date)})</div>
    </div>
    <div class="chart-note">Bar = measured rain per IST day. Red/amber days are IMD very-heavy thresholds. Day-of-month labels at month starts.</div>
  `;
  return wrap;
}

function hourlyPanel(h) {
  const hours = h.hours || [];
  const width = Math.max(280, ($('#drawer-body').clientWidth || 500) - 60);
  const n = hours.length;
  const t = (i) => new Date(String(hours[i].time).replace(' ', 'T') + ':00');
  const wind = hours.map((x) => Number(x.wind_mps) || 0);
  const gust = hours.map((x) => Number(x.gust_mps) || 0);
  const hum = hours.map((x) => Number(x.humidity_pct) || 0);
  const temp = hours.map((x) => Number(x.temp_c) || 0);
  const maxWind = Math.max(4, ...wind);
  const tMin = Math.min(...temp) - 2, tMax = Math.max(...temp) + 2;
  const plot = { w: width, h: 92, padL: 4, padR: 4, padT: 12, padB: 16 };
  const X = (i) => plot.padL + (n > 1 ? i * (plot.w - plot.padL - plot.padR) / (n - 1) : plot.w / 2);
  const Yw = (v) => plot.padT + (1 - v / maxWind) * (plot.h - plot.padT - plot.padB);
  const Yh = (v) => plot.padT + (1 - v / 100) * (plot.h - plot.padT - plot.padB);
  const Yt = (v) => plot.padT + (1 - (v - tMin) / (tMax - tMin)) * (plot.h - plot.padT - plot.padB);
  const line = (vals, Y) => vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join('');
  let bars = '';
  wind.forEach((v, i) => {
    bars += `<rect class="bar" x="${(X(i) - 2).toFixed(1)}" y="${Yw(v).toFixed(1)}" width="4" height="${(plot.h - plot.padB - Yw(v)).toFixed(1)}" fill="rgba(56,189,248,0.5)"><title>${t(i).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit' })}: wind ${num(v, 1)} m/s</title></rect>`;
  });
  let tix = '';
  hours.forEach((_, i) => {
    if (n <= 1 || i % Math.ceil(n / 5) === 0 || i === n - 1) {
      const tt = t(i);
      tix += `<text class="chart-label" x="${X(i).toFixed(1)}" y="${plot.h - 4}" font-size="8.5">${tt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })} ${tt.getHours()}:00</text>`;
    }
  });
  const wrap = el('div', 'trend-panel');
  wrap.innerHTML = `
    <h5>Wind, humidity &amp; temperature · next ~48 h <span class="provider-chip">${esc(providerName(h.provider))} · every ${h.step_hours} h</span></h5>
    <div class="chart-legend" style="margin-bottom:4px">
      <span><i style="background:#38bdf8"></i>wind (m/s)</span>
      <span><i class="ln" style="background:#fbbf24"></i>humidity %</span>
      <span><i class="ln" style="background:#fb7185"></i>temp °C</span>
    </div>
    <svg width="${plot.w}" height="${plot.h}" role="img" aria-label="48-hour wind humidity and temperature">
      <line x1="0" y1="${plot.h - plot.padB}" x2="${plot.w}" y2="${plot.h - plot.padB}" stroke="rgba(148,210,176,0.2)" stroke-width="1"/>
      ${bars}
      <path d="${line(hum, Yh)}" fill="none" stroke="#fbbf24" stroke-width="1.6" opacity="0.9"/>
      <path d="${line(temp, Yt)}" fill="none" stroke="#fb7185" stroke-width="1.6" opacity="0.9"/>
      ${tix}
    </svg>
    <div class="chart-note">Humidity (amber) and temperature (rose) share the band; wind bars scaled to the 48-h max (${num(maxWind, 1)} m/s).
      ${gust.some((g) => g > 0) ? `Gusts to ${num(Math.max(...gust), 1)} m/s expected.` : ''}</div>
  `;
  return wrap;
}

async function loadWards(item) {
  const box = drawerEl('#wards-box');
  if (!box) return;
  try {
    const wd = await fetchJSON(`/wards/${encodeURIComponent(item.locality)}`);
    if (drawerOpenFor.id !== item.locality) return;
    if (!wd.available) {
      box.innerHTML = '<div class="chart-empty">No ward structure for this area yet — add it in <code>data/static/wards.json</code>.</div>';
      return;
    }
    const top = wd.wards.slice(0, 7);
    const rows = top.map((w, i) => {
      const nm = String(w.ward_name || '').replace(/\b\w/g, (c) => c.toUpperCase());
      return `
        <div class="ward-item">
          <span class="ward-rank">${i + 1}</span>
          <span class="w-name" style="flex:1"><b>${esc(nm)}</b>
            <span class="w-meta">· ${Number(w.population).toLocaleString('en-IN')} people · ${w.incidents_nearby} incident${w.incidents_nearby === 1 ? '' : 's'} nearby</span>
          </span>
          <span class="ward-badge" style="color:${esc(w.color)}">${esc(w.tier)}</span>
        </div>`;
    }).join('');
    box.innerHTML = `
      <div class="ward-list">${rows}</div>
      <div class="ward-note">Ward score = panchayat danger raised by each ward's recorded-incident history. Structure: ${esc(wd.structure_source)}. Ward population: ${esc(wd.population_model)} of the panchayat total (${Number(wd.panchayat_population).toLocaleString('en-IN')}). Replace with the Census-2011 ward table via <code>data/static/wards_overrides.csv</code> for authoritative splits.</div>
    `;
  } catch (e) {
    if (drawerOpenFor.id !== item.locality) return;
    box.innerHTML = `<div class="chart-empty">Ward data unavailable: ${esc(e.message)}</div>`;
  }
}

function closeDrawer() {
  $('#drawer').classList.remove('open');
  $('#drawer').setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

function drawerEl(sel) {
  return $('#drawer-body').querySelector(sel);
}

async function loadDangerOutlook(locality) {
  const box = drawerEl('#forecast-box');
  if (!box) return;
  try {
    const o = await fetchJSON(`/danger-forecast/${encodeURIComponent(locality)}`);
    if (drawerOpenFor.id !== locality) return;
    box.innerHTML = '';
    if (!o.days || !o.days.length) throw new Error('empty outlook');
    box.appendChild(dangerChartHTML(o));
  } catch (e) {
    if (drawerOpenFor.id !== locality) return;
    // graceful fallback: plain rainfall chart via the older endpoint
    try {
      const f = await fetchJSON(`/forecast/${encodeURIComponent(locality)}`);
      if (drawerOpenFor.id !== locality) return;
      box.innerHTML = '';
      if (f.daily && f.daily.length) box.appendChild(chartSVG(f.daily, f.source === 'live'));
      else box.innerHTML = '<div class="chart-empty">No forecast available</div>';
    } catch (e2) {
      if (drawerOpenFor.id !== locality) return;
      box.innerHTML = `<div class="chart-empty">7-day outlook unavailable: ${esc(e.message)}</div>`;
    }
  }
}

function dangerChartHTML(o) {
  const days = o.days || [];
  const worst = o.worst_day || null;
  const max = Math.max(10, ...days.map((d) => Number(d.rainfall_mm) || 0));
  const width = Math.max(280, ($('#drawer-body').clientWidth || 480) - 34);
  const height = 190;
  const padB = 30;
  const padT = 16;
  const n = days.length;
  const bw = Math.min(48, (width - (n - 1) * 8) / n);
  const step = n > 1 ? (width - bw) / (n - 1) : 0;

  const fmt = (iso) => {
    const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
    const wd = d.toLocaleDateString('en-IN', { weekday: 'short' });
    const md = d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
    return { wd, md };
  };

  let bars = '';
  let dots = '';
  days.forEach((d, i) => {
    const v = Number(d.rainfall_mm) || 0;
    const x = n > 1 ? i * step : (width - bw) / 2;
    const h = Math.max(2, (v / max) * (height - padB - padT));
    const color = d.color || '#3b82f6';
    const meta = TIER_META[d.tier] || TIER_META.Low;
    const { wd, md } = fmt(d.date);
    const tip = `${wd} ${md}: ${d.tier} · ${num(v, 1)} mm` +
      (d.probability_pct == null ? '' : ` · ${Math.round(d.probability_pct)}% rain chance`);
    bars += `
      <rect class="bar" x="${x.toFixed(1)}" y="${(height - padB - h).toFixed(1)}" width="${bw.toFixed(1)}"
            height="${h.toFixed(1)}" fill="${color}" opacity="0.92">
        <title>${tip}</title>
      </rect>
      ${v >= 15 ? `<text class="chart-max" x="${(x + bw / 2).toFixed(1)}" y="${(height - padB - h - 6).toFixed(1)}">${Math.round(v)}</text>` : ''}
      <text class="chart-label" x="${(x + bw / 2).toFixed(1)}" y="${height - 16}">${wd}</text>
      ${d.probability_pct == null ? '' : `<text class="chart-label" style="font-size:8px;fill:var(--faint)" x="${(x + bw / 2).toFixed(1)}" y="${height - 5}">${Math.round(d.probability_pct)}%</text>`}
    `;
    dots += `
      <span class="day-dot" title="${esc(tip)}">
        <i style="background:${color}"></i>
        ${md} · ${esc(d.tier)}
      </span>`;
  });

  const wrapper = el('div');
  const worstNote = worst
    ? `<div class="outlook-worst" style="border-left:3px solid ${worst.color}">
         <b>Watch ${fmt(worst.date).wd} ${fmt(worst.date).md}</b> — ${esc(worst.tier)} risk (${num(worst.rainfall_mm, 1)} mm ${worst.probability_pct == null ? '' : `· ${Math.round(worst.probability_pct)}% chance`}) in this window. ${esc((worst.drivers || [])[0] || '')}
       </div>`
    : '';
  wrapper.innerHTML = `
    ${worstNote}
    <svg width="${width}" height="${height}" role="img" aria-label="7-day danger forecast for ${esc(o.locality)}">
      <line x1="0" y1="${height - padB}" x2="${width}" y2="${height - padB}" stroke="rgba(148,163,184,0.25)" stroke-width="1"/>
      ${bars}
    </svg>
    <div class="day-dots">${dots}</div>
    <div class="card-source" style="font-size:0.74rem;color:var(--faint);margin-top:6px">
      Bar colour = danger tier for that day · height = forecast rain (mm) · % = chance of rain.
      ${o.source === 'open-meteo' ? '● Live forecast (Open-Meteo)' : '⚠ Modelled outlook'} — ${esc(o.note || '')}
    </div>
  `;
  return wrapper;
}

function chartSVG(daily, live) {
  const values = daily.map((d) => Number(d.rainfall_mm) || 0);
  const max = Math.max(10, ...values);
  const width = Math.max(260, ($('#drawer-body').clientWidth || 480) - 34);
  const height = 170;
  const padB = 26;
  const padT = 14;
  const n = daily.length;
  const bw = Math.min(46, (width - (n - 1) * 8) / n);
  const step = n > 1 ? (width - bw) / (n - 1) : 0;

  let bars = '';
  values.forEach((v, i) => {
    const x = n > 1 ? i * step : (width - bw) / 2;
    const h = Math.max(2, (v / max) * (height - padB - padT));
    const color = v >= 115.5 ? '#ff2e5f' : v >= 64.5 ? '#ff5252' : v >= 35.5 ? '#f5a623' : '#3b82f6';
    bars += `
      <rect class="bar" x="${x.toFixed(1)}" y="${(height - padB - h).toFixed(1)}" width="${bw.toFixed(1)}"
            height="${h.toFixed(1)}" fill="${color}" opacity="0.92">
        <title>${fmtDay(daily[i].date)}: ${num(v, 1)} mm</title>
      </rect>
      <text class="chart-label" x="${(x + bw / 2).toFixed(1)}" y="${height - 8}">${fmtDay(daily[i].date)}</text>
      ${v >= 35.5 ? `<text class="chart-max" x="${(x + bw / 2).toFixed(1)}" y="${(height - padB - h - 6).toFixed(1)}">${Math.round(v)}</text>` : ''}
    `;
  });

  const wrapper = el('div');
  wrapper.style.position = 'relative';
  wrapper.innerHTML = `
    <svg width="${width}" height="${height}" role="img"
         aria-label="7-day rainfall forecast, ${live ? 'live' : 'modelled'} data">
      <line x1="0" y1="${height - padB}" x2="${width}" y2="${height - padB}"
            stroke="rgba(148,163,184,0.25)" stroke-width="1"/>
      ${bars}
    </svg>
    <div class="card-source" style="font-size:0.74rem;color:var(--faint);margin-top:2px">
      ${live ? '● Live forecast (Open-Meteo)' : '⚠ Modelled outlook — live feed unavailable'} ·
      colours: blue &lt;35 · amber 35–64 · red 64–115 · pink &gt;115 mm/day
    </div>
  `;
  return wrapper;
}

async function loadNearbyIncidents(item) {
  const box = drawerEl('#incidents-box');
  if (!box) return;
  try {
    if (!state.incidents.length) state.incidents = await fetchJSON('/incidents');
    if (drawerOpenFor.id !== item.locality) return;

    const lat0 = item.latitude, lon0 = item.longitude;
    const near = state.incidents
      .filter((inc) => Math.abs(inc.latitude - lat0) + Math.abs(inc.longitude - lon0) < 0.35)
      .sort((a, b) => b.year - a.year)
      .slice(0, 5);

    box.innerHTML = near.length
      ? near.map((inc) => `
          <div class="incident-item">
            <h5><span class="incident-year">${inc.year}</span> ·
              ${esc((inc.incident_type || '').replace(/_/g, ' '))} ·
              ${esc(inc.severity)}</h5>
            <p>${esc(inc.location)} — ${esc(inc.description)}</p>
          </div>`).join('')
      : '<div class="chart-empty">No major incidents recorded very close to this area.</div>';
  } catch (e) {
    if (drawerOpenFor.id !== item.locality) return;
    box.innerHTML = `<div class="chart-empty">Incidents unavailable: ${esc(e.message)}</div>`;
  }
}

/* ---------- SMS alert subscriptions ---------- */
const NOTIFY_KEY = 'idi-notify-phone';

function postJSON(url, body, method = 'POST') {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 20000);
  return fetch(url, {
    method, signal: ctrl.signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `${url} → HTTP ${res.status}`);
    return data;
  }).finally(() => clearTimeout(t));
}

function setNotifyStatus(html, tone) {
  const box = $('#notify-status');
  if (!box) return;
  box.className = 'notify-status' + (tone ? ' ' + tone : '');
  box.innerHTML = html || '';
}

function setNotifyLang(lang) {
  $('#nlang-en').classList.toggle('is-active', lang !== 'ml');
  $('#nlang-ml').classList.toggle('is-active', lang === 'ml');
}

async function refreshNotifyStatus() {
  try {
    state.notify = await fetchJSON('/notify/status');
  } catch (e) {
    state.notify = { demo: true, provider: 'demo', note: 'Alerts service unreachable — is the API running?' };
  }
  const box = $('#notify-mode');
  if (!box) return;
  const live = !state.notify.demo;
  box.className = 'notify-mode ' + (live ? 'live' : 'demo');
  box.textContent = (live ? '● Live SMS · ' : '⚠ Demo mode · ') + (state.notify.note || '');
}

async function openNotify(prefLocality) {
  if (!state.notify) await refreshNotifyStatus();
  if (!state.indices.length) {
    try { state.indices = await fetchJSON('/index'); } catch (e) { /* cards fall back below */ }
  }
  const names = [...new Set(state.indices.map((i) => i.locality))].sort();
  const wrap = $('#notify-loc');
  wrap.innerHTML = names.length
    ? names.map((n) =>
        `<button type="button" class="tf nloc${n === prefLocality ? ' is-active' : ''}" data-loc="${esc(n)}">${esc(n)}</button>`).join('')
    : '<span class="nhelp">Localities not loaded yet — try again in a moment.</span>';
  wrap.querySelectorAll('.nloc').forEach((b) =>
    b.addEventListener('click', () => b.classList.toggle('is-active')));

  const phone = localStorage.getItem(NOTIFY_KEY) || '';
  $('#notify-phone').value = phone;
  setNotifyLang(state.lang);   // message language follows the page language
  $('#nplan-danger').checked = true;
  $('#nplan-daily').checked = false;
  $('#nplan-weekly').checked = false;
  $('#nthreshold').value = 'High';
  $('#notify-unsub').classList.add('hidden');
  setNotifyStatus('', '');
  if (phone) {
    try {
      const rec = await fetchJSON('/notify/subscribe?phone=' + encodeURIComponent(phone));
      if (rec && Array.isArray(rec.plans)) {
        const have = new Set(rec.localities || []);
        wrap.querySelectorAll('.nloc').forEach((b) =>
          b.classList.toggle('is-active', have.has(b.dataset.loc)));
        setNotifyLang(rec.lang === 'ml' ? 'ml' : 'en');
        ['danger', 'daily', 'weekly'].forEach((p) => {
          $('#nplan-' + p).checked = (rec.plans || []).includes(p);
        });
        $('#nthreshold').value = rec.threshold === 'Extreme' ? 'Extreme' : 'High';
        $('#notify-unsub').classList.remove('hidden');
      }
    } catch (e) { /* 404: not subscribed yet — keep defaults */ }
  }
  $('#notify-modal').classList.add('open');
  $('#notify-modal').setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
  setTimeout(() => { try { $('#notify-phone').focus(); } catch (e) { /* noop */ } }, 80);
}

function closeNotify() {
  $('#notify-modal').classList.remove('open');
  $('#notify-modal').setAttribute('aria-hidden', 'true');
  if (!$('#drawer').classList.contains('open')) document.body.style.overflow = '';
}

function notifyPayload() {
  return {
    phone: $('#notify-phone').value.trim(),
    lang: $('#nlang-ml').classList.contains('is-active') ? 'ml' : 'en',
    localities: [...$('#notify-loc').querySelectorAll('.nloc.is-active')].map((b) => b.dataset.loc),
    plans: ['danger', 'daily', 'weekly'].filter((p) => $('#nplan-' + p).checked),
    threshold: $('#nthreshold').value,
  };
}

async function saveNotify(e) {
  e.preventDefault();
  const p = notifyPayload();
  if (!/^(\+91|91|0)?[6-9]\d{9}$/.test(p.phone.replace(/[\s-]/g, ''))) {
    setNotifyStatus('⚠ Enter a valid 10-digit Indian mobile number (e.g. 98765 43210).', 'err'); return;
  }
  if (!p.localities.length) { setNotifyStatus('⚠ Choose at least one locality to watch.', 'err'); return; }
  if (!p.plans.length) { setNotifyStatus('⚠ Choose at least one alert type.', 'err'); return; }
  const btn = $('#notify-save'); btn.disabled = true;
  try {
    const res = await postJSON('/notify/subscribe', p);
    localStorage.setItem(NOTIFY_KEY, p.phone);
    $('#notify-unsub').classList.remove('hidden');
    let html = '✓ Subscription saved' + (res.demo ? ' — demo mode (no SMS gateway key connected).' : ' — live SMS active.');
    if (res.demo && res.welcome) {
      html += `<div class="sms-preview">Confirmation SMS that would be sent:<br>${esc(res.welcome)}</div>`;
    }
    setNotifyStatus(html, 'ok');
    refreshNotifyStatus();
  } catch (err) {
    setNotifyStatus('⚠ ' + esc(err.message), 'err');
  } finally { btn.disabled = false; }
}

async function testNotify() {
  const p = notifyPayload();
  if (!/^(\+91|91|0)?[6-9]\d{9}$/.test(p.phone.replace(/[\s-]/g, ''))) {
    setNotifyStatus('⚠ Enter a valid 10-digit Indian mobile number first.', 'err'); return;
  }
  const btn = $('#notify-test'); btn.disabled = true;
  try {
    const res = await postJSON('/notify/test', { phone: p.phone, lang: p.lang });
    const tone = res.demo ? 'warn' : 'ok';
    let html = res.demo ? 'Test SMS recorded in demo mode (not actually sent).' : '✓ Test SMS sent.';
    if (res.preview) {
      html += `<div class="sms-preview">Message that ${res.demo ? 'would be' : 'was'} sent:<br>${esc(res.preview)}</div>`;
    }
    setNotifyStatus(html, tone);
  } catch (err) {
    setNotifyStatus('⚠ ' + esc(err.message), 'err');
  } finally { btn.disabled = false; }
}

async function unsubNotify() {
  const p = notifyPayload();
  if (!p.phone) return;
  if (!window.confirm('Unsubscribe ' + p.phone + ' from all SMS alerts?')) return;
  try {
    await postJSON('/notify/subscribe', { phone: p.phone }, 'DELETE');
    localStorage.removeItem(NOTIFY_KEY);
    $('#notify-unsub').classList.add('hidden');
    setNotifyStatus('✓ Unsubscribed — no more SMS alerts for this number.', 'ok');
  } catch (err) {
    setNotifyStatus('⚠ ' + esc(err.message), 'err');
  }
}

function bindNotifyUI() {
  $('#btn-notify').addEventListener('click', () => openNotify(null));
  $('#notify-form').addEventListener('submit', saveNotify);
  $('#notify-test').addEventListener('click', testNotify);
  $('#notify-unsub').addEventListener('click', unsubNotify);
  document.querySelectorAll('#notify-modal [data-notify-close]').forEach((n) =>
    n.addEventListener('click', closeNotify));
  $('#nlang-en').addEventListener('click', () => setNotifyLang('en'));
  $('#nlang-ml').addEventListener('click', () => setNotifyLang('ml'));
}

/* ---------- data loading ---------- */
async function loadAll() {    $('#cards').innerHTML = '<div class="card skeleton">Loading localities…</div>';
  try {
    const [summary, indices] = await Promise.all([fetchJSON('/summary'), fetchJSON('/index')]);
    state.summary = summary;
    state.indices = Array.isArray(indices) ? indices : [];
    renderSummary(summary);
    renderCards();
  } catch (e) {
    $('#cards').innerHTML = `
      <div class="card skeleton" style="grid-column:1/-1;justify-content:flex-start">
        ⚠ Could not load data — ${esc(e.message)}<br>
        <span style="font-size:0.85rem;color:var(--faint)">Start the API with <b>python3 api/server.py</b> and refresh.</span>
      </div>`;
    $('#synthetic-banner').classList.remove('hidden');
    $('#hero-tier').textContent = '—';
    $('#hero-sentence').textContent = 'Data unavailable.';
  }
  loadOutlook(); // ENSO + ML outlooks refresh alongside the dashboard
}

/* ---------- map tab ---------- */
function bindMapTab() {
  const btn = $('#load-map');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = 'Loading map…';
    try {
      const res = await fetch('/map');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();
      btn.replaceWith(el('iframe', '', undefined));
      const iframe = $('#view-map iframe');
      iframe.srcdoc = html;
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'Map failed to load — retry';
      btn.title = e.message;
    }
  });
}

function bindTabs() {
  const show = (which) => {
    $('#tab-localities').classList.toggle('is-active', which === 'localities');
    $('#tab-map').classList.toggle('is-active', which === 'map');
    $('#tab-localities').setAttribute('aria-selected', which === 'localities');
    $('#tab-map').setAttribute('aria-selected', which === 'map');
    $('#view-localities').classList.toggle('hidden', which !== 'localities');
    $('#view-map').classList.toggle('hidden', which !== 'map');
  };
  $('#tab-localities').addEventListener('click', () => show('localities'));
  $('#tab-map').addEventListener('click', () => show('map'));
  return show;
}

/* ---------- init ---------- */
document.addEventListener('DOMContentLoaded', () => {
  initLangUI();
  tickClock();
  setInterval(tickClock, 1000);
  setInterval(() => loadAll(), 10 * 60 * 1000); // gentle auto-refresh

  const show = bindTabs();
  bindMapTab();
  bindSearch();
  bindTierFilters();
  bindShortcuts();
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if ($('#notify-modal').classList.contains('open')) closeNotify();
      else closeDrawer();
    }
  });

  document.querySelectorAll('[data-close]').forEach((n) =>
    n.addEventListener('click', closeDrawer));

  $('#banner-retry').addEventListener('click', () => loadAll());

  bindNotifyUI();
  refreshNotifyStatus();
  loadAll();
  // if the visitor's stored language is Malayalam, translate the initial paint
  translatePage();
});
