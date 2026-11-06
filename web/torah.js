/* Daf Torah shelf and word lookup (Phase 7). */
(() => {
const C = window.DafCore, { api, esc, toast, $, ago } = C;
const mins = w => w ? Math.max(1, Math.round(w / 238)) + ' min' : '';

function weekCard(d){
  return '<a class="tcard" href="#read/' + encodeURIComponent(d.id) + '"><span class="tk">' + esc(d.author === 'Haftarah' ? 'Haftarah' : 'Parasha') + '</span>' +
    '<b>' + esc(d.title) + '</b><span class="mute tiny">' + esc(d.summary || '') + '</span>' +
    '<span class="tiny mute">' + (d.progress ? C.bar(d.progress) + ' ' + Math.round(d.progress) + '% · ' : '') + mins(d.words) + (d.highlights ? ' · ' + d.highlights + ' highlight' + (d.highlights === 1 ? '' : 's') : '') + '</span></a>';
}

// A post or an episode from the Divrei Torah folder; an episode opens in Daf's player.
const postRow = (r, t) => {
  const len = r.kind === 'podcast' ? (r.duration ? Math.round(r.duration / 60) + ' min' : '') : (r.words >= 200 ? mins(r.words) : '');
  return '<a class="nrow tr" href="#read/' + encodeURIComponent(r.id) + '"' + (r.status === 'seen' ? ' data-seen' : '') + '><b' + (/[֐-׿]/.test(r.title || '') ? ' dir="rtl" lang="he"' : '') + '>' + esc(r.title || 'Untitled') + '</b>' +
    '<span class="mute tiny">' + [esc(r.source || ''), r.this_parasha && t.parasha ? 'on ' + esc(t.parasha.name) : '', len, ago(r.when || r.added)].filter(Boolean).join(' · ') + '</span></a>';
};
const essayRow = e => '<button class="nrow tr essay" data-essay="' + esc(e.path) + '"><b>' + esc(e.title) + '</b><span class="mute tiny">' + esc(e.author || '') + (e.words ? ' · ' + mins(e.words) : '') + (e.progress ? ' · ' + Math.round(e.progress) + '% read' : '') + (e.highlights ? ' · ' + e.highlights + ' highlight' + (e.highlights === 1 ? '' : 's') : '') + '</span></button>';
const earlierRow = d => '<a class="nrow tr" href="#read/' + encodeURIComponent(d.id) + '"><b>' + esc(d.title) + '</b><span class="mute tiny">' + esc(d.summary || '') + (d.highlights ? ' · ' + d.highlights + ' highlights' : '') + '</span></a>';

// The search in the bar: the week's readings, the divrei Torah and episodes, the essays and the earlier
// weeks, by their titles and what's under them, on the page.
let shelf = null;
C.views.torah = async () => {
  $('#main').innerHTML = '<div class="top"><h1>Torah</h1><span class="spacer"></span><span class="mute tiny" id="tsub"></span>' + C.Find.html('torah', 'Search Torah', draw) + '</div><div class="page" id="tpage"><span class="mute">Loading…</span></div>';
  const t = shelf = await C.swr('/api/torah');
  if (t.parasha) $('#tsub').innerHTML = esc(t.parasha.name || '') + (t.parasha.he ? ' · <span lang="he">' + esc(t.parasha.he) + '</span>' : '');
  draw();
};
function draw(){
  const t0 = shelf, page = $('#tpage'); if (!t0 || !page) return;
  const q = C.Find.q('torah'), m = C.Find.match;
  if (q) {
    const t = Object.assign({}, t0, { week: t0.week.filter(d => m(q, d.title, d.summary, d.author)), divrei: (t0.divrei || []).filter(r => m(q, r.title, r.source, r.author)),
      listen: (t0.listen || []).filter(r => m(q, r.title, r.source, r.author)),
      essays: (t0.essays || []).filter(e => m(q, e.title, e.author, e.series)), earlier: t0.earlier.filter(d => m(q, d.title, d.summary)) });
    page.innerHTML = (t.week.length ? '<div class="tweek">' + t.week.map(weekCard).join('') + '</div>' : '') +
      (t.divrei.length ? '<section class="card"><div class="cardh"><h2>Divrei Torah this week</h2></div>' + t.divrei.map(r => postRow(r, t)).join('') + '</section>' : '') +
      (t.listen.length ? '<section class="card"><h2>Listen</h2>' + t.listen.map(r => postRow(r, t)).join('') + '</section>' : '') +
      (t.essays.length ? '<section class="card"><div class="cardh"><h2>From your vault</h2></div>' + t.essays.map(essayRow).join('') + '</section>' : '') +
      (t.earlier.length ? '<section class="card"><h2>Earlier weeks</h2>' + t.earlier.map(earlierRow).join('') + '</section>' : '') +
      (t.week.length + t.divrei.length + t.listen.length + t.essays.length + t.earlier.length ? '' : C.Find.none());
    return;
  }
  const t = t0;
  let h = '';
  h += t.week.length ? '<div class="tweek">' + t.week.map(weekCard).join('') + '</div>'
    : '<section class="card"><h2>This week’s reading isn’t here yet</h2><p class="mute" style="margin:0">Sefaria didn’t answer. Daf tries again on the next sync.</p></section>';
  const divrei = t.divrei || [], listen = t.listen || [];
  h += '<section class="card"><div class="cardh"><h2>Divrei Torah this week</h2>' + (t.folder ? '<a class="tiny" href="#feed/' + encodeURIComponent(t.folder) + '">In the Feed</a>' : '') + '</div>' +
    (divrei.length ? divrei.map(r => postRow(r, t)).join('') : '<p class="mute" style="margin:0">Nothing new this week.</p>') + '</section>';
  if (listen.length) h += '<section class="card"><h2>Listen</h2>' + listen.map(r => postRow(r, t)).join('') + '</section>';
  if (t.essays && t.essays.length) h += '<section class="card"><div class="cardh"><h2>From your vault</h2><span class="mute tiny">' + esc(t.essays[0].series || '') + ' on ' + esc(t.parasha ? t.parasha.name : '') + '</span></div>' +
    t.essays.map(essayRow).join('') +
    '<span class="mute tiny">Opens in Daf, so the time counts. Highlights go into the same note.</span></section>';
  if (t.earlier.length) h += '<section class="card"><h2>Earlier weeks</h2>' + t.earlier.map(earlierRow).join('') + '</section>';
  h += '<p class="mute tiny">Texts from Sefaria (JPS translation). Select a word to define it; select a Hebrew phrase to translate it. Highlights go to Reference/torah in the vault.</p>';
  page.innerHTML = h;
}

/* ---------- lookup ---------- */
function pop(rect, html){
  let p = $('#lookpop');
  if (!p) { p = document.createElement('div'); p.id = 'lookpop'; p.className = 'lkpop'; p.setAttribute('role', 'dialog'); document.body.appendChild(p); }
  p.innerHTML = '<button class="ib lkx" data-lk="close" aria-label="Close">×</button>' + html;
  p.hidden = false;
  const w = Math.min(380, window.innerWidth - 16);
  p.style.width = w + 'px';
  p.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, rect.left + rect.width / 2 - w / 2)) + 'px';
  const below = rect.bottom + 10, room = window.innerHeight - below;
  p.style.top = (room > 240 || rect.top < 260 ? below : Math.max(8, rect.top - 10 - Math.min(p.offsetHeight, 360))) + 'px';
  return p;
}
function entriesHTML(r){
  if (!r.entries.length) return '<p class="mute">Not in ' + esc(r.source) + '.</p>';
  return r.entries.map(e => '<div class="lke"><div class="lkh"><b' + (r.lang === 'he' ? ' lang="he" dir="rtl"' : '') + '>' + esc(e.head || r.word) + '</b> <span class="mute tiny">' + esc([e.pos, e.source].filter(Boolean).join(' · ')) + '</span></div><ol>' + e.defs.map(d => '<li>' + esc(d) + '</li>').join('') + '</ol></div>').join('');
}
let ctx = null;
C.lookup = async (info, sentence, translate) => {
  const word = info.text.trim();
  ctx = { word, sentence, rect: info.rect };
  if (translate) return inContext();
  pop(info.rect, '<div class="lkw">' + esc(word) + '</div><p class="mute">Looking it up…</p>');
  try {
    const r = await api('/api/lookup?q=' + encodeURIComponent(word));
    pop(info.rect, '<div class="lkw"' + (r.lang === 'he' ? ' lang="he" dir="rtl"' : '') + '>' + esc(word) + '</div><div class="lkbody">' + entriesHTML(r) + '</div>' +
      '<div class="lkfoot"><button class="btn sm" data-lk="ctx">In this sentence</button><span class="mute tiny">' + esc(r.source) + '</span></div>');
  } catch(e){ pop(info.rect, '<p class="mute">' + esc(e.message) + '</p><div class="lkfoot"><button class="btn sm" data-lk="ctx">Explain it in context</button></div>'); }
};
async function inContext(){
  const c = ctx; if (!c) return;
  pop(c.rect, '<div class="lkw"' + (/[֐-׿]/.test(c.word) ? ' lang="he" dir="rtl"' : '') + '>' + esc(c.word) + '</div><p class="mute">Working out what it means here… (about ten seconds)</p>');
  try {
    const r = await api('/api/lookup/context', { method:'POST', body:JSON.stringify({ word:c.word, sentence:c.sentence }) });
    pop(c.rect, '<div class="lkw"' + (/[֐-׿]/.test(c.word) ? ' lang="he" dir="rtl"' : '') + '>' + esc(c.word) + '</div><div class="lkbody lkctx">' + esc(r.answer).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>').replace(/\n/g, '<br>') + '</div><div class="lkfoot"><span class="mute tiny">In context</span></div>');
  } catch(e){ pop(c.rect, '<p class="mute">' + esc(e.message) + '</p>'); }
}
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-essay]'); if (!b) return;
  b.disabled = true;
  try { const r = await api('/api/torah/essay', { method:'POST', body:JSON.stringify({ path:b.dataset.essay }) }); location.hash = '#read/' + encodeURIComponent(r.id); }
  catch(err){ toast(err.message); b.disabled = false; }
});
function closePop(){ const p = $('#lookpop'); if (p) p.hidden = true; }
document.addEventListener('click', e => {
  const a = e.target.closest('[data-lk]');
  if (a) { if (a.dataset.lk === 'close') closePop(); else if (a.dataset.lk === 'ctx') inContext(); return; }
  if (!e.target.closest('#lookpop') && !e.target.closest('#selbar')) closePop();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePop(); });
window.addEventListener('hashchange', closePop);
})();
