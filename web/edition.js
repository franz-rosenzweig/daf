/* Daf Edition: a short paper each morning, chosen by what you read, watch and listen to (daf/edition.py),
   and its Taste page, where you see what it thinks you like and turn things up, down or off. */
(() => {
const C = window.DafCore, { api, esc, toast, $ } = C;
const svg = (d, w) => '<svg width="' + (w || 16) + '" height="' + (w || 16) + '" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
const ICON = {
  article: svg('<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h7M9 16h7"/>'),
  video: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3z"/>'),
  podcast: svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'),
};
const THUMB = '<path d="M7 11v9H4v-9zM7 11l4-8c1.5 0 2.5 1 2.5 2.5V9h5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7"/>';
const UP = svg(THUMB, 17), DOWN = '<span class="flip">' + svg(THUMB, 17) + '</span>';
const CHECK = svg('<path d="M5 12.5l4.5 4.5L19 7.5"/>', 15);
const KINDLE = svg('<rect x="5" y="2.5" width="14" height="19" rx="2"/><path d="M8.5 7h7M8.5 10.5h7M8.5 14h4"/>');
const AGAIN = svg('<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>');
C.I.edition = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"><path d="M3.5 4.5h10v11.5H5.2a1.7 1.7 0 0 1-1.7-1.7z"/><path d="M13.5 7.5h3v7a1.5 1.5 0 0 1-3 0M6 7.5h5M6 10.5h5M6 13.5h3"/></svg>';

const DOW = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const dayOf = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const longDate = s => { const d = dayOf(s); return DOW[d.getDay()] + ', ' + d.getDate() + ' ' + MON[d.getMonth()] + ' ' + d.getFullYear(); };
const shortDay = s => { const d = dayOf(s); return DOW[d.getDay()].slice(0, 3) + ' ' + d.getDate() + ' ' + MON[d.getMonth()].slice(0, 3); };
const hm = m => m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60 ? (m % 60) + ' m' : '') : m + ' min';
const len = it => it.minutes ? (it.kind === 'article' ? it.minutes + ' min' : hm(it.minutes)) : '';
const he = t => /[֐-׿]/.test(t || '') ? ' dir="auto" lang="he"' : '';
const href = it => it.exists === false ? '' : ' href="#read/' + encodeURIComponent(it.id) + '"';

let cur = null, poll = null;
C.views.edition = async args => {
  clearTimeout(poll);
  if (args[0] === 'taste') return taste();
  const day = /^\d{4}-\d{2}-\d{2}$/.test(args[0] || '') ? args[0] : '';
  $('#main').innerHTML = '<div class="top"><h1>Edition</h1><span class="spacer"></span><span id="edtools"></span></div><div class="page edpage" id="edpage"><span class="mute">Loading…</span></div>';
  cur = await C.swr('/api/edition' + (day ? '?day=' + day : ''));
  draw();
};

function tools(){
  const r = cur, ed = r.edition, days = r.days || [];
  const past = days.length > 1 || (days.length && days[0] !== r.day)
    ? '<select class="btn sm edpast" aria-label="Past editions">' + (days.includes(r.day) ? '' : '<option value="' + r.day + '" selected>' + esc(shortDay(r.day)) + '</option>') +
      days.map(d => '<option value="' + d + '"' + (d === r.day ? ' selected' : '') + '>' + esc(shortDay(d)) + '</option>').join('') + '</select>' : '';
  return past + '<a class="btn sm" href="#edition/taste">Taste</a>' +
    (ed ? '<button class="btn sm" data-ed="kindle" title="Send to the Kindle">' + KINDLE + '<span>' + (ed.kindle ? 'On Kindle' : 'Kindle') + '</span></button>' +
      '<button class="ib" data-ed="again" title="Make it again" aria-label="Make it again">' + AGAIN + '</button>' : '');
}

function segs(items){ return '<div class="edsegs">' + items.map(it => '<i class="' + (it.done || it.opened ? 'on' : '') + '"></i>').join('') + '</div>'; }

function acts(it){
  return '<div class="edacts">' + (it.done ? '<span class="eddone">' + CHECK + 'Read</span>' : '') +
    '<button class="ib' + (it.vote > 0 ? ' on' : '') + '" data-vote="1" data-id="' + esc(it.id) + '" aria-label="More like this" title="More like this">' + UP + '</button>' +
    '<button class="ib' + (it.vote < 0 ? ' on down' : '') + '" data-vote="-1" data-id="' + esc(it.id) + '" aria-label="Less like this" title="Less like this">' + DOWN + '</button></div>';
}

function thumb(it, cls){
  if (it.thumb && it.thumb.startsWith('/api/')) return '<div class="' + cls + '" style="background-image:url(\'' + esc(it.thumb) + '\')">' + (it.kind === 'video' ? '<span class="edplay">▶</span>' : '') + '</div>';
  return '<div class="' + cls + ' edtile ' + esc(it.kind) + '"><span>' + esc((it.publication || it.source || '?').trim().charAt(0)) + '</span></div>';
}
const kick = (it, n) => '<div class="edkick"><span class="edki">' + (ICON[it.kind] || ICON.article) + '</span>' + esc(it.section || '') + (n ? '<b>' + n + '</b>' : '') + '</div>';
const meta = it => '<div class="edmeta">' + [esc(it.publication || it.source || ''), len(it)].filter(Boolean).join(' · ') + '</div>';
const why = it => it.why ? '<div class="edwhy">' + esc(it.why) + '</div>' : '';

function card(it, n){
  return '<article class="edcard' + (it.done ? ' done' : '') + '"><a class="edlink"' + href(it) + '>' + thumb(it, 'edthumb') + kick(it, n) +
    '<h3' + he(it.title) + '>' + esc(it.title) + '</h3></a>' + meta(it) + why(it) + acts(it) + '</article>';
}

function draw(){
  const page = $('#edpage'), r = cur; if (!page || !r) return;
  $('#edtools').innerHTML = tools();
  const ed = r.edition;
  if (!ed) {
    page.innerHTML = r.building
      ? '<section class="card edempty"><h2>Making ' + (r.day === (C.S.data && C.S.data.today) ? 'today’s' : 'this') + ' edition…</h2></section>'
      : '<section class="card edempty"><h2>No edition for ' + esc(longDate(r.day)) + '</h2><div><button class="btn primary" data-ed="make">Make it now</button></div></section>';
    if (r.building) poll = setTimeout(refresh, 5000);
    return;
  }
  const items = ed.items, lead = items[0];
  let h = '<div class="edmast"><div class="eddate">' + esc(longDate(ed.day)) + (ed.hebrew ? ' · ' + esc(ed.hebrew) : '') + ' · No. ' + ed.number + '</div>' +
    '<div class="edprog">' + segs(items) + '<span>' + ed.done + ' of ' + items.length + (ed.left ? ' · ' + hm(ed.left) + ' left' : '') + '</span></div></div>';
  if (lead) h += '<section class="edlead' + (lead.done ? ' done' : '') + '"><div class="edlmain"><a class="edlink"' + href(lead) + '>' + kick(lead, 1) +
    '<h2' + he(lead.title) + '>' + esc(lead.title) + '</h2>' + (lead.summary ? '<p class="eddek"' + he(lead.summary) + '>' + esc(lead.summary) + '</p>' : '') + '</a>' +
    meta(lead) + why(lead) + acts(lead) + '</div>' +
    '<aside class="edlist"><div class="edlh">Today</div>' + items.map((it, i) => '<a class="edli' + (it.done || it.opened ? ' done' : '') + '"' + href(it) + '><b>' + (i + 1) + '</b>' +
      '<span class="edki">' + (ICON[it.kind] || ICON.article) + '</span><span' + he(it.title) + '>' + esc(it.title) + '</span></a>').join('') + '</aside></section>';
  h += '<section class="edgrid">' + items.slice(1).map((it, i) => card(it, i + 2)).join('') + '</section>';
  h += '<div class="edend"><span>End of the edition</span></div>';
  page.innerHTML = h;
  if (r.building) poll = setTimeout(refresh, 5000);
}

async function refresh(){
  if (C.S.route[0] !== 'edition') return;
  try { cur = await api('/api/edition?day=' + cur.day); draw(); } catch(e) { toast(e.message); }
}

document.addEventListener('change', e => {
  if (e.target.classList && e.target.classList.contains('edpast')) location.hash = '#edition/' + e.target.value;
});
document.addEventListener('click', async e => {
  const v = e.target.closest && e.target.closest('[data-vote]');
  if (v && cur && cur.edition) {
    e.preventDefault();
    const it = cur.edition.items.find(x => x.id === v.dataset.id); if (!it) return;
    const want = Number(v.dataset.vote), next = it.vote === want ? 0 : want;
    it.vote = next; draw();
    try { await api('/api/edition/vote', { method: 'POST', body: JSON.stringify({ id: it.id, vote: next }) }); }
    catch(err) { toast(err.message); }
    return;
  }
  const b = e.target.closest && e.target.closest('[data-ed]'); if (!b || !cur) return;
  const act = b.dataset.ed;
  if (act === 'make' || act === 'again') {
    if (act === 'again' && !confirm('Make this edition again from what’s new now?')) return;
    b.disabled = true;
    try { await api('/api/edition/build', { method: 'POST', body: JSON.stringify({ day: cur.day }) }); cur.building = true; if (act === 'again') cur.edition = null; draw(); }
    catch(err) { toast(err.message); b.disabled = false; }
  } else if (act === 'kindle') {
    b.disabled = true;
    try { const r = await api('/api/edition/kindle', { method: 'POST', body: JSON.stringify({ day: cur.day }) }); cur.edition.kindle = r.file; toast('On its way to the Kindle'); draw(); }
    catch(err) { toast(err.message); b.disabled = false; }
  }
});

/* ---------- Taste ---------- */
let T = null;
const FACT = { watched: 'watched', opened: 'opened', played: 'played', highlighted: 'highlighted', saved: 'saved', up: '👍', down: '👎' };
const facts = f => Object.entries(f || {}).filter(([k]) => FACT[k]).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k, n]) => k === 'up' || k === 'down' ? FACT[k] + ' ' + n : n + ' ' + FACT[k]).join(' · ');
const seg3 = (kind, name, adj) => '<div class="edseg3">' + [['less', 'Less'], ['more', 'More'], ['mute', 'Mute']].map(([k, l]) =>
  '<button class="' + (adj === k ? 'on' : '') + '" data-adj="' + k + '" data-kind="' + kind + '" data-name="' + esc(name) + '">' + l + '</button>').join('') + '</div>';
const ARROW = { up: '<b class="edtr up" title="Rising">↑</b>', down: '<b class="edtr down" title="Fading">↓</b>', steady: '<b class="edtr">–</b>' };
const MIX = [['pieces', 'Pieces', 3, 20, 1, ''], ['videos', 'Videos', 0, 6, 1, 'up to '], ['podcasts', 'Podcasts', 0, 6, 1, 'up to '], ['torah', 'Torah', 0, 4, 1, 'at least '],
  ['wildcard', 'Wildcard', 0, 3, 1, ''], ['longest', 'Longest piece', 5, 120, 5, ' min'], ['halflife', 'Habits fade over', 7, 180, 7, ' days'], ['hour', 'Ready by', 3, 11, 1, ':00']];
const fmt = (m, v) => m[5] === ' min' || m[5] === ' days' || m[5] === ':00' ? (m[5] === ':00' ? String(v).padStart(2, '0') + ':00' : v + m[5]) : (!v && m[5] ? 'none' : m[5] + v);
const DAYS = [['sun', 'Sun'], ['mon', 'Mon'], ['tue', 'Tue'], ['wed', 'Wed'], ['thu', 'Thu'], ['fri', 'Fri'], ['sat', 'Sat']];

async function taste(){
  $('#main').innerHTML = '<div class="top"><h1>Taste</h1><span class="spacer"></span><a class="btn sm" href="#edition">Edition</a></div><div class="page edtaste" id="edtaste"><span class="mute">Loading…</span></div>';
  T = await api('/api/edition/taste');
  drawTaste();
}
function drawTaste(){
  const page = $('#edtaste'); if (!page || !T) return;
  const s = T.settings, seen = T.seen || {};
  const learn = [['watched', 'Watched'], ['opened', 'Opened'], ['played', 'Played'], ['highlighted', 'Highlighted'], ['saved', 'Saved'], ['up', 'Thumbs up'], ['down', 'Thumbs down']]
    .filter(([k]) => seen[k]).map(([k, l]) => '<span class="edlchip"><b>' + l + '</b> ' + seen[k] + '</span>').join('');
  const top = Math.max(0.01, ...T.topics.map(t => t.weight));
  const topics = T.topics.length ? T.topics.map(t => '<div class="edtrow"><span class="edtn">' + esc(t.name) + '</span><div class="edbar"><i style="width:' + Math.round(100 * t.weight / top) + '%"></i></div>' +
      (ARROW[t.trend] || '') + seg3('topic', t.name, t.adj) + '</div>').join('') : '<p class="mute" style="margin:0">None yet.</p>';
  const srcs = T.sources.map(x => '<div class="edsrc"><div><span>' + esc(x.name) + '</span><em>' + esc(facts(x.facts)) + '</em></div>' + seg3('source', x.name, x.adj) + '</div>').join('');
  const muted = T.muted.map(m => '<div class="edsrc muted"><div><span>' + esc(m.replace(/^folder:/, '')) + '</span><em>' + (m.startsWith('folder:') ? 'folder' : '') + '</em></div><button class="linkbtn tiny" data-unmute="' + esc(m) + '">Unmute</button></div>').join('');
  const mix = MIX.map(m => '<div class="edmrow"><span>' + m[1] + '</span><div class="edstep"><button data-step="' + m[0] + '" data-d="-1" aria-label="Less">−</button><b>' + esc(fmt(m, s[m[0]])) + '</b><button data-step="' + m[0] + '" data-d="1" aria-label="More">+</button></div></div>').join('');
  const sw = (k, l) => '<label class="edmrow"><span>' + l + '</span><input type="checkbox" class="sw" data-flag="' + k + '"' + (s[k] ? ' checked' : '') + '></label>';
  const days = '<div class="edmrow"><span>Days</span><div class="eddays">' + DAYS.map(([k, l]) => '<button class="' + (s.days.includes(k) ? 'on' : '') + '" data-day="' + k + '">' + l + '</button>').join('') + '</div></div>';
  const rp = T.report || {}, rise = (T.rising || []).map(r => '<span class="edlchip">' + esc(r.word) + '</span>').join('');
  const how = rp.shown ? '<div class="edlearn"><span class="edlh2">Last 2 weeks</span>' + [['Shown', rp.shown], ['Opened', rp.opened], ['Read', rp.read], ['👍', rp.up], ['👎', rp.down]]
    .map(([l, n]) => '<span class="edlchip"><b>' + l + '</b> ' + n + '</span>').join('') + '</div>' : '';
  page.innerHTML = how + (learn ? '<div class="edlearn">' + learn + '</div>' : '') + (rise ? '<div class="edlearn"><span class="edlh2">Picking up on</span>' + rise + '</div>' : '') +
    '<div class="edtcols"><section class="card"><div class="cardh"><h2>Topics</h2><button class="linkbtn tiny" data-ed="topics">Name them again</button></div>' + topics + '</section>' +
    '<div class="edtside"><section class="card"><h2>Mix</h2>' + sw('on', 'Every morning') + days + mix + sw('kindle', 'Kindle') + sw('ai', 'Chosen by the model') + '</section></div></div>' +
    ((T.pool || []).length ? '<section class="card"><div class="cardh"><h2>Pool</h2><span class="mute tiny">' + T.pool.reduce((n, c) => n + c.feeds, 0) + ' feeds · ' +
      T.pool.reduce((n, c) => n + c.posts, 0) + ' posts in 2 days</span></div><div class="edsrcs">' + T.pool.map(c =>
      '<div class="edsrc' + (c.muted ? ' muted' : '') + '"><div><span>' + esc(c.name) + '</span><em>' + c.feeds + ' feeds · ' + c.posts + ' posts</em></div>' +
      '<button class="linkbtn tiny" data-poolmute="' + esc(c.folder) + '" data-on="' + (c.muted ? '0' : '1') + '">' + (c.muted ? 'Unmute' : 'Mute') + '</button></div>').join('') +
      '</div></section>' : '') +
    '<section class="card"><h2>Sources</h2><div class="edsrcs">' + srcs + '</div>' +
    '<div class="edmute"><input class="field" id="edmutein" aria-label="Mute a source" placeholder="Source, or folder:Name"><button class="btn sm" data-ed="mute">Mute</button></div>' +
    (muted ? '<h3 class="edmh">Muted</h3><div class="edsrcs">' + muted + '</div>' : '') + '</section>';
}
async function put(body){
  try { const r = await api('/api/edition/settings', { method: 'PUT', body: JSON.stringify(body) }); T.settings = Object.assign(T.settings, r.settings); }
  catch(e) { toast(e.message); }
}
document.addEventListener('click', async e => {
  if (!T || C.S.route[0] !== 'edition' || C.S.route[1] !== 'taste') return;
  const a = e.target.closest && e.target.closest('[data-adj]');
  if (a) {
    const name = a.dataset.name, kind = a.dataset.kind, adj = a.classList.contains('on') ? '' : a.dataset.adj;
    await put({ [kind]: { name, adj } });
    if (kind === 'topic') { const t = T.topics.find(x => x.name === name); if (t) t.adj = adj; }
    else { const x = T.sources.find(x => x.name === name); if (x) x.adj = adj === 'mute' ? '' : adj; if (adj === 'mute') { T.sources = T.sources.filter(x => x.name !== name); T.muted = [...T.muted, name].sort(); } }
    drawTaste(); return;
  }
  const pm = e.target.closest && e.target.closest('[data-poolmute]');
  if (pm) { const on = pm.dataset.on === '1'; await put({ source: { name: 'folder:' + pm.dataset.poolmute, adj: on ? 'mute' : '' } });
    const c = T.pool.find(x => x.folder === pm.dataset.poolmute); if (c) c.muted = on; drawTaste(); return; }
  const u = e.target.closest && e.target.closest('[data-unmute]');
  if (u) { await put({ source: { name: u.dataset.unmute, adj: '' } }); T.muted = T.muted.filter(m => m !== u.dataset.unmute); drawTaste(); return; }
  const st = e.target.closest && e.target.closest('[data-step]');
  if (st) {
    const m = MIX.find(x => x[0] === st.dataset.step), v = Math.max(m[2], Math.min(m[3], (T.settings[m[0]] || 0) + m[4] * Number(st.dataset.d)));
    T.settings[m[0]] = v; drawTaste(); await put({ [m[0]]: v }); return;
  }
  const d = e.target.closest && e.target.closest('[data-day]');
  if (d && d.closest('.eddays')) {
    const k = d.dataset.day, days = T.settings.days.includes(k) ? T.settings.days.filter(x => x !== k) : [...T.settings.days, k];
    T.settings.days = DAYS.map(x => x[0]).filter(x => days.includes(x)); drawTaste(); await put({ days: T.settings.days }); return;
  }
  const b = e.target.closest && e.target.closest('[data-ed]');
  if (b && b.dataset.ed === 'mute') {
    const v = ($('#edmutein').value || '').trim(); if (!v) return;
    await put({ source: { name: v, adj: 'mute' } }); T.muted = [...new Set([...T.muted, v])].sort(); drawTaste(); return;
  }
  if (b && b.dataset.ed === 'topics') {
    b.disabled = true; b.textContent = 'Naming…';
    try { await api('/api/edition/topics', { method: 'POST' }); T = await api('/api/edition/taste'); drawTaste(); }
    catch(err) { toast(err.message); b.disabled = false; b.textContent = 'Name them again'; }
  }
});
document.addEventListener('change', async e => {
  const f = e.target.dataset && e.target.dataset.flag;
  if (f && T && C.S.route[0] === 'edition') { T.settings[f] = e.target.checked; await put({ [f]: e.target.checked }); }
});
})();
