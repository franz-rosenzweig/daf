/* Learn (daf/areas.py): areas, a subject each, and what's gathered to learn it.

   #learn          the areas, a card each with a few of its things on it; Edit renames, recolours,
                   moves and removes them; New area asks for a name, a goal, a colour, and whether
                   the helper suggests things
   #learn/ask      Ask across every area (areaagent.py ALL), which can offer a new area to start
   #learn/<id>     an area: its band, then Overview (its sections), Everything (its books, articles,
                   videos and their highlights, its feeds, the helper's suggestions), Plan and Ask
                   (#learn/<id>/all, /plan, /ask; the agent in daf/areaagent.py)

   Highlights and Review are Learn's other pages in the new look (look2.js). Things get into an area
   from its own Add (a search over Daf, a link, a site to follow), from Add to Daf's Area, from Add to
   an area (L.pick: a book's page and ⋯, an article's or a video's ⋯, the rows picked in the Feed and
   the Library), and from the helper. */
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
// a thing's handle (drag it to move it) and its × (take it out)
const GRIPI = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="currentColor"><circle cx="7.5" cy="5" r="1.4"/><circle cx="12.5" cy="5" r="1.4"/><circle cx="7.5" cy="10" r="1.4"/><circle cx="12.5" cy="10" r="1.4"/><circle cx="7.5" cy="15" r="1.4"/><circle cx="12.5" cy="15" r="1.4"/></svg>';
const GRIP = '<button class="lngrip" type="button" data-drag aria-label="Move">' + GRIPI + '</button>';
const XI = '<svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>';
const takeBtn = ref => '<button class="lnrx" type="button" data-ln-x="' + esc(ref) + '" aria-label="Take out">' + XI + '</button>';

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
// Areas home's two pages: the areas, and Ask across all of them (#learn/ask)
const homeTabs = cur => '<nav class="lntabs lnhtabs" aria-label="Learn">' + [['areas', 'Areas', '#learn'], ['ask', 'Ask', '#learn/ask']].map(t =>
  '<a class="lntab' + (t[0] === cur ? ' on' : '') + '" href="' + t[2] + '"' + (t[0] === cur ? ' aria-current="page"' : '') + '>' + t[1] +
  (t[0] === 'ask' && H.data && H.data.chat.some(x => x.state === 'asking') ? '<span class="lndotw"></span>' : '') + '</a>').join('') + '</nav>';
async function home(){
  $('#main').innerHTML = '<div class="top"><h1 class="lnhide">Areas</h1><span class="spacer"></span><button class="btn sm" data-ln="edit">' + (editing ? 'Done' : 'Edit') + '</button></div>' +
    '<div class="page lnhome">' + homeTabs('areas') + '<div class="lnhomebody"></div></div>';
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
  const page = $('#main .lnhome .lnhomebody'); if (!page || $('#main .lnaskhome')) return;
  const card = (a, i) => editing
    ? '<div class="lncard editing" data-id="' + esc(a.id) + '" data-drow style="' + tint(a) + '">' + art(a) + '<span class="lncgrip">' + GRIP + '</span>' +
      '<span class="lnsw">' + COLORS.map(c => '<button class="' + (c === a.color ? 'on' : '') + '" data-ln-color="' + c + '" style="background:' + c + '" aria-label="Colour"></button>').join('') + '</span>' +
      '<button class="lnx" data-ln-del aria-label="Delete">×</button>' +
      '<span class="lnmove">' + (i ? '<button data-ln-move="-1" aria-label="Earlier">‹</button>' : '') + (i < list.length - 1 ? '<button data-ln-move="1" aria-label="Later">›</button>' : '') + '</span>' +
      '<span class="lnbody"><input class="field lnrename" data-ln-name value="' + esc(a.name) + '" aria-label="Name"><span class="lncount">' + esc(a.counts) + '</span></span></div>'
    : '<a class="lncard" href="#learn/' + enc(a.id) + '" style="' + tint(a) + '">' + art(a) +
      '<span class="lnbody"><b class="lnname">' + esc(a.name) + '</b><span class="lncount">' + esc(a.counts) + '</span>' + (a.month ? '<span class="lnmonth">' + esc(a.month) + '</span>' : '') + '</span></a>';
  page.innerHTML = '<div class="lngrid"' + (editing ? ' data-dlist="areas"' : '') + '>' + list.map(card).join('') + '<button class="lnnew" data-ln="new">' + PLUS + '<span>New area</span></button></div>';
}

/* ---------- an area ---------- */
// Its band (name, colour, how far along), then four pages: Overview (its sections: the helper's
// layout once one is kept, else DEFAULT's in areaagent.py), Everything (all its things, feeds and
// suggestions), Plan and Ask (areaagent.py). #learn/<id>[/all|/plan|/ask].
const TABS = [['overview', 'Overview'], ['all', 'Everything'], ['plan', 'Plan'], ['ask', 'Ask']];
const P = { id: null, tab: 'overview', kind: 'all', editing: false, data: null, poll: 0, anywhere: false, off: new Set(), pace: { mins: 30, weeks: 4 }, again: false, goQ: '' };
const offKey = id => 'lnoff.' + id;
async function area(id, tab){
  if (P.id !== id) Object.assign(P, { id, kind: 'all', editing: false, data: null, again: false, off: new Set(C.lsGet ? C.lsGet(offKey(id), []) : []) });
  const was = P.tab; P.tab = TABS.some(t => t[0] === tab) ? tab : 'overview';
  if (was !== P.tab) { P.editing = false; P.again = false; }
  $('#main').innerHTML = '<div class="top"><a class="btn sm" href="#learn" aria-label="Areas">' + C.I.back + '</a><h1>…</h1><span class="spacer"></span>' +
    '<button class="btn sm" data-ln="add">Add</button><button class="btn sm" data-ln="aedit">' + (P.editing ? 'Done' : 'Edit') + '</button></div><div class="page lnarea"></div>';
  if (P.data && P.data.area.id === id) draw();
  await refresh();
}
const busy = p => p.looking || p.working.plan || p.working.layout || p.chat.some(x => x.state === 'asking');
async function refresh(){
  const id = P.id;
  let p;
  try { p = await api('/api/areas/' + enc(id)); }
  catch(e){ const pg = $('#main .lnarea'); if (pg) pg.innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  if (S.route[0] !== 'learn' || decodeURIComponent(S.route[1] || '') !== id) return;
  P.data = p; draw();
  clearTimeout(P.poll);
  if (busy(p)) P.poll = setTimeout(() => { if (S.route[0] === 'learn' && decodeURIComponent(S.route[1] || '') === id) refresh(); }, 3500);
}
function pic(x){
  if (x.pic) return '<img class="lnimg ' + (x.kind === 'book' ? 'book' : 'wide') + '" src="' + esc(x.pic) + '" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">';
  return '<span class="lnimg tile ' + (x.kind === 'book' ? 'book' : 'wide') + '">' + svg(KIND[x.kind] || KIND.article) + '</span>';
}
const spin = words => '<p class="lnlook"><span class="spin"></span>' + words + '</p>';
const href = go => go ? ' href="#' + esc(go) + '"' : '';
function row(x, editable, i, n){
  return '<div class="lnrow" data-ref="' + esc(x.ref) + '" data-drow>' + (editable ? '' : GRIP) +
    (x.go ? '<a class="lnrowmain" href="#' + esc(x.go) + '">' : '<span class="lnrowmain">') + pic(x) +
    '<span class="lnrt"><b>' + esc(x.title) + '</b><i>' + svg(KIND[x.kind] || KIND.article) + esc([x.by, x.len].filter(Boolean).join(' · ')) + '</i></span>' + (x.go ? '</a>' : '</span>') +
    (x.st === 'Wanted' ? '<button class="btn sm" data-ln-find="' + esc(x.title) + '">Find</button>' : '') +
    (x.st ? '<span class="lnst' + (x.st === 'Done' ? ' done' : x.st === 'New' ? ' new' : '') + '">' + esc(x.st) + '</span>' : '') +
    (editable ? '<span class="lnedit">' + (i ? '<button data-ln-up aria-label="Earlier">↑</button>' : '') + (i < n - 1 ? '<button data-ln-down aria-label="Later">↓</button>' : '') +
      '<button data-ln-rm aria-label="Take out">×</button></span>' : takeBtn(x.ref)) + '</div>';
}
const feedRow = (f, editable) => '<div class="lnrow" data-ref="' + esc(f.ref) + '" data-drow>' + (editable ? '' : GRIP) + '<a class="lnrowmain" href="#' + esc(f.go) + '">' + svg(KIND.feed) +
  '<span class="lnrt"><b>' + esc(f.title) + '</b></span></a>' + (f.new ? '<span class="lnst new">' + f.new + ' new</span>' : '') +
  (editable ? '<span class="lnedit"><button data-ln-rm aria-label="Take out">×</button></span>' : takeBtn(f.ref)) + '</div>';
function draw(){
  const p = P.data, a = p.area, page = $('#main .lnarea'); if (!page) return;
  const h1 = $('#main .top h1'); h1.textContent = a.name; h1.classList.add('lnhide');        // (the band says it)
  const bar = $('#main .top [data-ln="aedit"]'); if (bar) bar.textContent = P.editing ? 'Done' : 'Edit';
  const det = $('#main .top [data-ln="details"]');
  if (P.editing && !det) bar.insertAdjacentHTML('beforebegin', '<button class="btn sm" data-ln="details">Details</button>'); else if (!P.editing && det) det.remove();
  // what's being typed in Ask stays as it was
  const q = $('#lnaskq'), typed = q ? q.value : '', had = q && document.activeElement === q;
  const band = '<section class="lnband" style="' + tint(a) + '"><span class="lnbt"><h2>' + esc(a.name) + '</h2>' + (a.goal ? '<span>' + esc(a.goal) + '</span>' : '') + '</span>' +
    '<span class="lnbstat"><b>' + a.done + ' of ' + a.n + '</b>' + (a.month ? '<span>' + esc(a.month) + '</span>' : '') + '</span></section>' +
    '<nav class="lntabs" aria-label="' + esc(a.name) + '">' + TABS.map(t => '<a class="lntab' + (t[0] === P.tab ? ' on' : '') + '" href="#learn/' + enc(a.id) + (t[0] === 'overview' ? '' : '/' + t[0]) + '"' +
      (t[0] === P.tab ? ' aria-current="page"' : '') + '>' + t[1] + (t[0] === 'ask' && p.chat.some(x => x.state === 'asking') || t[0] === 'plan' && p.working.plan ? '<span class="lndotw"></span>' : '') + '</a>').join('') + '</nav>';
  page.innerHTML = band + '<div class="lntabbody">' + ({ overview, all: everything, plan: planTab, ask: askTab }[P.tab])(p) + '</div>';
  const q2 = $('#lnaskq'); if (q2) { q2.value = typed; if (had) q2.focus(); }
  if (P.goQ) { const el = document.getElementById('lnq-' + P.goQ); P.goQ = ''; if (el) el.scrollIntoView({ block: 'start' }); }
}

/* Overview: the sections */
const SNAME = { plan: 'This week', continue: 'Continue', next: 'Up next', highlights: 'Highlights', things: 'Things', questions: 'Questions', feeds: 'Feeds', suggestions: 'Suggestions' };
const ADDABLE = ['plan', 'continue', 'next', 'highlights', 'questions', 'feeds', 'suggestions'];
function overview(p){
  const tools = '<div class="lntools">' + (p.working.layout ? spin('Arranging…') : '<button class="btn sm" data-ln="rearrange">' + SPARK + 'Rearrange</button>') +
    (p.failed.layout && !p.working.layout ? '<span class="mute tiny">' + esc(p.failed.layout) + '</span>' : '') + '</div>';
  if (p.draft) return '<div class="lnkeep">' + SPARK + '<b>New layout</b><span class="spacer"></span><button class="btn sm primary" data-ln="lkeep">Keep</button><button class="btn sm" data-ln="ldrop">Undo</button></div>' +
    '<div class="lnsecs">' + p.draft.map(s => section(s, false, 0, true)).join('') + '</div>';
  const raw = rawLayout(p);
  return tools + '<div class="lnsecs" data-dlist="sections">' + p.sections.map(s => section(s, P.editing, raw.length)).join('') + '</div>' +
    (P.editing ? '<div class="lnaddsec"><span class="mute tiny">Add</span>' + ADDABLE.map(k => '<button class="lnchip" data-ln-addsec="' + k + '">' + SNAME[k] + '</button>').join('') +
      (p.layout ? '<span class="spacer"></span><button class="btn sm" data-ln="plain">Plain</button>' : '') + '</div>' : '');
}
// the layout as it's kept (or the plain one), to change by hand: every section, shown or not (s.at is its place)
const rawLayout = p => JSON.parse(JSON.stringify(p.raw));
function section(s, editable, n, draft){
  const title = s.title || SNAME[s.kind] || '';
  const ed = editable ? '<span class="lnedit">' + (s.at ? '<button data-ln-sup="' + s.at + '" aria-label="Earlier">↑</button>' : '') +
    (s.at < n - 1 ? '<button data-ln-sdown="' + s.at + '" aria-label="Later">↓</button>' : '') + '<button data-ln-srm="' + s.at + '" aria-label="Take out">×</button></span>' : '';
  let body = '', side = '';
  if (s.kind === 'plan') { const w = s.plan.weeks[s.plan.now]; side = '<span class="mute tiny">Week ' + (s.plan.now + 1) + ' of ' + s.plan.weeks.length + '</span>';
    body = progress(s.plan) + '<div class="lnwname">' + esc(w.name) + '</div><div class="lnwsteps"' + (draft ? '' : ' data-dlist="plan" data-week="' + s.plan.now + '"') + '>' +
      w.steps.map(st => step(st, false, draft)).join('') + '</div>'; }
  else if (s.kind === 'continue') { const x = s.item;
    body = '<a class="lncont" href="#' + esc(x.go) + '">' + pic(x) + '<span class="lnrt"><b>' + esc(x.title) + '</b><i>' + esc([x.by, x.len].filter(Boolean).join(' · ')) + '</i>' +
      '<span class="lnbar"><span style="width:' + Math.round(x.pct || 0) + '%"></span></span><i>' + esc(x.st === 'New' ? 'New' : x.st) + '</i></span></a>'; }
  else if (s.kind === 'next') body = '<div class="lnnextv"' + (draft ? '' : ' data-dlist="items"') + '>' + s.items.map((x, i) => '<div class="lnstep" data-ref="' + esc(x.ref) + '" data-drow>' + (draft ? '' : GRIP) +
      '<a class="lnstepm"' + href(x.go) + '><span class="lnnum">' + (i + 1) + '</span><span class="lnrt"><b>' + esc(x.title) + '</b><i>' +
      esc([KNAME[x.kind], x.len].filter(Boolean).join(' · ')) + '</i></span></a>' + (draft ? '' : takeBtn(x.ref)) + '</div>').join('') + '</div>';
  else if (s.kind === 'highlights') body = s.groups.map(g => (g.name ? '<div class="lngname">' + esc(g.name) + '</div>' : '') + '<div class="lnhls">' +
      g.hls.map(h => '<a class="lnhlc"' + href(h.go) + '><p dir="auto">' + esc(h.text) + '</p><span>' + esc(h.title) + '</span></a>').join('') + '</div>').join('');
  else if (s.kind === 'things') body = '<div' + (draft ? '' : ' data-dlist="things" data-at="' + s.at + '"') + '>' + s.items.map(x => row(x)).join('') + '</div>';
  else if (s.kind === 'questions') body = s.asked.map(x => '<a class="lnqrow" href="#learn/' + enc(P.id) + '/ask" data-ln-goq="' + esc(x.id) + '">' + SPARK + '<span class="lnrt"><b>' + esc(x.q) + '</b><i>' +
      x.n + (x.n === 1 ? ' source' : ' sources') + '</i></span></a>').join('');
  else if (s.kind === 'feeds') body = '<div' + (draft ? '' : ' data-dlist="items"') + '>' + s.feeds.map(f => feedRow(f)).join('') + '</div>';
  else if (s.kind === 'suggestions') body = suggRows(s.suggestions, s.looking, P.data.error);
  return '<section class="card lnsec lnsec-' + s.kind + (s.wide ? ' wide' : '') + '"' + (draft ? '' : ' data-drow data-at="' + s.at + '"') + '><div class="cardh">' + (draft ? '' : GRIP) +
    '<h2>' + esc(title) + '</h2><span class="spacer"></span>' + side + ed + '</div>' + body + '</section>';
}
function progress(plan){
  return '<div class="lnprog">' + plan.weeks.map((w, i) => '<span class="' + (w.done ? 'done' : i === plan.now ? 'now' : '') + '"></span>').join('') + '</div>';
}
function step(st, draft, preview){
  const dr = draft ? ' data-draft="1"' : '';
  const tick = st.auto ? '<span class="lntick on" aria-label="Done">' + CHECK + '</span>'
    : st.add ? '<span class="lntick"></span>'
    : '<button class="lntick' + (st.done ? ' on' : '') + '" data-ln-tick="' + esc(st.id) + '"' + dr + ' aria-pressed="' + st.done + '" aria-label="Done">' + (st.done ? CHECK : '') + '</button>';
  const name = (st.go ? '<a href="#' + esc(st.go) + '">' : '<span>') + esc(st.title) + (st.go ? '</a>' : '</span>');
  return '<div class="lnpstep' + (st.done ? ' done' : '') + '" data-sid="' + esc(st.id) + '"' + (preview ? '' : ' data-drow') + '>' + (preview ? '' : GRIP) + tick + '<span class="lnpk">' + (st.kind === 'do' ? svg('M4 16h3l8.5-8.5-3-3L4 13v3z') : svg(KIND[st.kind] || KIND.article)) + '</span>' +
    '<span class="lnpt">' + name + (st.part ? '<i>' + esc(st.part) + '</i>' : '') + (st.by ? '<i>' + esc(st.by) + '</i>' : '') + '</span>' +
    (st.add ? '<button class="btn sm primary" data-ln-padd="' + esc(st.id) + '"' + dr + '>Add</button>' : '') +
    (st.mins ? '<span class="lnpm">' + mins(st.mins) + '</span>' : '') +
    (preview ? '' : '<button class="lnrx" type="button" data-ln-sx="' + esc(st.id) + '"' + dr + ' aria-label="Take out">' + XI + '</button>') + '</div>';
}
const mins = m => m >= 60 ? Math.floor(m / 60) + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : '') : m + ' min';
const SPARK = '<svg class="lnspark" width="15" height="15" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5l1.6 4.4 4.4 1.6-4.4 1.6L10 14.5l-1.6-4.4L4 8.5l4.4-1.6zM15.5 13l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" fill="currentColor"/></svg>';
const CHECK = '<svg width="13" height="13" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function suggRows(list, looking, error){
  return list.map(s => '<div class="lnsg">' + see(s) + '<span class="lnsk">' + svg(KIND[s.kind] || KIND.article) + '</span><span class="lnrt"><b>' + esc(s.title) + '</b><i>' + esc([KNAME[s.kind], s.by].filter(Boolean).join(' · ')) + OUT + '</i></span>' + (s.kind === 'book' ? '</button>' : '</a>') +
      '<button class="btn sm primary" data-ln-take="' + esc(s.id) + '">Add</button><button class="lnno" data-ln-skip="' + esc(s.id) + '" aria-label="Not this">×</button></div>').join('') +
    (looking ? spin('Looking…') : (error ? '<p class="mute tiny">' + esc(error) + '</p>' : '') + '<button class="btn sm" data-ln="more">Find more</button>');
}

/* Everything: all its things, and its feeds and suggestions beside them */
function everything(p){
  const a = p.area, n = k => p.items.filter(x => x.kind === k).length;
  const kinds = [['all', 'All ' + p.items.length], ['book', 'Books ' + n('book')], ['article', 'Articles ' + n('article')], ['video', 'Videos ' + n('video')], ['hl', 'Highlights ' + p.highlights.length]]
    .filter(k => k[0] === 'all' || !/ 0$/.test(k[1]));
  const chips = '<div class="lnchips">' + kinds.map(k => '<button class="lnchip' + (P.kind === k[0] ? ' on' : '') + '" data-ln-kind="' + k[0] + '">' + k[1] + '</button>').join('') + '</div>';
  let body;
  if (P.kind === 'hl') body = p.highlights.map(h => '<div class="lnhl"><p dir="auto">' + esc(h.text || '') + '</p><span>' + esc(h.title || '') + '</span></div>').join('');
  else { const rows = p.items.filter(x => P.kind === 'all' || x.kind === P.kind); body = rows.map((x, i) => row(x, P.editing, i, rows.length)).join(''); }
  const feeds = '<section class="card lnfeeds"><div class="cardh"><h2>Feeds</h2><span class="spacer"></span><button class="linkbtn" data-ln="follow">Follow</button></div>' +
    '<div data-dlist="items">' + p.feeds.map(f => feedRow(f, P.editing)).join('') + '</div></section>';
  const sugg = a.suggest ? '<section class="card lnsugg"><div class="cardh"><h2>Suggestions</h2></div>' + suggRows(p.suggestions, p.looking, p.error) + '</section>' : '';
  return '<div class="lncols"><section class="card lnlist">' + chips + (P.kind === 'hl' ? body : '<div data-dlist="items">' + body + '</div>') + '</section><div class="lnside">' + feeds + sugg + '</div></div>';
}

/* Plan */
const PACE = [[20, '20 min a day'], [30, '30 min a day'], [45, '45 min a day'], [60, '1 h a day']], WEEKS = [[2, '2 weeks'], [4, '4 weeks'], [8, '8 weeks']];
function paceRow(){
  return '<div class="lnpace">' + PACE.map(x => '<button class="lnchip' + (P.pace.mins === x[0] ? ' on' : '') + '" data-ln-mins="' + x[0] + '">' + x[1] + '</button>').join('') +
    '<span class="lnsep"></span>' + WEEKS.map(x => '<button class="lnchip' + (P.pace.weeks === x[0] ? ' on' : '') + '" data-ln-weeks="' + x[0] + '">' + x[1] + '</button>').join('') +
    '<button class="btn sm primary" data-ln="makeplan">' + SPARK + 'Make a plan</button></div>';
}
function weeks(plan, draft){
  return '<div class="lnweeks">' + plan.weeks.map((w, i) => '<section class="card lnweek' + (!draft && i === plan.now ? ' now' : '') + (w.done ? ' done' : '') + '"><span class="lnwk">Week ' + (i + 1) + '</span>' +
    '<div class="lnwname">' + esc(w.name) + '</div><div class="lnwsteps" data-dlist="plan" data-dgroup="plan" data-week="' + i + '"' + (draft ? ' data-draft="1"' : '') + '>' +
    w.steps.map(st => step(st, draft)).join('') + '</div></section>').join('') + '</div>';
}
function planTab(p){
  if (p.working.plan) return spin('Making a plan…');
  const fail = p.failed.plan ? '<p class="mute tiny">' + esc(p.failed.plan) + '</p>' : '';
  if (p.plan_draft) return fail + '<div class="lnphead"><h2>' + esc(p.plan_draft.title) + '</h2><span class="spacer"></span><button class="btn sm primary" data-ln="pkeep">Keep</button>' +
    '<button class="btn sm" data-ln="pagain">Again</button><button class="btn sm" data-ln="pdrop">Not now</button></div>' + (P.again ? paceRow() : '') + weeks(p.plan_draft, true);
  if (p.plan) return fail + '<div class="lnphead"><h2>' + esc(p.plan.title) + '</h2><span class="spacer"></span>' + progress(p.plan) +
    '<button class="btn sm" data-ln="pagain">Again</button>' + (P.editing ? '<button class="btn sm" data-ln="pclear">Remove</button>' : '') + '</div>' + (P.again ? paceRow() : '') + weeks(p.plan, false);
  return fail + '<div class="lnpempty">' + paceRow() + '</div>';
}

/* Ask */
function askTab(p){
  return askView(p.chat, { sources: p.sources.map(x => ({ key: x.ref, title: x.title, kind: x.kind })), off: P.off, attr: 'data-ln-src', anywhere: P.anywhere,
    placeholder: 'Ask about ' + p.area.name });
}
// the questions and their answers, the box, My sources / Anywhere, and the sources to draw from (an area's
// things, or on Areas home the areas)
function askView(chat, o){
  const on = o.sources.filter(x => !o.off.has(x.key)).length;
  const made = name => (L.areas || []).some(a => a.name.toLowerCase() === name.toLowerCase());
  const list = chat.map(x => '<div class="lnqa" id="lnq-' + esc(x.id) + '"><div class="lnq"><span dir="auto">' + esc(x.q) + '</span><button class="lnno" data-ln-forget="' + esc(x.id) + '" aria-label="Forget">×</button></div>' +
    (x.state === 'asking' ? spin('…') : x.state === 'error' ? '<p class="mute tiny">' + esc(x.error) + '</p>' :
      '<div class="lna">' + x.paras.map(pp => '<p dir="auto">' + esc(pp.text) + '</p>' + (pp.from.length ? '<div class="lnfrom">' + pp.from.map(ch =>
        '<a class="lnsrc" href="#' + esc(ch.go) + '">' + svg(KIND[ch.kind] || KIND.article) + '<span>' + esc(ch.label) + '</span></a>').join('') + '</div>' : '')).join('') +
      (x.outside && x.outside.length ? '<div class="lnoutside">' + x.outside.map((ot, i) => '<div class="lnsg"><a class="lnsgo"' + (ot.url ? ' href="' + esc(ot.url) + '" target="_blank" rel="noopener"' : '') + '><span class="lnsk">' + svg(KIND[ot.kind] || KIND.article) + '</span>' +
        '<span class="lnrt"><b>' + esc(ot.title) + '</b><i>' + esc([KNAME[ot.kind], ot.by].filter(Boolean).join(' · ')) + '</i></span></a><button class="btn sm primary" data-ln-oadd="' + esc(x.id) + ':' + i + '">Add</button></div>').join('') + '</div>' : '') +
      (x.new_area ? '<div class="lnnewarea">' + SPARK + '<span class="lnrt"><b>' + esc(x.new_area.name) + '</b><i>' + esc(x.new_area.goal || '') + '</i></span>' +
        (made(x.new_area.name) ? '<span class="lnst done">Made</span>' : '<button class="btn sm primary" data-ln-mkarea="' + esc(x.id) + '">New area</button>') + '</div>' : '') + '</div>') + '</div>').join('');
  const srcList = o.sources.map(x => '<label class="aaline"><input type="checkbox" ' + o.attr + '="' + esc(x.key) + '"' + (o.off.has(x.key) ? '' : ' checked') + '>' +
    (x.dot ? '<span class="lndot" style="background:' + esc(x.dot) + '"></span>' : svg(KIND[x.kind] || KIND.article)) + '<span>' + esc(x.title) + '</span></label>').join('');
  const sw = '<div class="lnseg"><button class="' + (o.anywhere ? '' : 'on') + '" data-ln-any="0">My sources</button><button class="' + (o.anywhere ? 'on' : '') + '" data-ln-any="1">Anywhere</button></div>';
  return '<div class="lnask"><div class="lnchat">' + list +
    '<form id="lnaskf" class="lnaskbox"><input class="field" id="lnaskq" placeholder="' + esc(o.placeholder) + '" autocomplete="off" enterkeyhint="send"><button class="btn primary" type="submit" aria-label="Ask">' + SPARK + 'Ask</button></form>' +
    '<div class="lnaskopts">' + sw + '<details class="lnsrcfold"><summary>Sources · ' + on + ' of ' + o.sources.length + '</summary><div class="lnsrcs">' + srcList + '</div></details></div></div>' +
    '<section class="card lnsrcside"><div class="cardh"><h2>Sources</h2><span class="spacer"></span><span class="mute tiny">' + on + ' of ' + o.sources.length + '</span></div><div class="lnsrcs">' + srcList + '</div></section></div>';
}

/* Areas home's Ask: across every area (areaagent.py ALL) */
const H = { data: null, poll: 0, anywhere: false, off: null };
const onAskHome = () => S.route[0] === 'learn' && S.route[1] === 'ask';
async function askHome(){
  if (!H.off) H.off = new Set(C.lsGet ? C.lsGet('lnoffall', []) : []);
  $('#main').innerHTML = '<div class="page lnhome lnaskhome"><h1 class="lnhide">Ask</h1>' + homeTabs('ask') + '<div class="lnhomebody"></div></div>';
  if (H.data) drawAsk();
  if (!L.areas) L.load();
  await refreshAsk();
}
async function refreshAsk(){
  let r;
  try { r = await api('/api/learn/ask'); }
  catch(e){ const b = $('#main .lnaskhome .lnhomebody'); if (b) b.innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  if (!onAskHome()) return;
  H.data = r; drawAsk();
  clearTimeout(H.poll);
  if (r.chat.some(x => x.state === 'asking')) H.poll = setTimeout(() => { if (onAskHome()) refreshAsk(); }, 3500);
}
function drawAsk(){
  const b = $('#main .lnaskhome .lnhomebody'); if (!b || !H.data) return;
  const q = $('#lnaskq'), typed = q ? q.value : '', had = q && document.activeElement === q;
  const tabs = $('#main .lnaskhome .lntabs'); if (tabs) tabs.outerHTML = homeTabs('ask');
  b.innerHTML = askView(H.data.chat, { sources: H.data.areas.map(a => ({ key: a.id, title: a.name, dot: a.color })), off: H.off, attr: 'data-ln-srca', anywhere: H.anywhere,
    placeholder: 'Ask' });
  const q2 = $('#lnaskq'); if (q2) { q2.value = typed; if (had) q2.focus(); }
}
// Areas home's Add (an outside thing from an answer): which area it goes into
let pickThen = null;
function chooseArea(then){
  pickThen = then;
  sheet('<h2>Add to an area</h2><div class="lnpick">' + (L.areas || []).map(a => '<button class="aaline lnpickb" data-ln-to="' + esc(a.id) + '"><span class="lndot" style="background:' + esc(a.color) + '"></span>' + esc(a.name) + '</button>').join('') + '</div>' +
    '<div class="lnbtns"><span class="spacer"></span><button class="btn" data-act="close">Cancel</button></div>');
}

// A suggestion opens where it comes from, to see it before adding it: the page or the video itself, a feed's
// site, and a book in Add a book (its cover and details, found by its title).
const OUT = '<svg class="lnout" width="12" height="12" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 4H4v12h12v-4M11 3h6v6M17 3l-8 8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function see(s){
  if (s.kind === 'book' || !s.url) return '<button class="lnsgo" data-ln-find="' + esc([s.title, s.by].filter(Boolean).join(' ')) + '">';
  let href = s.url;
  if (s.kind === 'feed') { try { href = new URL(s.url).origin; } catch(e){} }
  return '<a class="lnsgo" href="' + esc(href) + '" target="_blank" rel="noopener">';
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
  try { await L.put(P.id, feed ? { feed: v } : { url: v }); st.textContent = feed ? 'Following' : 'Saved'; i.value = ''; }
  catch(err){ st.textContent = err.message; }
});
// Add to an area, from anywhere (a book's page and ⋯, an article's or a video's ⋯, the rows picked in the
// Feed and the Library): the areas, each one switched on or off for this thing, or these things. A Feed
// item is saved to the Library as it goes in (areas.py kept), and moved(was, now) tells the caller.
const PK = { refs: [], moved: null };
L.pick = async (refs, title, moved) => {
  refs = [].concat(refs);
  let r; try { r = await api('/api/areas?' + refs.map(x => 'ref=' + enc(x)).join('&')); } catch(e){ toast(e.message); return; }
  const on = new Set(r.in);
  Object.assign(PK, { refs, moved: moved || null });
  sheet('<h2>Add to an area</h2>' + (title ? '<p class="mute" style="margin:0">' + esc(title) + '</p>' : '') +
    '<div class="lnpick">' + r.areas.map(a => '<label class="aaline"><input type="checkbox" data-ln-in="' + esc(a.id) + '"' + (on.has(a.id) ? ' checked' : '') + '><span class="lndot" style="background:' + esc(a.color) + '"></span>' + esc(a.name) + '</label>').join('') + '</div>' +
    '<div class="lnbtns"><button class="btn" data-ln="pnew">New area</button><span class="spacer"></span><button class="btn primary" data-act="close">Done</button></div>');
};
// each one in (the ref it's kept as from then on), or each one out
async function putAll(aid){
  for (let i = 0; i < PK.refs.length; i++) {
    const was = PK.refs[i], r = await L.put(aid, { ref: was });
    if (r.ref && r.ref !== was) { PK.refs[i] = r.ref; if (PK.moved) PK.moved(was, r.ref); }
  }
}
document.addEventListener('change', async e => {
  const t = e.target; if (!t.matches || !t.matches('[data-ln-in]')) return;
  const aid = t.dataset.lnIn;
  t.disabled = true;
  try {
    if (t.checked) await putAll(aid);
    else for (const ref of PK.refs) await api('/api/areas/' + enc(aid) + '/items?ref=' + enc(ref), { method: 'DELETE' });
    L.load();
  } catch(err){ toast(err.message); t.checked = !t.checked; }
  t.disabled = false;
});
// Add to Daf (reader.js openAdd): which area, when there are any; on an area's page, that one.
L.addPicker = m => {
  const list = L.areas || [], f = m.querySelector('#addlink'); if (!list.length || !f) return;
  const here = S.route[0] === 'learn' ? decodeURIComponent(S.route[1] || '') : '';
  f.insertAdjacentHTML('afterend', '<div class="lnaddto"><span class="mute tiny">Area</span><select class="field sm" id="addarea" aria-label="Area"><option value="">None</option>' +
    list.map(a => '<option value="' + esc(a.id) + '"' + (a.id === here ? ' selected' : '') + '>' + esc(a.name) + '</option>').join('') + '</select></div>');
};
L.chosen = () => { const s = $('#addarea'); return s && s.value; };

const post = async (what, body) => { await api('/api/areas/' + enc(P.id) + '/' + what, { method: 'POST', body: JSON.stringify(body || {}) }); refresh(); };
const put = (what, body) => api('/api/areas/' + enc(P.id) + '/' + what, { method: 'PUT', body: JSON.stringify(body) });
document.addEventListener('submit', async e => {
  if (e.target.id !== 'lnaskf') return;
  e.preventDefault();
  const i = $('#lnaskq'), q = i.value.trim(); if (!q) return;
  if (onAskHome()) {
    const ids = H.data.areas.filter(a => !H.off.has(a.id)).map(a => a.id);
    if (!ids.length && !H.anywhere) { toast('No sources'); return; }
    i.value = '';
    try { await api('/api/learn/ask', { method: 'POST', body: JSON.stringify({ q, anywhere: H.anywhere, areas: H.off.size ? ids : [] }) }); await refreshAsk(); }
    catch(err){ i.value = q; toast(err.message); }
    setTimeout(() => { const c = $('#main .lnchat .lnqa:last-of-type'); if (c) c.scrollIntoView({ block: 'end', behavior: 'smooth' }); }, 60);
    return;
  }
  const refs = P.data.sources.filter(x => !P.off.has(x.ref)).map(x => x.ref);
  if (!refs.length && !P.anywhere) { toast('No sources'); return; }
  i.value = '';
  try { await post('ask', { q, anywhere: P.anywhere, refs: P.off.size ? refs : [] }); }
  catch(err){ i.value = q; toast(err.message); }
  setTimeout(() => { const c = $('#main .lnchat .lnqa:last-of-type'); if (c) c.scrollIntoView({ block: 'end', behavior: 'smooth' }); }, 60);
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.matches || !t.matches('[data-ln-srca]')) return;
  if (t.checked) H.off.delete(t.dataset.lnSrca); else H.off.add(t.dataset.lnSrca);
  if (C.lsSet) C.lsSet('lnoffall', [...H.off]);
  drawAsk();
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.matches || !t.matches('[data-ln-src]')) return;
  if (t.checked) P.off.delete(t.dataset.lnSrc); else P.off.add(t.dataset.lnSrc);
  if (C.lsSet) C.lsSet(offKey(P.id), [...P.off]);
  draw();
});

/* ---------- moving things by hand, and taking them out ---------- */
// Drag a handle ([data-drag]) on a row ([data-drow]) in a list ([data-dlist]; lists with the same data-dgroup
// take each other's rows): the row moves through the list as the finger or the mouse goes, a copy of it
// under the pointer, and the page scrolls at its edges. On the drop, moved() saves the new order.
const DR = { row: null };
const inRect = (r, x, y) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
const rowsOf = list => [...list.children].filter(c => c.matches('[data-drow]'));
const keyOf = c => c.dataset.ref || c.dataset.sid || c.dataset.at || c.dataset.id;
document.addEventListener('pointerdown', e => {
  const h = e.target.closest && e.target.closest('[data-drag]'); if (!h || (e.pointerType === 'mouse' && e.button !== 0)) return;
  const row = h.closest('[data-drow]'), list = row && row.parentElement; if (!list || !list.matches('[data-dlist]')) return;
  e.preventDefault();
  const r = row.getBoundingClientRect(), ghost = row.cloneNode(true);
  ghost.classList.add('lnghost'); ghost.removeAttribute('data-drow');
  Object.assign(ghost.style, { width: r.width + 'px', height: r.height + 'px', left: r.left + 'px', top: r.top + 'px' });
  document.body.appendChild(ghost); document.body.classList.add('lndragging'); row.classList.add('lndrag');
  const group = list.dataset.dgroup ? [...document.querySelectorAll('[data-dgroup="' + CSS.escape(list.dataset.dgroup) + '"]')] : [list];
  Object.assign(DR, { row, group, ghost, id: e.pointerId, ox: e.clientX - r.left, oy: e.clientY - r.top, x: e.clientX, y: e.clientY,
    was: group.map(l => rowsOf(l).map(keyOf).join('|')).join('/') });
  try { h.setPointerCapture(e.pointerId); } catch(err){}
  const sc = $('#main');
  (function edge(){
    if (!DR.row) return;
    const m = sc.getBoundingClientRect(), d = DR.y < m.top + 70 ? -12 : DR.y > m.bottom - 70 ? 12 : 0;
    if (d) { sc.scrollTop += d; place(); }
    requestAnimationFrame(edge);
  })();
}, { passive: false });
function place(){
  const { x, y } = DR;
  const list = DR.group.find(l => inRect(l.getBoundingClientRect(), x, y)) || DR.group.reduce((a, l) => {
    const r = l.getBoundingClientRect(), d = Math.abs(y - Math.min(Math.max(y, r.top), r.bottom));
    return !a || d < a.d ? { l, d } : a; }, null).l;
  const rows = rowsOf(list).filter(c => c !== DR.row);
  let at = rows.find(c => inRect(c.getBoundingClientRect(), x, y)), before = true;
  if (!at && rows.length) {
    at = rows.reduce((a, c) => { const r = c.getBoundingClientRect(), d = Math.hypot(r.left + r.width / 2 - x, r.top + r.height / 2 - y); return !a || d < a.d ? { c, d } : a; }, null).c;
    const r = at.getBoundingClientRect(); before = y < r.top + r.height / 2;
  } else if (at) {                         // a list: above or below its middle; a grid (sections, cards): its top-left half
    const r = at.getBoundingClientRect();
    before = r.width > list.getBoundingClientRect().width * 0.7 ? y < r.top + r.height / 2 : (x - r.left) / r.width + (y - r.top) / r.height < 1;
  }
  if (!at) { const last = rowsOf(list).pop(); if (last !== DR.row) (last ? last.after(DR.row) : list.prepend(DR.row)); return; }
  if (before) { if (at.previousElementSibling !== DR.row) at.before(DR.row); }
  else if (at.nextElementSibling !== DR.row) at.after(DR.row);
}
document.addEventListener('pointermove', e => {
  if (!DR.row || e.pointerId !== DR.id) return;
  e.preventDefault();
  DR.x = e.clientX; DR.y = e.clientY;
  DR.ghost.style.left = (e.clientX - DR.ox) + 'px'; DR.ghost.style.top = (e.clientY - DR.oy) + 'px';
  place();
}, { passive: false });
const dragEnd = e => {
  if (!DR.row || (e && e.pointerId !== DR.id)) return;
  const { row, group, was } = DR;
  DR.ghost.remove(); row.classList.remove('lndrag'); document.body.classList.remove('lndragging'); DR.row = null;
  if (group.map(l => rowsOf(l).map(keyOf).join('|')).join('/') !== was) moved(row.parentElement, group).catch(err => { toast(err.message); if (onArea()) refresh(); });
};
document.addEventListener('pointerup', dragEnd);
document.addEventListener('pointercancel', dragEnd);
const onArea = () => S.route[0] === 'learn' && S.route[1] && S.route[1] !== 'ask';
// the new order, saved
async function moved(list, group){
  const kind = list.dataset.dlist, rows = rowsOf(list);
  if (kind === 'areas') { const r = await api('/api/areas/order', { method: 'PUT', body: JSON.stringify({ ids: rows.map(c => c.dataset.id) }) }); L.areas = r.areas; drawHome(r.areas); L.load(); return; }
  if (kind === 'items') {                 // (a list shows some of the things: they change places among their own)
    const shown = rows.map(c => c.dataset.ref), all = P.data.items.map(x => x.ref).concat(P.data.feeds.map(x => x.ref)), out = all.slice();
    all.map((r, i) => shown.includes(r) ? i : -1).filter(i => i >= 0).forEach((slot, k) => { out[slot] = shown[k]; });
    await put('items/order', { refs: out });
  }
  else if (kind === 'things') { const raw = rawLayout(P.data), at = +list.dataset.at; raw[at] = Object.assign({}, raw[at], { refs: rows.map(c => c.dataset.ref) }); await put('layout', { sections: raw }); }
  else if (kind === 'sections') {
    const raw = rawLayout(P.data), ats = rows.map(c => +c.dataset.at), out = raw.slice();
    ats.slice().sort((a, b) => a - b).forEach((slot, k) => { out[slot] = raw[ats[k]]; });
    await put('layout', { sections: out });
  }
  else if (kind === 'plan') {
    const order = {}; group.forEach(l => { order[l.dataset.week] = rowsOf(l).map(c => c.dataset.sid); });
    await put('plan', { order, draft: !!list.dataset.draft });
  }
  refresh(); L.load();
}
// Undo, in the toast
function undoable(msg, fn){
  const t = $('#toast');
  t.innerHTML = '<span>' + esc(msg) + '</span><button class="tundo" type="button">Undo</button>'; t.hidden = false;
  t.querySelector('.tundo').onclick = async () => { t.hidden = true; try { await fn(); } catch(err){ toast(err.message); } };
  clearTimeout(undoable.t); undoable.t = setTimeout(() => { t.hidden = true; }, 7000);
}
// a thing's ×: out of the area, or out as not a good source (the helper won't suggest it again)
function outMenu(btn, ref){
  const p = $('#pop'), r = btn.getBoundingClientRect();
  p.innerHTML = '<div class="menu lnoutm"><button data-ln-out="0">Take out</button><button data-ln-out="1">Not a good source</button></div>';
  p.dataset.lnref = ref; p.hidden = false;
  const w = p.offsetWidth, h = p.offsetHeight;
  p.style.right = 'auto'; p.style.bottom = 'auto';
  p.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
  p.style.top = (r.bottom + 6 + h > innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6) + 'px';
}
async function takeOut(ref, bad){
  $('#pop').hidden = true;
  const aid = P.id, before = P.data.items.map(x => x.ref).concat(P.data.feeds.map(x => x.ref));
  C.$$('#main [data-ln-x="' + CSS.escape(ref) + '"]').forEach(b => { const r = b.closest('[data-drow]'); if (r) r.classList.add('lngone'); });
  const r = await api('/api/areas/' + enc(aid) + '/items?ref=' + enc(ref) + (bad ? '&bad=1' : ''), { method: 'DELETE' });
  refresh(); L.load();
  undoable('Taken out', async () => {
    await L.put(aid, { ref });
    await api('/api/areas/' + enc(aid) + '/items/order', { method: 'PUT', body: JSON.stringify({ refs: before }) });
    if (r.skip) await api('/api/areas/suggestions/' + enc(r.skip), { method: 'POST', body: JSON.stringify({ unskip: true }) });
    if (P.id === aid) refresh(); L.load();
  });
}

/* ---------- clicks ---------- */
document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('[data-ln],[data-ln-color],[data-ln-del],[data-ln-move],[data-ln-kind],[data-ln-up],[data-ln-down],[data-ln-rm],[data-ln-take],[data-ln-skip],[data-ln-pick],[data-ln-addref],[data-ln-find],' +
    '[data-ln-sup],[data-ln-sdown],[data-ln-srm],[data-ln-addsec],[data-ln-tick],[data-ln-padd],[data-ln-mins],[data-ln-weeks],[data-ln-forget],[data-ln-oadd],[data-ln-any],[data-ln-goq],[data-ln-mkarea],[data-ln-to],[data-ln-x],[data-ln-out],[data-ln-sx]');
  if (!t) return;
  const d = t.dataset, cardId = (t.closest('[data-id]') || {}).dataset;
  try {
    if (d.ln === 'edit') { editing = !editing; t.textContent = editing ? 'Done' : 'Edit'; drawHome(L.areas || []); }
    else if (d.ln === 'new' || d.ln === 'pnew') { areaSheet(null); $('#modal').dataset.lnthen = d.ln === 'pnew' ? '1' : ''; }
    else if (d.ln === 'save') {
      const m = $('#modal'), name = $('#lnname').value.trim(); if (!name) { $('#lnname').focus(); return; }
      const body = { name, goal: $('#lngoal').value.trim(), color: (m.querySelector('[data-ln-pick].on') || {}).dataset.lnPick, suggest: $('#lnsug').checked };
      if (m.dataset.lnfor) { await api('/api/areas/' + enc(m.dataset.lnfor), { method: 'PUT', body: JSON.stringify(body) }); C.closeModal(); await L.load(); refresh(); }
      else {
        const r = await api('/api/areas', { method: 'POST', body: JSON.stringify(body) }), then = m.dataset.lnthen;
        if (then) await putAll(r.id);
        C.closeModal(); L.areas = r.areas; await L.load(); location.hash = 'learn/' + enc(r.id);
      }
    }
    else if (d.ln === 'delete') {
      const id = $('#modal').dataset.lnfor, a = (L.areas || []).find(x => x.id === id);
      if (!confirm('Delete “' + (a ? a.name : '') + '”?')) return;
      await api('/api/areas/' + enc(id), { method: 'DELETE' }); C.closeModal(); await L.load(); location.hash = 'learn';
    }
    else if (d.lnPick) { t.parentNode.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === t)); }
    else if (d.lnColor) { await api('/api/areas/' + enc(cardId.id), { method: 'PUT', body: JSON.stringify({ color: d.lnColor }) }); drawHome(await L.load()); }
    else if (d.lnDel !== undefined && cardId) {
      const a = (L.areas || []).find(x => x.id === cardId.id);
      if (!confirm('Delete “' + (a ? a.name : '') + '”?')) return;
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
    // the agent (areaagent.py): the Overview's layout, the plan, Ask
    else if (d.ln === 'rearrange') { sheet('<h2>Rearrange</h2><input class="field" id="lnhow" placeholder="For" autocomplete="off">' +
      '<div class="lnbtns"><span class="spacer"></span><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-ln="arrange">Rearrange</button></div>'); $('#lnhow').focus(); }
    else if (d.ln === 'arrange') { const how = ($('#lnhow') || {}).value || ''; C.closeModal(); await post('layout', { how }); }
    else if (d.ln === 'lkeep' || d.ln === 'ldrop' || d.ln === 'plain') { await put('layout', { [{ lkeep: 'keep', ldrop: 'drop', plain: 'plain' }[d.ln]]: true }); if (d.ln === 'plain') P.editing = false; refresh(); }
    else if (d.lnSup || d.lnSdown || d.lnSrm || d.lnAddsec) {
      const raw = rawLayout(P.data), i = +(d.lnSup || d.lnSdown || d.lnSrm);
      if (d.lnAddsec) raw.push({ kind: d.lnAddsec, wide: ['plan', 'next', 'highlights'].includes(d.lnAddsec) });
      else if (d.lnSrm) raw.splice(i, 1);
      else { const j = i + (d.lnSup ? -1 : 1); if (j < 0 || j >= raw.length) return; [raw[i], raw[j]] = [raw[j], raw[i]]; }
      await put('layout', { sections: raw }); refresh();
    }
    else if (d.lnMins || d.lnWeeks) { if (d.lnMins) P.pace.mins = +d.lnMins; else P.pace.weeks = +d.lnWeeks; draw(); }
    else if (d.ln === 'makeplan') { P.again = false; await post('plan', P.pace); }
    else if (d.ln === 'pagain') { P.again = !P.again; draw(); }
    else if (d.ln === 'pkeep' || d.ln === 'pdrop') { await put('plan', { [d.ln === 'pkeep' ? 'keep' : 'drop']: true }); P.again = false; refresh(); }
    else if (d.ln === 'pclear') { if (!confirm('Remove the plan?')) return; await put('plan', { clear: true }); P.editing = false; refresh(); }
    else if (d.lnTick) { t.disabled = true; await put('plan', { tick: d.lnTick, done: t.getAttribute('aria-pressed') !== 'true', draft: !!d.draft }); refresh(); }
    else if (d.lnPadd) { t.disabled = true; t.textContent = 'Adding…'; await put('plan', { add: d.lnPadd, draft: !!d.draft }); refresh(); L.load(); }
    else if (d.lnSx) {
      const sid = d.lnSx, draft = !!d.draft, aid = P.id; t.closest('[data-drow]').classList.add('lngone');
      await put('plan', { remove: sid, draft }); refresh();
      undoable('Taken out', async () => { await api('/api/areas/' + enc(aid) + '/plan', { method: 'PUT', body: JSON.stringify({ restore: sid, draft }) }); if (P.id === aid) refresh(); });
    }
    else if (d.lnX) { if (!$('#pop').hidden && $('#pop').dataset.lnref === d.lnX && $('#pop .lnoutm')) $('#pop').hidden = true; else outMenu(t, d.lnX); }
    else if (d.lnOut) await takeOut($('#pop').dataset.lnref, d.lnOut === '1');
    else if (d.lnAny) { if (onAskHome()) { H.anywhere = d.lnAny === '1'; drawAsk(); } else { P.anywhere = d.lnAny === '1'; draw(); } }
    else if (d.lnForget) {
      if (onAskHome()) { await api('/api/learn/ask/' + enc(d.lnForget), { method: 'DELETE' }); refreshAsk(); }
      else { await api('/api/areas/' + enc(P.id) + '/ask/' + enc(d.lnForget), { method: 'DELETE' }); refresh(); }
    }
    else if (d.lnOadd) {
      const home = onAskHome(), [cid, i] = d.lnOadd.split(':'), x = (home ? H.data : P.data).chat.find(c => c.id === cid), o = x && x.outside[+i]; if (!o) return;
      const what = o.kind === 'book' ? { ref: 'want:' + o.title + (o.by ? '|' + o.by : '') } : { url: o.url, title: o.title };
      const go = async aid => {
        const b = $('[data-ln-oadd="' + CSS.escape(d.lnOadd) + '"]'); if (b) { b.disabled = true; b.textContent = 'Adding…'; }
        try { await L.put(aid, what); const b2 = $('[data-ln-oadd="' + CSS.escape(d.lnOadd) + '"]'); if (b2) b2.outerHTML = '<span class="lnst done">Added</span>'; L.load(); }
        catch(err){ toast(err.message); if (b) { b.disabled = false; b.textContent = 'Add'; } }
      };
      if (home) chooseArea(go); else await go(P.id);
    }
    else if (d.lnTo) { const then = pickThen; pickThen = null; C.closeModal(); if (then) await then(d.lnTo); }
    else if (d.lnMkarea) {
      const x = H.data && H.data.chat.find(c => c.id === d.lnMkarea), na = x && x.new_area; if (!na) return;
      t.disabled = true;
      const r = await api('/api/areas', { method: 'POST', body: JSON.stringify({ name: na.name, goal: na.goal || '', suggest: true }) });
      L.areas = r.areas; await L.load(); location.hash = 'learn/' + enc(r.id);
    }
    else if (d.lnGoq) P.goQ = d.lnGoq;           // (the link goes to Ask, which shows that one)
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
  return id === 'ask' ? askHome() : id ? area(id, (args || [])[1]) : home();
};
if (C.Look && C.Look.on) L.load();
})();
