/* Learn (daf/areas.py): areas, a subject each, and what's gathered to learn it.

   #learn          the areas, a card each with a few of its things on it; Edit renames, recolours,
                   moves and removes them; New area asks for a name, a goal, a colour, and whether
                   the helper suggests things
   #learn/<id>     an area: Continue with the next thing, Up next in order, its books, articles and
                   videos (and their highlights), its feeds, and the helper's suggestions

   Highlights and Review are Learn's other pages in the new look (look2.js). Things get into an area
   from its own Add (a search over Daf, a link, a site to follow), from Add to Daf's Area, from a
   book's ⋯, and from the helper. */
(() => {
const C = window.DafCore, { $, esc, api, toast, S } = C;
const L = C.Learn = { areas: null };
const COLORS = ['#7a1f2b', '#3d5468', '#6b4a2b', '#2f5d46', '#4b3a78', '#8a5a12'];
const shade = (hex, f) => '#' + (hex || COLORS[0]).slice(1).match(/../g).map(h => Math.round(parseInt(h, 16) * f).toString(16).padStart(2, '0')).join('');
const tint = a => '--a1:' + shade(a.color, 0.5) + ';--a2:' + a.color;
const svg = d => '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="' + d + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const KIND = { book: 'M5 3.5h8l2 2v11H5zM8 3.5v13', article: 'M5 3.5h10v13H5zM7.5 7h5M7.5 10h5M7.5 13h3', video: 'M3 5.5h14v9H3zM8.5 8l3.5 2-3.5 2z',
  feed: 'M5 4.5a10.5 10.5 0 0 1 10.5 10.5M5 9a6 6 0 0 1 6 6M5.5 14.5h.01' };
const KNAME = { book: 'Book', article: 'Article', video: 'Video', feed: 'Feed' };
const PLUS = '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
const enc = encodeURIComponent;

L.load = async () => {
  try { L.areas = (await api('/api/areas')).areas; } catch(e){ L.areas = L.areas || []; }
  if (C.Look && C.Look.on && C.Look.side) C.Look.side();
  return L.areas;
};
// Into an area: { ref } (book:, doc:, feed:), { url } (saved to the Library first) or { feed } (followed first)
L.put = (aid, what) => api('/api/areas/' + enc(aid) + '/items', { method: 'POST', body: JSON.stringify(what) });

function sheet(html, wide){
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false; m.classList.toggle('wide', !!wide);
  m.innerHTML = html; return m;
}

/* ---------- the areas ---------- */
let editing = false;
async function home(){
  $('#main').innerHTML = '<div class="top"><h1>Areas</h1><span class="spacer"></span><button class="btn sm" data-ln="edit">' + (editing ? 'Done' : 'Edit') + '</button></div><div class="page lnhome"></div>';
  const list = L.areas || await L.load();
  drawHome(list);
  L.load().then(fresh => { if (S.route[0] === 'learn' && !S.route[1] && JSON.stringify(fresh) !== JSON.stringify(list)) drawHome(fresh); });
}
function art(a){
  const pics = a.pics.slice(0, 4).map((p, i) => '<img class="lnpic" src="' + esc(p) + '" alt="" loading="lazy" style="--r:' + [-3, 2, -1, 3][i] + 'deg" onerror="this.remove()">').join('');
  const tiles = pics ? '' : a.tiles.slice(0, 4).map((t, i) => '<span class="lntile" style="--r:' + [-3, 2, -1, 3][i] + 'deg">' + esc(t) + '</span>').join('');
  return '<span class="lnart">' + (pics || tiles) + '</span>';
}
function drawHome(list){
  const page = $('#main .lnhome'); if (!page) return;
  const card = (a, i) => editing
    ? '<div class="lncard editing" data-id="' + esc(a.id) + '" style="' + tint(a) + '">' + art(a) +
      '<span class="lnsw">' + COLORS.map(c => '<button class="' + (c === a.color ? 'on' : '') + '" data-ln-color="' + c + '" style="background:' + c + '" aria-label="Colour"></button>').join('') + '</span>' +
      '<button class="lnx" data-ln-del aria-label="Delete">×</button>' +
      '<span class="lnmove">' + (i ? '<button data-ln-move="-1" aria-label="Earlier">‹</button>' : '') + (i < list.length - 1 ? '<button data-ln-move="1" aria-label="Later">›</button>' : '') + '</span>' +
      '<span class="lnbody"><input class="field lnrename" data-ln-name value="' + esc(a.name) + '" aria-label="Name"><span class="lncount">' + esc(a.counts) + '</span></span></div>'
    : '<a class="lncard" href="#learn/' + enc(a.id) + '" style="' + tint(a) + '">' + art(a) +
      '<span class="lnbody"><b class="lnname">' + esc(a.name) + '</b><span class="lncount">' + esc(a.counts) + '</span>' + (a.month ? '<span class="lnmonth">' + esc(a.month) + '</span>' : '') + '</span></a>';
  page.innerHTML = '<div class="lngrid">' + list.map(card).join('') + '<button class="lnnew" data-ln="new">' + PLUS + '<span>New area</span></button></div>';
}

/* ---------- an area ---------- */
const P = { id: null, kind: 'all', editing: false, data: null, poll: 0 };
async function area(id){
  if (P.id !== id) Object.assign(P, { id, kind: 'all', editing: false, data: null });
  $('#main').innerHTML = '<div class="top"><a class="btn sm" href="#learn" aria-label="Areas">' + C.I.back + '</a><h1>…</h1><span class="spacer"></span>' +
    '<button class="btn sm" data-ln="add">Add</button><button class="btn sm" data-ln="aedit">' + (P.editing ? 'Done' : 'Edit') + '</button></div><div class="page lnarea"></div>';
  await refresh();
}
async function refresh(){
  const id = P.id;
  let p;
  try { p = await api('/api/areas/' + enc(id)); }
  catch(e){ const pg = $('#main .lnarea'); if (pg) pg.innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  if (S.route[0] !== 'learn' || decodeURIComponent(S.route[1] || '') !== id) return;
  P.data = p; draw();
  clearTimeout(P.poll);
  if (p.looking) P.poll = setTimeout(() => { if (S.route[0] === 'learn' && decodeURIComponent(S.route[1] || '') === id) refresh(); }, 4000);
}
function pic(x){
  if (x.pic) return '<img class="lnimg ' + (x.kind === 'book' ? 'book' : 'wide') + '" src="' + esc(x.pic) + '" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">';
  return '<span class="lnimg tile ' + (x.kind === 'book' ? 'book' : 'wide') + '">' + svg(KIND[x.kind] || KIND.article) + '</span>';
}
function draw(){
  const p = P.data, a = p.area, page = $('#main .lnarea'); if (!page) return;
  const h1 = $('#main .top h1'); h1.textContent = a.name; h1.classList.add('lnhide');        // (the panel says it)
  const bar = $('#main .top [data-ln="aedit"]'); if (bar) bar.textContent = P.editing ? 'Done' : 'Edit';
  const det = $('#main .top [data-ln="details"]');
  if (P.editing && !det) bar.insertAdjacentHTML('beforebegin', '<button class="btn sm" data-ln="details">Details</button>'); else if (!P.editing && det) det.remove();
  const next = p.next.find(x => x.go);
  const hero = '<section class="lnhero" style="' + tint(a) + '"><div class="lnhtext"><span class="lab">Area</span><h2>' + esc(a.name) + '</h2>' +
    (a.goal ? '<p>' + esc(a.goal) + '</p>' : '') +
    (next ? '<div class="lnhacts"><a class="btn primary" href="#' + esc(next.go) + '"><svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><path d="M6 4l10 6-10 6z" fill="currentColor"/></svg><span>Continue: ' + esc(C.shortTitle ? C.shortTitle(next.title) : next.title) + '</span></a></div>' : '') +
    '</div><div class="lnstat"><b>' + a.done + ' of ' + a.n + '</b>' + (a.month ? '<span>' + esc(a.month) + '</span>' : '') + '</div></section>';
  const steps = p.next.length ? '<div class="lnsteps"><div class="lnlab">Up next</div><div class="lnnext">' + p.next.map((x, i) =>
    '<a class="lnstep"' + (x.go ? ' href="#' + esc(x.go) + '"' : '') + '><span class="lnnum">' + (i + 1) + '</span><span class="lnrt"><b>' + esc(x.title) + '</b><i>' + esc([KNAME[x.kind], x.len].filter(Boolean).join(' · ')) + '</i></span></a>').join('') + '</div></div>' : '';
  const n = k => p.items.filter(x => x.kind === k).length;
  const kinds = [['all', 'All ' + p.items.length], ['book', 'Books ' + n('book')], ['article', 'Articles ' + n('article')], ['video', 'Videos ' + n('video')], ['hl', 'Highlights ' + p.highlights.length]]
    .filter(k => k[0] === 'all' || !/ 0$/.test(k[1]));
  const chips = '<div class="lnchips">' + kinds.map(k => '<button class="lnchip' + (P.kind === k[0] ? ' on' : '') + '" data-ln-kind="' + k[0] + '">' + k[1] + '</button>').join('') + '</div>';
  let body;
  if (P.kind === 'hl') body = p.highlights.map(h => '<div class="lnhl"><p dir="auto">' + esc(h.text || '') + '</p><span>' + esc(h.title || '') + '</span></div>').join('');
  else {
    const rows = p.items.filter(x => P.kind === 'all' || x.kind === P.kind);
    body = rows.map((x, i) => '<div class="lnrow" data-ref="' + esc(x.ref) + '">' +
      (x.go ? '<a class="lnrowmain" href="#' + esc(x.go) + '">' : '<span class="lnrowmain">') + pic(x) +
      '<span class="lnrt"><b>' + esc(x.title) + '</b><i>' + svg(KIND[x.kind] || KIND.article) + esc([x.by, x.len].filter(Boolean).join(' · ')) + '</i></span>' + (x.go ? '</a>' : '</span>') +
      (x.st === 'Wanted' ? '<button class="btn sm" data-ln-find="' + esc(x.title) + '">Find</button>' : '') +
      (x.st ? '<span class="lnst' + (x.st === 'Done' ? ' done' : x.st === 'New' ? ' new' : '') + '">' + esc(x.st) + '</span>' : '') +
      (P.editing ? '<span class="lnedit">' + (i ? '<button data-ln-up aria-label="Earlier">↑</button>' : '') + (i < rows.length - 1 ? '<button data-ln-down aria-label="Later">↓</button>' : '') +
        '<button data-ln-rm aria-label="Take out">×</button></span>' : '') + '</div>').join('');
  }
  const feeds = '<section class="card lnfeeds"><div class="cardh"><h2>Feeds</h2><span class="spacer"></span><button class="linkbtn" data-ln="follow">Follow</button></div>' +
    p.feeds.map(f => '<div class="lnrow" data-ref="' + esc(f.ref) + '"><a class="lnrowmain" href="#' + esc(f.go) + '">' + svg(KIND.feed) + '<span class="lnrt"><b>' + esc(f.title) + '</b></span></a>' +
      (f.new ? '<span class="lnst new">' + f.new + ' new</span>' : '') + (P.editing ? '<span class="lnedit"><button data-ln-rm aria-label="Take out">×</button></span>' : '') + '</div>').join('') + '</section>';
  const sugg = a.suggest ? '<section class="card lnsugg"><div class="cardh"><h2>Suggestions</h2></div>' +
    p.suggestions.map(s => '<div class="lnsg"><span class="lnsk">' + svg(KIND[s.kind] || KIND.article) + '</span><span class="lnrt"><b>' + esc(s.title) + '</b><i>' + esc([KNAME[s.kind], s.by].filter(Boolean).join(' · ')) + '</i></span>' +
      '<button class="btn sm primary" data-ln-take="' + esc(s.id) + '">Add</button><button class="lnno" data-ln-skip="' + esc(s.id) + '" aria-label="Not this">×</button></div>').join('') +
    (p.looking ? '<p class="lnlook"><span class="spin"></span>Looking…</p>' : (p.error ? '<p class="mute tiny">' + esc(p.error) + '</p>' : '') + '<button class="btn sm" data-ln="more">Find more</button>') + '</section>' : '';
  page.innerHTML = hero + steps + '<div class="lncols"><section class="card lnlist">' + chips + body + '</section><div class="lnside">' + feeds + sugg + '</div></div>';
}

/* ---------- the sheets ---------- */
function areaSheet(a){
  const m = sheet('<h2>' + (a ? 'Area' : 'New area') + '</h2>' +
    '<input class="field" id="lnname" placeholder="Name" autocomplete="off" value="' + esc(a ? a.name : '') + '">' +
    '<input class="field" id="lngoal" placeholder="Goal" autocomplete="off" value="' + esc(a ? a.goal : '') + '">' +
    '<div class="lnswrow">' + COLORS.map((c, i) => '<button class="' + ((a ? a.color === c : !i) ? 'on' : '') + '" data-ln-pick="' + c + '" style="background:' + c + '" aria-label="Colour"></button>').join('') + '</div>' +
    '<label class="aaline"><input type="checkbox" id="lnsug"' + (!a || a.suggest ? ' checked' : '') + '> Suggestions</label>' +
    '<div class="lnbtns">' + (a ? '<button class="btn" data-ln="delete">Delete</button><span class="spacer"></span>' : '') +
    '<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-ln="save">' + (a ? 'Save' : 'Create') + '</button></div>');
  m.dataset.lnfor = a ? a.id : '';
  $('#lnname').focus();
}
function addSheet(){
  const a = P.data.area;
  sheet('<h2>Add to ' + esc(a.name) + '</h2>' +
    '<input class="field" id="lnq" placeholder="Search Daf" autocomplete="off"><div id="lnres" class="lnres"></div>' +
    '<form id="lnlink" class="addrow"><input class="field" id="lnurl" type="url" inputmode="url" placeholder="Paste a link" autocomplete="off"><button class="btn" type="submit">Save</button></form>' +
    '<form id="lnfeed" class="addrow"><input class="field" id="lnfeedurl" type="url" inputmode="url" placeholder="A site or its feed" autocomplete="off"><button class="btn" type="submit">Follow</button></form>' +
    '<div id="lnstatus" class="tiny" role="status"></div><div class="lnbtns"><span class="spacer"></span><button class="btn primary" data-act="close" data-ln-after>Done</button></div>', true);
  $('#lnq').focus();
}
let searchT = 0;
document.addEventListener('input', e => {
  if (e.target.id !== 'lnq') return;
  clearTimeout(searchT);
  const q = e.target.value.trim();
  searchT = setTimeout(async () => {
    const box = $('#lnres'); if (!box) return;
    if (q.length < 2) { box.innerHTML = ''; return; }
    let r; try { r = await api('/api/search?q=' + enc(q)); } catch(err){ box.textContent = err.message; return; }
    const have = new Set((P.data ? P.data.items.concat(P.data.feeds) : []).map(x => x.ref));
    const rows = r.books.map(b => ['book:' + b.id, 'book', b.title, b.author]).concat(r.docs.map(d => ['doc:' + d.id, d.kind === 'video' ? 'video' : 'article', d.title, d.source]));
    box.innerHTML = rows.length ? rows.map(x => '<div class="lnsg"><span class="lnsk">' + svg(KIND[x[1]]) + '</span><span class="lnrt"><b>' + esc(x[2] || '') + '</b><i>' + esc(x[3] || '') + '</i></span>' +
      (have.has(x[0]) ? '<span class="lnst done">Added</span>' : '<button class="btn sm" data-ln-addref="' + esc(x[0]) + '">Add</button>') + '</div>').join('') : '<p class="mute tiny">Nothing in Daf</p>';
  }, 250);
});
document.addEventListener('submit', async e => {
  if (e.target.id !== 'lnlink' && e.target.id !== 'lnfeed') return;
  e.preventDefault();
  const feed = e.target.id === 'lnfeed', i = feed ? $('#lnfeedurl') : $('#lnurl'), st = $('#lnstatus'), v = i.value.trim(); if (!v) return;
  st.textContent = feed ? 'Looking for its feed…' : 'Saving…';
  try { await L.put(P.id, feed ? { feed: v } : { url: v }); st.textContent = feed ? 'Following it, in this area' : 'Saved, in this area'; i.value = ''; }
  catch(err){ st.textContent = err.message; }
});
// Add to an area, from anywhere: the areas, each one switched on or off for this thing.
L.pick = async (ref, title) => {
  let r; try { r = await api('/api/areas?ref=' + enc(ref)); } catch(e){ toast(e.message); return; }
  const on = new Set(r.in);
  sheet('<h2>Add to an area</h2>' + (title ? '<p class="mute" style="margin:0">' + esc(title) + '</p>' : '') +
    '<div class="lnpick">' + r.areas.map(a => '<label class="aaline"><input type="checkbox" data-ln-in="' + esc(a.id) + '"' + (on.has(a.id) ? ' checked' : '') + '><span class="lndot" style="background:' + esc(a.color) + '"></span>' + esc(a.name) + '</label>').join('') + '</div>' +
    '<div class="lnbtns"><button class="btn" data-ln="pnew">New area</button><span class="spacer"></span><button class="btn primary" data-act="close">Done</button></div>');
  $('#modal').dataset.lnref = ref;
};
document.addEventListener('change', async e => {
  const t = e.target; if (!t.matches || !t.matches('[data-ln-in]')) return;
  const ref = $('#modal').dataset.lnref, aid = t.dataset.lnIn;
  try {
    if (t.checked) await L.put(aid, { ref });
    else await api('/api/areas/' + enc(aid) + '/items?ref=' + enc(ref), { method: 'DELETE' });
    L.load();
  } catch(err){ toast(err.message); t.checked = !t.checked; }
});
// Add to Daf (reader.js openAdd): which area, when there are any; on an area's page, that one.
L.addPicker = m => {
  const list = L.areas || [], f = m.querySelector('#addlink'); if (!list.length || !f) return;
  const here = S.route[0] === 'learn' ? decodeURIComponent(S.route[1] || '') : '';
  f.insertAdjacentHTML('afterend', '<div class="lnaddto"><span class="mute tiny">Area</span><select class="field sm" id="addarea" aria-label="Area"><option value="">None</option>' +
    list.map(a => '<option value="' + esc(a.id) + '"' + (a.id === here ? ' selected' : '') + '>' + esc(a.name) + '</option>').join('') + '</select></div>');
};
L.chosen = () => { const s = $('#addarea'); return s && s.value; };

/* ---------- clicks ---------- */
document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('[data-ln],[data-ln-color],[data-ln-del],[data-ln-move],[data-ln-kind],[data-ln-up],[data-ln-down],[data-ln-rm],[data-ln-take],[data-ln-skip],[data-ln-pick],[data-ln-addref],[data-ln-find]');
  if (!t) return;
  const d = t.dataset, cardId = (t.closest('[data-id]') || {}).dataset;
  try {
    if (d.ln === 'edit') { editing = !editing; t.textContent = editing ? 'Done' : 'Edit'; drawHome(L.areas || []); }
    else if (d.ln === 'new' || d.ln === 'pnew') { const ref = d.ln === 'pnew' ? $('#modal').dataset.lnref : ''; areaSheet(null); $('#modal').dataset.lnthen = ref || ''; }
    else if (d.ln === 'save') {
      const m = $('#modal'), name = $('#lnname').value.trim(); if (!name) { $('#lnname').focus(); return; }
      const body = { name, goal: $('#lngoal').value.trim(), color: (m.querySelector('[data-ln-pick].on') || {}).dataset.lnPick, suggest: $('#lnsug').checked };
      if (m.dataset.lnfor) { await api('/api/areas/' + enc(m.dataset.lnfor), { method: 'PUT', body: JSON.stringify(body) }); C.closeModal(); await L.load(); refresh(); }
      else {
        const r = await api('/api/areas', { method: 'POST', body: JSON.stringify(body) }), then = m.dataset.lnthen;
        if (then) await L.put(r.id, { ref: then });
        C.closeModal(); L.areas = r.areas; await L.load(); location.hash = 'learn/' + enc(r.id);
      }
    }
    else if (d.ln === 'delete') {
      const id = $('#modal').dataset.lnfor, a = (L.areas || []).find(x => x.id === id);
      if (!confirm('Delete “' + (a ? a.name : '') + '”? What’s in it stays in Daf.')) return;
      await api('/api/areas/' + enc(id), { method: 'DELETE' }); C.closeModal(); await L.load(); location.hash = 'learn';
    }
    else if (d.lnPick) { t.parentNode.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === t)); }
    else if (d.lnColor) { await api('/api/areas/' + enc(cardId.id), { method: 'PUT', body: JSON.stringify({ color: d.lnColor }) }); drawHome(await L.load()); }
    else if (d.lnDel !== undefined && cardId) {
      const a = (L.areas || []).find(x => x.id === cardId.id);
      if (!confirm('Delete “' + (a ? a.name : '') + '”? What’s in it stays in Daf.')) return;
      await api('/api/areas/' + enc(cardId.id), { method: 'DELETE' }); drawHome(await L.load());
    }
    else if (d.lnMove) {
      const ids = (L.areas || []).map(a => a.id), i = ids.indexOf(cardId.id), j = i + +d.lnMove;
      if (j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      const r = await api('/api/areas/order', { method: 'PUT', body: JSON.stringify({ ids }) }); L.areas = r.areas; drawHome(r.areas); L.load();
    }
    else if (d.ln === 'aedit') { P.editing = !P.editing; draw(); }
    else if (d.ln === 'details') areaSheet(P.data.area);
    else if (d.ln === 'add') addSheet();
    else if (d.ln === 'follow') { addSheet(); $('#lnfeedurl').focus(); }
    else if (d.ln === 'more') { await api('/api/areas/' + enc(P.id) + '/suggest', { method: 'POST' }); refresh(); }
    else if (d.lnKind) { P.kind = d.lnKind; draw(); }
    else if (d.lnUp !== undefined || d.lnDown !== undefined) {
      const ref = t.closest('[data-ref]').dataset.ref, refs = P.data.items.map(x => x.ref).concat(P.data.feeds.map(x => x.ref)), i = refs.indexOf(ref), j = i + (d.lnUp !== undefined ? -1 : 1);
      if (j < 0 || j >= refs.length) return;
      [refs[i], refs[j]] = [refs[j], refs[i]];
      await api('/api/areas/' + enc(P.id) + '/items/order', { method: 'PUT', body: JSON.stringify({ refs }) }); refresh();
    }
    else if (d.lnRm !== undefined) { await api('/api/areas/' + enc(P.id) + '/items?ref=' + enc(t.closest('[data-ref]').dataset.ref), { method: 'DELETE' }); refresh(); L.load(); }
    else if (d.lnTake) { t.disabled = true; t.textContent = 'Adding…'; await api('/api/areas/suggestions/' + enc(d.lnTake), { method: 'POST', body: '{}' }); refresh(); L.load(); }
    else if (d.lnSkip) { await api('/api/areas/suggestions/' + enc(d.lnSkip), { method: 'POST', body: JSON.stringify({ skip: true }) }); refresh(); }
    else if (d.lnAddref) { await L.put(P.id, { ref: d.lnAddref }); t.outerHTML = '<span class="lnst done">Added</span>'; }
    else if (d.lnFind) { if (C.AddBook) C.AddBook.open(d.lnFind); }
  } catch(err){ toast(err.message); }
});
// renaming an area in place: on Enter, or when the box is left
document.addEventListener('change', async e => {
  const t = e.target; if (!t.matches || !t.matches('[data-ln-name]')) return;
  const id = t.closest('[data-id]').dataset.id, name = t.value.trim(); if (!name) return;
  try { await api('/api/areas/' + enc(id), { method: 'PUT', body: JSON.stringify({ name }) }); L.load(); } catch(err){ toast(err.message); }
});
// the Add sheet's Done: the area's page again, with what was added
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('[data-ln-after]') && S.route[0] === 'learn' && S.route[1]) setTimeout(refresh, 50); });

C.views.learn = async args => {
  const id = decodeURIComponent((args || [])[0] || '');
  return id ? area(id) : home();
};
if (C.Look && C.Look.on) L.load();
})();
