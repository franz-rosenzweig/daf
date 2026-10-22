/* Goals: Preferences → Goals (a card per goal, presets, a live preview while you drag), the
   main goal's ring on Today with the others beside it, and a small celebration when a goal
   or a milestone is reached. The server keeps each goal's history, so changing a target
   never rewrites how earlier days did. */
(() => {
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const G = C.Goals = {};
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const KIND_ICON = {
  minutes: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M10 6v4.3l2.8 1.7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  pages: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3.5h7l3 3v10H5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 9.5h4.5M8 12.5h4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  books: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4.5h3.2v11H4zM8.6 4.5h3.2v11H8.6zM13.2 5.2l3-.8 2.6 10.6-3 .8z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  days: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="3.5" y="4.5" width="13" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M3.5 8.5h13M7 3v3M13 3v3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  streak: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M10.5 2.8c.6 3-2.7 4.2-2.7 7.4 0 1 .5 1.9 1.2 2.4-.2-1.8 1.3-2.6 1.9-4.1 1.6 1.4 2.8 3.2 2.8 5.1A3.7 3.7 0 0 1 10 17.3a4.6 4.6 0 0 1-4.6-4.6c0-4.6 4.4-6 5.1-9.9z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  highlights: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 15.5h13" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" opacity=".35"/><path d="M5 12.5 12.5 5l2.5 2.5L7.5 15H5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  reviews: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4.5h10v11H5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="m7.6 10.2 1.7 1.7 3.3-3.6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
const fmt = n => (Math.round(n * 10) / 10).toLocaleString('en-US');
const plural = (n, one, many) => n === 1 ? one : (many || one + 's');
const hrs = m => m >= 90 ? fmt(m / 60) + ' hours' : Math.round(m) + ' minutes';

// "At the hour" while the daily goal is an hour; "at your goal" once it's something else.
G.atWord = goalMin => +goalMin === 60 ? 'at the hour' : 'at your goal';
G.metWord = (g) => g.kind === 'minutes' && g.period === 'day' && g.target === 60 ? 'That’s the hour.' :
  g.period === 'day' ? 'That’s today’s goal.' : g.period === 'week' ? 'That’s this week’s goal.' : g.period === 'month' ? 'That’s this month’s goal.' : 'Goal met.';

/* ---------- the preview: what a target means at your pace --------- */
function perDay(kind, period, t){ return period === 'day' ? t : period === 'week' ? t / 7 : period === 'month' ? t / 30 : t; }
function preview(g, p){
  const t = g.target, mpb = p.minutes_per_book || 540;
  if (g.kind === 'minutes') {
    const d = perDay('minutes', g.period, t), books = Math.round(d * 365 / mpb);
    const typical = /typical/.test(p.book_basis || '');
    let s = 'That’s ' + hrs(d * 7) + ' a week, about ' + books + ' ' + (typical ? plural(books, 'nine-hour book') : plural(books, 'book') + ' at your pace') + ' a year';
    if (p.nightstand_left > 0 && d > 0) {
      const when = new Date(); when.setDate(when.getDate() + Math.ceil(p.nightstand_left / d));
      s += '. You’d finish the nightstand by ' + (when.getFullYear() === new Date().getFullYear() && when.getMonth() === new Date().getMonth() ? 'the end of the month' : MONTHS[when.getMonth()] + (when.getFullYear() !== new Date().getFullYear() ? ' ' + when.getFullYear() : ''));
    }
    s += '.';
    if (p.avg_day >= 1) {
      const r = d / p.avg_day;
      s += r >= 1.8 ? ' Lately it’s been about ' + Math.round(p.avg_day) + ' minutes a day, so this is a stretch.' : r <= 0.8 ? ' Lately you’ve averaged ' + Math.round(p.avg_day) + ' minutes a day, so this one is gentle.' : ' About what you’ve read lately.';
    }
    return s;
  }
  if (g.kind === 'pages') {
    const m = t / (p.pages_per_minute || 0.8);
    return 'About ' + hrs(m) + ' of Kindle reading ' + (g.period === 'day' ? 'a day' : 'a week') + ' at your pace (' + fmt(p.pages_per_minute) + (p.pages_per_minute === 1 ? ' page' : ' pages') + ' a minute).';
  }
  if (g.kind === 'books') {
    const days = g.period === 'by35' ? p.days_to_35 : g.period === 'y30' ? p.y30_days_left : 365;
    const so = g.period === 'by35' ? p.books_since30 : p.books_y30;
    const left = Math.max(0, t - so), every = left ? days / left : 0;
    const perday = left ? left * mpb / days : 0;
    return (left ? 'One every ' + (every >= 2 ? Math.round(every) + ' days' : fmt(every) + ' days') + ', about ' + Math.round(perday) + ' minutes a day for ' + p.book_basis + '.' : 'Already there.') +
      (so ? ' ' + so + ' finished so far.' : '');
  }
  if (g.kind === 'days') return (t === 7 ? 'Every day. ' : t <= 3 ? 'Room for the busy days. ' : '') + 'Lately you’ve read on about ' + fmt(p.days_week) + ' days a week.';
  if (g.kind === 'streak') return 'A day counts when it reaches the daily goal. Your best run so far is ' + p.best_streak + ' ' + plural(p.best_streak, 'day') + (p.streak ? ', and you’re on ' + p.streak + ' now.' : '.');
  if (g.kind === 'highlights') return 'Lately about ' + fmt(p.highlights_week) + ' a week.';
  if (g.kind === 'reviews') return 'Lately the review on about ' + fmt(p.reviews_week) + ' days a week.';
  return '';
}

/* ---------- Preferences → Goals ---------- */
let D = null, saveT = 0;
G.prefs = async (card) => {
  card = card || $('#goalscard'); if (!card) return;
  try { D = await api('/api/goals'); } catch(e){ card.innerHTML = '<h2>Goals</h2><p class="mute">' + esc(e.message) + '</p>'; return; }
  draw(card);
};
function stepOf(kind, period){ return (D.kinds[kind].range[period] || [1, 100, 1]); }
function goalCard(g){
  const k = D.kinds[g.kind], [lo, hi, step] = stepOf(g.kind, g.period);
  const periods = k.periods.length > 1 ? '<div class="seg gseg" role="radiogroup" aria-label="How often">' + k.periods.map(p => '<button type="button" role="radio" aria-checked="' + (p.id === g.period) + '" class="' + (p.id === g.period ? 'on' : '') + '" data-gper="' + p.id + '">' + esc(p.words) + '</button>').join('') + '</div>' : '';
  const unit = g.target === 1 ? k.unit[0] : k.unit[1];
  return '<div class="goal' + (g.on ? ' on' : '') + (g.main ? ' main' : '') + (g.met && g.on ? ' met' : '') + '" data-goal="' + g.id + '">' +
    '<div class="gh"><span class="gi">' + KIND_ICON[g.kind] + '</span><b>' + esc(k.label) + '</b>' +
      (g.on ? '<button type="button" class="gmain' + (g.main ? ' on' : '') + '" data-gmain aria-pressed="' + g.main + '" title="' + (g.main ? 'The main goal: the ring, the widget, the menu bar and the Kindle show it' : 'Make this the main goal') + '">' + (g.main ? 'Main goal' : 'Make main') + '</button>' : '') +
      '<input type="checkbox" class="sw" data-gon' + (g.on ? ' checked' : '') + ' aria-label="' + esc(k.label) + ' on"></div>' +
    (g.on ? '<div class="gb">' +
      '<div class="gt"><button type="button" class="btn sm gstep" data-gstep="-1" aria-label="Less">−</button><span class="gv"><b data-gval>' + g.target + '</b> <span data-gunit>' + esc(unit) + '</span></span><button type="button" class="btn sm gstep" data-gstep="1" aria-label="More">+</button>' +
        '<input type="range" class="grange" min="' + lo + '" max="' + hi + '" step="' + step + '" value="' + g.target + '" aria-label="Target"></div>' +
      periods +
      (g.kind === 'books' ? '<label class="gopt"><input type="checkbox" class="sw" data-gmanga' + (D.goals.find(x => x.id === 'books').manga ? ' checked' : '') + '> Manga and comic volumes count as books</label>' : '') +
      '<p class="gprev" data-gprev>' + esc(preview(g, D.pace)) + '</p>' +
      '<div class="gprog"><span class="pbar"><i style="width:' + g.pct + '%"></i></span><span class="tiny ' + (g.met ? 'gmet' : 'mute') + '">' + esc(g.text) + (g.met ? ' · met' : '') + '</span></div>' +
    '</div>' : '') + '</div>';
}
function milestones(){
  const ms = D.milestones || []; if (!ms.length) return '';
  const fam = {};
  ms.forEach(m => { (fam[m.family] = fam[m.family] || []).push(m); });
  const rows = Object.values(fam).map(list => {
    const got = list.filter(m => m.reached), next = list.find(m => !m.reached);
    return got.map(m => '<li class="got"><span class="gk">✓</span><span>' + esc(m.label) + '</span><span class="mute tiny">' + esc(C.shortDate ? C.shortDate(m.reached) : m.reached) + '</span></li>').join('') +
      (next ? '<li><span class="gk"></span><span>' + esc(next.label) + '</span><span class="mute tiny">' + fmt(next.done) + ' of ' + next.target + '</span></li>' : '');
  }).join('');
  return '<h3 class="gms">Year 30 milestones</h3><ul class="gmiles">' + rows + '</ul>';
}
function draw(card){
  const preset = Object.entries(D.presets).map(([id, p]) => '<button type="button" class="gpre" data-gpreset="' + id + '"><b>' + esc(p.label) + '</b><span>' + esc(p.text) + '</span></button>').join('');
  card.innerHTML = '<div class="cardh"><h2>Goals</h2><span class="mute tiny">Changes count from today. Earlier days keep the goal they had.</span></div>' +
    '<div class="gpres" aria-label="Start from">' + preset + '</div>' +
    '<div class="goals">' + D.goals.map(goalCard).join('') + '</div>' + milestones();
  bind(card);
}
function save(card, changes, redraw){
  clearTimeout(saveT);
  saveT = setTimeout(async () => {
    try { D = await api('/api/goals', { method: 'PUT', body: JSON.stringify({ goals: changes() }) }); C.S.goalsChanged = true; if (redraw) draw(card); else refresh(card); }
    catch(e){ toast(e.message); }
  }, redraw ? 0 : 500);
}
function refresh(card){
  // After a save while dragging: progress lines only, so the slider under the finger stays put.
  D.goals.forEach(g => {
    const el = card.querySelector('[data-goal="' + g.id + '"] .gprog'); if (!el) return;
    el.innerHTML = '<span class="pbar"><i style="width:' + g.pct + '%"></i></span><span class="tiny ' + (g.met ? 'gmet' : 'mute') + '">' + esc(g.text) + (g.met ? ' · met' : '') + '</span>';
    el.closest('.goal').classList.toggle('met', !!g.met);
  });
}
function bind(card){
  card.onclick = e => {
    const pre = e.target.closest('[data-gpreset]');
    if (pre) {
      api('/api/goals', { method: 'PUT', body: JSON.stringify({ preset: pre.dataset.gpreset }) }).then(r => { D = r; C.S.goalsChanged = true; draw(card); toast(D.presets[pre.dataset.gpreset].label + ': ' + D.presets[pre.dataset.gpreset].text); }).catch(err => toast(err.message));
      return;
    }
    const box = e.target.closest('[data-goal]'); if (!box) return;
    const g = D.goals.find(x => x.id === box.dataset.goal);
    if (e.target.closest('[data-gmain]')) { if (!g.main) save(card, () => [{ id: g.id, main: true }], true); return; }
    const per = e.target.closest('[data-gper]');
    if (per && per.dataset.gper !== g.period) { save(card, () => [{ id: g.id, period: per.dataset.gper }], true); return; }
    const st = e.target.closest('[data-gstep]');
    if (st) {
      const [lo, hi, step] = stepOf(g.kind, g.period);
      setTarget(box, g, Math.max(lo, Math.min(hi, g.target + (+st.dataset.gstep) * step)));
      save(card, () => [{ id: g.id, target: g.target }]);
    }
  };
  card.onchange = e => {
    const box = e.target.closest('[data-goal]'); if (!box) return;
    const g = D.goals.find(x => x.id === box.dataset.goal);
    if (e.target.matches('[data-gon]')) save(card, () => [{ id: g.id, on: e.target.checked }], true);
    else if (e.target.matches('[data-gmanga]')) save(card, () => [{ id: 'books', manga: e.target.checked }], true);
    else if (e.target.matches('.grange')) save(card, () => [{ id: g.id, target: g.target }]);
  };
  card.oninput = e => {
    if (!e.target.matches('.grange')) return;
    const box = e.target.closest('[data-goal]'), g = D.goals.find(x => x.id === box.dataset.goal);
    setTarget(box, g, +e.target.value);
  };
}
function setTarget(box, g, v){
  g.target = v;
  const k = D.kinds[g.kind];
  box.querySelector('[data-gval]').textContent = v;
  box.querySelector('[data-gunit]').textContent = v === 1 ? k.unit[0] : k.unit[1];
  const r = box.querySelector('.grange'); if (r && +r.value !== v) r.value = v;
  box.querySelector('[data-gprev]').textContent = preview(g, D.pace);
}

/* ---------- Today: the main goal's ring, and the others ---------- */
G.ringCard = (d, ring, srcRows) => {
  const gl = d.goals || [], m = d.main;
  const minutesMain = !m || (m.kind === 'minutes' && m.period === 'day');
  let head;
  if (minutesMain) {
    const goal = d.goal;
    head = ring(118, 11, d.counted, goal) + '<div><div style="font-size:20px;font-weight:700">of ' + Math.round(goal) + ' minutes</div><div class="mute tiny">' + (d.counted >= goal ? (goal === 60 ? 'That’s the hour.' : 'That’s today’s goal.') : Math.ceil(goal - d.counted) + ' to go') + '</div></div>';
  } else {
    head = ring(118, 11, m.done, m.target).replace(/minutes/, esc(m.unit)) + '<div><div style="font-size:20px;font-weight:700">of ' + m.target + ' ' + esc(m.unit) + '</div><div class="mute tiny">' + esc(m.period_label) + ' · ' + (m.met ? esc(G.metWord(m)) : (m.target - m.done) + ' to go') + '</div><div class="mute tiny">' + Math.round(d.counted) + ' minutes today</div></div>';
  }
  const others = gl.filter(g => !g.main);
  const chips = others.length ? '<div class="gchips">' + others.map(g => '<a class="gchip' + (g.met ? ' met' : '') + '" href="#prefs/goals" title="' + esc(g.label) + '"><span class="gi">' + KIND_ICON[g.kind] + '</span><span>' + esc(g.text) + '</span></a>').join('') + '</div>' : '';
  const pend = d.pendingMin >= 1 ? '<div class="mute tiny" style="margin-top:6px">' + Math.round(d.pendingMin) + ' min of these are on this device, not yet synced</div>' : '';
  return '<section class="card" aria-label="Today’s goal"><div class="ringrow"><a href="#prefs/goals" class="ringlink" title="Goals">' + head.replace(/^(<svg[\s\S]*?<\/svg>)/, '$1</a>') + '</div>' + chips + '<div class="rows">' + srcRows + '</div>' + pend + '</section>';
};

/* ---------- the celebration ---------- */
function seen(){ try { return JSON.parse(localStorage.getItem('daf.celebrated') || '[]'); } catch(e){ return []; } }
function remember(keys){ try { localStorage.setItem('daf.celebrated', JSON.stringify(keys.slice(-200))); } catch(e){} }
G.celebrate = (d) => {
  if (!d || d.date !== d.today) return;
  const done = seen(), fresh = [];
  (d.goals || []).filter(g => g.met && g.on).forEach(g => { if (done.indexOf(g.key) < 0) fresh.push({ key: g.key, text: g.kind === 'streak' ? g.target + ' days in a row at the goal.' : G.metWord(g) + ' ' + g.text.replace(/^./, c => c.toUpperCase()) + '.' }); });
  (d.milestones_new || []).forEach(m => { const k = 'ms:' + m.id; if (done.indexOf(k) < 0) fresh.push({ key: k, text: m.label + '.', big: true }); });
  if (!fresh.length) return;
  // The first time a device sees Daf with goals, it remembers what's already met without a party.
  if (!localStorage.getItem('daf.celebrated')) { remember(fresh.map(f => f.key)); return; }
  remember(done.concat(fresh.map(f => f.key)));
  const f = fresh.find(x => x.big) || fresh[0];
  toast(f.text.replace(/\.\.$/, '.'));
  confetti(f.big ? 70 : 40);
};
function confetti(n){
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const box = document.createElement('div'); box.className = 'gconf'; box.setAttribute('aria-hidden', 'true');
  const cols = ['#d9ba80', '#bc8e52', '#ead7b0', 'var(--accent)', '#9a5b1f'];
  for (let i = 0; i < n; i++) {
    const p = document.createElement('i');
    p.style.left = (Math.random() * 100) + '%';
    p.style.background = cols[i % cols.length];
    p.style.setProperty('--dx', (Math.random() * 160 - 80) + 'px');
    p.style.setProperty('--r', (Math.random() * 720 - 360) + 'deg');
    p.style.animationDelay = (Math.random() * 0.35) + 's';
    p.style.animationDuration = (1.4 + Math.random() * 0.9) + 's';
    box.append(p);
  }
  document.body.append(box);
  setTimeout(() => box.remove(), 2800);
}
G.confetti = confetti;
})();
