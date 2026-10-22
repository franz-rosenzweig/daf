/* Daf's taste: the real web app on sample data, with no server behind it.

   tools/build_taste.py puts this (with demo-seed.js before it) ahead of the app's own scripts. It
   stands in front of fetch and answers the app's api/ calls here in the browser: the sample library
   from demo-seed.js, a made-up reader's past year, and whatever you do in the demo, which is kept in
   this browser's localStorage (daftaste.v1) and nowhere else. Anything that needs the real server
   (sync, the Kindle, Audiobookshelf, Hardcover, Claude, read-aloud, accounts) answers that it isn't
   in the demo. Nothing here leaves the browser. */
(function(){
'use strict';
const SEED = window.DAF_SEED;
const KEY = 'daftaste.v1';
const APP = new URL('./', location.href);
const API = APP.pathname + 'api/';
const realFetch = window.fetch.bind(window);
const NOT_HERE = 'That needs Daf’s own server, so it isn’t in this demo.';

/* ---------- days, in this browser's own time ---------- */
const pad = n => String(n).padStart(2, '0');
const iso = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
const parse = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); };
const daysBetween = (a, b) => Math.round((parse(b) - parse(a)) / 86400000);
const nowSec = () => Math.floor(Date.now() / 1000);
const todayIso = () => iso(new Date());
const dayOf = t => iso(new Date(t * 1000));
const at = (day, h, m) => { const d = parse(day); d.setHours(h, m || 0, 0, 0); return Math.floor(d / 1000); };
const hhmm = t => { const d = new Date(t * 1000); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
const pyWeekday = s => (parse(s).getDay() + 6) % 7;                    // Monday = 0, as Python counts
const Y30 = '2026-10-09', Y29 = '2025-10-09', AGE35 = '2031-10-09';

/* ---------- small helpers ---------- */
function hash(str){                                                    // 16 hex digits, stable
  let a = 0x811c9dc5, b = 0x9e3779b9;
  for (let i = 0; i < str.length; i++) { const c = str.charCodeAt(i); a = Math.imul(a ^ c, 16777619); b = Math.imul(b ^ c, 2246822519) ^ (b >>> 13); }
  return ((a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0'));
}
function rng(seed){                                                    // mulberry32
  let t = parseInt(hash(seed).slice(0, 8), 16);
  return () => { t |= 0; t = t + 0x6D2B79F5 | 0; let r = Math.imul(t ^ t >>> 15, 1 | t); r = r + Math.imul(r ^ r >>> 7, 61 | r) ^ r; return ((r ^ r >>> 14) >>> 0) / 4294967296; };
}
const clone = x => JSON.parse(JSON.stringify(x));
const err = (status, detail) => Object.assign(new Error(detail), { status });
const LABELS = { kindle: 'Kindle', ebook: 'Books in Daf', manga: 'Manga in Daf', audio: 'Audiobooks', article: 'Articles in Daf', paper: 'Paper', podcast: 'Podcasts', video: 'Videos' };
const SOURCES = ['kindle', 'ebook', 'manga', 'audio', 'article', 'paper', 'podcast', 'video'];
const COLORS = ['yellow', 'green', 'blue', 'pink', 'purple'];
const BOOK_BY_ID = Object.fromEntries(SEED.books.map(b => [b.id, b]));
const TEXTS = SEED.articles.concat(SEED.feed || []);                 // the Feed only in the docs screenshots' build
const BLOCKS = Object.fromEntries(TEXTS.map(a => [a.id, a.blocks]));
if (SEED.docs) document.documentElement.classList.add('demo-docs');

/* ---------- the store: made once from the seed, then kept in this browser ---------- */
let db = load();
function load(){
  try { const d = JSON.parse(localStorage.getItem(KEY) || 'null'); if (d && d.v === 1) return d; } catch(e){}
  const d = fresh(); try { localStorage.setItem(KEY, JSON.stringify(d)); } catch(e){}
  return d;
}
let frozen = false;                                                   // after a reset, until the page reloads
function save(){ if (frozen) return; try { localStorage.setItem(KEY, JSON.stringify(db)); } catch(e){} }
function fresh(){
  const born = nowSec(), today = todayIso();
  let tz = 'America/Phoenix'; try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || tz; } catch(e){}
  const d = { v: 1, born, books: {}, docs: {}, hls: {}, rs: {}, reviewDays: {}, positions: {}, marks: {}, sessions: [], notes: [], cards: {}, shelves: {}, freq: {},
    settings: { home_tz: tz, count: { kindle: true, ebook: true, manga: true, audio: true, article: true, paper: true, podcast: false, video: false },
      review_size: 5, feed_expire_days: 30, tts_voice: 'af_heart', tts_speed: 1.0, cards_per_day: 5,
      nightstand: SEED.books.filter(b => b.nightstand).map(b => b.id), views: [], keys: {},
      tips: { off: false, seen: {}, news: SEED.news || '' }, library: { karakeep: 'off' }, public_url: 'https://daf.example.org' } };
  const back = (days, h, m) => at(addDays(today, -days), h, m);
  for (const b of SEED.books) {
    const k = b.kindle;
    d.books[b.id] = { id: b.id, title: b.title, author: b.author, kind: 'book', private: false, status: b.nightstand ? 'reading' : null,
      progress: k ? Math.round(k.page / k.total * 1000) / 10 : b.daf ? b.daf : null, progress_note: k ? 'page ' + k.page + ' of ' + k.total : b.daf ? b.daf + '% in Daf' : null,
      last_read: k ? back(k.days, 22, 10) : b.id === 'cal:2' ? back(1, 21, 30) : null, kindle_at: k ? back(k.days, 22, 10) : null,
      audio_pct: b.audio ? b.audio.pct : null, audio_note: b.audio ? b.audio.note : null };
    b.highlights.forEach((h, i) => {
      const id = 'k' + hash(b.id + '|' + h.text);
      let created = h.years_ago ? (() => { const x = parse(today); x.setFullYear(x.getFullYear() - h.years_ago); return Math.floor(x / 1000) + 21 * 3600 + 15 * 60; })() : back(h.days, 21 - (i % 3), 10 + i * 7);
      d.hls[id] = { id, book_id: b.id, source: h.source || 'kindle', text: h.text, note: h.note || null, chapter: h.chapter || null, page: h.page || null,
        created, pos: h.xp || null, color: h.color === 'yellow' ? null : h.color, deleted: false };
      if (h.tags || h.fav || h.user_note) d.rs[id] = { status: 'noted', interval: 0, due: null, reviews: 0, last: null, user_note: h.user_note || null, tags: h.tags || null, fav: h.fav ? 1 : null };
    });
  }
  for (const a of SEED.articles) {
    const s = a.state || {};
    d.docs[a.id] = { id: a.id, kind: 'article', where_: 'library', status: s.status || 'inbox', title: a.title, author: a.author, source: a.source, category: null,
      url: a.url, published: null, added: back(s.days || 0, 8, 20), words: a.words, summary: a.summary, thumb: null, progress: s.progress || 0,
      note: null, opened: s.progress ? back(s.days || 0, 20, 0) : null, tags: s.tags || [], starred: s.starred ? 1 : 0, ai_summary: null, duration: null, feed: null };
    (s.highlights || []).forEach((h, i) => {
      const id = 'd' + hash(a.id + '|' + h.pos.b + '|' + h.pos.s + '|' + h.text);
      d.hls[id] = { id, book_id: a.id, source: 'daf', text: h.text, note: null, chapter: null, page: null, created: back(h.days || 0, 20, 30 + i * 4), pos: h.pos,
        color: h.color === 'yellow' ? null : h.color, deleted: false };
      if (h.tags || h.fav || h.user_note) d.rs[id] = { status: 'noted', interval: 0, due: null, reviews: 0, last: null, user_note: h.user_note || null, tags: h.tags || null, fav: h.fav ? 1 : null };
    });
  }
  for (const f of SEED.feed || []) {
    d.docs[f.id] = { id: f.id, kind: 'article', where_: 'feed', status: 'unseen', title: f.title, author: f.author, source: f.source, category: f.folder,
      url: null, published: back(f.days || 0, f.hour || 9, 0), added: back(f.days || 0, f.hour || 9, 5), words: f.words, summary: f.summary, thumb: null, progress: 0,
      note: null, opened: null, tags: [], starred: 0, ai_summary: null, duration: null, feed: f.feed, full: 1 };
  }
  // The last three days' reviews were done: a streak to keep going.
  const ids = Object.keys(d.hls).filter(id => d.hls[id].text.length >= 30);
  [3, 2, 1].forEach((n, i) => {
    const day = addDays(today, -n), id = ids[(i * 5 + 3) % ids.length];
    d.reviewDays[day] = { ids: [id], done: { [id]: 'keep' } };
    d.rs[id] = Object.assign(d.rs[id] || { user_note: null, tags: null, fav: null }, { status: 'kept', interval: 4, due: addDays(day, 4), reviews: 1, last: day });
  });
  d.shelves['read-again'] = { id: 'read-again', name: 'Read again', created: back(20, 12), books: [{ book_id: 'cal:1', added: back(20, 12) }, { book_id: 'cal:2', added: back(19, 12) }] };
  return d;
}
// Reset the demo: the sample library as it was, and the app's own settings (theme, places) gone.
// Nothing this page still does before it reloads is kept.
window.DafTaste = { reset(){
  try { Object.keys(localStorage).filter(k => k.startsWith('daf.') || k.startsWith('daftaste.')).forEach(k => localStorage.removeItem(k)); } catch(e){}
  db = load(); frozen = true;
} };

/* ---------- a made-up reader's year: the same every time for a given day ---------- */
// Each day before today gets a few sittings from the sample library, from the seed's day. Year 29
// (the year before) is patchy; Year 30 mostly reaches the hour; the last five days all do.
const PICK = {
  kindle: [['cal:1', 'Meditations', 40], ['cal:3', 'Pride and Prejudice', 75]],
  ebook: [['cal:2', 'Walden, and On the Duty of Civil Disobedience', 21]],
  audio: [['cal:4', 'The Odyssey', 30]],
  article: SEED.articles.map(a => [a.id, a.title, (a.state && a.state.days) || 0]),
  paper: [[null, 'Paper', 9999]],
};
// Before the sample books were started, the made-up reader was on other old books (not in the library).
const EARLIER = {
  kindle: ['Middlemarch', 'Moby-Dick', 'Jane Eyre', 'The Count of Monte Cristo', 'Great Expectations'],
  ebook: ['Little Women', 'Persuasion'], audio: ['Treasure Island', 'The Hound of the Baskervilles'], article: ['Self-Reliance', 'Walking'],
};
const madeCache = {};
function madeUp(day){
  if (madeCache[day]) return madeCache[day];
  const today = todayIso(), r = rng('daf-taste|' + day), out = [];
  if (day >= today || day < Y29) return (madeCache[day] = out);
  const ago = daysBetween(day, today);
  let total;
  if (day >= Y30 || ago <= 20) {
    if (ago <= 5) total = 62 + Math.round(r() * 30);
    else if (ago === 6) total = 34;
    else { const x = r(); total = x < 0.04 ? 0 : x < 0.16 ? 12 + Math.round(r() * 20) : x < 0.32 ? 35 + Math.round(r() * 22) : 60 + Math.round(r() * 40); }
  } else {
    const x = r(); total = x < 0.52 ? 0 : x < 0.8 ? 6 + Math.round(r() * 24) : 30 + Math.round(r() * 45);
  }
  if (!total) return (madeCache[day] = out);
  const n = total < 25 ? 1 : total < 60 ? 2 : 2 + Math.round(r());
  const slots = [[6, 40], [12, 30], [18, 50], [21, 20]].sort(() => r() - 0.5).slice(0, n).sort((a, b) => a[0] - b[0]);
  const srcs = ['kindle', 'kindle', 'ebook', 'audio', 'article', 'paper', 'kindle'];
  let left = total;
  slots.forEach((s, i) => {
    const mins = i === slots.length - 1 ? left : Math.max(5, Math.round(total / n * (0.7 + r() * 0.6)));
    left = Math.max(0, left - mins); if (mins < 1) return;
    const src = srcs[Math.floor(r() * srcs.length)], now = PICK[src].filter(p => p[2] >= ago), x = r();
    const pick = now.length ? now[Math.floor(x * now.length)] : [null, EARLIER[src][Math.floor(x * EARLIER[src].length)]];
    const start = at(day, s[0], s[1] + Math.floor(r() * 25));
    out.push({ source: src, item: pick[0], title: pick[1], start, seconds: mins * 60, made: true, note: null });
  });
  return (madeCache[day] = out);
}
// Today so far: a sitting this morning, one at lunch and one in the evening, as far as the clock has got.
function madeToday(){
  const day = todayIso(), now = nowSec(), out = [];
  const plan = [[7, 5, 18, 'kindle', 'cal:1', 'Meditations'], [12, 40, 9, 'article', SEED.articles[1].id, SEED.articles[1].title], [18, 10, 14, 'audio', 'cal:4', 'The Odyssey']];
  for (const p of plan) { const start = at(day, p[0], p[1]); if (start + p[2] * 60 + 300 <= now) out.push({ source: p[3], item: p[4], title: p[5], start, seconds: p[2] * 60, made: true, note: null }); }
  if (!out.length && now - at(day, 0) > 25 * 60) out.push({ source: 'kindle', item: 'cal:1', title: 'Meditations', start: now - 22 * 60, seconds: 12 * 60, made: true, note: null });
  return out;
}
function sessionsOn(day){
  const made = day === todayIso() ? madeToday() : madeUp(day);
  return made.concat(db.sessions.filter(s => (s.start ? dayOf(s.start) : s.day) === day));
}
function kindleNote(s){
  if (s.source !== 'kindle') return s.note;
  const b = SEED.books.find(x => x.id === s.item), k = b && b.kindle; if (!k) return s.note;
  const back = daysBetween(dayOf(s.start), todayIso());
  return 'page ' + Math.max(1, k.page - back * 4) + ' of ' + k.total;
}

/* ---------- goals (daf/goals.py, the parts the demo needs) ---------- */
const KINDS = {
  minutes: { label: 'Reading time', unit: ['minute', 'minutes'], periods: ['day', 'week', 'month'], default: { day: 60, week: 420, month: 1800 }, range: { day: [5, 300, 5], week: [30, 2100, 15], month: [60, 9000, 60] } },
  pages: { label: 'Pages', unit: ['page', 'pages'], periods: ['day', 'week'], default: { day: 30, week: 200 }, range: { day: [5, 400, 5], week: [20, 2500, 10] } },
  books: { label: 'Books', unit: ['book', 'books'], periods: ['y30', 'year', 'by35'], default: { y30: 24, year: 24, by35: 120 }, range: { y30: [1, 150, 1], year: [1, 150, 1], by35: [5, 600, 5] } },
  days: { label: 'Days with reading', unit: ['day', 'days'], periods: ['week'], default: { week: 5 }, range: { week: [1, 7, 1] } },
  streak: { label: 'A streak at the goal', unit: ['day in a row', 'days in a row'], periods: ['run'], default: { run: 30 }, range: { run: [3, 365, 1] } },
  highlights: { label: 'Highlights', unit: ['highlight', 'highlights'], periods: ['week'], default: { week: 10 }, range: { week: [1, 300, 1] } },
  reviews: { label: 'The daily review', unit: ['day', 'days'], periods: ['week'], default: { week: 5 }, range: { week: [1, 7, 1] } },
};
const GDEFAULTS = [
  { id: 'minutes', period: 'day', target: 60, on: true, main: true }, { id: 'pages', period: 'week', target: 200, on: false },
  { id: 'books', period: 'y30', target: 24, on: false, manga: false }, { id: 'days', period: 'week', target: 5, on: false },
  { id: 'streak', period: 'run', target: 30, on: false }, { id: 'highlights', period: 'week', target: 10, on: false }, { id: 'reviews', period: 'week', target: 5, on: false }];
const PRESETS = {
  gentle: { label: 'Gentle', text: 'Half an hour a day, five days a week.', goals: { minutes: { period: 'day', target: 30, on: true }, days: { period: 'week', target: 5, on: true } } },
  year30: { label: 'Year 30', text: 'An hour a day, and two books a month.', goals: { minutes: { period: 'day', target: 60, on: true }, books: { period: 'y30', target: 24, on: true } } },
  deep: { label: 'Deep', text: 'An hour and a half a day, three books a month.', goals: { minutes: { period: 'day', target: 90, on: true }, books: { period: 'y30', target: 36, on: true } } },
};
const BEGINNING = '2000-01-01';
function cleanTarget(kind, period, v){
  const [lo, hi, step] = KINDS[kind].range[period]; v = Number(v); if (!isFinite(v)) return KINDS[kind].default[period];
  v = Math.max(lo, Math.min(hi, v)); return Math.round(v / step) * step;
}
function allGoals(){
  const saved = Object.fromEntries((db.settings.goals || []).map(g => [g.id, g]));
  const has = Object.keys(saved).length > 0;
  const out = GDEFAULTS.map(dft => {
    const g = Object.assign({}, dft), s = saved[dft.id] || {}, kind = dft.id;
    if (KINDS[kind].periods.includes(s.period)) g.period = s.period;
    if ('target' in s) g.target = cleanTarget(kind, g.period, s.target);
    if (typeof s.on === 'boolean') g.on = s.on;
    if (kind === 'books') g.manga = !!s.manga;
    g.main = has ? !!s.main : !!dft.main;
    g.history = (s.history || []).filter(h => h && typeof h.from === 'string').sort((a, b) => a.from < b.from ? -1 : 1);
    if (!g.history.length) g.history = [{ from: BEGINNING, period: g.period, target: g.target, on: g.on }];
    g.kind = kind;
    return g;
  });
  const mains = out.filter(g => g.main && g.on); out.forEach(g => { g.main = false; });
  (mains[0] || out.find(g => g.on) || out[0]).main = true;
  return out;
}
const effective = (g, day) => { let cur = g.history[0]; for (const h of g.history) if (h.from <= day) cur = h; return cur; };
const perDay = e => Math.round((e.period === 'day' ? e.target : e.period === 'week' ? e.target / 7 : e.target / 30) * 10) / 10;
const minutesGoal = day => perDay(effective(allGoals().find(g => g.id === 'minutes'), day || todayIso()));
function saveGoals(incoming){
  const cur = Object.fromEntries(allGoals().map(g => [g.id, g])), day = todayIso();
  const by = Object.fromEntries(incoming.filter(x => x && cur[x.id]).map(x => [x.id, x]));
  if (Object.values(by).some(x => x.main)) Object.values(cur).forEach(g => { g.main = false; });
  for (const [gid, x] of Object.entries(by)) {
    const g = cur[gid];
    if (KINDS[gid].periods.includes(x.period) && x.period !== g.period) { g.period = x.period; if (!('target' in x)) g.target = KINDS[gid].default[g.period]; }
    if ('target' in x) g.target = cleanTarget(gid, g.period, x.target);
    if (typeof x.on === 'boolean') g.on = x.on;
    if (gid === 'books' && typeof x.manga === 'boolean') g.manga = x.manga;
    if (x.main) { g.main = true; g.on = true; }
  }
  for (const g of Object.values(cur)) {
    const last = g.history[g.history.length - 1], now = { from: day, period: g.period, target: g.target, on: g.on };
    if (last.period !== g.period || last.target !== g.target || last.on !== g.on) {
      if (last.from === day && g.history.length > 1) g.history[g.history.length - 1] = now;
      else if (last.from === day) g.history[g.history.length - 1] = Object.assign(now, { from: last.from });
      else g.history.push(now);
    }
  }
  db.settings.goals = Object.values(cur).map(g => ({ id: g.id, period: g.period, target: g.target, on: g.on, main: g.main, history: g.history, manga: g.manga }));
  save();
}
function periodRange(period, t){
  if (period === 'day') return [t, t];
  if (period === 'week') { const a = addDays(t, -((pyWeekday(t) + 1) % 7)); return [a, addDays(a, 6)]; }
  if (period === 'month') { const d = parse(t); const a = iso(new Date(d.getFullYear(), d.getMonth(), 1)); return [a, iso(new Date(d.getFullYear(), d.getMonth() + 1, 0))]; }
  if (period === 'year') { const y = parse(t).getFullYear(); return [y + '-01-01', y + '-12-31']; }
  if (period === 'y30') { const a = ystart(t); return [a, addDays(String(+a.slice(0, 4) + 1) + a.slice(4), -1)]; }
  if (period === 'by35') return [Y30, addDays(AGE35, -1)];
  return [t, t];
}
function ystart(t){ const y = +t.slice(0, 4), b = y + Y30.slice(4); return t >= b ? b : (y - 1) + Y30.slice(4); }
function periodWords(period, t){
  if (period === 'y30') { const n = 30 + (+ystart(t).slice(0, 4) - +Y30.slice(0, 4)); return ['in Year ' + n, 'in Year ' + n]; }
  return { day: ['a day', 'today'], week: ['a week', 'this week'], month: ['a month', 'this month'], year: ['a year', 'in ' + t.slice(0, 4)], by35: ['by 35', 'since 30'], run: ['in a row', 'now'] }[period];
}
const unitOf = (kind, n) => KINDS[kind].unit[n === 1 ? 0 : 1];
function progress(g, t){
  t = t || todayIso();
  const [a, b] = periodRange(g.period, t), upto = b < t ? b : t, kind = g.kind, target = g.target;
  let done = 0;
  if (kind === 'minutes') done = Math.round(gridVals(a, daysBetween(a, upto) + 1).reduce((x, y) => x + y, 0));
  else if (kind === 'pages') { for (let d = a; d <= upto; d = addDays(d, 1)) done += Math.round(sessionsOn(d).filter(s => ['kindle', 'ebook', 'paper'].includes(s.source)).reduce((x, s) => x + s.seconds, 0) / 60 * 0.8); }
  else if (kind === 'days') done = gridVals(a, daysBetween(a, upto) + 1).filter(v => v >= 1).length;
  else if (kind === 'streak') done = streaks().goal;
  else if (kind === 'highlights') done = liveHls().filter(h => dayOf(h.created) >= a && dayOf(h.created) <= upto).length;
  else if (kind === 'reviews') done = reviewDaysDone(a, upto).length;
  const [goalWords, nowWords] = periodWords(g.period, t), unit = unitOf(kind, target);
  let text, label;
  if (kind === 'streak') { text = done + ' of ' + target + ' days in a row at the goal'; label = target + ' days in a row at the goal'; }
  else if (kind === 'reviews') { text = 'The review on ' + done + ' of ' + target + ' days ' + nowWords; label = 'The review ' + target + ' ' + unit + ' ' + goalWords; }
  else if (kind === 'days') { text = 'Reading on ' + done + ' of ' + target + ' days ' + nowWords; label = 'Reading ' + target + ' ' + unit + ' ' + goalWords; }
  else { text = done + ' of ' + target + ' ' + unit + ' ' + nowWords; label = target + ' ' + unit + ' ' + goalWords; }
  return { id: g.id, kind, label, unit: KINDS[kind].unit[1], done, target, period: g.period, period_label: nowWords, met: done >= target, main: g.main, on: g.on,
    pct: target ? Math.round(Math.min(1, done / target) * 100) : 0, text, key: g.id + ':' + a + ':' + target, from: a, to: b };
}
function goalsOut(){
  const t = todayIso();
  return { today: t, goals: allGoals().map(g => Object.assign(progress(g, t), { history: g.history })),
    kinds: Object.fromEntries(Object.entries(KINDS).map(([k, v]) => [k, { label: v.label, unit: v.unit, periods: v.periods.map(p => ({ id: p, words: periodWords(p, t)[0] })), default: v.default, range: v.range }])),
    presets: PRESETS, pace: pace(), milestones: milestones(), minutes_day: minutesGoal(t) };
}
function pace(){
  const t = todayIso(), vals = gridVals(addDays(t, -59), 60), st = streaks();
  const stand = standBooks();
  const left = stand.reduce((x, b) => x + Math.max(0, 100 - (b.progress || 0)) / 100 * 540, 0);
  const sun = addDays(t, -((pyWeekday(t) + 1) % 7));
  const wk = []; for (let i = 0; i < 4; i++) { const a = addDays(sun, -7 * (i + 1)); wk.push(gridVals(a, 7).filter(v => v >= 1).length); }
  const hl8 = liveHls().filter(h => dayOf(h.created) >= addDays(sun, -56) && dayOf(h.created) < sun).length;
  const [ya] = periodRange('y30', t);
  return { avg_day: Math.round(vals.slice(-30).reduce((a, b) => a + b, 0) / 30 * 10) / 10, week: Math.round(vals.slice(-7).reduce((a, b) => a + b, 0)), pages_per_minute: 0.8,
    minutes_per_book: 540, nightstand_left: Math.round(left), nightstand_books: stand.length, days_week: Math.round(wk.reduce((a, b) => a + b, 0) / 4 * 10) / 10,
    highlights_week: Math.round(hl8 / 8 * 10) / 10, reviews_week: Math.round(reviewDaysDone(addDays(sun, -28), addDays(sun, -1)).length / 4 * 10) / 10,
    streak: st.goal, best_streak: st.best_goal, books_y30: 0, books_since30: 0, book_basis: 'a typical book of about nine hours', today: t,
    y30_days_left: daysBetween(t, periodRange('y30', t)[1]) + 1, days_to_35: daysBetween(t, AGE35), y30_from: ya };
}
function milestones(){
  const t = todayIso(); if (t < Y30) return [];
  const n = daysBetween(Y30, t) + 1, vals = gridVals(Y30, n), targets = targetsFrom(Y30, n), out = [];
  let run = 0, cum = 0, best = 0; const rh = {}, rs = {};
  vals.forEach((v, i) => {
    cum += v; const day = addDays(Y30, i);
    [10, 50, 100, 200, 365].forEach(h => { if (!rh[h] && cum / 60 >= h) rh[h] = day; });
    run = v >= targets[i] ? run + 1 : 0; best = Math.max(best, run);
    [7, 30, 100, 365].forEach(s => { if (!rs[s] && run >= s) rs[s] = day; });
  });
  const hours = Math.round(cum / 6) / 10;
  [10, 50, 100, 200, 365].forEach(h => out.push({ id: 'hours' + h, label: h + ' hours in Year 30', reached: rh[h] || null, done: Math.min(hours, h), target: h, family: 'hours' }));
  [1, 10, 25, 50].forEach(b => out.push({ id: 'books' + b, label: b === 1 ? 'The first book finished in Year 30' : b + ' books in Year 30', reached: null, done: 0, target: b, family: 'books' }));
  [7, 30, 100, 365].forEach(s => out.push({ id: 'streak' + s, label: s + ' days in a row at the goal', reached: rs[s] || null, done: Math.min(best, s), target: s, family: 'streak' }));
  const rd = reviewDaysDone(Y30, t);
  [30, 100].forEach(r => out.push({ id: 'review' + r, label: 'The daily review on ' + r + ' days', reached: rd.length >= r ? rd[r - 1] : null, done: Math.min(rd.length, r), target: r, family: 'review' }));
  return out;
}

/* ---------- minutes: days, the grids, streaks ---------- */
const counted = s => !!db.settings.count[s.source];
function dayMinutes(day){ return sessionsOn(day).filter(counted).reduce((x, s) => x + s.seconds / 60, 0); }
function gridVals(start, n){ const out = []; for (let i = 0; i < n; i++) out.push(Math.round(dayMinutes(addDays(start, i)) * 10) / 10); return out; }
function targetsFrom(start, n){ const g = allGoals().find(x => x.id === 'minutes'), out = []; for (let i = 0; i < n; i++) out.push(perDay(effective(g, addDays(start, i)))); return out; }
function grid(start, days){
  days = days || 365;
  const vals = gridVals(start, days), targets = targetsFrom(start, days), t = todayIso(), ti = daysBetween(start, t);
  return { start, weekday: pyWeekday(start), days: vals, elapsed: Math.max(0, Math.min(days, ti + 1)), today_index: ti >= 0 && ti < days ? ti : null,
    total_hours: Math.round(vals.reduce((a, b) => a + b, 0) / 6) / 10, days_read: vals.filter(v => v >= 1).length,
    days_goal: vals.filter((v, i) => v >= targets[i]).length, targets };
}
function streaks(){
  const t = todayIso(), start = addDays(t, -399), g = grid(start, 400), vals = g.days, ti = g.today_index;
  const met = vals.map((v, i) => v >= g.targets[i]);
  const run = (arr, test) => { let i = ti; if (!test(arr[i])) i--; let n = 0; while (i >= 0 && test(arr[i])) { n++; i--; } return n; };
  const best = (arr, test) => { let b = 0, c = 0; for (const v of arr) { c = test(v) ? c + 1 : 0; b = Math.max(b, c); } return b; };
  return { goal: run(met, Boolean), any: run(vals, v => v >= 1), best_goal: best(met, Boolean), best_any: best(vals, v => v >= 1), vals, today_index: ti };
}

/* ---------- books ---------- */
function bookCard(b){
  const p = db.positions[b.id], inDaf = p && !BOOK_BY_ID[b.id].kindle ? Math.round(p.fraction * 100) : null;
  return { id: b.id, title: b.title, author: b.author, progress: inDaf != null ? inDaf : b.progress, progress_note: inDaf != null ? inDaf + '% in Daf' : b.progress_note, last_read: lastRead(b), audio_pct: b.audio_pct,
    audio_note: b.audio_note, vault_path: null, status: b.status, kind: 'book', url: null, has_cover: true };
}
function lastRead(b){
  const mine = db.sessions.filter(s => s.item === b.id).map(s => s.start + s.seconds), p = db.positions[b.id];
  return Math.max(b.last_read || 0, ...mine, p ? p.updated : 0) || null;
}
const standBooks = () => (db.settings.nightstand || []).map(id => db.books[id]).filter(Boolean);
const readable = id => !!BOOK_BY_ID[id];
function hlCount(id){ return liveHls().filter(h => h.book_id === id).length; }
function bookStats(id, progressPct, dafFrac){
  const t = todayIso(), rows = [];
  for (let i = 0; i < 400; i++) { const day = addDays(t, -i); for (const s of sessionsOn(day)) if (s.item === id) rows.push([day, s]); }
  if (!rows.length) return null;
  const bySrc = {}, perDay = {};
  rows.forEach(([day, s]) => { bySrc[s.source] = (bySrc[s.source] || 0) + s.seconds / 60; perDay[day] = (perDay[day] || 0) + s.seconds / 60; });
  const days = Object.keys(perDay).sort(), last30 = []; for (let i = 29; i >= 0; i--) last30.push(Math.round((perDay[addDays(t, -i)] || 0) * 10) / 10);
  const total = Object.values(bySrc).reduce((a, b) => a + b, 0);
  const out = { minutes: Math.round(total), by_source: Object.fromEntries(Object.entries(bySrc).map(([k, v]) => [k, Math.round(v)])), sittings: rows.length, days: days.length,
    first: days[0], last: days[days.length - 1], last30 };
  const frac = dafFrac != null && dafFrac > 0.02 ? dafFrac : progressPct != null && progressPct > 2 ? progressPct / 100 : null;
  const readMin = (bySrc.kindle || 0) + (bySrc.ebook || 0);
  if (frac && frac < 0.985 && readMin >= 20) {
    const left = readMin / frac * (1 - frac); out.minutes_left = Math.round(left);
    const recent = last30.slice(-14).reduce((a, b) => a + b, 0) / 14;
    if (recent >= 2) { out.finish = addDays(t, Math.max(1, Math.round(left / recent))); out.recent_per_day = Math.round(recent); }
  }
  return out;
}

/* ---------- highlights ---------- */
const liveHls = () => Object.values(db.hls).filter(h => !h.deleted);
const docIds = () => new Set(Object.keys(db.docs));
function posOf(h){ const p = h.pos; return p && typeof p === 'object' ? p : typeof p === 'string' && p ? { xp: p } : {}; }
function order(h){
  const p = posOf(h);
  if (p.fraction != null) return p.fraction * 1e6;
  if (p.b != null) return p.b * 1e4 + (p.s || 0);
  if (h.page) return h.page * 1000;
  const m = /DocFragment\[(\d+)\]/.exec(p.xp || ''); if (m) return +m[1] * 1e5;
  return (h.created || 0) / 1e4;
}
function openOf(h){
  const q = encodeURIComponent;
  if (db.docs[h.book_id]) return '#read/' + q(h.book_id) + '/hl:' + q(h.id);
  if (readable(h.book_id)) return '#ebook/' + q(h.book_id) + '/hl:' + q(h.id);
  return '#book/' + q(h.book_id) + '/hl:' + q(h.id);
}
function row(h){
  const s = db.rs[h.id] || {}, b = db.books[h.book_id], d = db.docs[h.book_id];
  return { id: h.id, book_id: h.book_id, source: h.source, text: h.text, note: h.note, chapter: h.chapter, page: h.page, created: h.created, pos: h.pos, color: h.color,
    user_note: s.user_note || null, r_status: s.status || null, due: s.due || null, tags: s.tags || [], fav: s.fav ? 1 : 0,
    cards: Object.values(db.cards).filter(c => c.hl_id === h.id).length, book_title: b ? b.title : d ? d.title : null, book_author: b ? b.author : d ? d.author : null,
    private: 0, kind: b ? 'book' : 'article', vault_path: null, calibre_path: b ? 'yes' : null, open: openOf(h), order: order(h) };
}
const HLSRC = { kindle: h => h.source === 'kindle', daf: h => h.source === 'epub' || h.source === 'daf', articles: h => !!db.docs[h.book_id],
  audio: h => h.source === 'audiobookshelf' || h.source === 'clip', paper: h => h.source === 'paper', readwise: h => h.source === 'readwise' };
function hlRows(q){
  q = q || new URLSearchParams();
  const book = q.get('book'), source = q.get('source'), color = q.get('color'), tag = q.get('tag'), fav = q.get('fav') === '1', text = (q.get('q') || '').toLowerCase();
  let rows = liveHls().map(row);
  if (book) rows = rows.filter(r => r.book_id === book);
  if (HLSRC[source]) rows = rows.filter(r => HLSRC[source](r));
  if (COLORS.includes(color)) rows = rows.filter(r => (r.color || 'yellow') === color);
  if (tag) rows = rows.filter(r => r.tags.includes(tag));
  if (fav) rows = rows.filter(r => r.fav);
  if (text) rows = rows.filter(r => [r.text, r.note, r.user_note, r.book_title, r.book_author, r.tags.join(' ')].some(x => String(x || '').toLowerCase().includes(text)));
  return rows;
}
function allTags(){
  const n = {}; for (const h of liveHls()) for (const t of ((db.rs[h.id] || {}).tags || [])) n[t] = (n[t] || 0) + 1;
  return Object.keys(n).sort((a, b) => n[b] - n[a] || (a < b ? -1 : 1));
}
const cleanTags = tags => [...new Set((tags || []).map(t => String(t).trim().replace(/^#/, '').toLowerCase().replace(/[^\p{L}\p{N}_/-]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 40)).filter(Boolean))].slice(0, 12);
function state(id){ return db.rs[id] || (db.rs[id] = { status: 'noted', interval: 0, due: null, reviews: 0, last: null, user_note: null, tags: null, fav: null }); }
function addHighlight(bookId, src, text, pos, extra){
  const id = (src === 'epub' ? 'e' : 'd') + hash(bookId + '|' + JSON.stringify(pos) + '|' + text);
  const h = { id, book_id: bookId, source: src, text, note: null, chapter: (extra && extra.chapter) || null, page: null, created: nowSec(), pos, color: (extra && extra.color && extra.color !== 'yellow') ? extra.color : null, deleted: false };
  const olds = ((extra && extra.replaces) || []).map(x => db.hls[x]).filter(o => o && !o.deleted && o.id !== id && (o.source === 'epub' || o.source === 'daf'));
  db.hls[id] = h;
  if (olds.length) {                                                    // review.carry: notes, tags, favorite and history come along
    olds.forEach(o => { o.deleted = true; });
    const ss = olds.map(o => db.rs[o.id]).filter(Boolean);
    if (ss.length) {
      const s = state(id), notes = ss.map(x => x.user_note).filter(Boolean), tags = ss.flatMap(x => x.tags || []);
      s.user_note = [...new Set([s.user_note, ...notes].filter(Boolean))].join('\n\n') || null;
      s.tags = cleanTags((s.tags || []).concat(tags)); if (!s.tags.length) s.tags = null;
      if (ss.some(x => x.fav)) s.fav = 1;
      const hist = ss.find(x => x.status && x.status !== 'noted'); if (hist) Object.assign(s, { status: hist.status, interval: hist.interval, due: hist.due, reviews: hist.reviews, last: hist.last });
    }
  }
  save();
  return id;
}

/* ---------- the daily review (daf/review.py) ---------- */
function candidates(){
  return liveHls().filter(h => h.text && h.text.length >= 30 && !/^!\[/.test(h.text)).map(h => ({ h, s: db.rs[h.id] || {} }));
}
function buildDay(day){
  if (db.reviewDays[day]) return db.reviewDays[day].ids;
  const size = db.settings.review_size || 5, freq = db.freq, t = todayIso();
  const taken = new Set(); for (const [k, v] of Object.entries(db.reviewDays)) if (k >= t && k < day) v.ids.forEach(i => taken.add(i));
  const cands = candidates().filter(c => freq[c.h.book_id] !== 'never' && !taken.has(c.h.id));
  const night = new Set(db.settings.nightstand || []);
  const due = cands.filter(c => c.s.due && c.s.due <= day).sort((a, b) => a.s.due < b.s.due ? -1 : 1);
  const fresh = cands.filter(c => !c.s.status || c.s.status === 'noted');
  const r = rng('review|' + day), now = nowSec();
  const weight = c => { let w = 1; if (night.has(c.h.book_id)) w *= 3; if (c.h.created && now - c.h.created < 60 * 86400) w *= 2; if (c.h.note) w *= 1.5; if (c.s.fav) w *= 2;
    const f = freq[c.h.book_id]; if (f === 'more') w *= 2.5; else if (f === 'less') w *= 0.35; return w; };
  const picked = [], per = {};
  const take = c => { if (picked.length >= size || (per[c.h.book_id] || 0) >= 2 || picked.includes(c.h.id)) return; picked.push(c.h.id); per[c.h.book_id] = (per[c.h.book_id] || 0) + 1; };
  due.filter(c => freq[c.h.book_id] !== 'less').slice(0, 3).forEach(take);
  const pool = fresh.slice();
  while (pool.length && picked.length < size) {
    const ws = pool.map(weight), sum = ws.reduce((a, b) => a + b, 0); let x = r() * sum, k = 0;
    while (k < pool.length - 1 && x > ws[k]) { x -= ws[k]; k++; }
    take(pool.splice(k, 1)[0]);
  }
  due.slice(3).forEach(take);
  db.reviewDays[day] = { ids: picked, done: {} }; save();
  return picked;
}
function reviewStreak(){
  const t = todayIso(), fin = d => { const x = db.reviewDays[d]; return !!x && x.ids.length > 0 && x.ids.every(i => x.done[i]); };
  let d = t, n = 0; if (!fin(d)) d = addDays(d, -1); while (fin(d)) { n++; d = addDays(d, -1); }
  const week = []; for (let k = 0; k < 7; k++) { const day = addDays(t, -(6 - k)); week.push({ date: day, done: fin(day) }); }
  return { days: n, week };
}
function reviewDaysDone(a, b){ return Object.entries(db.reviewDays).filter(([d, x]) => d >= a && d <= b && x.ids.length && x.ids.every(i => x.done[i])).map(([d]) => d).sort(); }
function pub(h, action){
  const s = db.rs[h.id] || {}, b = db.books[h.book_id], d = db.docs[h.book_id];
  return { id: h.id, text: h.text, note: h.note, user_note: s.user_note || null, book_id: h.book_id, title: b ? b.title : d ? d.title : null, author: b ? b.author : d ? d.author : null,
    kind: b ? 'book' : 'article', source: h.source, chapter: h.chapter, page: h.page, created: h.created, reviews: s.reviews || 0, action: action || null, color: h.color,
    pos: h.pos, tags: s.tags || [], fav: !!s.fav, open: openOf(h) };
}
function dayItems(day){
  day = day || todayIso();
  const ids = buildDay(day), done = (db.reviewDays[day] || {}).done || {};
  const items = ids.map(i => db.hls[i]).filter(h => h && !h.deleted).map(h => pub(h, done[h.id]));
  return { date: day, items, done: items.filter(x => x.action).length, total: items.length, streak: reviewStreak() };
}
function reviewAct(id, action, note, at){
  const day = at && Math.abs(nowSec() - at) < 7 * 86400 ? dayOf(at) : todayIso();
  const s = state(id); let interval = s.interval || 0, status;
  if (action === 'keep' || action === 'note') { interval = interval <= 0 ? 4 : Math.min(365, Math.round(interval * 2.5)); status = 'kept'; }
  else if (action === 'less') { interval = Math.max(120, interval * 4); status = 'less'; }
  else if (action === 'later') { interval = 1; status = s.status && s.status !== 'noted' ? s.status : 'kept'; }
  else if (action === 'never') { interval = 0; status = 'never'; }
  else if (action === 'back') { interval = 4; status = 'kept'; }
  else throw err(400, 'Unknown action');
  Object.assign(s, { status, interval, due: status !== 'never' ? addDays(day, interval) : null, reviews: (s.reviews || 0) + 1, last: day });
  if (note != null) s.user_note = String(note).trim() || null;
  if (db.reviewDays[day]) db.reviewDays[day].done[id] = action;
  save();
  return { due: s.due, interval };
}

/* ---------- flashcards (daf/cards.py) ---------- */
const CLOZE = /\{\{(.+?)\}\}/gs;
function cardRow(c){ return Object.assign({}, c, { blanks: c.kind === 'cloze' ? [...c.front.matchAll(CLOZE)].map(m => m[1]) : [] }); }
function cardsDue(){
  const t = todayIso(), list = Object.values(db.cards).filter(c => db.hls[c.hl_id] && !db.hls[c.hl_id].deleted);
  const ext = c => { const h = db.hls[c.hl_id], b = db.books[h.book_id], d = db.docs[h.book_id];
    return Object.assign(cardRow(c), { hl_text: h.text, book_id: h.book_id, chapter: h.chapter, page: h.page, title: b ? b.title : d ? d.title : null, author: b ? b.author : d ? d.author : null, open: openOf(h) }); };
  const reviews = list.filter(c => c.due && c.due <= t).sort((a, b) => a.due < b.due ? -1 : 1).map(ext);
  const seenNew = list.filter(c => c.first_seen === t).length, nNew = Math.max(0, (db.settings.cards_per_day || 5) - seenNew);
  return reviews.concat(list.filter(c => !c.due).sort((a, b) => a.created - b.created).slice(0, nNew).map(ext));
}

/* ---------- the Library (daf/reader.py) ---------- */
const MINS = d => d.duration ? d.duration / 60 : (d.words || 0) / 238;
const docMins = d => d.duration ? Math.round(d.duration / 60) : d.words ? Math.max(1, Math.round(d.words / 238)) : null;
function listDocs(q){
  const where = q.get('where') || 'feed', tab = q.get('tab') || (where === 'feed' ? 'unseen' : 'inbox'), kind = q.get('kind'), sort = q.get('sort') || 'new';
  let xs = Object.values(db.docs).filter(d => d.where_ === where && d.status !== 'deleted');
  if (where === 'feed') { xs = xs.filter(d => d.status === (tab === 'seen' ? 'seen' : 'unseen')); if (q.get('cat')) xs = xs.filter(d => d.category === q.get('cat')); if (q.get('feed')) xs = xs.filter(d => d.feed === q.get('feed')); }
  else if (kind === 'starred') xs = xs.filter(d => d.starred && d.status !== 'archive');
  else { xs = xs.filter(d => d.status === tab); if (kind) xs = xs.filter(d => d.kind === kind); }
  const src = q.get('source'), author = q.get('author'), minlen = +q.get('minlen') || 0, maxlen = +q.get('maxlen') || 0, since = +q.get('since') || 0;
  if (src) xs = xs.filter(d => d.source === src);
  if (author) xs = xs.filter(d => String(d.author || '').toLowerCase().includes(author.toLowerCase()));
  if (minlen) xs = xs.filter(d => MINS(d) >= minlen);
  if (maxlen) xs = xs.filter(d => MINS(d) < maxlen);
  if (since) xs = xs.filter(d => d.added >= nowSec() - since * 86400);
  if (q.get('hl')) xs = xs.filter(d => liveHls().some(h => h.book_id === d.id));
  if (q.get('fresh')) xs = xs.filter(d => (d.progress || 0) < 1);
  const by = { new: (a, b) => b.added - a.added, old: (a, b) => a.added - b.added, published: (a, b) => (b.published || b.added) - (a.published || a.added),
    short: (a, b) => MINS(a) - MINS(b), long: (a, b) => MINS(b) - MINS(a), progress: (a, b) => ((b.progress > 0 && b.progress < 98) - (a.progress > 0 && a.progress < 98)) || b.progress - a.progress || b.added - a.added };
  xs.sort(by[sort] || by.new);
  return xs.map(d => Object.assign(docPublic(d), { highlights: liveHls().filter(h => h.book_id === d.id && h.source === 'daf').length, mins: docMins(d), expired: false }));
}
function docPublic(d){ return Object.assign({}, d, { tags: JSON.stringify(d.tags || []) }); }
function counts(){
  const lib = {}; Object.values(db.docs).filter(d => d.where_ === 'library' && d.status === 'inbox').forEach(d => { lib[d.kind] = (lib[d.kind] || 0) + 1; });
  const feed = {}; Object.values(db.docs).filter(d => d.where_ === 'feed' && d.status === 'unseen').forEach(d => { feed[d.category || ''] = (feed[d.category || ''] || 0) + 1; });
  return { feed, feed_total: Object.values(feed).reduce((a, b) => a + b, 0), freshrss_unread: null, expired_in_daf: 0, library: lib, emails_on: false,
    starred: Object.values(db.docs).filter(d => d.where_ === 'library' && d.starred && !['archive', 'deleted'].includes(d.status)).length };
}
function getDoc(id){
  const d = db.docs[id]; if (!d) throw err(404, 'Not found');
  if (!d.opened) { d.opened = nowSec(); save(); }
  return Object.assign(docPublic(d), { blocks: BLOCKS[id] || [], has_pdf: false, mins: docMins(d), counted: !!db.settings.count.article,
    highlights: liveHls().filter(h => h.book_id === id).sort((x, y) => x.created - y.created).map(h => ({ id: h.id, text: h.text, pos: h.pos, created: h.created, color: h.color, source: h.source,
      user_note: (db.rs[h.id] || {}).user_note || null })), asks: [], vault_path: null, kindle_sent: null,
    questions: ['Summarize this', 'What’s the main argument?', 'What should I remember from this?'] });
}
function home(){
  const now = nowSec(), out = {};
  const card = d => ({ type: 'doc', id: d.id, kind: d.kind, title: d.title, author: d.author, source: d.source, thumb: null, mins: docMins(d), progress: d.progress || 0, href: '#read/' + d.id });
  const bcard = b => { const p = db.positions[b.id]; const prog = p ? Math.round(p.fraction * 1000) / 10 : (b.progress || 0);
    return { type: 'book', id: b.id, kind: 'book', title: b.title, author: b.author, source: 'Book', has_cover: true, mins: null, progress: prog, href: '#ebook/' + b.id, note: b.progress_note }; };
  const books = Object.values(db.books).filter(b => lastRead(b) && lastRead(b) > now - 60 * 86400).sort((a, b) => lastRead(b) - lastRead(a)).map(bcard).filter(b => b.progress >= 2 && b.progress <= 97);
  const lib = Object.values(db.docs).filter(d => d.where_ === 'library' && ['inbox', 'later'].includes(d.status)).sort((a, b) => b.added - a.added);
  out.continue = books.concat(lib.filter(d => d.progress >= 3 && d.progress <= 95).map(card));
  out.recent = lib.filter(d => d.added > now - 7 * 86400).map(card);
  out.quick = lib.filter(d => docMins(d) && docMins(d) <= 10).map(card);
  out.long = lib.filter(d => docMins(d) && docMins(d) >= 30).map(card);
  const recent = {}; liveHls().filter(h => h.created > now - 21 * 86400).forEach(h => { const r = recent[h.book_id] || (recent[h.book_id] = { at: 0, n: 0 }); r.at = Math.max(r.at, h.created); r.n++; });
  out.highlighted = Object.entries(recent).sort((a, b) => b[1].at - a[1].at).map(([id, r]) => { const d = db.docs[id], b = db.books[id];
    const c = d ? card(d) : b ? bcard(b) : null; if (c) c.highlights = r.n; return c; }).filter(Boolean);
  out.feed = Object.values(db.docs).filter(d => d.where_ === 'feed' && d.status === 'unseen').sort((a, b) => b.added - a.added).slice(0, 12).map(card);
  return out;
}

/* ---------- reading time ---------- */
function beat(b){
  const secs = Math.max(0, Math.min(60, +b.seconds || 0)), t = b.at && Math.abs(nowSec() - b.at) < 7 * 86400 ? +b.at : nowSec(), day = dayOf(t);
  const item = b.book_id || b.doc_id, src = b.book_id ? 'ebook' : 'article';
  if (!item || !secs) return;
  let s = db.sessions.find(x => x.item === item && x.source === src && dayOf(x.start) === day);
  if (!s) { const title = (db.books[item] || db.docs[item] || {}).title || ''; s = { source: src, item, title, start: Math.max(at(day, 0), t - secs), seconds: 0, note: null }; db.sessions.push(s); }
  s.seconds += secs; save();
}

/* ---------- Today (app.py get_today) ---------- */
function daySummary(day){
  const by = {}, items = [];
  for (const s of sessionsOn(day)) {
    by[s.source] = (by[s.source] || 0) + s.seconds / 60;
    items.push({ source: s.source, label: LABELS[s.source] || s.source, title: s.title || '', author: s.item && db.books[s.item] ? db.books[s.item].author : null,
      minutes: Math.round(s.seconds / 6) / 10, start: s.start ? hhmm(s.start) : null, note: kindleNote(s), counted: counted(s), private: false });
  }
  items.sort((a, b) => (a.start || '99:99') < (b.start || '99:99') ? -1 : 1);
  const minutes = Object.fromEntries(SOURCES.map(s => [s, Math.round((by[s] || 0) * 10) / 10]));
  return { date: day, minutes, counted: Math.round(SOURCES.filter(s => db.settings.count[s]).reduce((x, s) => x + minutes[s], 0) * 10) / 10, goal: minutesGoal(day), sessions: items };
}
function onThisDay(limit){
  const t = todayIso(), md = t.slice(5);
  return liveHls().filter(h => h.text.length >= 30 && dayOf(h.created).slice(5) === md && dayOf(h.created) < t).sort((a, b) => b.created - a.created).slice(0, limit || 6).map(h => {
    const b = db.books[h.book_id] || db.docs[h.book_id] || {};
    return { id: h.id, text: h.text, title: b.title, author: b.author, year: +dayOf(h.created).slice(0, 4), years_ago: +t.slice(0, 4) - +dayOf(h.created).slice(0, 4), book_id: h.book_id, open: openOf(h) };
  });
}
function today(q){
  const t = todayIso(), day = q.get('d') || t, out = daySummary(day), r = dayItems(t), st = streaks(), gl = allGoals().filter(g => g.on || g.main).map(g => progress(g, day <= t ? day : null));
  const week = grid(addDays(t, -6), 7);
  return Object.assign(out, {
    today: t, week: week.days.map((m, i) => ({ date: addDays(t, -6 + i), minutes: m, target: week.targets[i] })), year30: grid(Y30), shabbat: false, settings: settingsOut(), labels: LABELS,
    fresh: { kindle: { last: { plugin: Math.max(...Object.values(db.books).map(b => b.kindle_at || 0)) } }, audiobookshelf: { ok: true, checked: nowSec() - 180, last: nowSec() - 3600 } },
    review: { done: r.done, total: r.total, first: r.items[0] || null, streak: r.streak, books: [...new Set(r.items.map(i => i.title).filter(Boolean))].slice(0, 3) },
    nightstand: standBooks().map(bookCard), nightstand_suggested: [], offstand: null, on_this_day: onThisDay(2), cards_due: cardsDue().length, hc_finished: [],
    streak: { goal: st.goal, any: st.any }, goals: gl, main: gl.find(g => g.main) || gl[0] || null, milestones_new: [] });
}
function settingsOut(){ return clone(db.settings); }

/* ---------- Stats (daf/stats.py) ---------- */
function stats(){
  const t = todayIso(), st = streaks(), vals = st.vals, ti = st.today_index, last = n => vals.slice(ti - n + 1, ti + 1), y30 = grid(Y30), goal = minutesGoal(t);
  const avg30 = last(30).reduce((a, b) => a + b, 0) / 30, daysLeft = Math.max(0, 365 - y30.elapsed);
  const bySrc = {}, hours = new Array(24).fill(0), wd = new Array(7).fill(0);
  for (let i = 0; i < 90; i++) for (const s of sessionsOn(addDays(t, -i))) {
    bySrc[s.source] = (bySrc[s.source] || 0) + s.seconds / 60;
    if (counted(s) && s.start) { const d = new Date(s.start * 1000); hours[d.getHours()] += s.seconds / 60; wd[d.getDay()] += s.seconds / 60; }
  }
  const now = nowSec(), inprog = [], stalled = [];
  Object.values(db.books).filter(b => lastRead(b)).sort((a, b) => lastRead(b) - lastRead(a)).forEach(b => {
    const p = db.positions[b.id] && !b.progress ? Math.round(db.positions[b.id].fraction * 100) : (b.progress || 0);
    const c = { id: b.id, title: b.title, author: b.author, progress: p, note: b.progress_note, last_read: lastRead(b), days_ago: Math.floor((now - lastRead(b)) / 86400), has_cover: true, readable: true };
    if (p >= 2 && p < 97) (c.days_ago >= 14 ? stalled : inprog).push(c);
  });
  const sun = addDays(t, -((pyWeekday(t) + 1) % 7)), weeks = [];
  for (let i = 11; i >= 0; i--) { const a = addDays(sun, -7 * i), b = addDays(a, 7); weeks.push({ week: a, n: liveHls().filter(h => dayOf(h.created) >= a && dayOf(h.created) < b).length }); }
  return { streak: { goal: st.goal, any: st.any, best_goal: st.best_goal, best_any: st.best_any },
    days14: last(14).map((v, i) => ({ date: addDays(t, -13 + i), minutes: v })),
    totals: { today: vals[ti], week: Math.round(last(7).reduce((a, b) => a + b, 0)), month: Math.round(last(30).reduce((a, b) => a + b, 0)), avg30: Math.round(avg30 * 10) / 10,
      year30_hours: y30.total_hours, year30_days_goal: y30.days_goal, year30_days_read: y30.days_read, year30_elapsed: y30.elapsed,
      projection_hours: Math.round(y30.total_hours + avg30 * daysLeft / 60), goal_hours: Math.round(y30.targets.reduce((a, b) => a + b, 0) / 60) },
    goal, sources: SOURCES.filter(s => bySrc[s]).map(s => ({ source: s, label: LABELS[s], minutes: Math.round(bySrc[s]), counted: !!db.settings.count[s] })),
    hours: hours.map(Math.round), weekdays: wd.map(w => Math.round(w / 13)), in_progress: inprog.slice(0, 12), stalled: stalled.slice(0, 12), finished: [],
    highlight_weeks: weeks, on_this_day: onThisDay(6) };
}

/* ---------- search (⌘K) ---------- */
function search(q){
  q = (q || '').trim(); const ql = q.toLowerCase();
  if (q.length < 2) return { docs: [], highlights: [], books: [] };
  const docs = Object.values(db.docs).filter(d => d.status !== 'deleted' && [d.title, d.source, d.author].some(x => String(x || '').toLowerCase().includes(ql)))
    .map(d => ({ id: d.id, title: d.title, source: d.source, kind: d.kind, where_: d.where_ }));
  const books = Object.values(db.books).filter(b => [b.title, b.author].some(x => String(x || '').toLowerCase().includes(ql))).map(b => ({ id: b.id, title: b.title, author: b.author }));
  const highlights = liveHls().filter(h => h.text.toLowerCase().includes(ql) || String((db.rs[h.id] || {}).user_note || '').toLowerCase().includes(ql)).slice(0, 10)
    .map(h => ({ id: h.id, text: h.text, book_id: h.book_id, title: (db.books[h.book_id] || db.docs[h.book_id] || {}).title }));
  const have = new Set(docs.map(d => d.id)), text = [];
  for (const a of TEXTS) {
    const d = db.docs[a.id]; if (!d || d.status === 'deleted' || have.has(a.id)) continue;
    for (const b of a.blocks) {
      const i = b.x.toLowerCase().indexOf(ql); if (i < 0) continue;
      const s = Math.max(0, i - 60), snip = (s ? '…' : '') + b.x.slice(s, i) + '\u0002' + b.x.slice(i, i + q.length) + '\u0003' + b.x.slice(i + q.length, i + q.length + 60) + '…';
      text.push({ id: a.id, snip, title: d.title, source: d.source, where_: d.where_ }); break;
    }
  }
  return { docs, highlights, books, vault: [], text };
}

/* ---------- exports ---------- */
function exportHighlights(q){
  const fmt = q.get('fmt') || 'md', rows = hlRows(q), stamp = todayIso();
  if (fmt === 'json') return file(JSON.stringify(rows.map(r => ({ id: r.id, book_title: r.book_title, book_author: r.book_author, text: r.text, note: r.note, user_note: r.user_note, chapter: r.chapter, page: r.page, source: r.source, color: r.color, tags: r.tags, created: r.created })), null, 1), 'application/json', 'daf-highlights-' + stamp + '.json');
  if (fmt === 'csv') {
    const c = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
    const lines = [['Highlight', 'Title', 'Author', 'Note', 'Chapter', 'Page', 'Source', 'Color', 'Tags', 'Date'].join(',')].concat(rows.map(r => [r.text, r.book_title, r.book_author, [r.note, r.user_note].filter(Boolean).join('\n'), r.chapter || '', r.page || '', r.source, r.color || 'yellow', r.tags.join(' '), dayOf(r.created)].map(c).join(',')));
    return file(lines.join('\r\n') + '\r\n', 'text/csv', 'daf-highlights-' + stamp + '.csv');
  }
  const by = {}; rows.forEach(r => (by[r.book_id] = by[r.book_id] || []).push(r));
  const out = [];
  Object.values(by).sort((a, b) => String(a[0].book_title).toLowerCase() < String(b[0].book_title).toLowerCase() ? -1 : 1).forEach(items => {
    items.sort((a, b) => a.order - b.order); const h = items[0]; let ch = null;
    out.push('## ' + (h.book_title || 'Untitled') + (h.book_author ? ' — ' + h.book_author : ''), '');
    for (const r of items) {
      if (r.chapter && r.chapter !== ch) { ch = r.chapter; out.push('### ' + ch, ''); }
      out.push(String(r.text || '').trim().split('\n').map(l => '> ' + l).join('\n'));
      const meta = [r.page ? 'p. ' + r.page : '', r.tags.map(t => '#' + t).join(' ')].filter(Boolean);
      if (meta.length) out.push('', meta.join(' · '));
      for (const n of [r.note, r.user_note]) if (n) out.push('', '**Note:** ' + n.trim());
      out.push('');
    }
  });
  const book = q.get('book');
  return file(out.join('\n'), 'text/markdown', (book && rows.length ? String(rows[0].book_title).replace(/[^\w\- ]+/g, '').slice(0, 60).trim() + ' highlights' : 'daf-highlights-' + stamp) + '.md');
}
function exportCards(){
  const lines = ['#separator:tab', '#html:false', '#notetype column:1', '#tags column:5'];
  for (const c of Object.values(db.cards).sort((a, b) => a.created - b.created)) {
    const h = db.hls[c.hl_id]; if (!h || h.deleted) continue;
    const src = String((db.books[h.book_id] || db.docs[h.book_id] || {}).title || '').split(':')[0], tag = 'daf' + (src ? ' daf::' + src.replace(/[^\w-]+/g, '_').slice(0, 60) : '');
    const clean = x => String(x || '').split(/\s+/).join(' ').trim();
    if (c.kind === 'cloze') { let n = 0; lines.push(['Cloze', clean(c.front.replace(CLOZE, (m, w) => '{{c' + (++n) + '::' + w + '}}')), '', clean(src), tag].join('\t')); }
    else lines.push(['Basic', clean(c.front), clean(c.back), clean(src), tag].join('\t'));
  }
  return file(lines.join('\n') + '\n', 'text/plain', 'daf-flashcards-' + todayIso() + '.txt');
}
function file(body, type, name){
  return new Response(body, { status: 200, headers: { 'Content-Type': type + '; charset=utf-8', 'Content-Disposition': 'attachment; filename="' + name.replace(/"/g, '') + '"' } });
}

/* ---------- the routes ---------- */
const R = [];
const on = (method, pattern, fn) => R.push([method, new RegExp('^' + pattern.replace(/:\w+/g, '([^/]+)') + '$'), fn]);
const notHere = () => { throw err(404, NOT_HERE); };

on('GET', '/api/me', () => ({ signed_in: true, has_password: true, user: 'reader' }));
on('GET', '/api/health', () => ({ ok: true, version: '' }));
on('GET', '/api/today', (p, q) => today(q));
on('GET', '/api/year/:which', p => grid(p[0] === '29' ? Y29 : Y30));
on('GET', '/api/settings', () => settingsOut());
on('PUT', '/api/settings', (p, q, b) => {
  const s = db.settings;
  for (const [k, v] of Object.entries(b.count || {})) if (k in s.count && k !== 'podcast') s.count[k] = !!v;
  if (Number.isInteger(b.review_size) && b.review_size >= 1 && b.review_size <= 20) s.review_size = b.review_size;
  if (typeof b.home_tz === 'string') s.home_tz = b.home_tz;
  if (typeof b.tts_voice === 'string') s.tts_voice = b.tts_voice;
  if (typeof b.tts_speed === 'number') s.tts_speed = b.tts_speed;
  if (Number.isInteger(b.feed_expire_days)) s.feed_expire_days = b.feed_expire_days;
  if (Number.isInteger(b.cards_per_day)) s.cards_per_day = b.cards_per_day;
  if (b.appearance && typeof b.appearance === 'object') { const ok = v => typeof v === 'string' && /^[\w-]{1,30}$/.test(v);
    s.appearance = { mode: ['system', 'light', 'dark'].includes(b.appearance.mode) ? b.appearance.mode : 'system', light: ok(b.appearance.light) ? b.appearance.light : 'daf', dark: ok(b.appearance.dark) ? b.appearance.dark : 'daf' }; }
  for (const k of ['hc_progress', 'hc_autostart']) if (typeof b[k] === 'boolean') s[k] = b[k];
  save(); return settingsOut();
});
on('GET', '/api/goals', () => goalsOut());
on('PUT', '/api/goals', (p, q, b) => {
  let incoming = b.goals;
  if (b.preset) { const pr = PRESETS[b.preset]; if (!pr) throw err(400, 'No such preset'); const first = Object.keys(pr.goals)[0]; incoming = Object.entries(pr.goals).map(([id, v]) => Object.assign({ id }, v, { main: id === first })); }
  if (!Array.isArray(incoming)) throw err(400, 'goals: a list');
  saveGoals(incoming); return goalsOut();
});
on('GET', '/api/tips', () => clone(db.settings.tips));
on('POST', '/api/tips', (p, q, b) => {
  const t = db.settings.tips;
  if (typeof b.seen === 'string') t.seen[b.seen] = nowSec();
  if (typeof b.news === 'string') t.news = b.news;
  if (typeof b.off === 'boolean') t.off = b.off;
  if (b.reset === true) t.seen = {};
  save(); return clone(t);
});
on('PUT', '/api/keys', (p, q, b) => { db.settings.keys = b.keys && typeof b.keys === 'object' ? b.keys : {}; save(); return { keys: db.settings.keys }; });
on('GET', '/api/views', () => ({ views: db.settings.views || [] }));
on('PUT', '/api/views', (p, q, b) => { db.settings.views = (b.views || []).filter(v => v && ['library', 'feed'].includes(v.where) && String(v.name || '').trim()).slice(0, 30).map(v => Object.assign({}, v, { id: String(v.id || hash(JSON.stringify(v)).slice(0, 10)).toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 24) })); save(); return { views: db.settings.views }; });
on('GET', '/api/fonts', () => ({ fonts: [] }));
on('GET', '/api/offline/plan', () => ({ urls: [], docs: [], ebooks: [], images: [] }));
on('POST', '/api/sync', () => ({ ok: true }));
on('GET', '/api/sources', () => ({ checks: [] }));

on('GET', '/api/review', (p, q) => { const day = q.get('day'); const t = todayIso(); return dayItems(day && day >= addDays(t, -7) && day <= addDays(t, 7) ? day : t); });
on('GET', '/api/review/themed', (p, q) => {
  const n = Math.max(1, Math.min(30, +q.get('n') || 10)), tag = q.get('tag'), fav = q.get('fav'), color = q.get('color'), book = q.get('book');
  const rows = hlRows(q).filter(r => r.text.length >= 20 && r.r_status !== 'never'), r = rng('themed|' + Date.now());
  for (let i = rows.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [rows[i], rows[j]] = [rows[j], rows[i]]; }
  const bt = book && db.books[book] ? db.books[book].title : book && db.docs[book] ? db.docs[book].title : null;
  return { items: rows.slice(0, n).map(x => pub(db.hls[x.id])), total: rows.length,
    theme: tag ? '#' + tag : fav ? 'Favorites' : color ? color[0].toUpperCase() + color.slice(1) : bt ? bt.split(':')[0] : 'These highlights' };
});
on('POST', '/api/review/:id', (p, q, b) => { const out = reviewAct(p[0], b.action, b.action === 'note' ? b.note : null, b.at); if (b.action === 'note') out.vault = 'later'; return out; });

on('GET', '/api/highlights', (p, q) => {
  const sort = q.get('sort') || 'recent', rows = hlRows(q).sort((a, b) => sort === 'oldest' ? a.created - b.created : b.created - a.created), groups = {};
  for (const r of rows) {
    const g = groups[r.book_id] || (groups[r.book_id] = { book_id: r.book_id, title: r.book_title, author: r.book_author, vault_path: null, kind: r.kind, has_cover: !!r.calibre_path, items: [], latest: 0, notes: 0 });
    g.items.push(r); g.latest = Math.max(g.latest, r.created || 0); g.notes += (r.user_note || r.note) ? 1 : 0;
  }
  const gl = Object.values(groups);
  if (sort === 'book') { gl.sort((a, b) => String(a.title).toLowerCase() < String(b.title).toLowerCase() ? -1 : 1); gl.forEach(g => g.items.sort((a, b) => a.order - b.order)); }
  else if (sort === 'oldest') gl.sort((a, b) => Math.min(...a.items.map(x => x.created)) - Math.min(...b.items.map(x => x.created)));
  else gl.sort((a, b) => b.latest - a.latest);
  return { count: rows.length, books: gl.length, notes: gl.reduce((x, g) => x + g.notes, 0), groups: gl, tags: allTags(), sources: Object.keys(HLSRC) };
});
on('GET', '/api/highlights/tags', () => ({ tags: allTags() }));
on('GET', '/api/highlights/export', (p, q) => exportHighlights(q));
on('PUT', '/api/highlights/:id/tags', (p, q, b) => { if (!Array.isArray(b.tags)) throw err(400, 'tags: a list'); const s = state(p[0]); s.tags = cleanTags(b.tags); const tags = s.tags; if (!s.tags.length) s.tags = null; save(); return { tags, all: allTags() }; });
on('PUT', '/api/highlights/:id/fav', (p, q, b) => { state(p[0]).fav = b.fav ? 1 : null; save(); return { ok: true }; });
on('PUT', '/api/highlights/:id/note', (p, q, b) => { state(p[0]).user_note = String(b.note || '').trim() || null; save(); return { ok: true, vault: 'later' }; });
on('PUT', '/api/highlights/:id/color', (p, q, b) => { if (!COLORS.includes(b.color)) throw err(400, 'yellow, green, blue, pink or purple'); const h = db.hls[p[0]]; if (h) { h.color = b.color === 'yellow' ? null : b.color; save(); } return { ok: true }; });
on('DELETE', '/api/highlights/:id', p => { const h = db.hls[p[0]]; if (!h) throw err(400, 'No such highlight'); h.deleted = true; save(); return { ok: true }; });
on('POST', '/api/highlights/:id/restore', p => { const h = db.hls[p[0]]; if (!h) throw err(404, 'No such highlight'); h.deleted = false; save(); return { ok: true }; });
on('GET', '/api/highlights/:id/cards', p => ({ cards: Object.values(db.cards).filter(c => c.hl_id === p[0]).sort((a, b) => a.created - b.created).map(cardRow) }));
on('POST', '/api/highlights/:id/cards', (p, q, b) => {
  const kind = b.kind, front = String(b.front || '').trim(), back = String(b.back || '').trim() || null;
  if (!['cloze', 'qa'].includes(kind)) throw err(400, 'cloze or qa');
  if (kind === 'cloze' && !/\{\{(.+?)\}\}/s.test(front)) throw err(400, 'Hide at least one word');
  if (kind === 'qa' && (!front || !back)) throw err(400, 'A question and an answer, please');
  if (!db.hls[p[0]]) throw err(400, 'No such highlight');
  let id = b.id;
  if (id && db.cards[id]) Object.assign(db.cards[id], { kind, front, back });
  else { id = 'c' + hash(p[0] + '|' + Date.now() + '|' + front).slice(0, 15); db.cards[id] = { id, hl_id: p[0], kind, front, back, created: nowSec(), due: null, interval: 0, ease: 2.5, reps: 0, lapses: 0, last: null, first_seen: null }; }
  save(); return { id, cards: Object.values(db.cards).filter(c => c.hl_id === p[0]).map(cardRow) };
});
on('POST', '/api/highlights/:id/cards/suggest', () => { throw err(503, 'Suggestions come from Claude on Daf’s server, so they aren’t in this demo. Pick the words to hide yourself.'); });
on('GET', '/api/cards/due', () => ({ items: cardsDue() }));
on('GET', '/api/cards/export', () => exportCards());
on('DELETE', '/api/cards/:id', p => { delete db.cards[p[0]]; save(); return { ok: true }; });
on('POST', '/api/cards/:id/grade', (p, q, b) => {
  const g = { again: 1, hard: 2, good: 3, easy: 4 }[b.grade] || b.grade, c = db.cards[p[0]];
  if (![1, 2, 3, 4].includes(g)) throw err(400, 'again, hard, good or easy'); if (!c) throw err(400, 'No such card');
  const day = todayIso(); let ease = c.ease || 2.5, interval = c.interval || 0, reps = c.reps || 0, lapses = c.lapses || 0;
  if (reps === 0) interval = { 1: 0, 2: 1, 3: 1, 4: 4 }[g];
  else if (g === 1) { interval = 1; ease = Math.max(1.3, ease - 0.2); lapses++; }
  else if (g === 2) { interval = Math.max(1, Math.round(interval * 1.2)); ease = Math.max(1.3, ease - 0.15); }
  else if (g === 3) interval = Math.max(interval + 1, Math.round(interval * ease));
  else { interval = Math.max(interval + 2, Math.round(interval * ease * 1.3)); ease += 0.15; }
  Object.assign(c, { interval, ease: Math.round(ease * 100) / 100, reps: reps + 1, lapses, due: addDays(day, interval), last: day, first_seen: c.first_seen || day }); save();
  return { due: c.due, interval };
});

on('GET', '/api/books', () => {
  const stand = new Set(db.settings.nightstand || []), hl = id => hlCount(id);
  const reading = Object.values(db.books).filter(b => b.status === 'reading' || lastRead(b) || b.audio_pct != null).sort((a, b) => (lastRead(b) || 0) - (lastRead(a) || 0));
  return { nightstand: standBooks().map(b => Object.assign(bookCard(b), { highlights: hl(b.id), readable: readable(b.id) })), suggested: [],
    others: reading.filter(b => !stand.has(b.id)).map(b => Object.assign(bookCard(b), { highlights: hl(b.id), readable: readable(b.id) })),
    marked_reading: reading.filter(b => b.status === 'reading').length, manga: 0 };
});
on('PUT', '/api/nightstand', (p, q, b) => {
  const ids = (b.ids || []).filter(i => typeof i === 'string'); if (ids.length > 3) throw err(400, 'Three books at most. Take one off first.');
  db.settings.nightstand = ids.filter(i => db.books[i]); save(); return { nightstand: db.settings.nightstand };
});
on('GET', '/api/books/:id', p => {
  const b = db.books[p[0]]; if (!b) throw err(404, 'No such book');
  const pos = db.positions[b.id] || null;
  return Object.assign(bookCard(b), { private: false, minutes_kindle: Math.round(sessionsOnBook(b.id, 'kindle') / 60),
    highlights: liveHls().filter(h => h.book_id === b.id).map(row).sort((a, c) => c.created - a.created), notes: db.notes.filter(n => n.book_id === b.id).sort((a, c) => c.created - a.created),
    bookmarks: [], on_nightstand: (db.settings.nightstand || []).includes(b.id), readable: readable(b.id), daf_position: pos ? { fraction: pos.fraction, chapter: pos.chapter, updated: pos.updated } : null,
    stats: bookStats(b.id, b.progress, pos ? pos.fraction : null), review_freq: db.freq[b.id] || 'normal', shelves: Object.values(db.shelves).filter(s => s.books.some(x => x.book_id === b.id)).map(s => s.id) });
});
function sessionsOnBook(id, src){ let n = 0; const t = todayIso(); for (let i = 0; i < 400; i++) for (const s of sessionsOn(addDays(t, -i))) if (s.item === id && (!src || s.source === src)) n += s.seconds; return n; }
on('PUT', '/api/books/:id/review', (p, q, b) => { if (!['more', 'normal', 'less', 'never'].includes(b.freq)) throw err(400, 'more, normal, less or never'); if (b.freq === 'normal') delete db.freq[p[0]]; else db.freq[p[0]] = b.freq; save(); return { freq: b.freq }; });
on('POST', '/api/notes', (p, q, b) => {
  const text = String(b.text || '').trim(); if (!text) throw err(400, 'Empty note'); if (!b.book_id) throw err(400, 'No book to file it under');
  db.notes.push({ id: db.notes.length + 1, book_id: b.book_id, text, page: b.page || null, total: null, source: 'text', created: nowSec() }); save(); return { ok: true, vault: 'later' };
});
const shelfList = () => Object.values(db.shelves).sort((a, b) => a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1).map(s => ({ id: s.id, name: s.name, count: s.books.length, covers: s.books.slice().sort((a, b) => b.added - a.added).map(x => x.book_id).slice(0, 4), hardcover: false }));
on('GET', '/api/shelves', () => ({ shelves: shelfList() }));
on('POST', '/api/shelves', (p, q, b) => {
  const name = String(b.name || '').split(/\s+/).join(' ').trim().slice(0, 60); if (!name) throw err(400, 'A name, please');
  if (Object.values(db.shelves).some(s => s.name.toLowerCase() === name.toLowerCase())) throw err(400, 'There’s a shelf by that name');
  let id = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30) || 'shelf'; while (db.shelves[id]) id += '-' + hash(name + Date.now()).slice(0, 4);
  db.shelves[id] = { id, name, created: nowSec(), books: b.book && db.books[b.book] ? [{ book_id: b.book, added: nowSec() }] : [] }; save(); return { id, shelves: shelfList() };
});
on('GET', '/api/shelves/:id', p => {
  const s = db.shelves[p[0]]; if (!s) throw err(404, 'No such shelf');
  return { id: s.id, name: s.name, hardcover: false, hardcover_url: null, books: s.books.slice().sort((a, b) => b.added - a.added).map(x => db.books[x.book_id]).filter(Boolean).map(b => Object.assign(bookCard(b), { readable: readable(b.id), highlights: hlCount(b.id) })) };
});
on('PUT', '/api/shelves/:id', (p, q, b) => { const s = db.shelves[p[0]], name = String(b.name || '').trim().slice(0, 60); if (!name) throw err(400, 'A name, please'); if (s) s.name = name; save(); return { shelves: shelfList() }; });
on('DELETE', '/api/shelves/:id', p => { delete db.shelves[p[0]]; save(); return { shelves: shelfList() }; });
on('PUT', '/api/shelves/:id/books/:book', p => { const s = db.shelves[p[0]]; if (!s || !db.books[p[1]]) throw err(404, 'No such shelf or book'); if (!s.books.some(x => x.book_id === p[1])) s.books.push({ book_id: p[1], added: nowSec() }); save(); return { ok: true }; });
on('DELETE', '/api/shelves/:id/books/:book', p => { const s = db.shelves[p[0]]; if (s) s.books = s.books.filter(x => x.book_id !== p[1]); save(); return { ok: true }; });

on('GET', '/api/ebooks', (p, q) => {
  const ql = (q.get('q') || '').trim().toLowerCase();
  const rows = Object.values(db.books).filter(b => readable(b.id)).sort((a, b) => (lastRead(b) || 0) - (lastRead(a) || 0) || (a.title < b.title ? -1 : 1))
    .filter(b => !ql || b.title.toLowerCase().includes(ql) || String(b.author).toLowerCase().includes(ql));
  return { books: rows.map(b => Object.assign(bookCard(b), { daf_fraction: db.positions[b.id] ? db.positions[b.id].fraction : null })) };
});
on('GET', '/api/ebooks/:id', p => {
  const b = db.books[p[0]], s = BOOK_BY_ID[p[0]]; if (!b || !s) throw err(404, 'No readable file for this book');
  const all = liveHls().filter(h => h.book_id === b.id), rs = h => db.rs[h.id] || {};
  const k = s.kindle;
  return { id: b.id, title: b.title, author: b.author, private: false, format: 'EPUB', size: s.size, has_cover: true, vault_path: null, description: s.description, language: 'en', year: s.year,
    series: null, position: db.positions[b.id] || null,
    highlights: all.filter(h => h.source === 'epub').sort((a, c) => a.created - c.created).map(h => ({ id: h.id, text: h.text, chapter: h.chapter, pos: h.pos || {}, created: h.created, color: h.color, source: h.source, user_note: rs(h).user_note || null, tags: rs(h).tags || [], fav: !!rs(h).fav })),
    other_highlights: all.filter(h => h.source !== 'epub').sort((a, c) => (a.page || 0) - (c.page || 0) || a.created - c.created).map(h => {
      const x = { id: h.id, text: h.text, note: h.note, chapter: h.chapter, page: h.page, source: h.source, created: h.created, color: h.color, user_note: rs(h).user_note || null, tags: rs(h).tags || [], fav: !!rs(h).fav };
      if (typeof h.pos === 'string' && h.pos) x.xp = h.pos; return x; }),
    bookmarks: (db.marks[b.id] || []).slice().sort((a, c) => (a.fraction || 0) - (c.fraction || 0)),
    kindle: k ? { page: k.page, total: k.total, fraction: Math.round(k.page / k.total * 10000) / 10000, at: b.kindle_at } : null,
    minutes_here: Math.round(sessionsOnBook(b.id, 'ebook') / 60), questions: ['What happens in this chapter?', 'Who is this?', 'Explain this passage'] };
});
on('GET', '/api/ebooks/:id/file', async p => { const s = BOOK_BY_ID[p[0]]; if (!s) throw err(404, 'No readable file for this book'); return realFetch(new URL('books/' + s.file, APP)); });
on('PUT', '/api/ebooks/:id/position', (p, q, b) => {
  if (!b.cfi) throw err(400, 'No position');
  const t = b.at && Math.abs(nowSec() - b.at) < 7 * 86400 ? +b.at : nowSec(), cur = db.positions[p[0]];
  if (!cur || cur.updated <= t) db.positions[p[0]] = { cfi: String(b.cfi).slice(0, 2000), fraction: b.fraction || 0, chapter: b.chapter || null, updated: t };
  save(); return { ok: true, kept: true };
});
on('DELETE', '/api/ebooks/:id/position', p => { delete db.positions[p[0]]; save(); return { ok: true }; });
on('POST', '/api/ebooks/:id/bookmarks', (p, q, b) => {
  if (!b.cfi) throw err(400, 'No place to mark');
  const id = 'm' + hash(p[0] + '|' + b.cfi).slice(0, 15), list = db.marks[p[0]] = (db.marks[p[0]] || []).filter(m => m.id !== id);
  list.push({ id, cfi: b.cfi, fraction: b.fraction, chapter: b.chapter || null, excerpt: String(b.excerpt || '').trim().slice(0, 200) || null, created: nowSec() }); save(); return { id };
});
on('DELETE', '/api/ebooks/:id/bookmarks/:mark', p => { db.marks[p[0]] = (db.marks[p[0]] || []).filter(m => m.id !== p[1]); save(); return { ok: true }; });
on('POST', '/api/ebooks/:id/highlights', (p, q, b) => {
  if (!db.books[p[0]]) throw err(400, 'No such book'); if (!b.cfi) throw err(400, 'No place');
  const id = addHighlight(p[0], 'epub', String(b.text || '').slice(0, 5000), { cfi: String(b.cfi), fraction: b.fraction != null ? b.fraction : null }, { chapter: b.chapter, color: b.color, replaces: b.replaces });
  return { id };
});
on('POST', '/api/read/beat', (p, q, b) => { beat(b); return { ok: true }; });

on('GET', '/api/home', () => home());
on('GET', '/api/stats', () => stats());
on('GET', '/api/docs', (p, q) => ({ items: listDocs(q), counts: counts() }));
on('GET', '/api/docs/counts', () => counts());
on('GET', '/api/docs/tags', () => ({ tags: [...new Set(Object.values(db.docs).flatMap(d => d.tags || []))].sort() }));
on('POST', '/api/docs/bulk', (p, q, b) => {
  const st = b.status; if (!['archive', 'later', 'inbox', 'seen', 'unseen', 'deleted'].includes(st)) throw err(400, 'Unknown status');
  const done = []; for (const id of b.ids || []) if (db.docs[id]) { db.docs[id].status = st; done.push(id); } save(); return { done, failed: [] };
});
on('GET', '/api/docs/:id', p => getDoc(p[0]));
on('POST', '/api/docs/:id/status', (p, q, b) => { const d = db.docs[p[0]]; if (!d) throw err(404, 'Not found'); if (!['archive', 'later', 'inbox', 'seen', 'unseen', 'deleted'].includes(b.status)) throw err(400, 'Unknown status'); d.status = b.status; save(); return { ok: true }; });
on('PUT', '/api/docs/:id/star', (p, q, b) => { const d = db.docs[p[0]]; if (!d) throw err(404, 'No such document'); d.starred = b.starred ? 1 : 0; save(); return { ok: true }; });
on('PUT', '/api/docs/:id/tags', (p, q, b) => { const d = db.docs[p[0]]; if (!d) throw err(404, 'Not found'); d.tags = cleanTags(b.tags); save(); return { tags: d.tags, all: [...new Set(Object.values(db.docs).flatMap(x => x.tags || []))].sort() }; });
on('PUT', '/api/docs/:id/progress', (p, q, b) => { const d = db.docs[p[0]]; if (d) { d.progress = Math.max(d.progress || 0, Math.min(100, +b.pct || 0)); save(); } return { ok: true }; });
on('DELETE', '/api/docs/:id/progress', p => { const d = db.docs[p[0]]; if (d) { d.progress = 0; save(); } return { ok: true }; });
on('PUT', '/api/docs/:id/note', (p, q, b) => { const d = db.docs[p[0]]; if (d) { d.note = String(b.note || '').trim() || null; save(); } return { ok: true }; });
on('PUT', '/api/docs/:id/meta', (p, q, b) => { const d = db.docs[p[0]]; if (!d) throw err(404, 'No such document'); if (String(b.title || '').trim()) d.title = String(b.title).trim(); if (b.author != null) d.author = String(b.author).trim() || null; save(); return { title: d.title, author: d.author }; });
on('POST', '/api/docs/:id/highlights', (p, q, b) => {
  if (!db.docs[p[0]]) throw err(400, 'Bad highlight');
  const pos = { b: +b.b, s: +b.s, e: +b.e }; if (b.be != null) pos.be = +b.be; if (b.img) pos.img = String(b.img);
  return { id: addHighlight(p[0], 'daf', String(b.text || ''), pos, { color: b.color, replaces: b.replaces }) };
});
on('POST', '/api/docs/:id/summary', () => { throw err(503, 'Summaries are written by Claude on Daf’s server, so they aren’t in this demo.'); });
on('POST', '/api/docs/:id/ask', () => { throw err(503, 'Ask is Claude on Daf’s server, so it isn’t in this demo.'); });
on('POST', '/api/ebooks/:id/ask', () => { throw err(503, 'Ask is Claude on Daf’s server, so it isn’t in this demo.'); });
on('GET', '/api/search', (p, q) => search(q.get('q')));
on('POST', '/api/paper', (p, q, b) => {
  const minutes = parseInt(b.minutes, 10), pages = parseInt(b.pages || 0, 10) || 0;
  if (!(minutes >= 1 && minutes <= 720)) throw err(400, 'Minutes should be between 1 and 720');
  const t = todayIso(), day = b.shabbat ? addDays(t, -((pyWeekday(t) - 5 + 7) % 7)) : (/^\d{4}-\d\d-\d\d$/.test(b.date || '') ? b.date : t);
  const start = day === t ? nowSec() - minutes * 60 : at(day, 20, 30);
  db.sessions.push({ source: 'paper', item: null, title: 'Paper', start: Math.max(at(day, 0), start), seconds: minutes * 60, note: String(b.note || '').trim() || null, pages }); save();
  return { ok: true, date: day, note: 'this browser' };
});
on('GET', '/api/hardcover', () => ({ connected: false }));
on('GET', '/api/phone', () => ({ devices: [], nudges: { shown: 0, followed: 0 }, inbox: [] }));
on('GET', '/api/podcasts', () => ({ subs: [], clips: [], recent: [], last_sync: null, device: null }));
on('GET', '/api/voices', () => ({ voices: [] }));
on('GET', '/api/newsletters', () => ({ configured: false, senders: [], chosen: [] }));
on('GET', '/api/imports', () => ({ imports: [] }));
on('GET', '/api/feed/folders', () => ({ folders: [...new Set((SEED.feed || []).map(f => f.folder))].sort() }));
on('GET', '/api/feed/sources', () => {
  const folders = {};
  for (const f of SEED.feed || []) {
    const fo = folders[f.folder] || (folders[f.folder] = { name: f.folder, count: 0, feeds: [] });
    let x = fo.feeds.find(y => y.id === f.feed); if (!x) fo.feeds.push(x = { id: f.feed, title: f.source, folder: f.folder, url: '', site: '', icon: '', count: 0, full: true, notify: false });
    if (db.docs[f.id] && db.docs[f.id].status === 'unseen') { x.count++; fo.count++; }
  }
  const out = Object.values(folders).sort((a, b) => a.name < b.name ? -1 : 1); out.forEach(f => f.feeds.sort((a, b) => a.title < b.title ? -1 : 1));
  return { folders: out, total: out.reduce((a, f) => a + f.count, 0), stale: false };
});
// The Torah shelf and a Hardcover status: only in the docs screenshots' build, from made-up data.
on('GET', '/api/torah', () => {
  if (!SEED.torah) throw err(404, NOT_HERE);
  const t = clone(SEED.torah), now = nowSec();
  t.ruach.forEach(r => { r.added = now - (r.days || 0) * 86400 - 3600; r.status = 'unseen'; });
  return Object.assign({ essays: [] }, t);
});
on('GET', '/api/hardcover/book/:id', p => {
  const h = SEED.hardcover && SEED.hardcover[p[0]]; if (!h) throw err(404, NOT_HERE);
  return Object.assign({ linked: true, on_shelf: true, url: null, rating: null, finished_at: null, private: false }, h);
});
on('POST', '/api/feedback', () => { throw err(503, 'Feedback goes to Daf’s own server, so it can’t be sent from this demo. An issue on GitHub reaches me too.'); });

async function route(method, path, q, body){
  for (const [m, re, fn] of R) {
    if (m !== method) continue;
    const hit = re.exec(path); if (!hit) continue;
    return fn(hit.slice(1).map(decodeURIComponent), q, body || {});
  }
  if (window.DafTaste.strict) console.warn('daf-taste: not in the demo', method, path);
  throw err(method === 'GET' ? 404 : 503, NOT_HERE);
}
function reply(x, status){
  if (x instanceof Response) return x;
  return new Response(JSON.stringify(x === undefined ? { ok: true } : x), { status: status || 200, statusText: status && status >= 400 ? 'Not in the demo' : 'OK', headers: { 'Content-Type': 'application/json' } });
}
async function answer(url, init, req){
  const path = '/api/' + url.pathname.slice(API.length), method = String((init && init.method) || (req && req.method) || 'GET').toUpperCase();
  let body = init && init.body;
  if (body == null && req && method !== 'GET') { try { body = await req.clone().text(); } catch(e){} }
  if (typeof body === 'string') { try { body = JSON.parse(body || '{}'); } catch(e){ body = {}; } } else if (body && !(body instanceof Object && body.constructor === Object)) body = {};
  try { return reply(await route(method, path, url.searchParams, body)); }
  catch(e){ return reply({ detail: e.message || NOT_HERE }, e.status || 500); }
}
window.fetch = function(input, init){
  const req = typeof Request !== 'undefined' && input instanceof Request ? input : null;
  let url; try { url = new URL(req ? req.url : String(input), location.href); } catch(e){ return realFetch(input, init); }
  if (url.origin !== location.origin || !url.pathname.startsWith(API)) return realFetch(input, init);
  return answer(url, init, req);
};
window.DafTaste.answer = (href, init) => answer(new URL(href, location.href), init || {}, null);
window.DafTaste.docs = !!SEED.docs;
window.DafTaste.db = () => db;

// The places that need the server, left out from the app's first drawing on: the sidebar is
// filtered and those pages say why they aren't here as soon as app.js makes DafCore and reader.js
// adds its part of the sidebar (a page can draw before the later scripts have run). Recovery isn't
// in the demo at all, nor in the docs' screenshots; the Feed, Manga, Torah and Podcasts read
// services on the server. The docs build (--docs) keeps the rest of the sidebar and has no demo notes.
const GONE = /<button[^>]*data-go="(?:manga|torah|recovery|podcasts|library\/(?:video|tweet|pdf|email))"[^>]*>[\s\S]*?<\/button>/g;
const RECOVERY = /<button[^>]*data-go="recovery"[^>]*>[\s\S]*?<\/button>/g;
const INFO = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 9v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="10" cy="6.3" r="1.1" fill="currentColor"/></svg>';
const navFilter = SEED.docs ? h => h.replace(RECOVERY, '') : h => h.replace(GONE, '').replace(/<div class="navh"><span>Feed<\/span>[\s\S]*$/, '') +
  '<div class="nav demonav"><button class="nv" data-demo="about">' + INFO + '<span>About this demo</span></button></div>';
const escHTML = t => String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function away(title, text){
  return () => {
    document.getElementById('main').innerHTML = '<div class="top"><h1>' + escHTML(title) + '</h1></div><div class="page"><section class="card demoaway"><h2>Not in the demo</h2>' +
      '<p>' + text + '</p><div class="demoacts"><a class="btn primary" href="#today">Back to Today</a><button class="btn" data-demo="about">About this demo</button></div></section></div>';
  };
}
const AWAY = {
  feed: away('Feed', 'The Feed is my RSS reader, FreshRSS, running on my server. Daf reads it from there, so there’s nothing here to read it from.'),
  torah: away('Torah', 'The Torah shelf brings in the week’s parasha from Sefaria through my server, so it can’t open here.'),
  manga: away('Manga', 'Manga come from Komga, a comics server on my machine, so there aren’t any in this demo.'),
  mread: away('Manga', 'Manga come from Komga, a comics server on my machine, so there aren’t any in this demo.'),
  podcasts: away('Podcasts', 'Podcasts arrive when AntennaPod syncs with my server, so there aren’t any here.'),
  paper: away('Paper pages', 'A photo of a marked-up paper page goes to Claude on my server, which reads out the lines I marked. That can’t happen in a browser.'),
  pdf: away('PDF', 'There are no PDFs in this demo.'),
};
const RECOVERY_VIEW = () => { location.replace('#today'); };
let core;
Object.defineProperty(window, 'DafCore', { configurable: true, get(){ return core; }, set(v){
  core = v;
  if (!v || typeof v !== 'object') return;
  let extra = v.navExtra;
  Object.defineProperty(v, 'navExtra', { configurable: true, enumerable: true, get(){ return extra && ((x, n) => navFilter(extra(x, n))); }, set(f){ extra = f; } });
  const views = v.views || (v.views = {}), fixed = Object.assign(SEED.docs ? {} : AWAY, { recovery: RECOVERY_VIEW });
  for (const [k, f] of Object.entries(fixed)) Object.defineProperty(views, k, { configurable: true, enumerable: true, get(){ return f; }, set(){} });
} });

// No service worker and no Cache Storage in the taste: everything above answers at once, and this
// page shares its address with the other stuffs, which mustn't keep Daf's lists.
try { if (navigator.serviceWorker) Object.defineProperty(navigator.serviceWorker, 'register', { configurable: true, value: () => Promise.reject(new Error('No service worker in the demo')) }); } catch(e){}
try { Object.defineProperty(window, 'caches', { configurable: true, value: undefined }); } catch(e){}
})();
