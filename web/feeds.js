/* The Feeds page (#feeds) and the menu on a folder or a feed: where each one's posts show (Show:
   Everywhere, Its folder, Hidden, rss.py), whether it's pinned under Feed in the sidebar (settings
   feed_pins), and how much the Edition takes from it (the Taste page's dial, edition.sources). One folder's
   settings are its feeds' too, unless a feed has its own. Hidden is the Edition's pool: Daf still reads it. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const SHOW = [['all', 'Everywhere'], ['folder', 'Its folder'], ['hidden', 'Hidden']];
const ED = [['more', 'More'], ['', 'Normal'], ['less', 'Less'], ['mute', 'Off']];
const svg = (d, w) => '<svg width="' + (w || 16) + '" height="' + (w || 16) + '" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
const PIN = on => '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M7 3h6l-1 5 3 3H5l3-3zM10 11v6" fill="' + (on ? 'currentColor' : 'none') + '" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>';
const CHEV = open => svg('<path d="' + (open ? 'M5 8l5 5 5-5' : 'M8 5l5 5-5 5') + '"/>', 14);
const DOTS = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>';
const hue = t => { let h = 0; for (const ch of String(t || '')) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; };
const tile = x => x.icon ? '<img class="fdico" src="/api/feed/icon/' + esc(x.icon) + '" alt="" loading="lazy">'
  : '<span class="fdico" style="background:hsl(' + hue(x.title) + ' 34% 42%)">' + esc((x.title || '?').replace(/^(the |")/i, '').charAt(0).toUpperCase()) + '</span>';
const P = { data: null, q: '', chip: 'all', sel: new Set(), open: new Set(store.get('feedsOpen', [])) };

/* ---------- the changes, the same from the page, the menu and the sidebar ---------- */
async function setShow(keys, show){
  await api('/api/feed/show', { method: 'PUT', body: JSON.stringify({ keys, show }) });
  after();
}
async function setEdition(name, adj){
  await api('/api/edition/settings', { method: 'PUT', body: JSON.stringify({ source: { name, adj } }) });
  after(true);
}
async function setPin(key, on){
  const d = P.data || await api('/api/feed/manage');
  let pins = (d.pins || []).filter(k => k !== key);
  if (on) pins.push(key);
  await api('/api/settings', { method: 'PUT', body: JSON.stringify({ feed_pins: pins }) });
  if (P.data) P.data.pins = pins;
  after();
}
// After a change: this page, the Sources sheet and the sidebar's counts are drawn again.
function after(quiet){
  if (C.FeedSrc) { C.FeedSrc.invalidate(); if (!quiet) C.FeedSrc.refresh(); }
  if (C.S.route[0] === 'feeds') load();
}
const findFolder = name => (P.data && P.data.folders || []).find(f => f.name === name);
const findFeed = id => { for (const f of (P.data && P.data.folders) || []) for (const x of f.feeds) if (x.id === id) return [x, f]; return [null, null]; };

/* ---------- the menu on a folder or a feed: right-click, or hold it down ---------- */
async function openMenu(anchor, key){
  if (!P.data) { try { P.data = await api('/api/feed/manage'); } catch(e){ toast(e.message); return; } }
  const isFolder = key.startsWith('folder:'), [feed, home] = isFolder ? [null, null] : findFeed(key);
  const f = isFolder ? findFolder(key.slice(7)) : feed; if (!f) return;
  const pinned = (P.data.pins || []).includes(key), show = isFolder ? f.show : (feed.own_show || ''), ed = f.edition || '';
  const row = (act, label, on) => '<button data-fm="' + act + '"' + (on ? ' class="on"' : '') + '><i>' + (on ? '✓' : '') + '</i>' + label + '</button>';
  const p = $('#pop');
  p.innerHTML = '<div class="menu fmenu"><div class="fmh">' + esc(isFolder ? f.name : f.title) + '</div>' +
    (show === 'hidden' && isFolder ? '' : row('pin', pinned ? 'Unpin from the sidebar' : 'Pin to the sidebar', false)) + '<hr><div class="ml">Show</div>' +
    (isFolder ? '' : row('show:', 'Like its folder', !show)) + SHOW.map(([k, l]) => row('show:' + k, l, show === k)).join('') + '<hr><div class="ml">Edition</div>' +
    (isFolder ? '' : row('ed:inherit', 'Like its folder', !ed)) + ED.filter(([k]) => !(k === '' && !isFolder)).map(([k, l]) => row('ed:' + k, l, isFolder ? ed === k : ed && ed === k)).join('') +
    '<hr>' + (show === 'hidden' ? '' : '<button data-fm="seen"><i></i>Mark all as seen</button>') +
    (isFolder ? '' : '<button data-fm="edit"><i></i>Rename, move or unfollow</button>') + '<button data-fm="manage"><i></i>Feeds</button></div>';
  p.dataset.key = key; p.hidden = false;
  const r = anchor.getBoundingClientRect();
  if (matchMedia('(max-width:700px)').matches) return;          // a sheet from the bottom (style.css)
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.left + Math.min(r.width, 180))) + 'px';
  p.style.top = Math.max(8, Math.min(innerHeight - p.offsetHeight - 8, r.top)) + 'px';
}
async function menuAct(a){
  const p = $('#pop'), key = p.dataset.key; p.hidden = true;
  const isFolder = key.startsWith('folder:');
  try {
    if (a === 'pin') await setPin(key, !(P.data.pins || []).includes(key));
    else if (a.startsWith('show:')) await setShow([key], a.slice(5) || null);
    else if (a.startsWith('ed:')) {
      const adj = a.slice(3), name = isFolder ? key : (findFeed(key)[0] || {}).title;
      if (name) await setEdition(name, adj === 'inherit' ? '' : adj);
    }
    else if (a === 'seen') {
      await api('/api/feed/seen', { method: 'POST', body: JSON.stringify(isFolder ? { cat: key.slice(7) } : { feed: key }) });
      after();
    }
    else if (a === 'edit' && C.FeedSrc) C.FeedSrc.edit(key);
    else if (a === 'manage') location.hash = 'feeds';
  } catch(e){ toast(e.message); }
}
// Right-click, or hold a finger on it, on a folder or a feed in the sidebar, the Sources sheet or this page.
document.addEventListener('contextmenu', e => {
  const t = e.target.closest && e.target.closest('[data-fkey]'); if (!t) return;
  e.preventDefault(); openMenu(t, t.dataset.fkey);
});
let hold = null;
document.addEventListener('pointerdown', e => {
  const t = e.target.closest && e.target.closest('[data-fkey]'); if (!t || e.pointerType === 'mouse') return;
  const x = e.clientX, y = e.clientY;
  hold = { t, x, y, timer: setTimeout(() => { hold.fired = true; navigator.vibrate && navigator.vibrate(10); openMenu(t, t.dataset.fkey); }, 520) };
}, true);
const unhold = e => { if (hold && (e.type !== 'pointermove' || Math.hypot(e.clientX - hold.x, e.clientY - hold.y) > 10)) { clearTimeout(hold.timer); if (e.type === 'pointerup' && hold.fired) { e.preventDefault(); e.stopPropagation(); } if (e.type !== 'pointermove') { const h = hold; setTimeout(() => { if (hold === h) hold = null; }, 450); } } };
['pointerup', 'pointercancel', 'pointermove'].forEach(ev => document.addEventListener(ev, unhold, true));
document.addEventListener('click', e => { if (hold && hold.fired) { e.preventDefault(); e.stopPropagation(); hold = null; } }, true);
document.addEventListener('click', e => {
  const m = e.target.closest && e.target.closest('[data-fm]'); if (m) { e.stopPropagation(); menuAct(m.dataset.fm); return; }
  const pin = e.target.closest && e.target.closest('[data-fpin]');
  if (pin) { e.preventDefault(); e.stopPropagation(); const k = pin.dataset.fpin; (P.data ? Promise.resolve() : api('/api/feed/manage').then(d => { P.data = d; }))
    .then(() => setPin(k, !(P.data.pins || []).includes(k))).catch(err => toast(err.message)); }
}, true);

/* ---------- the Feeds page ---------- */
C.views.feeds = async args => {
  if (args[0] && ['all', 'everywhere', 'folder', 'hidden', 'quiet', 'problems'].includes(args[0])) P.chip = args[0];
  P.sel.clear();
  $('#main').innerHTML = '<div class="top"><h1>Feeds</h1><span class="spacer"></span><input class="field fdq" id="fdq" type="search" placeholder="Search" autocomplete="off" value="' + esc(P.q) + '">' +
    '<button class="btn sm" data-act="add">Follow a site</button></div><div class="page fdpage" id="fdpage"><span class="mute">Loading…</span></div>';
  await load();
};
async function load(){
  try { P.data = await api('/api/feed/manage'); } catch(e){ const pg = $('#fdpage'); if (pg) pg.innerHTML = '<div class="placeholder">' + esc(e.message) + '</div>'; return; }
  draw();
}
const QUIET = 30 * 86400;
function keep(f, x){
  const now = Date.now() / 1000, c = P.chip, q = P.q.trim().toLowerCase();
  if (q && !(x.title.toLowerCase().includes(q) || f.name.toLowerCase().includes(q) || (x.site || '').toLowerCase().includes(q))) return false;
  if (c === 'everywhere') return x.show === 'all';
  if (c === 'folder') return x.show === 'folder';
  if (c === 'hidden') return x.show === 'hidden';
  if (c === 'quiet') return !x.last || now - x.last > QUIET;
  if (c === 'problems') return !!x.error;
  return true;
}
function draw(){
  const pg = $('#fdpage'); if (!pg || !P.data) return;
  const all = P.data.folders.flatMap(f => f.feeds), now = Date.now() / 1000, pins = new Set(P.data.pins || []);
  const n = { all: all.length, everywhere: all.filter(x => x.show === 'all').length, folder: all.filter(x => x.show === 'folder').length,
    hidden: all.filter(x => x.show === 'hidden').length, quiet: all.filter(x => !x.last || now - x.last > QUIET).length, problems: all.filter(x => x.error).length };
  const chip = (k, l) => (k === 'problems' && !n[k]) ? '' : '<button class="fdchip' + (P.chip === k ? ' on' : '') + (k === 'problems' ? ' warn' : '') + '" data-fdchip="' + k + '">' + l + ' <b>' + n[k] + '</b></button>';
  const seg = (key, cur, inherit) => '<span class="fdseg' + (inherit ? ' inh' : '') + '">' + SHOW.map(([k, l]) => '<button class="' + (cur === k ? 'on' : '') + '" data-fdshow="' + k + '" data-k="' + esc(key) + '">' + l + '</button>').join('') + '</span>';
  const dial = (name, cur, feed) => '<select class="field sm fded" data-fded="' + esc(name) + '" aria-label="Edition">' +
    (feed ? '<option value=""' + (!cur ? ' selected' : '') + '>Like folder</option>' : '') +
    ED.filter(([k]) => !(feed && k === '')).map(([k, l]) => '<option value="' + k + '"' + (cur === k && (k || !feed) ? ' selected' : '') + '>' + l + '</option>').join('') + '</select>';
  const vol = w => '<span class="fdvol"><i style="width:' + Math.max(2, Math.min(56, Math.round(Math.sqrt(w) * 9))) + 'px"></i>' + (w ? (w >= 10 ? Math.round(w) : w) : '') + '</span>';
  const ck = key => '<input type="checkbox" class="fdck" data-fdsel="' + esc(key) + '"' + (P.sel.has(key) ? ' checked' : '') + ' aria-label="Select">';
  let rows = '', group = null;
  const filtered = P.chip !== 'all' || P.q.trim();
  for (const f of P.data.folders) {
    const feeds = f.feeds.filter(x => keep(f, x)); if (!feeds.length) continue;
    const g = f.show === 'hidden' ? 'Hidden' : '';
    if (g !== group) { if (g) rows += '<div class="fdgrp">' + g + '</div>'; group = g; }
    const key = 'folder:' + f.name, open = filtered || P.open.has(f.name);
    rows += '<div class="fdrow fold' + (P.sel.has(key) ? ' sel' : '') + '" data-fkey="' + (f.name ? esc(key) : '') + '">' + (f.name ? ck(key) : '<span></span>') +
      '<button class="fdname" data-fdopen="' + esc(f.name) + '">' + CHEV(open) + '<b>' + esc(f.name || 'No folder') + '</b><span class="mute">' + f.feeds.length + '</span></button>' +
      vol(f.week) + (f.name ? seg(key, f.show) : '<span></span>') +
      (f.name && f.show !== 'hidden' ? '<button class="ib fdpin' + (pins.has(key) ? ' on' : '') + '" data-fpin="' + esc(key) + '" aria-label="' + (pins.has(key) ? 'Unpin' : 'Pin') + '">' + PIN(pins.has(key)) + '</button>' : '<span></span>') +
      (f.name ? dial(key, f.edition, false) : '<span></span>') +
      (f.name ? '<button class="ib fdmore" data-fdmenu="' + esc(key) + '" aria-label="More">' + DOTS + '</button>' : '<span></span>') + '</div>';
    if (!open) continue;
    for (const x of feeds) {
      rows += '<div class="fdrow feed' + (P.sel.has(x.id) ? ' sel' : '') + '" data-fkey="' + esc(x.id) + '">' + ck(x.id) +
        '<a class="fdname" href="#feed/' + encodeURIComponent(x.id) + '">' + tile(x) + '<span>' + esc(x.title) + '</span>' + (x.error ? '<span class="fderr" title="' + esc(x.error) + '">!</span>' : '') + '</a>' +
        vol(x.week) + seg(x.id, x.show, !x.own_show) +
        (x.show !== 'hidden' ? '<button class="ib fdpin' + (pins.has(x.id) ? ' on' : '') + '" data-fpin="' + esc(x.id) + '" aria-label="' + (pins.has(x.id) ? 'Unpin' : 'Pin') + '">' + PIN(pins.has(x.id)) + '</button>' : '<span></span>') +
        dial(x.title, x.edition, true) + '<button class="ib fdmore" data-fdmenu="' + esc(x.id) + '" aria-label="More">' + DOTS + '</button></div>';
    }
  }
  const sel = P.sel.size;
  pg.innerHTML = '<div class="fdwrap"><div class="fdchips">' + chip('all', 'All') + chip('everywhere', 'Everywhere') + chip('folder', 'Its folder') + chip('hidden', 'Hidden') + chip('quiet', 'Quiet') + chip('problems', 'Problems') + '</div>' +
    '<div class="fdhead"><span></span><span>Name</span><span>A week</span><span>Show</span><span>Sidebar</span><span>Edition</span><span></span></div>' +
    '<div class="fdrows">' + (rows || '<div class="placeholder">Nothing here</div>') + '</div>' +
    (sel ? '<div class="fdbulk"><b>' + sel + ' selected</b><select class="field sm" data-fdbulk="show"><option value="">Show…</option>' + SHOW.map(([k, l]) => '<option value="' + k + '">' + l + '</option>').join('') + '</select>' +
      '<select class="field sm" data-fdbulk="ed"><option value="x">Edition…</option>' + ED.map(([k, l]) => '<option value="' + k + '">' + l + '</option>').join('') + '</select>' +
      '<select class="field sm" data-fdbulk="move"><option value="">Move to…</option>' + P.data.folders.filter(f => f.name).map(f => '<option>' + esc(f.name) + '</option>').join('') + '<option value="\u0000new">A new folder…</option></select>' +
      '<button class="btn sm" data-fdbulk="unfollow">Unfollow</button><span class="spacer"></span><button class="btn sm" data-fdbulk="clear">Clear</button></div>' : '') + '</div>';
}
// a selected folder stands for its feeds where a feed is needed (Move, Unfollow)
function selectedFeeds(){
  const out = new Set();
  for (const k of P.sel) {
    if (k.startsWith('folder:')) { const f = findFolder(k.slice(7)); (f ? f.feeds : []).forEach(x => out.add(x.id)); }
    else out.add(k);
  }
  return [...out];
}
document.addEventListener('click', async e => {
  if (C.S.route[0] !== 'feeds') return;
  const t = e.target;
  const c = t.closest('[data-fdchip]'); if (c) { P.chip = c.dataset.fdchip; draw(); return; }
  const o = t.closest('[data-fdopen]');
  if (o) { const n = o.dataset.fdopen; if (P.open.has(n)) P.open.delete(n); else P.open.add(n); store.set('feedsOpen', [...P.open]); draw(); return; }
  const sh = t.closest('[data-fdshow]');
  if (sh) { const k = sh.dataset.k, v = sh.dataset.fdshow; const [x] = k.startsWith('folder:') ? [null] : findFeed(k);
    // a feed's Show: the one it has from its folder, pressed again, is its folder's again
    const want = x && x.own_show === v ? null : x && !x.own_show && x.show === v ? v : v;
    try { await setShow([k], want); } catch(err){ toast(err.message); } return; }
  const mn = t.closest('[data-fdmenu]'); if (mn) { openMenu(mn, mn.dataset.fdmenu); return; }
  const b = t.closest('button[data-fdbulk]');
  if (b) {
    const a = b.dataset.fdbulk;
    if (a === 'clear') { P.sel.clear(); draw(); return; }
    if (a === 'unfollow') {
      const ids = selectedFeeds(); if (!ids.length || !confirm('Unfollow ' + ids.length + (ids.length === 1 ? ' feed?' : ' feeds?'))) return;
      try { for (const id of ids) await api('/api/feed/sources?feed=' + encodeURIComponent(id), { method: 'DELETE' }); P.sel.clear(); after(); } catch(err){ toast(err.message); }
    }
  }
});
document.addEventListener('change', async e => {
  if (C.S.route[0] !== 'feeds') return;
  const t = e.target;
  if (t.dataset.fdsel != null) { const k = t.dataset.fdsel; if (t.checked) P.sel.add(k); else P.sel.delete(k); draw(); return; }
  if (t.dataset.fded != null) { try { await setEdition(t.dataset.fded, t.value); } catch(err){ toast(err.message); } return; }
  const a = t.dataset.fdbulk; if (!a) return;
  try {
    if (a === 'show' && t.value) { await setShow([...P.sel], t.value); P.sel.clear(); }
    else if (a === 'ed' && t.value !== 'x') {
      for (const k of P.sel) { const name = k.startsWith('folder:') ? k : (findFeed(k)[0] || {}).title; if (name) await api('/api/edition/settings', { method: 'PUT', body: JSON.stringify({ source: { name, adj: t.value } }) }); }
      P.sel.clear(); after(true);
    }
    else if (a === 'move' && t.value) {
      let folder = t.value;
      if (folder === '\u0000new') { folder = (prompt('The new folder’s name') || '').trim(); if (!folder) { draw(); return; } }
      for (const id of selectedFeeds()) await api('/api/feed/sources', { method: 'PUT', body: JSON.stringify({ feed: id, folder }) });
      P.sel.clear(); after();
    }
  } catch(err){ toast(err.message); draw(); }
});
document.addEventListener('input', e => { if (e.target.id === 'fdq') { P.q = e.target.value; draw(); } });

/* ---------- Preferences › Sidebar: what's pinned under Feed ---------- */
C.FeedPins = {
  card: async el => {
    let d; try { d = P.data = await api('/api/feed/manage'); } catch(e){ el.innerHTML = ''; return; }
    const names = {}; d.folders.forEach(f => { names['folder:' + f.name] = f.name; f.feeds.forEach(x => { names[x.id] = x.title; }); });
    const pins = (d.pins || []).filter(k => names[k]);
    el.innerHTML = '<div class="prow"><div class="d"><b>Under Feed</b></div><a class="btn sm" href="#feeds">Feeds</a></div><div class="pinlist">' +
      pins.map((k, i) => '<div class="fdpinrow"><span>' + esc(names[k]) + '</span>' + (i ? '<button class="ib" data-fdup="' + i + '" aria-label="Up">' + svg('<path d="M10 15V5M5 10l5-5 5 5"/>', 14) + '</button>' : '<span class="ib"></span>') +
        '<button class="ib" data-fpin="' + esc(k) + '" aria-label="Unpin">' + PIN(true) + '</button></div>').join('') + '</div>' +
      '<label class="aaline"><input type="checkbox" data-fdhide' + (d.hide_empty ? ' checked' : '') + '> Hide pins with nothing new</label>';
  },
};
document.addEventListener('click', async e => {
  const u = e.target.closest && e.target.closest('[data-fdup]'); if (!u) return;
  const i = +u.dataset.fdup, pins = [...((P.data && P.data.pins) || [])]; if (i < 1 || i >= pins.length) return;
  [pins[i - 1], pins[i]] = [pins[i], pins[i - 1]];
  try { await api('/api/settings', { method: 'PUT', body: JSON.stringify({ feed_pins: pins }) }); P.data.pins = pins; after(); const el = $('#feedpins'); if (el) C.FeedPins.card(el); } catch(err){ toast(err.message); }
});
document.addEventListener('change', async e => {
  if (!e.target.hasAttribute || !e.target.hasAttribute('data-fdhide')) return;
  try { await api('/api/settings', { method: 'PUT', body: JSON.stringify({ feed_pins_hide_empty: e.target.checked }) }); after(); } catch(err){ toast(err.message); }
});
window.addEventListener('daf-feedpins', () => { const el = $('#feedpins'); if (el) C.FeedPins.card(el); });
C.FeedMenu = { open: openMenu };
})();
