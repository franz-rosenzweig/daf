/* Daf reader (Phases 4–5): the Feed (FreshRSS), the Library (Daf's own; Karakeep's before), the reading
   view with highlights, notes, Ask and read-aloud, and ⌘K search. */
(function(){
'use strict';
const C = window.DafCore, H = C.HL, K = C.Keys;
const { api, esc, toast, $, $$, epochDate, ago, shortTitle, I } = C;
const R = { tabs: { feed: 'unseen', library: 'inbox' }, list: null, sel: null, multi: new Set(), anchor: null, selecting: false, filters: { feed: {}, library: {} }, doc: null, focus: 0, panel: 'info', toc: true,
            lastActive: Date.now(), tts: { on: false, playing: false, i: 0, audio: null }, counts: null, progT: 0 };
const KIND = { article: 'Articles', email: 'Emails', video: 'Videos', tweet: 'Tweets', pdf: 'PDFs', podcast: 'Podcasts' };
const ICON = {
  feed: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 15.5h.01M4.5 10a5.5 5.5 0 0 1 5.5 5.5M4.5 4.5a11 11 0 0 1 11 11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  article: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3.5h7l3 3v10H5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M7.5 10h5M7.5 13h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  video: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="5" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8.5 7.8v4.4l3.6-2.2z" fill="currentColor"/></svg>',
  tweet: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5h12v8H9l-3 3v-3H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  pdf: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3.5h7l3 3v10H5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 3.5v3h3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  search: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M13 13l4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  later: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M10 6v4l2.5 2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  trash: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4.5h4V6M5.5 6l.8 10h7.4l.8-10M8.5 9v4.5M11.5 9v4.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  done: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="4" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4.5 8v7.5h11V8M8 11h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  save: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 3.5h9v13l-4.5-3-4.5 3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  ext: '<svg width="15" height="15" viewBox="0 0 20 20" aria-hidden="true"><path d="M11 4h5v5M16 4l-7 7M14 12v4H4V6h4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  listen: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 8h3l4-3.5v11L7 12H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M14 7.5a3.5 3.5 0 0 1 0 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  panel: '<svg width="17" height="17" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.5 4v12" stroke="currentColor" stroke-width="1.6"/></svg>',
  play: '<svg width="15" height="15" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5v11l9-5.5z" fill="currentColor"/></svg>',
  pause: '<svg width="15" height="15" viewBox="0 0 14 14" aria-hidden="true"><rect x="2.2" y="1.5" width="3.4" height="11" rx="1" fill="currentColor"/><rect x="8.4" y="1.5" width="3.4" height="11" rx="1" fill="currentColor"/></svg>',
  chev: '<svg class="chev" width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 8l4.5 4.5L14.5 8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  dots: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>',
  check: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  refresh: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M15.5 6.5A6.2 6.2 0 1 0 16.2 11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M16 2.8v4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  close: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  email: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4.5" width="14" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3.5 6l6.5 5 6.5-5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  star: on => '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.8l2.2 4.6 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5L2.8 8.1l5-.7z" fill="' + (on ? 'currentColor' : 'none') + '" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
  up: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 12.5l5-5 5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  down: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};
const KIND_STAR = 'starred';
const rtl = t => { const s = String(t || ''); const h = (s.match(/[֐-׿]/g) || []).length; return h > 0 && h > s.replace(/\s/g, '').length * 0.3; };
const dirAttr = t => rtl(t) ? ' dir="rtl" lang="he"' : '';
const hue = s => [...String(s || '?')].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 11);
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };

/* ---------- typography preferences (Aa) ---------- */
function applyType(){
  const r = document.documentElement, t = store.get('type', {});
  r.dataset.font = t.font === 'book' ? 'serif' : (t.font || 'serif');
  if (C.Themes) r.style.setProperty('--read', C.Themes.stack(r.dataset.font));      // any of the typefaces, your own too
  r.style.setProperty('--read-size', (t.size || 20) + 'px');
  r.style.setProperty('--measure', (t.measure || 38) + 'rem');
  r.style.setProperty('--read-lh', String(t.spacing || 1.6));
  window.dispatchEvent(new Event('daf-type'));
}
applyType();

/* ---------- sidebar sections ---------- */
// The sidebar's counts: the kept ones at once, then the network's.
async function refreshCounts(){
  if (!R.counts) try { const m = window.caches && await (await caches.open('daf-data-v1')).match(new URL('/api/docs/counts', location.href).href); if (m) { R.counts = await m.json(); C.renderSide(); } } catch(e){}
  try { R.counts = await api('/api/docs/counts'); C.renderSide(); } catch(e){}
}
C.navSearch = () => '<button class="nv" data-act="palette">' + ICON.search + '<span>Search</span><span class="ct"><span class="kbd">⌘K</span></span></button>';
C.navExtra = (v, n) => {
  const rt = C.S.route || [];
  const on = (a, b) => rt[0] === a && (b == null || decodeURIComponent(rt[1] || '') === b) ? ' on' : '';
  const k = R.counts || { feed: {}, library: {}, feed_total: '' };
  const lib = '<button class="nv' + (rt[0] === 'library' && !rt[1] ? ' on' : '') + '" data-go="library"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 9 10 3.8 16.5 9v7.2h-4.3v-4.4H7.8v4.4H3.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg><span>Home</span></button>' + ['article', ...(k.emails_on || (k.library || {}).email ? ['email'] : []), 'video', 'tweet', 'pdf'].map(x => '<button class="nv' + on('library', x) + '" data-go="library/' + x + '">' + ICON[x] + '<span>' + KIND[x] + '</span><span class="ct">' + (k.library[x] || '') + '</span></button>').join('');
  const cats = Object.keys(k.feed || {}).filter(Boolean).sort();
  const open = store.get('catsOpen', true);
  const short = '<button class="nv' + on('library', KIND_STAR) + '" data-go="library/' + KIND_STAR + '">' + ICON.star(false) + '<span>Shortlist</span><span class="ct">' + (k.starred || '') + '</span></button>' +
    (R.views || []).map(v => '<button class="nv sub' + on('view', v.id) + '" data-go="view/' + encodeURIComponent(v.id) + '" title="A saved view"><span>' + esc(v.name) + '</span></button>').join('');
  return '<div class="navh"><span>Library</span><button class="ib tiny" data-act="add" aria-label="Add to Daf" title="Add a link, a book or a PDF">+</button></div><div class="nav">' + lib + short + n('books', 'Books', I.books) + '<button class="nv' + (rt[0] === 'manga' || rt[0] === 'mread' ? ' on' : '') + '" data-go="manga"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M4 3.5h8.5v13H4zM12.5 5.5H16v11h-3.5"/><path d="M6.5 6.5h3.5M6.5 9h3.5"/></svg><span>Manga</span></button>' + n('torah', 'Torah', I.torah) + n('recovery', 'Recovery', '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 14.5h14M5.5 14.5a4.5 4.5 0 0 1 9 0M10 4.5v2M4.6 7.1l1.4 1.4M15.4 7.1 14 8.5"/></svg>') + '<button class="nv' + (rt[0] === 'podcasts' ? ' on' : '') + '" data-go="podcasts"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="7.5" y="3" width="5" height="9" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5 10a5 5 0 0 0 10 0M10 15v2.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><span>Podcasts</span></button>' + n('highlights', 'Highlights', I.hl) + '</div>' +
    '<div class="navh"><span>Feed</span><button class="ib tiny" data-act="cats" aria-label="Show or hide feed folders">' + (open ? '–' : '+') + '</button></div><div class="nav">' +
    '<button class="nv' + (rt[0] === 'feed' && !rt[1] ? ' on' : '') + '" data-go="feed">' + ICON.feed + '<span>All feeds</span><span class="ct">' + (k.feed_total || '') + '</span></button>' +
    (open ? cats.map(c => '<button class="nv sub' + on('feed', c) + '" data-go="feed/' + encodeURIComponent(c) + '"><span' + dirAttr(c) + '>' + esc(c) + '</span><span class="ct">' + k.feed[c] + '</span></button>').join('') : '') + '</div>';
};

/* ---------- Add: a link, a book or a PDF, as in Readwise's Add menu ---------- */
function openAdd(file, url){
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  m.innerHTML = '<h2>Add to Daf</h2>' +
    '<form id="addlink" class="addrow"><input class="field" id="addurl" type="url" inputmode="url" placeholder="Paste a link" autocomplete="off" value="' + esc(url || '') + '"><button class="btn primary" type="submit">Save</button></form>' +
    '<span class="mute tiny">Links go to the Library, and Daf reads the page.</span>' +
    '<div class="addfeed"><span class="mute tiny">Or follow the site in the Feed, in</span><select class="field sm" id="addfolder" aria-label="Feed folder"><option value="">no folder</option></select><button class="btn sm" type="button" id="addfollow">Follow</button></div>' +
    '<label class="adddrop" id="adddrop"><input type="file" id="addfile" accept=".epub,.kepub,.mobi,.azw3,.azw,.fb2,.cbz,.pdf" multiple hidden><b>Drop books or PDFs here</b><span class="mute tiny">or click to choose. EPUB, MOBI, AZW3 and FB2 go into Calibre, then Books, where Daf opens them. PDFs go straight into the Library.</span></label>' +
    '<div id="addstatus" class="tiny" role="status"></div><div style="display:flex;justify-content:flex-end"><button class="btn" data-act="close">Close</button></div>';
  if (file) uploadFiles(Array.isArray(file) ? file : [file]); else $('#addurl').focus();
  api('/api/feed/folders').then(r => { const s = $('#addfolder'); if (s) s.innerHTML = '<option value="">no folder</option>' + r.folders.filter(f => f !== 'Uncategorized').map(f => '<option>' + esc(f) + '</option>').join(''); }).catch(() => {});
}
document.addEventListener('click', async e => {
  if (e.target.id !== 'addfollow') return;
  const url = $('#addurl').value.trim(), st = $('#addstatus');
  if (!url) { st.textContent = 'Paste the site’s address or its feed first.'; $('#addurl').focus(); return; }
  st.textContent = 'Asking FreshRSS…'; e.target.disabled = true;
  try { const r = await api('/api/add/feed', { method:'POST', body:JSON.stringify({ url, folder:$('#addfolder').value }) }); st.innerHTML = 'Following <b>' + esc(r.name) + '</b>. New posts show up in the Feed after the next sync.'; $('#addurl').value = ''; }
  catch(err){ st.textContent = err.message; }
  e.target.disabled = false;
});
// Several dropped at once go one after another, each with its own line.
async function uploadFiles(files){
  const st = $('#addstatus'); if (!st) return;
  if (files.length === 1) return uploadFile(files[0]);
  st.innerHTML = '';
  for (const f of files) {
    const line = document.createElement('div'); st.appendChild(line);
    await uploadFile(f, line);
  }
}
async function uploadFile(f, line){
  const st = line || $('#addstatus'); if (!st) return;
  st.textContent = 'Uploading ' + f.name + '…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/api/add/file', { method:'POST', body:fd, credentials:'same-origin' });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText);
    if (j.where === 'books') st.innerHTML = '<b>' + esc(j.name) + '</b> is on its way into Calibre. It shows up under Books in a few minutes, once Calibre-Web has taken it in and Daf has synced.';
    else { st.innerHTML = 'Saved to the Library. ' + (j.id ? '<a href="#read/' + encodeURIComponent(j.id) + '" data-act="close">Open it</a>' : 'It shows up in the Library after the next sync.'); refreshCounts(); }
  } catch(e){ st.textContent = e.message; }
}
document.addEventListener('submit', async e => {
  if (e.target.id !== 'addlink') return; e.preventDefault();
  const url = $('#addurl').value.trim(), st = $('#addstatus'); if (!url) return;
  st.textContent = 'Saving…';
  try {
    const r = await api('/api/add/link', { method:'POST', body:JSON.stringify({ url }) });
    st.innerHTML = r.where === 'library' ? 'Saved to the Library. ' + (r.id ? '<a href="#read/' + encodeURIComponent(r.id) + '" data-act="close">Open it</a>' : '') : 'It didn’t save just now, so it waits in Daf’s inbox and goes in on the next sync.';
    $('#addurl').value = ''; refreshCounts();
    if (R.list && R.list.where === 'library') listView(R.list.where, R.list.arg);
  } catch(err){ st.textContent = err.message; }
});
document.addEventListener('change', e => { if (e.target.id === 'addfile' && e.target.files.length) uploadFiles([...e.target.files]); });
// Drop files anywhere on Daf (several at once), or a link dragged from another tab; or paste a link
// outside a text field. A drag that starts inside Daf (text, a picture) isn't one.
let dragN = 0, dragInside = false;
document.addEventListener('dragstart', () => { dragInside = true; });
document.addEventListener('dragend', () => { dragInside = false; });
const dropKind = e => { const t = [...((e.dataTransfer && e.dataTransfer.types) || [])]; return dragInside ? null : t.includes('Files') ? 'files' : t.includes('text/uri-list') ? 'link' : null; };
window.addEventListener('dragenter', e => { if (!dropKind(e)) return; dragN++; document.body.classList.add('dropping'); });
window.addEventListener('dragleave', e => { if (!dropKind(e)) return; if (--dragN <= 0) { dragN = 0; document.body.classList.remove('dropping'); } });
window.addEventListener('dragover', e => { if (dropKind(e)) e.preventDefault(); });
// Any drop ends the drag, even one a drop zone keeps for itself (Preferences → Import): the count and the overlay reset first.
window.addEventListener('drop', () => { dragN = 0; document.body.classList.remove('dropping'); }, true);
window.addEventListener('drop', e => {
  const kind = dropKind(e); if (!kind) return; e.preventDefault(); dragN = 0; document.body.classList.remove('dropping');
  if ($('#app').classList.contains('loggedout')) return;
  if (kind === 'link') {
    const urls = [...new Set((e.dataTransfer.getData('text/uri-list') || '').split(/\r?\n/).map(l => l.trim()).filter(l => /^https?:\/\//.test(l)))];
    if (!urls.length) return;
    if (urls.length === 1) { openAdd(null, urls[0]); const f = $('#addlink'); if (f && f.requestSubmit) f.requestSubmit(); return; }
    // Several links at once (a selection of tabs): each is saved, one after another.
    openAdd(); const st = $('#addstatus');
    (async () => { let n = 0; for (const url of urls) { try { await api('/api/add/link', { method:'POST', body:JSON.stringify({ url }) }); n++; } catch(err){} if (st) st.textContent = 'Saved ' + n + ' of ' + urls.length + '…'; }
      if (st) st.textContent = 'Saved ' + n + ' of ' + urls.length + ' links to the Library.'; refreshCounts(); })();
    return;
  }
  const files = [...e.dataTransfer.files]; if (!files.length) return;
  if ($('#adddrop') && !$('#modal').hidden) uploadFiles(files); else openAdd(files);
});
document.addEventListener('paste', e => {
  const tag = (e.target.tagName || '').toLowerCase(); if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
  if (!$('#modal').hidden || $('#app').classList.contains('loggedout')) return;
  const t = (e.clipboardData && e.clipboardData.getData('text') || '').trim();
  if (/^https?:\/\/\S+$/.test(t)) { e.preventDefault(); openAdd(null, t); }
});

/* ---------- lists ---------- */
function thumb(d){
  if (d.thumb) return '<span class="thumb"><img src="' + esc(d.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.textContent=\'' + esc((d.source || '?').charAt(0).toUpperCase()) + '\'"></span>';
  const letter = rtl(d.title) ? 'ע' : (d.source || d.title || '?').replace(/^(the |r\/)/i, '').charAt(0).toUpperCase();
  return '<span class="thumb" style="background:hsl(' + hue(d.source || d.title) + ' 34% 42%)">' + esc(letter) + '</span>';
}
function rowHTML(d){
  const feed = d.where_ === 'feed';
  const tip = (label, a) => label + K.tip('list', a);
  const acts = (feed ? [['save', tip('Save to Library', 'save'), ICON.save], ['seen', d.status === 'seen' ? 'Mark unseen' : tip('Mark seen', 'archive'), ICON.done]]
    : [['star', tip(d.starred ? 'Off the Shortlist' : 'Shortlist', 'star'), ICON.star(!!d.starred)], ['later', tip('Later', 'later'), ICON.later], ['archive', d.status === 'archive' ? 'Back to Inbox' : tip('Archive', 'archive'), ICON.done]])
    .concat([['delete', tip('Delete', 'delete'), ICON.trash]]);
  const meta = [feed && d.category ? '<span class="pill"' + dirAttr(d.category) + '>' + esc(d.category) + '</span>' : '', esc(d.source || ''), d.author && d.author !== d.source ? '· ' + esc(d.author) : '',
    d.kind === 'podcast' ? '· episode' : d.mins ? '· ' + d.mins + ' min' : '', d.progress >= 1 ? '· ' + Math.round(d.progress) + '%' : '',
    d.highlights ? '· ' + d.highlights + ' highlight' + (d.highlights > 1 ? 's' : '') : '', d.expired ? '· <span class="mute">expired</span>' : ''].filter(Boolean).join(' ');
  const picked = R.multi.has(d.id);
  return '<div class="row' + (d.id === R.sel ? ' on' : '') + (d.starred ? ' starred' : '') + (picked ? ' picked' : '') + '" data-doc="' + esc(d.id) + '" role="option" aria-selected="' + (d.id === R.sel) + '">' +
    '<span class="pick" data-pick="' + esc(d.id) + '" role="checkbox" aria-checked="' + picked + '" aria-label="Select" title="Select (x)"></span>' +
    (feed && d.status === 'unseen' && !d.expired ? '<span class="dot" aria-hidden="true"></span>' : '') + thumb(d) +
    '<div class="rowb"><div class="rowt"><span' + dirAttr(d.title) + '>' + esc(d.kind === 'tweet' && tweetParts(d).lead ? tweetParts(d).title + ': ' + tweetParts(d).lead : d.title) + '</span><span class="when">' + esc(epochDate(d.added)) + '</span></div>' +
    ((d.ai_summary || d.summary) ? '<div class="snip"' + dirAttr(d.ai_summary || d.summary) + '>' + esc(d.ai_summary || d.summary) + '</div>' : '') + '<div class="meta">' + meta + '</div></div>' +
    '<div class="hov">' + acts.map(a => '<button class="ib" data-dact="' + a[0] + '" data-id="' + esc(d.id) + '" title="' + a[1] + '" aria-label="' + a[1] + '">' + a[2] + '</button>').join('') + '</div></div>';
}
const tagsOf = d => { try { return d && d.tags ? (typeof d.tags === 'string' ? JSON.parse(d.tags) : d.tags) : []; } catch(e){ return []; } };
function infoHTML(d){
  if (!d) return '<div class="pbody mute">Nothing selected.</div>';
  const kv = [['Type', (KIND[d.kind] || 'Article').replace(/s$/, '') + (d.where_ === 'feed' ? ' · RSS' : '')], ['Source', d.source], d.category ? ['Folder', d.category] : null,
    d.url ? ['Domain', d.url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]] : null, d.published ? ['Published', epochDate(d.published)] : null,
    ['Added', epochDate(d.added)], d.mins ? ['Length', d.mins + ' min (' + (d.words || 0).toLocaleString() + ' words)'] : null, ['Progress', Math.round(d.progress || 0) + '%'],
    ['Stored in', d.where_ === 'feed' ? 'FreshRSS' : d.id.startsWith('kk:') ? 'Daf (saved first in Karakeep)' : 'Daf']].filter(Boolean);
  return '<div class="pbody"><div style="display:flex;flex-direction:column;gap:4px"><b style="font-size:16px;line-height:1.3"' + dirAttr(d.title) + '>' + esc(d.title) + '</b>' +
    (d.author ? '<span class="mute tiny">' + esc(d.author) + '</span>' : '') + '</div>' +
    (d.ai_summary ? '<div class="isum"><span class="lbl">Summary</span><p' + dirAttr(d.ai_summary) + '>' + esc(d.ai_summary) + '</p><span class="mute tiny">Written by AI</span></div>'
      : '<div class="isum">' + (d.summary ? '<span class="lbl">Opening</span><p' + dirAttr(d.summary) + '>' + esc(d.summary) + '</p>' : '') +
        (d.kind !== 'podcast' ? '<button class="linkbtn tiny" data-summ="' + esc(d.id) + '">Summarize</button>' : '') + '</div>') +
    '<div class="itags">' + tagsOf(d).map(t => '<button class="dtag" data-dtag="' + esc(t) + '">' + esc(t) + '</button>').join('') +
      '<button class="dtag add" data-dtagedit="' + esc(d.id) + '" title="Tags">' + (tagsOf(d).length ? 'Edit' : '+ Tag') + '</button></div>' +
    '<div class="kv">' + kv.map(x => '<span>' + esc(x[0]) + '</span><span>' + esc(x[1] || '') + '</span>').join('') + '</div>' +
    '<div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn primary" href="#read/' + encodeURIComponent(d.id) + '">' + (d.kind === 'video' ? 'Watch' : 'Read') + '</a>' +
    (d.where_ === 'feed' ? '<button class="btn" data-dact="save" data-id="' + esc(d.id) + '">' + ICON.save + 'Save to Library</button>' : '') +
    '<button class="btn" data-dact="delete" data-id="' + esc(d.id) + '" title="Delete' + K.tip('list', 'delete') + '">' + ICON.trash + 'Delete</button></div></div>';
}
function tagSelect(L){
  if (!L || L.where !== 'library') return '<span id="tagf"></span>';
  const n = {}; L.items.forEach(d => tagsOf(d).forEach(t => { n[t] = (n[t] || 0) + 1; }));
  const list = Object.keys(n).sort((a, b) => n[b] - n[a] || a.localeCompare(b));
  if (!list.length && !R.tag) return '<span id="tagf"></span>';
  return '<select class="field sm" id="tagf" aria-label="Tag"><option value="">All tags</option>' + list.map(t => '<option value="' + esc(t) + '"' + (t === R.tag ? ' selected' : '') + '>' + esc(t) + ' (' + n[t] + ')</option>').join('') + '</select>';
}
/* ---------- filters, like Readwise's filtered views ---------- */
const LENS = [['', 'Any length'], ['0-10', 'Under 10 min'], ['10-30', '10 to 30 min'], ['30-', 'Over 30 min']];
const SINCE = [[0, 'Any time'], [1, 'Today'], [7, 'This week'], [30, 'This month']];
function curFilter(){
  if (R.view) return R.view.filter || (R.view.filter = {});
  const key = R.list ? (R.list.where === 'feed' ? 'feed' : 'library') : (C.S.route[0] === 'feed' ? 'feed' : 'library');
  return R.filters[key] || (R.filters[key] = {});
}
function filterQuery(f){ return Object.entries(f).map(([k, v]) => '&' + k + '=' + encodeURIComponent(v === true ? 1 : v)).join(''); }
function lenOf(f){ return f.minlen || f.maxlen ? (f.minlen || 0) + '-' + (f.maxlen || '') : ''; }
function filterLabels(f){
  const out = [];
  if (f.source) out.push(['source', f.source]);
  if (f.author) out.push(['author', 'by ' + f.author]);
  if (f.minlen || f.maxlen) out.push(['len', (LENS.find(l => l[0] === lenOf(f)) || [0, (f.minlen ? f.minlen + '+' : 'up to ' + f.maxlen) + ' min'])[1]]);
  if (f.since) out.push(['since', 'Added ' + (SINCE.find(x => x[0] === +f.since) || [0, 'in ' + f.since + ' days'])[1].toLowerCase()]);
  if (f.hl) out.push(['hl', 'Highlighted']);
  if (f.fresh) out.push(['fresh', 'Not started']);
  return out;
}
function filterChips(){
  const ls = filterLabels(curFilter());
  return '<div class="fchips" id="fchips"' + (ls.length ? '' : ' hidden') + '>' + ls.map(l => '<button class="fchip" data-funset="' + l[0] + '" title="Remove this filter">' + esc(l[1]) + ' <span aria-hidden="true">×</span></button>').join('') +
    (R.view && R.viewDirty ? '<button class="btn sm primary" data-ract="updview">Save to the view</button>' : '') + '</div>';
}
function drawFChips(){ const el = $('#fchips'); if (el) el.outerHTML = filterChips(); }
function setFilter(change){
  const f = curFilter();
  for (const [k, v] of Object.entries(change)) { if (v === '' || v == null || v === 0 || v === false) delete f[k]; else f[k] = v; }
  if (R.view) R.viewDirty = true;
  if (R.list) listView(R.list.where, R.list.arg);
}
function openFilter(anchor){
  const f = curFilter(), L = R.list, p = $('#pop'), r = anchor.getBoundingClientRect();
  const sources = [...new Set((L ? L.items : []).map(d => d.source).filter(Boolean).concat(f.source ? [f.source] : []))].sort((a, b) => a.localeCompare(b));
  const seg = (name, list, cur) => '<div class="seg fseg" role="radiogroup">' + list.map(x => '<button type="button" role="radio" aria-checked="' + (String(x[0]) === String(cur)) + '" class="' + (String(x[0]) === String(cur) ? 'on' : '') + '" data-f' + name + '="' + x[0] + '">' + x[1] + '</button>').join('') + '</div>';
  p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="fpop"><span class="lbl">Source</span><select class="field sm" id="fsource"><option value="">Any source</option>' + sources.map(x => '<option' + (x === f.source ? ' selected' : '') + '>' + esc(x) + '</option>').join('') + '</select>' +
    '<span class="lbl">Author</span><input class="field sm" id="fauthor" placeholder="Any author" value="' + esc(f.author || '') + '" autocomplete="off">' +
    '<span class="lbl">Length</span>' + seg('len', LENS, lenOf(f)) + '<span class="lbl">Added</span>' + seg('since', SINCE, f.since || 0) +
    '<label class="aaline"><input type="checkbox" id="fhl"' + (f.hl ? ' checked' : '') + '> With highlights</label><label class="aaline"><input type="checkbox" id="ffresh"' + (f.fresh ? ' checked' : '') + '> Not started</label>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn sm" data-fclear>Clear</button><button class="btn sm primary" data-fdone>Done</button></div></div>';
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 320, r.right - 300)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
  p.onclick = e => {
    const len = e.target.closest('[data-flen]'), since = e.target.closest('[data-fsince]');
    if (len) { const [a, b] = len.dataset.flen.split('-'); setFilter({ minlen: +a || 0, maxlen: +b || 0 }); openFilter(anchor); }
    else if (since) { setFilter({ since: +since.dataset.fsince }); openFilter(anchor); }
    else if (e.target.closest('[data-fclear]')) { for (const k of Object.keys(f)) delete f[k]; if (R.view) R.viewDirty = true; p.hidden = true; if (R.list) listView(R.list.where, R.list.arg); }
    else if (e.target.closest('[data-fdone]')) p.hidden = true;
  };
  p.onchange = e => {
    if (e.target.id === 'fsource') setFilter({ source: e.target.value });
    else if (e.target.id === 'fhl') setFilter({ hl: e.target.checked ? 1 : 0 });
    else if (e.target.id === 'ffresh') setFilter({ fresh: e.target.checked ? 1 : 0 });
    else if (e.target.id === 'fauthor') setFilter({ author: e.target.value.trim() });
  };
  p.onkeydown = e => { if (e.target.id === 'fauthor' && e.key === 'Enter') { e.preventDefault(); setFilter({ author: e.target.value.trim() }); } };
}
async function listView(where, arg){
  const key = where === 'feed' ? 'feed' : 'library';
  const tab = R.tabs[key];
  const tabs = where === 'feed' ? [['unseen', 'UNSEEN'], ['seen', 'SEEN']] : [['inbox', 'INBOX'], ['later', 'LATER'], ['archive', 'ARCHIVE']];
  const one = where === 'feed' && isFeedId(arg);
  const title = R.view ? R.view.name : where === 'feed' ? (one ? feedTitle(arg) : arg || 'Feed') : arg === KIND_STAR ? 'Shortlist' : KIND[arg] || 'Library';
  const sort = R.view && R.view.sort ? R.view.sort : store.get('sort.' + key, 'new');
  $('#main').innerHTML = '<div class="lv"><div class="lvmain"><div class="top"><h1' + dirAttr(title) + '>' +
    (where === 'feed' && !R.view ? '<button class="srcpick" data-ract="sources" aria-haspopup="dialog" title="Choose a folder or a feed"><span id="ltitle">' + esc(title) + '</span>' + ICON.chev + '</button>' : esc(title)) + '</h1><div class="tabs" role="tablist">' +
    (arg === KIND_STAR ? '<span class="mute tiny">Starred, until you archive them</span>' : tabs.map(t => '<button class="tab' + (tab === t[0] ? ' on' : '') + '" role="tab" aria-selected="' + (tab === t[0]) + '" data-tab="' + t[0] + '">' + t[1] + '</button>').join('')) +
    '</div><span class="spacer"></span>' + (where === 'library' ? '<span id="tagf"></span>' : '') +
    (R.view ? '<button class="btn sm" data-ract="rmview" title="Remove this saved view">Remove view</button>' : '<button class="btn sm" data-ract="saveview" title="Keep this list, with its tab, tag and order, in the sidebar">Save view</button>') +
    '<button class="btn sm' + (Object.keys(curFilter()).length ? ' on' : '') + '" data-ract="lfilter" title="Filter by source, author, length, date">Filter' + (Object.keys(curFilter()).length ? ' · ' + Object.keys(curFilter()).length : '') + '</button>' +
    '<button class="btn sm' + (R.selecting ? ' on' : '') + '" data-ract="selmode" title="Select several (x)">' + (R.selecting ? 'Done' : 'Select') + '</button>' +
    '<select class="field sm" id="lsort" aria-label="Order">' + [['new', 'Newest'], ['old', 'Oldest'], ['published', 'Published'], ['short', 'Shortest'], ['long', 'Longest'], ['progress', 'Started first']].map(o => '<option value="' + o[0] + '"' + (sort === o[0] ? ' selected' : '') + '>' + o[1] + '</option>').join('') + '</select>' +
    '<button class="ib" data-ract="lmore" aria-label="More for this list" title="More">' + ICON.dots + '</button></div>' + filterChips() + '<div class="lrows" id="rows"><span class="mute" style="padding:20px">Loading…</span></div><div class="bulkbar" id="bulkbar" hidden></div></div><aside class="lvinfo" id="lvinfo"></aside></div>';
  const q = one ? '&feed=' + encodeURIComponent(arg) : where === 'feed' ? '&cat=' + encodeURIComponent(arg || '') : '&kind=' + encodeURIComponent(arg || 'article');
  const r = await C.swr('/api/docs?where=' + where + '&tab=' + tab + q + '&sort=' + sort + '&limit=200' + filterQuery(curFilter()));
  if (one && !R.view && r.items[0] && !feedTitle(arg, true) && $('#ltitle')) $('#ltitle').textContent = r.items[0].source || 'Feed';
  R.counts = r.counts; C.renderSide();
  R.list = { where, arg, items: r.items };
  if (!r.items.find(d => d.id === R.sel)) R.sel = r.items[0] ? r.items[0].id : null;
  drawRows();
  if (where === 'library' && tab !== 'archive') prefetchDocs(r.items);
}
function drawRows(){
  const L = R.list; if (!L) return;
  const rows = $('#rows'); if (!rows) return;
  if (!L.items.length) {
    const c = R.counts || {};
    rows.innerHTML = '<div class="empty"><b>Nothing here</b><span>' + (L.where === 'feed' && R.tabs.feed === 'unseen' ? 'You’re through the last two weeks of the Feed.' + (c.freshrss_unread ? ' FreshRSS still counts ' + c.freshrss_unread.toLocaleString() + ' unread, mostly older; Daf leaves anything past 14 days in Seen.' : '') : L.where === 'library' && R.tabs.library === 'later' ? 'Things you mark Later wait here.' : 'Nothing to show.') + '</span></div>';
    $('#lvinfo').innerHTML = '';
    return;
  }
  let extra = '';
  if (L.where === 'feed' && R.tabs.feed === 'seen' && R.counts && R.counts.freshrss_unread > (R.counts.feed_total || 0)) {
    extra = '<div class="notice" style="margin:10px 12px"><span style="flex:1">FreshRSS still counts ' + R.counts.freshrss_unread.toLocaleString() + ' unread, most of them older than two weeks. Daf already treats those as seen.</span><button class="btn sm" data-act="expirefr">Mark them read in FreshRSS too</button></div>';
  }
  const items = R.tag ? L.items.filter(d => tagsOf(d).includes(R.tag)) : L.items;
  const tf = $('#tagf'); if (tf) tf.outerHTML = tagSelect(L);
  if (R.tag) extra += '<div class="notice" style="margin:10px 12px"><span style="flex:1">Tagged <b>' + esc(R.tag) + '</b> · ' + items.length + '</span><button class="btn sm" data-dtag="">Show all</button></div>';
  for (const id of [...R.multi]) if (!items.find(d => d.id === id)) R.multi.delete(id);
  rows.classList.toggle('picking', R.selecting || R.multi.size > 0);
  rows.innerHTML = extra + items.map(rowHTML).join('') + (L.items.length >= 200 ? '<p class="mute tiny" style="text-align:center">Showing the newest 200.</p>' : '');
  markOnDevice();
  drawBulk();
  if (!items.find(d => d.id === R.sel)) R.sel = items[0] ? items[0].id : null;
  $('#lvinfo').innerHTML = infoHTML(items.find(d => d.id === R.sel));
}
/* ---------- articles on this device (the Android app keeps them for no network) ---------- */
const deviceKeeps = () => !!(window.dafShell && dafShell.can && dafShell.can('offline'));
async function deviceList(fresh){
  if (!deviceKeeps()) return null;
  if (!fresh && R.onDevice && Date.now() - R.onDevice.at < 30000) return R.onDevice;
  try {
    const l = await dafShell.offline({ op: 'list' });
    const docs = l.docs || [];
    R.onDevice = { at: Date.now(), all: new Set(docs.map(x => x.id)), pinned: new Set(docs.filter(x => x.pinned).map(x => x.id)) };
  } catch(e){}
  return R.onDevice;
}
async function markOnDevice(){
  const on = await deviceList(); if (!on) return;
  $$('#rows .row[data-doc]').forEach(r => r.classList.toggle('ondevice', on.all.has(r.dataset.doc)));
}
async function keepOnDevice(id, on){
  toast(on ? 'Keeping it on this device…' : 'Removing it from this device…');
  if (R.onDevice) {                       // a list drawn while the pictures are still coming shows it already
    R.onDevice.all[on ? 'add' : 'delete'](id); R.onDevice.pinned[on ? 'add' : 'delete'](id);
  }
  try {
    await dafShell.offline({ op: 'doc', id, on });
    await deviceList(true);
    toast(on ? 'On this device, also with no network' : 'Removed from this device');
  } catch(e){ await deviceList(true); toast(e.message); }
  markOnDevice();
}

/* ---------- the full article, for a feed that sends a summary (daf/fulltext.py) ---------- */
async function loadFull(id, btn){
  if (btn) { btn.disabled = true; btn.textContent = 'Reading the page…'; }
  try {
    const r = await api('/api/docs/' + encodeURIComponent(id) + '/full', { method: 'POST' });
    toast('The full article · ' + r.words.toLocaleString() + ' words');
    if (R.doc && R.doc.id === id) { const y = $('#main').scrollTop; await readView(id); $('#main').scrollTop = y; }
  } catch(e){
    toast(e.message);
    if (btn) { btn.disabled = false; btn.textContent = 'Load the full article'; }
  }
}

/* ---------- the Feed's sources: folders and single feeds, as a feed reader has them ---------- */
// A single feed's list is #feed/feed%2F12 (FreshRSS's id for it); a folder's is #feed/<name>.
const isFeedId = a => /^feed\/\d+$/.test(a || '');
function feedTitle(id, strict){
  for (const f of (R.sources && R.sources.folders) || []) for (const x of f.feeds) if (x.id === id) return x.title;
  return strict ? null : 'Feed';
}
const buzz = kind => { try { if (window.dafShell && dafShell.can && dafShell.can('haptic')) dafShell.haptic(kind).catch(() => {}); } catch(e){} };
// Undo: the last few things done to documents, newest last. The toast's Undo and z take back the
// newest; a delete can be taken back for ten minutes (reader.py purge_deleted).
const UNDO = [];
function pushUndo(label, run){ UNDO.push({ label, run }); if (UNDO.length > 20) UNDO.shift(); }
async function undoLast(){
  const u = UNDO.pop(); if (!u) { toast('Nothing to undo'); return; }
  try {
    await u.run(); toast('Undone');
    refreshCounts();
    const v = C.S.route[0]; if (R.list && (v === 'feed' || v === 'library' || v === 'view')) listView(R.list.where, R.list.arg);
    else if (v === 'read' && R.doc) readView(R.doc.id);
  } catch(e){ toast(e.message); }
}
function undoToast(msg, undo){
  if (undo) pushUndo(msg, undo);
  const t = $('#toast'), key = K.label('list', 'undo');
  t.innerHTML = '<span>' + esc(msg) + '</span><button class="tundo" type="button"' + (key ? ' title="Undo (' + esc(key) + ')"' : '') + '>Undo</button>'; t.hidden = false;
  t.querySelector('.tundo').onclick = () => { t.hidden = true; undoLast(); };
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 6000);
}
function srcIcon(x){
  const letter = esc((x.title || '?').replace(/^(the |r\/|")/i, '').charAt(0).toUpperCase());
  const tile = '<span class="sico" style="background:hsl(' + hue(x.title) + ' 34% 42%)">' + letter + '</span>';
  return x.icon ? '<img class="sico" src="/api/feed/icon/' + esc(x.icon) + '" alt="" loading="lazy" onerror="this.outerHTML=this.dataset.tile" data-tile="' + esc(tile) + '">' : tile;
}
function sourcesHTML(s){
  const L = R.list, cur = L && L.where === 'feed' && !R.view ? (L.arg || '') : null;
  const open = store.get('srcOpen', {}), hide = store.get('srcHideEmpty', false);
  const ct = n => '<span class="ct">' + (n || '') + '</span>';
  return '<div class="srow' + (cur === '' ? ' on' : '') + '"><button class="sgo" data-src="">' + ICON.feed + '<span class="sn">All feeds</span>' + ct(s.total) + '</button></div>' +
    s.folders.map(f => {
      const isOpen = open[f.name] != null ? open[f.name] : f.feeds.some(x => x.id === cur);
      const feeds = f.feeds.filter(x => !hide || x.count || x.id === cur);
      return '<div class="sfold' + (isOpen ? ' open' : '') + '"><div class="srow' + (cur === f.name && f.name ? ' on' : '') + '">' +
        '<button class="ib sfx" data-srcfold="' + esc(f.name) + '" aria-expanded="' + isOpen + '" aria-label="Show the feeds in ' + esc(f.name || 'no folder') + '">' + ICON.chev + '</button>' +
        (f.name ? '<button class="sgo" data-src="' + esc(f.name) + '"><span class="sn"' + dirAttr(f.name) + '>' + esc(f.name) + '</span>' + ct(f.count) + '</button>'
          : '<span class="sgo mute"><span class="sn">No folder</span>' + ct(f.count) + '</span>') + '</div>' +
        '<div class="sfeeds">' + (feeds.length ? feeds.map(x => '<div class="srow feed' + (x.id === cur ? ' on' : '') + (x.count ? '' : ' zero') + '">' +
          '<button class="sgo" data-src="' + esc(x.id) + '">' + srcIcon(x) + '<span class="sn"' + dirAttr(x.title) + '>' + esc(x.title) + '</span>' + ct(x.count) + '</button>' +
          '<button class="ib" data-srcedit="' + esc(x.id) + '" aria-label="Edit ' + esc(x.title) + '" title="Rename, move or unfollow">' + ICON.dots + '</button></div>').join('')
          : '<span class="mute tiny" style="padding:6px 52px">Nothing new in these feeds</span>') + '</div></div>';
    }).join('') +
    '<div class="sfoot"><label class="shide"><input type="checkbox" data-srchide' + (hide ? ' checked' : '') + '> Hide feeds with nothing new</label>' +
    '<button class="btn sm" data-act="add">Follow a site</button></div>' +
    (s.stale ? '<p class="mute tiny">FreshRSS didn’t answer; this is the list from before.</p>' : '');
}
async function openSources(){
  const m = $('#modal'); $('#scrim').hidden = false; m.hidden = false; m.classList.add('sheet');
  m.innerHTML = '<div class="srchead"><h2>Sources</h2><button class="ib" data-act="close" aria-label="Close">' + ICON.close + '</button></div><div class="srcs" id="srcs">' +
    (R.sources ? sourcesHTML(R.sources) : '<span class="mute" style="padding:12px">Loading…</span>') + '</div>';
  try {
    R.sources = await api('/api/feed/sources');
    if (!m.hidden && $('#srcs') && !$('#fename')) { const y = m.scrollTop; $('#srcs').innerHTML = sourcesHTML(R.sources); m.scrollTop = y; }
  } catch(e){ if (!R.sources && $('#srcs')) $('#srcs').innerHTML = '<span class="mute">' + esc(e.message) + '</span>'; }
  const on = m.querySelector('.srow.on'); if (on && on.offsetTop > m.clientHeight * .6) on.scrollIntoView({ block: 'center' });
}
function openFeedEdit(id){
  const s = R.sources; let feed = null;
  for (const f of (s && s.folders) || []) for (const x of f.feeds) if (x.id === id) feed = x;
  if (!feed) return;
  const folders = s.folders.map(f => f.name).filter(Boolean);
  let host = ''; try { host = new URL(feed.site || feed.url).hostname.replace(/^www\./, ''); } catch(e){}
  const m = $('#modal'); m.classList.add('sheet');
  m.innerHTML = '<div class="srchead"><h2>Edit the feed</h2><button class="ib" data-act="close" aria-label="Close">' + ICON.close + '</button></div>' +
    '<label class="fl">Name<input class="field" id="fename" value="' + esc(feed.title) + '" autocomplete="off"></label>' +
    '<label class="fl">Folder<select class="field" id="fefolder">' + folders.map(f => '<option' + (f === feed.folder ? ' selected' : '') + '>' + esc(f) + '</option>').join('') +
    '<option value="" ' + (feed.folder ? '' : 'selected') + '>No folder</option><option value="" data-new="1">A new folder…</option></select></label>' +
    '<input class="field" id="fenew" placeholder="The new folder’s name" hidden autocomplete="off">' +
    '<label class="shide fsw"><input type="checkbox" id="fefull"' + (feed.full ? ' checked' : '') + '> Always load the full article</label>' +
    '<label class="shide fsw"><input type="checkbox" id="fenotify"' + (feed.notify ? ' checked' : '') + '> Notify me of new posts' +
      (window.dafShell ? '' : ' <span class="mute">(in the Daf apps)</span>') + '</label>' +
    (host ? '<p class="mute tiny">From <a href="' + esc(feed.site || feed.url) + '" target="_blank" rel="noopener">' + esc(host) + '</a>' + (feed.count ? ' · ' + feed.count + ' unseen' : '') + '</p>' : '') +
    '<div class="ferow"><button class="btn primary" data-fe="save" data-id="' + esc(id) + '">Save</button><button class="btn" data-fe="back">Back</button><span class="spacer"></span>' +
    '<button class="btn" data-fe="unfollow" data-id="' + esc(id) + '">Unfollow</button></div>';
}
async function feedEditAct(a, id){
  if (a === 'back') { openSources(); return; }
  if (a === 'save') {
    const sel = $('#fefolder'), isNew = !!sel.selectedOptions[0].dataset.new, folder = isNew ? $('#fenew').value.trim() : sel.value;
    if (isNew && !folder) { $('#fenew').focus(); return; }
    try {
      const notify = $('#fenotify').checked;
      const r = await api('/api/feed/sources', { method: 'PUT', body: JSON.stringify({ feed: id, title: $('#fename').value, folder, full: $('#fefull').checked, notify }) });
      // the apps ask for permission to notify, and start looking for new posts
      if (notify && window.dafShell && dafShell.can && dafShell.can('alerts')) dafShell.alerts().then(ok => { if (!ok) toast('Notifications are off for Daf in the system settings'); }).catch(() => {});
      R.sources = null; toast('Saved: ' + r.title + (r.folder ? ' · ' + r.folder : ''));
      refreshCounts(); openSources();
      if (R.list && R.list.arg === id && $('#ltitle')) $('#ltitle').textContent = r.title;
    } catch(e){ toast(e.message); }
    return;
  }
  if (a === 'unfollow') {
    const name = feedTitle(id);
    if (!confirm('Unfollow “' + name + '”? FreshRSS stops fetching it, and what’s unseen from it leaves the Feed.')) return;
    try {
      await api('/api/feed/sources?feed=' + encodeURIComponent(id), { method: 'DELETE' });
      R.sources = null; toast('Unfollowed ' + name); refreshCounts();
      if (R.list && R.list.arg === id) { C.closeModal(); location.hash = 'feed'; } else openSources();
    } catch(e){ toast(e.message); }
  }
}
// The list's … menu: on a phone it holds what the header has no room for (order, select, views).
function openListMore(anchor){
  const L = R.list; if (!L) return;
  const feed = L.where === 'feed', phone = matchMedia('(max-width:600px)').matches, one = feed && isFeedId(L.arg);
  const key = feed ? 'feed' : 'library', sort = R.view && R.view.sort ? R.view.sort : store.get('sort.' + key, 'new');
  const it = (act, label, on) => '<button data-lm="' + act + '"' + (on ? ' aria-checked="true"' : '') + '><span>' + label + '</span>' + (on ? ICON.check : '') + '</button>';
  const unseen = feed && R.tabs.feed === 'unseen' && L.items.length;
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  p.innerHTML = '<div class="menu">' +
    (unseen ? '<span class="mh">Mark seen</span>' + it('seen:', 'All ' + L.items.length + (L.items.length >= 200 ? '+' : '') + ' in this list') +
      it('seen:86400', 'Older than a day') + it('seen:259200', 'Older than three days') + it('seen:604800', 'Older than a week') + '<hr>' : '') +
    it('refresh', feed ? 'Check for new posts' : 'Sync now') +
    (one ? it('editfeed', 'Rename or move this feed') : '') +
    (phone ? '<hr>' + it('select', R.selecting ? 'Stop selecting' : 'Select several') +
      (R.view ? it('rmview', 'Remove this view') : it('saveview', 'Save as a view')) +
      '<hr><span class="mh">Order</span>' + [['new', 'Newest'], ['old', 'Oldest'], ['published', 'Published'], ['short', 'Shortest'], ['long', 'Longest'], ['progress', 'Started first']].map(o => it('sort:' + o[0], o[1], sort === o[0])).join('') : '') +
    '</div>';
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 288, r.right - 280)) + 'px'; p.style.top = (r.bottom + 6) + 'px';
}
async function listMoreAct(a){
  const L = R.list; if (!L) return;
  $('#pop').hidden = true;
  if (a.startsWith('seen:')) return markScopeSeen(a.slice(5) || null);
  if (a === 'refresh') return refreshList();
  if (a === 'editfeed') { await openSources(); openFeedEdit(L.arg); return; }
  if (a === 'select' || a === 'saveview' || a === 'rmview') { const b = $('[data-ract="' + (a === 'select' ? 'selmode' : a) + '"]'); if (b) b.click(); return; }
  if (a.startsWith('sort:')) { const sel = $('#lsort'); if (sel) { sel.value = a.slice(5); sel.dispatchEvent(new Event('change', { bubbles: true })); } }
}
async function markScopeSeen(older){
  const L = R.list, one = isFeedId(L.arg);
  try {
    const r = await api('/api/feed/seen', { method: 'POST', body: JSON.stringify(Object.assign(one ? { feed: L.arg } : { cat: L.arg || '' }, older ? { older: +older } : {})) });
    await listView(L.where, L.arg); refreshCounts(); R.sources = null;
    if (!r.ids.length) { toast(older ? 'Nothing that old here' : 'Nothing to mark'); return; }
    buzz('confirm');
    undoToast(r.ids.length + ' marked seen', () => api('/api/docs/bulk', { method: 'POST', body: JSON.stringify({ ids: r.ids, status: 'unseen' }) })
      .then(() => { toast('Back in Unseen'); refreshCounts(); if (R.list) listView(R.list.where, R.list.arg); }).catch(e => toast(e.message)));
  } catch(e){ toast(e.message); }
}
async function refreshList(){
  const L = R.list; if (!L || refreshList.busy) return;
  refreshList.busy = true; pullShow(70, true);
  try {
    if (L.where === 'feed') { const r = await api('/api/feed/refresh', { method: 'POST' }); toast(r.busy ? 'Daf is already syncing; try again in a moment' : r.new ? r.new + ' new' : 'Nothing new'); }
    else { await api('/api/sync', { method: 'POST' }); toast('Synced'); }
    R.sources = null;
    if (R.list === L) await listView(L.where, L.arg);
    refreshCounts();
  } catch(e){ toast(e.message); }
  finally { refreshList.busy = false; pullShow(0); }
}

/* ---------- a phone: swipe a row, hold it to select, pull the list down to refresh ---------- */
// Feed: right marks seen, left saves to the Library. Library: right archives, left is Later.
const swipeActs = (feed, dx) => feed ? (dx > 0 ? ['seen', R.tabs.feed === 'seen' ? 'Unseen' : 'Seen'] : ['save', 'Save']) : (dx > 0 ? ['archive', R.tabs.library === 'archive' ? 'Inbox' : 'Archive'] : ['later', R.tabs.library === 'later' ? 'Inbox' : 'Later']);
const SW = { row: null, ate: 0 };
function swipeEnd(row, keep){
  row.classList.add('settle'); row.style.setProperty('--sx', '0px');
  setTimeout(() => { row.classList.remove('swiping', 'settle', 'armed'); const b = row.querySelector('.swbg'); if (b && !keep) b.remove(); }, 200);
}
document.addEventListener('pointerdown', e => {
  if (e.pointerType !== 'touch' || !R.list) return;
  const row = e.target.closest('#rows .row[data-doc]'); if (!row) return;
  Object.assign(SW, { row, x: e.clientX, y: e.clientY, dx: 0, on: false, id: e.pointerId, armed: false });
  clearTimeout(SW.long);
  SW.long = setTimeout(() => {      // held still: start selecting, as a phone's lists do
    if (SW.row !== row || SW.on) return;
    SW.row = null; SW.ate = Date.now();
    if (!R.selecting) { R.selecting = true; const b = $('[data-ract=selmode]'); if (b) { b.classList.add('on'); b.textContent = 'Done'; } }
    pick(row.dataset.doc, true); drawRows(); buzz('long');
  }, 520);
}, { passive: true });
document.addEventListener('pointermove', e => {
  const s = SW; if (!s.row || e.pointerId !== s.id) return;
  const dx = e.clientX - s.x, dy = e.clientY - s.y;
  if (!s.on) {
    if (Math.abs(dy) > 10) { s.row = null; clearTimeout(s.long); return; }
    if (Math.abs(dx) < 14 || R.selecting || R.multi.size) { if (Math.abs(dx) >= 14) { s.row = null; clearTimeout(s.long); } return; }
    s.on = true; clearTimeout(s.long);
    s.row.classList.add('swiping');
    s.row.insertAdjacentHTML('afterbegin', '<span class="swbg" aria-hidden="true"><b></b></span>');
  }
  const w = s.row.offsetWidth, act = swipeActs(R.list.where === 'feed', dx), armed = Math.abs(dx) > w * .3;
  s.dx = dx;
  s.row.style.setProperty('--sx', dx + 'px');
  const bg = s.row.querySelector('.swbg');
  bg.className = 'swbg ' + (dx > 0 ? 'r' : 'l') + ' sw-' + act[0]; bg.firstChild.textContent = act[1];
  if (armed !== s.armed) { s.armed = armed; s.row.classList.toggle('armed', armed); if (armed) buzz('tick'); }
}, { passive: true });
function swipeUp(e){
  const s = SW; if (!s.row || e.pointerId !== s.id) return;
  clearTimeout(s.long);
  const row = s.row; s.row = null;
  if (!s.on) return;
  s.ate = Date.now();
  const L = R.list, id = row.dataset.doc, d = L && L.items.find(x => x.id === id);
  if (e.type === 'pointercancel' || !s.armed || !d) { swipeEnd(row); return; }
  const feed = L.where === 'feed', act = swipeActs(feed, s.dx)[0];
  row.classList.add('settle', 'gone'); row.style.setProperty('--sx', (s.dx > 0 ? 1 : -1) * row.offsetWidth + 'px');
  buzz('confirm');
  setTimeout(async () => {
    await docAct(act, id);
    if (L.items.find(x => x.id === id)) swipeEnd(row);       // it didn't go: docAct said why (it gave the Undo too)
  }, 170);
}
document.addEventListener('pointerup', swipeUp, { passive: true });
document.addEventListener('pointercancel', swipeUp, { passive: true });
// A swipe or a hold isn't a tap: don't open the row under the finger.
document.addEventListener('click', e => { if (Date.now() - SW.ate < 450 && e.target.closest && e.target.closest('#rows')) { e.preventDefault(); e.stopPropagation(); } }, true);
document.addEventListener('contextmenu', e => { if (e.target.closest && e.target.closest('#rows .row') && matchMedia('(pointer:coarse)').matches) e.preventDefault(); });

const PR = { y: null };
function pullShow(d, spin){
  let p = $('#ptr');
  if (!p) { document.body.insertAdjacentHTML('beforeend', '<div class="ptr" id="ptr" aria-hidden="true">' + ICON.refresh + '</div>'); p = $('#ptr'); }
  p.style.setProperty('--pd', d + 'px'); p.style.setProperty('--pr', (d * 4) + 'deg');
  p.classList.toggle('on', d > 0); p.classList.toggle('spin', !!spin); p.classList.toggle('ready', d >= 60);
}
document.addEventListener('touchstart', e => {
  PR.y = null;
  const m = $('#main');
  if (!R.list || !['feed', 'library', 'view'].includes(C.S.route[0]) || !m || m.scrollTop > 0 || e.touches.length !== 1 || !$('#modal').hidden || refreshList.busy) return;
  if (!e.target.closest('#main')) return;
  PR.y = e.touches[0].clientY; PR.x = e.touches[0].clientX; PR.on = false; PR.d = 0;
}, { passive: true });
document.addEventListener('touchmove', e => {
  if (PR.y == null) return;
  const dy = e.touches[0].clientY - PR.y, dx = e.touches[0].clientX - PR.x;
  if (!PR.on) {
    if (dy < 10 || Math.abs(dx) > dy || SW.on) { if (dy < -4 || Math.abs(dx) > 10 || SW.on) PR.y = null; return; }
    if ($('#main').scrollTop > 0) { PR.y = null; return; }
    PR.on = true;
  }
  if (e.cancelable) e.preventDefault();
  PR.d = Math.min(96, (dy - 10) * .5); pullShow(PR.d);
}, { passive: false });
document.addEventListener('touchend', () => {
  if (PR.on) { if (PR.d >= 60) { buzz('tick'); refreshList(); } else pullShow(0); }
  PR.y = null; PR.on = false;
}, { passive: true });

/* ---------- several at once ---------- */
function drawBulk(){
  const bar = $('#bulkbar'), L = R.list; if (!bar || !L) return;
  const n = R.multi.size;
  $('#rows') && $('#rows').classList.toggle('picking', R.selecting || n > 0);
  if (!n) { bar.hidden = true; bar.innerHTML = ''; return; }
  const tab = R.tabs[L.where === 'feed' ? 'feed' : 'library'];
  const acts = L.where === 'feed' ? (tab === 'seen' ? [['unseen', 'Mark unseen']] : [['seen', 'Mark seen']]).concat([['save', 'Save to Library']])
    : (tab === 'inbox' ? [['later', 'Later'], ['archive', 'Archive']] : tab === 'later' ? [['inbox', 'Inbox'], ['archive', 'Archive']] : [['inbox', 'Back to Inbox']]).concat([['star', 'Shortlist'], ['kindle', 'Send to Kindle']]);
  acts.push(['deleted', 'Delete']);
  bar.innerHTML = '<b>' + n + ' selected</b><span class="spacer"></span>' + acts.map(a => '<button class="btn sm' + (a[0] === 'archive' || a[0] === 'seen' ? ' primary' : '') + '" data-bulk="' + a[0] + '">' + a[1] + '</button>').join('') +
    '<button class="btn sm" data-bulk="all">Select all</button><button class="btn sm" data-bulk="none">Clear</button>';
  bar.hidden = false;
}
function pick(id, on){
  if (on === undefined) on = !R.multi.has(id);
  on ? R.multi.add(id) : R.multi.delete(id);
  const r = $('.row[data-doc="' + CSS.escape(id) + '"]');
  if (r) { r.classList.toggle('picked', on); const p = r.querySelector('.pick'); if (p) p.setAttribute('aria-checked', on); }
  R.anchor = id; drawBulk();
}
// Send to the Kindle: one EPUB (a digest for several) into the folder Syncthing shares with it.
async function sendToKindle(ids){
  toast('Making the EPUB, images and all…');
  try {
    const r = await api('/api/kindle/send', { method:'POST', body:JSON.stringify({ ids }) });
    toast((r.count > 1 ? 'A digest of ' + r.count : 'It') + ' goes to the Kindle (Libros/Daf) next time it’s online' + (r.skipped.length ? ' · ' + r.skipped.length + ' had no text yet' : ''));
    return r;
  } catch(e){ toast(e.message); return null; }
}
async function bulkAct(act){
  const L = R.list; if (!L) return;
  if (act === 'none') { R.multi.clear(); R.selecting = false; drawRows(); return; }
  if (act === 'all') { visibleItems().forEach(d => R.multi.add(d.id)); drawRows(); return; }
  if (act === 'kindle') { const r = await sendToKindle([...R.multi]); if (r) { R.multi.clear(); R.selecting = false; drawRows(); } return; }
  const ids = [...R.multi]; if (!ids.length) return;
  const bar = $('#bulkbar'); if (bar) bar.querySelectorAll('button').forEach(b => { b.disabled = true; });
  try {
    if (act === 'star' || act === 'save') {
      let n = 0;
      for (const id of ids) {
        try {
          if (act === 'star') { await api('/api/docs/' + encodeURIComponent(id) + '/star', { method:'PUT', body:JSON.stringify({ starred:true }) }); const d = L.items.find(x => x.id === id); if (d) d.starred = 1; }
          else await api('/api/docs/' + encodeURIComponent(id) + '/save', { method:'POST' });
          n++;
        } catch(e){}
      }
      toast(act === 'star' ? n + ' on the Shortlist' : n + ' saved to Library');
    } else {
      const before = {}; ids.forEach(id => { const d = L.items.find(x => x.id === id); if (d) before[id] = d.status; });
      const r = await api('/api/docs/bulk', { method:'POST', body:JSON.stringify({ ids, status: act }) });
      const gone = new Set(r.done);
      // Undo puts each one back where it was.
      const back = {}; r.done.forEach(id => { if (before[id]) (back[before[id]] = back[before[id]] || []).push(id); });
      pushUndo(({ deleted: 'Deleted ', archive: 'Archived ', later: 'Moved to Later ', seen: 'Marked seen ', unseen: 'Back in Unseen ', inbox: 'Back in Inbox ' }[act] || '') + r.done.length,
        () => Promise.all(Object.entries(back).map(([st, xs]) => api('/api/docs/bulk', { method:'POST', body:JSON.stringify({ ids: xs, status: st }) }))));
      L.items = L.items.filter(d => !gone.has(d.id));
      if (!L.items.find(d => d.id === R.sel)) R.sel = L.items[0] ? L.items[0].id : null;
      undoToast({ seen:'Marked seen', unseen:'Back in Unseen', later:'Moved to Later', archive:'Archived', inbox:'Back in Inbox', deleted:'Deleted' }[act] + ': ' + r.done.length + (r.failed.length ? ' · ' + r.failed.length + ' didn’t go through' : ''));
    }
    R.multi.clear(); R.selecting = false; drawRows(); refreshCounts();
  } catch(e){ toast(e.message); drawBulk(); }
}
function selectRow(id){
  R.sel = id;
  $$('.row').forEach(r => { const on = r.dataset.doc === id; r.classList.toggle('on', on); r.setAttribute('aria-selected', on); });
  const d = R.list && R.list.items.find(x => x.id === id);
  const info = $('#lvinfo'); if (info) info.innerHTML = infoHTML(d);
}
async function docAct(act, id){
  const L = R.list, d = (L && L.items.find(x => x.id === id)) || (R.doc && R.doc.id === id ? R.doc : null);
  if (!d) return;
  try {
    if (act === 'star') {
      const on = !d.starred; await api('/api/docs/' + encodeURIComponent(id) + '/star', { method:'PUT', body:JSON.stringify({ starred:on }) });
      for (const x of [d, R.doc, ...(L ? L.items : [])]) if (x && x.id === id) x.starred = on ? 1 : 0;
      undoToast(on ? 'On the Shortlist' : 'Off the Shortlist', () => api('/api/docs/' + encodeURIComponent(id) + '/star', { method:'PUT', body:JSON.stringify({ starred:!on }) })); refreshCounts();
      if (R.doc && R.doc.id === id) drawReaderTop();
      if (L && !(L.arg === KIND_STAR && !on)) { drawRows(); return; }
    }
    else if (act === 'save') { const r = await api('/api/docs/' + encodeURIComponent(id) + '/save', { method:'POST' }); toast('Saved to the Library'); if (R.doc && R.doc.id === id) { location.hash = 'read/' + encodeURIComponent(r.id); return; } }
    else {
      const status = act === 'seen' ? (d.status === 'seen' ? 'unseen' : 'seen') : act === 'later' ? (d.status === 'later' ? 'inbox' : 'later') : act === 'archive' ? (d.status === 'archive' ? 'inbox' : 'archive') : act === 'delete' ? 'deleted' : act;
      const before = d.status;
      await api('/api/docs/' + encodeURIComponent(id) + '/status', { method:'POST', body:JSON.stringify({ status }) });
      const hls = (R.doc && R.doc.id === id ? R.doc.highlights.length : d.highlights) || 0;
      undoToast({ seen:'Marked seen', unseen:'Back in Unseen', later:'Moved to Later', archive:'Archived', inbox:'Back in Inbox', deleted: hls ? 'Deleted. Its highlights stay in Highlights' : 'Deleted' }[status],
        () => api('/api/docs/' + encodeURIComponent(id) + '/status', { method:'POST', body:JSON.stringify({ status: before }) }));
      if (R.doc && R.doc.id === id && (status === 'seen' || status === 'archive' || status === 'deleted' || (status === 'later' && store.get('autoAdvance', false)))) {
        stopTTS();
        const nx = store.get('autoAdvance', false) && neighbor(id, 1);
        if (L) { const i = L.items.findIndex(x => x.id === id); if (i >= 0) L.items.splice(i, 1); }
        if (nx) location.hash = 'read/' + encodeURIComponent(nx.id); else leaveDoc(d);
        return;
      }
      if (R.doc && R.doc.id === id) { R.doc.status = status; drawReaderTop(); }
    }
    if (L) {
      const i = L.items.findIndex(x => x.id === id);
      L.items.splice(i, 1);
      if (R.sel === id) R.sel = L.items[Math.min(i, L.items.length - 1)] ? L.items[Math.min(i, L.items.length - 1)].id : null;
      drawRows();
    }
    refreshCounts();
  } catch(e){ toast(e.message); }
}

/* ---------- the reading view ---------- */
// Back from an article: to the page before it in Daf, or, opened straight from a link (the
// extension's Open in Daf, a Signal message), to its list.
function leaveDoc(d){
  if ((C.S.navs || 0) > 1) history.back();
  else location.hash = d && d.where_ === 'feed' ? 'feed' : d && d.kind && KIND[d.kind] ? 'library/' + d.kind : 'library/article';
}
const fmtT = t => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), x = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
// X saves a tweet's title as '(2) Name on X: "first tweet" / X'. Show "Name" and the tweet apart.
function tweetParts(d){
  const m = d && d.kind === 'tweet' ? /^(?:\(\d+\)\s*)?(.+?) on X:\s*["“]([\s\S]*)["”]\s*\/\s*X$/.exec(d.title || '') : null;
  return m ? { title: m[1] + ' on X', lead: m[2] } : { title: d ? d.title : '', lead: '' };
}
const TLNAME = { both: 'עב · EN', he: 'עברית', en: 'English' };
function setTL(v){
  store.set('torahLang', v); document.body.dataset.tl = v;
  $$('[data-tlang]').forEach(x => { x.classList.toggle('on', x.dataset.tlang === v); x.setAttribute('aria-checked', x.dataset.tlang === v); });
  const c = $('[data-tlcycle]'); if (c) c.textContent = TLNAME[v];
}
// X's login wall, which Karakeep saves along with the tweets. Hidden, never removed (highlights count blocks).
const XJUNK = /^(Don’t miss what’s happening|Don't miss what's happening|People on X are the first to know\.?|Log in|Sign up|Trending now|Post|Conversation|Relevant people|What’s happening|New to X\?|Sign up now to get your own personalized timeline!|Terms of Service|Privacy Policy|Cookie Policy|Show more|@\w+)$/i;
function blockHTML(b, i){
  if (R.junk && R.junk.has(i)) return '';
  if (b.t === 'pg') return '<div class="pgmark" aria-label="Page ' + esc(b.h) + '"><span>' + esc(b.h) + '</span></div>';
  if (b.t === 'verse') return '<div class="verse' + (i === R.focus ? ' focus' : '') + '" data-i="' + i + '"><span class="vn">' + esc(b.n) + '</span><p class="vhe" dir="rtl" lang="he">' + esc(b.he || '') + '</p><p class="ven">' + b.h + '</p></div>';
  if (b.t === 'cue') return '<div class="tl" data-li="' + i + '"><button class="ts" data-seek="' + b.ts + '" aria-label="Play from ' + fmtT(b.ts) + '">' + fmtT(b.ts) + '</button><p data-i="' + i + '" class="cue' + (i === R.focus ? ' focus' : '') + '"' + dirAttr(b.x) + '>' + (b.spk ? '<span class="spk">' + esc(b.spk) + '</span> ' : '') + b.h + '</p></div>';
  if (b.t === 'h3' && b.ts != null) return '<h3 data-i="' + i + '" class="chap"><button class="ts" data-seek="' + b.ts + '">' + fmtT(b.ts) + '</button> ' + b.h + '</h3>';
  if (b.t === 'img' && R.avatars && R.avatars.has(b.src)) return '';
  if (b.t === 'img') return '<figure class="fig" data-img="' + i + '"><img src="' + esc(b.src) + '" alt="' + esc(b.alt || '') + '" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></figure>';
  const tag = b.t === 'h2' || b.t === 'h3' ? b.t : b.t === 'blockquote' ? 'blockquote' : b.t === 'pre' ? 'pre' : 'p';
  const cls = (b.t === 'li' ? 'li ' : '') + (R.avatars && b.t === 'p' ? 'tw ' : '') + (i === R.focus ? 'focus' : '');
  return '<' + tag + ' data-i="' + i + '" class="' + cls.trim() + '"' + dirAttr(b.x) + '>' + b.h + '</' + tag + '>';
}
function applyMarks(){
  const d = R.doc, body = $('#docbody'); if (!d || !body) return;
  d.highlights.forEach(h => {
    if (H.picture(h.text)) { markImg(h); return; }
    if (!h.pos || h.pos.b == null) h.pos = findPos(h.text, h.pos && h.pos.pre);   // Karakeep's and the browser extension's come without a place in Daf's text
    if (h.pos && h.pos.b != null) markHl(h);
  });
}
// A highlighted picture: its figure gets the color's frame. Found by its block, else by its address.
function markImg(h){
  const pic = H.picture(h.text); if (!pic) return null;
  let f = h.pos && h.pos.b != null ? $('#docbody figure[data-img="' + h.pos.b + '"]') : null;
  if (!f || (f.querySelector('img') || {}).getAttribute('src') !== (h.pos && h.pos.img || pic.src)) {
    f = $$('#docbody figure[data-img]').find(x => { const im = x.querySelector('img'); return im && (im.getAttribute('src') === pic.src || im.src === pic.src); }) || null;
    if (f) h.pos = Object.assign({}, h.pos || {}, { b: +f.dataset.img, s: 0, e: 0, img: pic.src });
  }
  if (!f) return null;
  f.classList.add('hlimg'); f.dataset.h = h.id; f.dataset.color = h.color || 'yellow';
  f.classList.toggle('has-note', !!(h.user_note || '').trim());
  return f;
}
// Selecting a picture: tap or click it, then Highlight, or h.
function pickImg(f){
  const d = R.doc; if (!d) return;
  const i = +f.dataset.img, h = f.dataset.h && d.highlights.find(x => x.id === f.dataset.h);
  if (h) { showHlBar(h); return; }
  R.imgSel = i; $$('#docbody figure.picked').forEach(x => x.classList.remove('picked')); f.classList.add('picked');
  H.show(H.imgBar(), f.getBoundingClientRect(), { img: i, text: d.blocks[i].alt || '' });
}
async function highlightImg(i, withNote){
  const d = R.doc, b = d && d.blocks[i]; if (!b || b.t !== 'img') return;
  H.hide(); R.imgSel = null; $$('#docbody figure.picked').forEach(x => x.classList.remove('picked'));
  const text = '![' + String(b.alt || '').replace(/[\[\]\n]+/g, ' ').trim() + '](' + b.src + ')', color = H.color();
  try {
    const r = await api('/api/docs/' + encodeURIComponent(d.id) + '/highlights', { method:'POST', body:JSON.stringify({ b: i, s: 0, e: 0, text, img: b.src, color }) });
    const h = { id: r.id, text, pos: { b: i, s: 0, e: 0, img: b.src }, user_note: null, color, source: 'daf', tags: [], created: Date.now() / 1000 };
    d.highlights = d.highlights.filter(x => x.id !== h.id).concat(h);
    markImg(h); drawToc();
    if (!d.vault_path) d.vault_path = 'Reference/clippings/…';
    if (r.saved_as) movedToLibrary(d, r.saved_as);
    if (withNote) openNoteA(h); else { drawPanel(); showHlBar(h); }
  } catch(err){ toast(err.message); }
}
const reEsc = w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
// pre (from the browser extension): the words just before it, which pick between two places with the same words.
// One word is found as a whole word, and its words before choose which of its places it is.
function findPos(text, pre){
  const words = String(text || '').trim().split(/\s+/).filter(Boolean); if (!words.length) return null;
  const head = words.length === 1 ? new RegExp('(?<![\\p{L}\\p{N}])' + reEsc(words[0]) + '(?![\\p{L}\\p{N}])', 'gu')
    : new RegExp(words.slice(0, 10).map(reEsc).join('\\s+'), 'g');
  const tail = new RegExp(words.slice(-6).map(reEsc).join('\\s+'));
  const want = String(pre || '').replace(/\s+/g, '').slice(-12); let first = null;
  for (const el of $$('#docbody [data-i]')) {
    const full = el.textContent; head.lastIndex = 0;
    for (let m = head.exec(full); m; m = head.exec(full)) {
      const rest = full.slice(m.index), t = words.length > 10 ? tail.exec(rest) : null;
      const p = { b: +el.dataset.i, s: m.index, e: t ? m.index + t.index + t[0].length : Math.min(full.length, m.index + Math.max(m[0].length, text.length)) };
      const before = full.slice(0, m.index).replace(/\s+/g, '');
      if (!want || (before.length >= want.length ? before.endsWith(want) : want.endsWith(before))) return p;
      first = first || p;
      if (!m[0].length) head.lastIndex++;
    }
  }
  return first;
}
// A highlight can run over several paragraphs: pos {b, s, e} plus be, the block where it ends.
function markHl(h){
  const p = h.pos, b2 = p.be != null ? p.be : p.b, marks = [];
  for (let i = p.b; i <= b2; i++) {
    const el = $('#docbody [data-i="' + i + '"]'); if (!el) continue;
    marks.push(...markRange(el, i === p.b ? p.s : 0, i === b2 ? p.e : el.textContent.length, h));
  }
  if (marks.length) marks[marks.length - 1].classList.add('end');
  return marks;
}
function unmark(id){ $$('figure.hlimg[data-h="' + CSS.escape(id) + '"]').forEach(f => { f.classList.remove('hlimg', 'has-note'); delete f.dataset.h; delete f.dataset.color; }); $$('mark[data-h="' + CSS.escape(id) + '"]').forEach(m => { const p = m.parentNode; while (m.firstChild) p.insertBefore(m.firstChild, m); p.removeChild(m); p.normalize(); }); }
function markRange(el, s, e, h){
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let pos = 0, node; const parts = [];
  while ((node = walker.nextNode())) {
    const len = node.nodeValue.length, a = Math.max(s, pos), b = Math.min(e, pos + len);
    if (a < b) parts.push([node, a - pos, b - pos]);
    pos += len;
  }
  const out = [];
  parts.forEach(([n, a, b]) => {
    const r = document.createRange(); r.setStart(n, a); r.setEnd(n, b);
    const m = document.createElement('mark'); m.className = 'hl' + (h.user_note ? ' has-note' : ''); m.dataset.h = h.id; m.dataset.color = h.color || 'yellow';
    try { r.surroundContents(m); out.push(m); } catch(err){}
  });
  return out;
}
// The item before or after this one in the list it was opened from (the tag filter counts).
function visibleItems(){ const L = R.list; if (!L) return []; return R.tag ? L.items.filter(d => tagsOf(d).includes(R.tag)) : L.items; }
function neighbor(id, dir){ const xs = visibleItems(), i = xs.findIndex(d => d.id === id); return i < 0 ? null : xs[i + dir] || null; }
function drawReaderTop(){
  const d = R.doc, top = $('#rtop'); if (!d || !top) return;
  const feed = d.where_ === 'feed';
  const pv = neighbor(d.id, -1), nx = neighbor(d.id, 1);
  top.innerHTML = '<button class="ib" data-ract="back" aria-label="Back">' + I.back + '</button>' +
    (pv || nx ? '<button class="ib" data-ract="prevdoc" title="Previous in the list' + K.tip('article', 'prevdoc') + '" aria-label="Previous in the list"' + (pv ? '' : ' disabled') + '>' + ICON.up + '</button><button class="ib" data-ract="nextdoc" title="Next in the list' + K.tip('article', 'nextdoc') + '" aria-label="Next in the list"' + (nx ? '' : ' disabled') + '>' + ICON.down + '</button>' : '') +
    '<button class="ib aa" data-ract="aa" aria-label="Typography and theme">Aa</button>' +
    (d.kind === 'torah' ? '<button class="btn sm tlcycle" data-tlcycle aria-label="Language: tap to switch">' + TLNAME[store.get('torahLang', 'both')] + '</button>' : '') +
    (d.kind === 'torah' ? '<div class="seg sm tlang" role="radiogroup" aria-label="Language">' + [['both', 'Both'], ['he', 'עברית'], ['en', 'English']].map(x => '<button type="button" role="radio" data-tlang="' + x[0] + '" class="' + ((store.get('torahLang', 'both') === x[0]) ? 'on' : '') + '" aria-checked="' + (store.get('torahLang', 'both') === x[0]) + '">' + x[1] + '</button>').join('') + '</div>' : '') +
    '<span class="spacer"></span>' +     // whether it counts toward the hour shows on Today and in Stats, not over the text (decided 2026-10-11)
    (d.blocks.length && d.kind !== 'video' ? '<button class="btn sm' + (R.tts.on && R.tts.doc === d.id && R.tts.playing ? ' on' : '') + '" data-ract="listen">' + ICON.listen + (R.tts.on && R.tts.doc === d.id && R.tts.playing ? 'Pause' : 'Listen') + '</button>' : '') +
    (!feed ? '<button class="ib' + (d.starred ? ' on' : '') + '" data-dact="star" data-id="' + esc(d.id) + '" title="' + (d.starred ? 'Off the Shortlist' : 'Shortlist') + K.tip('article', 'star') + '" aria-label="Shortlist">' + ICON.star(!!d.starred) + '</button>' : '') +
    (feed ? '<button class="btn sm" data-dact="save" data-id="' + esc(d.id) + '">' + ICON.save + 'Save to Library</button>' : '<button class="ib' + (d.status === 'later' ? ' on' : '') + '" data-dact="later" data-id="' + esc(d.id) + '" title="Later' + K.tip('article', 'later') + '" aria-label="Later">' + ICON.later + '</button>') +
    '<button class="ib" data-dact="' + (feed ? 'seen' : 'archive') + '" data-id="' + esc(d.id) + '" title="Done' + K.tip('article', 'archive') + '" aria-label="Done">' + ICON.done + '</button>' +
    (d.has_pdf ? '<a class="btn sm" href="#pdf/' + encodeURIComponent(d.id) + '" title="The PDF as printed, to read and highlight on">Pages</a>' : '') +
    (d.url ? '<a class="ib" href="' + esc(d.url) + '" target="_blank" rel="noopener" title="Open original" aria-label="Open original">' + ICON.ext + '</a>' : '') +
    '<button class="ib" data-ract="more" title="More actions (m)" aria-label="More actions"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg></button>' +
    (C.Focus ? C.Focus.button('article') : '') +
    '<button class="ib' + (R.panelOpen ? ' on' : '') + '" data-ract="panel" aria-label="Show or hide the side panel">' + ICON.panel + '</button>';
}
// The … menu (Readwise's "More actions"): everything the bar doesn't show, with its key.
function openMore(anchor){
  const d = R.doc; if (!d) return;
  const feed = d.where_ === 'feed', lib = d.where_ === 'library';
  const it = (act, label, key, cls) => '<button data-more="' + act + '"' + (cls ? ' class="' + cls + '"' : '') + '><span>' + label + '</span>' + (key ? '<kbd>' + key + '</kbd>' : '') + '</button>';
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  // on a phone the bar has no room for these, so they're here (see style.css, max-width 600px)
  const phone = matchMedia('(max-width:600px)').matches, pv = neighbor(d.id, -1), nx = neighbor(d.id, 1);
  p.innerHTML = '<div class="menu">' +
    (phone ? (nx ? it('nextdoc', 'Next in the list', K.label('article', 'nextdoc')) : '') + (pv ? it('prevdoc', 'Previous in the list', K.label('article', 'prevdoc')) : '') +
      it('panel', R.panelOpen ? 'Hide the notebook' : 'Notebook and info', '') +
      (d.has_pdf && d.blocks.length ? it('pages', 'The PDF as printed', '') : '') + '<hr>' : '') +
    it('note', 'Add a document note', K.label('article', 'docnote')) +
    (d.blocks.length && d.kind !== 'video' ? it('listen', R.tts.on && R.tts.doc === d.id ? 'Stop reading aloud' : 'Read aloud from here', K.label('article', 'aloud')) : '') +
    it('ask', 'Ask about this', '') +
    (feed && d.url ? it('full', d.full ? 'Load the full article again' : 'Load the full article', '') : '') +
    (d.blocks.length && d.kind !== 'video' && d.kind !== 'podcast' ? it('kindle', d.kindle_sent ? 'Send to the Kindle again' : 'Send to the Kindle', '') : '') +
    (deviceKeeps() && d.blocks.length ? it('device', R.onDevice && R.onDevice.pinned.has(d.id) ? 'Remove from this device' : 'Keep on this device', '') : '') + '<hr>' +
    (feed ? it('save', 'Save to Library', K.label('article', 'save')) + it('seen', d.status === 'seen' ? 'Back to Unseen' : 'Mark seen', K.label('article', 'archive')) :
     lib ? it('later', d.status === 'later' ? 'Back to Inbox' : 'Read later', K.label('article', 'later')) + it('archive', d.status === 'archive' ? 'Back to Inbox' : 'Archive', K.label('article', 'archive')) : '') +
    it('reset', 'Reset reading progress', K.label('article', 'reset')) + it('meta', 'Edit title and author', K.label('article', 'meta')) + it('delete', 'Delete', K.label('article', 'delete'), 'danger') + '<hr>' +
    (d.url ? it('open', 'Open the original', K.label('article', 'open')) + it('copy', 'Copy the link', K.label('article', 'copy')) : '') +
    (d.vault_path ? it('vault', 'Open the note in Obsidian', '') : '') +
    (phone ? '' : it('keys', 'Keyboard shortcuts', '?')) + '</div>';
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 300, r.right - 280)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
  if (deviceKeeps() && d.blocks.length) deviceList().then(on => {   // opened from a link or a card, no list has asked yet
    const b = p.querySelector('[data-more="device"] span');
    if (b && on) b.textContent = on.pinned.has(d.id) ? 'Remove from this device' : 'Keep on this device';
  });
}
function moreAct(a){
  const d = R.doc; if (!d) return;
  $('#pop').hidden = true;
  if (a === 'nextdoc' || a === 'prevdoc') { const nb = neighbor(d.id, a === 'nextdoc' ? 1 : -1); if (nb) location.hash = 'read/' + encodeURIComponent(nb.id); }
  else if (a === 'panel') { R.panelOpen = !R.panelOpen; const g = $('.rvgrid'); if (g) g.classList.toggle('withpanel', R.panelOpen); drawReaderTop(); if (R.panelOpen) drawPanel(); }
  else if (a === 'full') loadFull(d.id);
  else if (a === 'device') deviceList().then(on => keepOnDevice(d.id, !(on && on.pinned.has(d.id))));
  else if (a === 'pages') location.hash = 'pdf/' + encodeURIComponent(d.id);
  else if (a === 'note') { R.panel = 'notebook'; openPanel(); drawPanel(); setTimeout(() => { const x = $('#docnote'); if (x) x.focus(); }, 40); }
  else if (a === 'listen') { if (R.tts.on && R.tts.doc === d.id) stopTTS(); else startTTS(); }
  else if (a === 'kindle') sendToKindle([d.id]).then(r => { if (r) d.kindle_sent = { file: r.file, at: Date.now() / 1000 }; });
  else if (a === 'ask') { R.panel = 'ask'; openPanel(); drawPanel(); setTimeout(() => { const x = $('#rpanel textarea'); if (x) x.focus(); }, 40); }
  else if (['save', 'seen', 'later', 'archive', 'delete'].includes(a)) docAct(a, d.id);
  else if (a === 'reset') api('/api/docs/' + encodeURIComponent(d.id) + '/progress', { method:'DELETE' }).then(() => { d.progress = 0; $('#main').scrollTo({ top:0, behavior:'smooth' }); toast('Back to the start; progress cleared'); }).catch(e => toast(e.message));
  else if (a === 'open' && d.url) window.open(d.url, '_blank', 'noopener');
  else if (a === 'copy' && d.url) navigator.clipboard && navigator.clipboard.writeText(d.url).then(() => toast('Link copied'), () => {});
  else if (a === 'vault' && d.vault_path) location.href = 'obsidian://open?vault=' + encodeURIComponent(d.vault_name || 'vault') + '&file=' + encodeURIComponent(d.vault_path.replace(/\.md$/, ''));
  else if (a === 'keys') showKeys();
  else if (a === 'meta') editMeta();
}
function editMeta(){
  const d = R.doc; if (!d) return;
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  m.innerHTML = '<h2>Edit title and author</h2><label class="mute tiny" for="mtitle">Title</label><input class="field" id="mtitle" value="' + esc(d.title || '') + '"' + dirAttr(d.title) + '>' +
    '<label class="mute tiny" for="mauthor">Author</label><input class="field" id="mauthor" value="' + esc(d.author || '') + '">' +
    '<span class="mute tiny">Stays this way after FreshRSS syncs.</span><div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button><button class="btn primary" id="msave">Save</button></div>';
  const t = $('#mtitle'); t.focus(); t.select();
  const save = async () => {
    try { const r = await api('/api/docs/' + encodeURIComponent(d.id) + '/meta', { method:'PUT', body:JSON.stringify({ title:$('#mtitle').value, author:$('#mauthor').value }) });
      d.title = r.title; d.author = r.author; C.closeModal(); const h = $('.doc h1'); if (h) h.textContent = tweetParts(d).title; const by = $('.doc .byline'); if (by) by.innerHTML = [d.author ? esc(d.author) : '', d.mins ? d.mins + ' min' : '', d.published ? epochDate(d.published) : ''].filter(Boolean).join(' · '); drawPanel(); toast('Saved'); }
    catch(e){ toast(e.message); }
  };
  $('#msave').onclick = save;
  m.onkeydown = e => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); save(); } };
}
function showKeys(){ K.sheet('article'); }
// A document's tags, from its row, the side pane or t.
function tagDoc(id, anchor){
  const d = (R.list && R.list.items.find(x => x.id === id)) || (R.doc && R.doc.id === id ? R.doc : null); if (!d || !anchor) return;
  api('/api/docs/tags').then(r => H.tagEditor({ id, tags: tagsOf(d) }, anchor.getBoundingClientRect(), x => {
    for (const y of [d, R.doc, ...(R.list ? R.list.items : [])]) if (y && y.id === id) y.tags = x.tags;
    const info = $('#lvinfo'); if (info && R.sel === id) info.innerHTML = infoHTML(d);
  }, { url: '/api/docs/' + encodeURIComponent(id) + '/tags', all: r.tags, plain: true, hint: 'Enter adds a tag · kept in Daf' })).catch(e => toast(e.message));
}
async function readView(id){
  stopSel();
  $('#main').innerHTML = '<div class="rv"><div class="top" id="rtop"><button class="ib" data-ract="back" aria-label="Back">' + I.back + '</button></div><div class="docwrap"><div class="doc"><span class="mute">Loading…</span></div></div></div>';
  let d;
  try { d = await api('/api/docs/' + encodeURIComponent(id)); } catch(e){ $('.doc').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  R.doc = d; R.focus = 0; document.body.dataset.tl = store.get('torahLang', 'both');
  R.junk = d.kind === 'tweet' ? new Set(d.blocks.map((b, i) => [b, i]).filter(([b]) => XJUNK.test((b.x || '').trim())).map(([, i]) => i)) : null;
  const heads = d.blocks.map((b, i) => [b, i]).filter(x => (x[0].t === 'h2' || x[0].t === 'h3') && !(R.junk && R.junk.has(x[1])));
  const showToc = R.toc && window.innerWidth > 1000 && (heads.length > 1 || d.highlights.length);
  let h = '<div class="progress"><i id="rprog"></i></div><div class="rv"><div class="top" id="rtop"></div><div class="rvgrid' + (showToc ? '' : ' notoc') + (R.panelOpen ? ' withpanel' : '') + '">' +
    '<nav class="toc" aria-label="Contents" id="toc"></nav><div class="docwrap"><article class="doc">' +
    '<div class="eyebrow"' + dirAttr(d.source) + '>' + esc([d.source, d.category].filter(Boolean).join(' · ')) + '</div><h1' + dirAttr(d.title) + '>' + esc(tweetParts(d).title) + '</h1>' +
    '<div class="byline">' + [d.author ? esc(d.author) : '', d.mins ? d.mins + ' min' : '', d.published ? epochDate(d.published) : ''].filter(Boolean).join(' · ') + '</div>';
  if (d.kind === 'video') h += videoHead(d);
  if (tweetParts(d).lead) h += '<p class="tweetlead">' + esc(tweetParts(d).lead) + '</p>';
  if (d.kind === 'tweet') { const seen = {}; d.blocks.forEach(b => { if (b.t === 'img') seen[b.src] = (seen[b.src] || 0) + 1; }); R.avatars = new Set(Object.keys(seen).filter(k => seen[k] > 1)); } else R.avatars = null;
  if (!d.blocks.length && d.reel) { /* reelHead says where it is */ }
  else if (!d.blocks.length && d.kind === 'video') h += '<div class="placeholder" id="trstatus">No transcript yet. <button class="btn sm" data-tr="captions">Get YouTube’s captions</button> <button class="btn sm" data-tr="whisper">Transcribe on the server (slow)</button></div>';
  else if (!d.blocks.length && d.kind === 'pdf') h += '<div class="placeholder">' + (d.preparing ? '<span id="trstatus">Reading the PDF on the server. The text appears here in a moment.</span>' : 'Couldn’t read this PDF: ' + esc(d.content_error || '') + '.') + ' <a href="/api/docs/' + encodeURIComponent(d.id) + '/pdf" target="_blank" rel="noopener">Open the original layout</a></div>';
  else if (!d.blocks.length && d.preparing) h += '<div class="placeholder"><span id="trstatus">Reading the page on the server. The text appears here in a moment.</span> <a href="' + esc(d.url || '#') + '" target="_blank" rel="noopener">Open the original</a></div>';
  else if (!d.blocks.length) h += '<div class="placeholder">' + (d.content_error ? (/^Daf /.test(d.content_error) ? esc(d.content_error) : 'Karakeep didn’t answer: ' + esc(d.content_error)) : d.kind === 'pdf' ? 'PDFs open in the reader in a later round. For now, open the original.' : d.kind === 'podcast' ? 'A podcast episode. Listen in AntennaPod, and share it to Ezer with its position to clip the minute before.' : 'There’s no saved text for this one.') + (d.url ? ' <a href="' + esc(d.url) + '" target="_blank" rel="noopener">Open the original</a>' : '') + '</div>';
  else h += '<div class="body" id="docbody">' + d.blocks.map(blockHTML).join('') + '</div>';
  // A feed that sends only the start: the page has the rest (daf/fulltext.py)
  if (d.where_ === 'feed' && d.url && !d.full && (d.words || 0) < 220) h += '<div class="fullnote" id="fullnote"><span>' + (d.blocks.length ? 'That’s what the feed sends.' : 'The feed sent no text.') +
    '</span><button class="btn sm" data-ract="full">Load the full article</button></div>';
  h += '</article></div><aside class="rpanel" id="rpanel"></aside></div></div>';
  $('#main').innerHTML = h;
  drawReaderTop(); drawToc(); applyMarks(); drawPanel();
  if (d.kind === 'video') startPlayer(d);
  if (d.preparing) pollTranscript(d.id);
  const main = $('#main');
  if (d.progress > 3 && d.progress < 98) setTimeout(() => { main.scrollTop = (main.scrollHeight - main.clientHeight) * d.progress / 100; }, 50);
  main.onscroll = onScroll; R.lastActive = Date.now();
  markSpeaking();
  if (C.Ink) C.Ink.open(d);                           // what's written on it with a pen (ink.js)
}
function drawToc(){
  const d = R.doc, t = $('#toc'); if (!t || !d) return;
  const heads = d.blocks.map((b, i) => [b, i]).filter(x => (x[0].t === 'h2' || x[0].t === 'h3') && !(R.junk && R.junk.has(x[1])));
  t.innerHTML = '<div class="lbl">Contents</div><button data-jump="0">' + esc(shortTitle(d.title)) + '</button>' + heads.map(x => '<button data-jump="' + x[1] + '"' + dirAttr(x[0].x) + '>' + esc(x[0].x.slice(0, 80)) + '</button>').join('') +
    (d.highlights.length ? '<div class="lbl" style="margin-top:14px">Your highlights</div>' + d.highlights.filter(x => x.pos).map(x => '<button data-jump="' + x.pos.b + '"' + dirAttr(x.text) + '>' + (H.picture(x.text) ? 'A picture' + (H.picture(x.text).alt ? ': ' + esc(H.picture(x.text).alt.slice(0, 60)) : '') : esc(x.text.slice(0, 70)) + '…') + '</button>').join('') : '');
}
function drawPanel(){
  const p = $('#rpanel'), d = R.doc; if (!p || !d) return;
  const tabs = [['info', 'Info'], ['notebook', 'Notebook <span class="c">' + d.highlights.length + '</span>'], ['ask', 'Ask']];
  let h = '<div class="ptabs" role="tablist">' + tabs.map(t => '<button class="ptab' + (R.panel === t[0] ? ' on' : '') + '" data-ptab="' + t[0] + '" role="tab">' + t[1] + '</button>').join('') + '<button class="ib pclose" data-ract="panel" aria-label="Close">' + ICON.close + '</button></div>';
  if (R.panel === 'info') h += infoHTML(d).replace(/<a class="btn primary"[^>]*>(Read|Watch)<\/a>/, '');
  else if (R.panel === 'notebook') {
    h += '<div class="pbody"><div style="display:flex;flex-direction:column;gap:6px"><label class="lbl" for="docnote">Document note</label><input class="field" id="docnote" placeholder="Why you saved this, in a line" value="' + esc(d.note || '') + '"></div>' +
      '<div class="nbook"><div class="nbhead"><span class="lbl">Highlights</span><span class="spacer"></span>' + (d.highlights.length ? '<a class="linkbtn tiny" href="/api/highlights/export?fmt=md&book=' + encodeURIComponent(d.id) + '" download>Export</a>' : '') + '</div>' +
        (d.highlights.length ? sortedHls(d).map(x => H.row(Object.assign(x, { source: x.source || 'daf', open: '#read/' + encodeURIComponent(d.id) + '/hl:' + encodeURIComponent(x.id) }), (H.rowOpts = { chapter: false, date: false }))).join('')
          : '<span class="mute tiny">' + (H.auto() ? 'Select a passage and it’s highlighted (hold Alt to select without), or press h on the paragraph with the bar.' : 'Select text and choose Highlight, or press h on the paragraph with the bar.') + '</span>') + '</div>' +
      (d.vault_path ? '<div class="vault"><b>In your vault</b><code>' + esc(d.vault_path) + '</code><a class="tiny" href="obsidian://open?vault=' + encodeURIComponent(d.vault_name || 'vault') + '&file=' + encodeURIComponent(d.vault_path.replace(/\.md$/, '')) + '">Open in Obsidian</a></div>' : '<div class="vault"><span class="mute tiny">The first highlight creates a note in <code>Reference/clippings</code>.</span></div>') + '</div>';
  } else {
    const chips = d.questions || ['Summarize this', 'What’s the main argument?', 'What should I remember from this?'];   // Preferences → AI
    h += '<div class="pbody"><span class="mute tiny">Answers come from this document and your highlights in it.</span>' +
      '<div style="display:flex;gap:6px;flex-wrap:wrap">' + chips.map(c => '<button class="chip" data-askq="' + esc(c) + '">' + esc(c) + '</button>').join('') + '</div>' +
      d.asks.map(a => '<div class="qa"><div class="q">' + esc(a.q) + '</div>' + (a.quote ? '<q class="mute tiny">' + esc(a.quote) + '</q>' : '') + '<div class="a">' + esc(a.a).replace(/\n/g, '<br>') + '</div></div>').join('') +
      (R.asking ? '<div class="qa"><div class="q">' + esc(R.asking) + '</div><div class="a mute">Thinking…</div></div>' : '') +
      '<form id="askf" style="display:flex;gap:6px"><input class="field" id="askin" placeholder="Ask about this…" aria-label="Question"><button class="btn primary" type="submit"' + (R.asking ? ' disabled' : '') + '>Ask</button></form></div>';
  }
  p.innerHTML = h;
}
function sortedHls(d){ return d.highlights.slice().sort((a, b) => ((a.pos && a.pos.b) ?? 1e9) - ((b.pos && b.pos.b) ?? 1e9) || ((a.pos && a.pos.s) || 0) - ((b.pos && b.pos.s) || 0)); }
async function ask(q, quote){
  const d = R.doc; if (!d || R.asking) return;
  R.asking = q; R.panel = 'ask'; openPanel(); drawPanel();
  try { const r = await api('/api/docs/' + encodeURIComponent(d.id) + '/ask', { method:'POST', body:JSON.stringify({ q, quote }) }); d.asks.push({ q, quote, a:r.a }); }
  catch(e){ toast(e.message); }
  R.asking = null; if (R.doc === d) drawPanel();
}
function openPanel(){ if (!R.panelOpen){ R.panelOpen = true; const g = $('.rvgrid'); if (g) g.classList.add('withpanel'); drawReaderTop(); } }
function onScroll(){
  // (on a touch screen a selection's bar stays and follows the words: the scroll listener below)
  const main = $('#main'), d = R.doc; if (!(H.touch() && H.ctx && H.ctx.kind === 'sel')) stopSel(); R.lastActive = Date.now();
  if (!d) return;
  const max = main.scrollHeight - main.clientHeight, pct = max > 0 ? Math.round(main.scrollTop / max * 100) : 100;
  const bar = $('#rprog'); if (bar) bar.style.width = pct + '%';
  if (pct > (d.progress || 0) && Date.now() - R.progT > 4000) { R.progT = Date.now(); d.progress = pct; api('/api/docs/' + encodeURIComponent(d.id) + '/progress', { method:'PUT', body:JSON.stringify({ pct }) }).catch(() => {}); }
}
function setFocus(i, scroll){
  const d = R.doc; if (!d || !d.blocks.length) return;
  const idx = []; d.blocks.forEach((b, j) => { if (b.t !== 'img') idx.push(j); });
  if (!idx.length) return;
  let k = idx.indexOf(R.focus); if (k < 0) k = 0;
  if (i === '+') k = Math.min(idx.length - 1, k + 1); else if (i === '-') k = Math.max(0, k - 1); else k = Math.max(0, idx.indexOf(i));
  R.focus = idx[k];
  $$('#docbody .focus').forEach(el => el.classList.remove('focus'));
  const el = $('#docbody [data-i="' + R.focus + '"]');
  if (el){ el.classList.add('focus'); if (scroll) el.scrollIntoView({ block:'center', behavior:'smooth' }); }
}

/* ---------- video (YouTube's privacy-mode player, synced to the transcript) ---------- */
const V = { player: null, playing: false, follow: true, timer: null, cur: -1 };
const ytId = u => (String(u || '').match(/(?:v=|youtu\.be\/|\/shorts\/|\/embed\/)([A-Za-z0-9_-]{11})/) || [])[1];
// A reel (social.py): Daf's own copy, standing up, in a <video>; V.player speaks the YouTube player's
// few words (getCurrentTime, seekTo, playVideo, pauseVideo), so the transcript, Clip and the keys
// work the same.
function reelHead(d){
  const wait = d.preparing ? 'Getting the reel from Instagram. It plays here in a moment.'
    : d.content_error ? esc(d.content_error) : 'Daf doesn’t have this video yet.';
  const signIn = /sign in again/.test(d.content_error || '') ? ' <a href="#prefs/instagram">Instagram in Preferences</a>' : '';
  return '<div class="vhead"><div class="vframe tall">' + (d.media
      ? '<video id="lvp" controls playsinline preload="metadata"' + (d.thumb ? ' poster="' + esc(d.thumb) + '"' : '') + ' src="' + esc(d.media) + '"></video>'
      : '<div class="vwait"><span id="trstatus">' + wait + '</span>' + signIn + '</div>') + '</div><div class="vctl">' +
    (d.media ? '<button class="btn sm" data-vclip="30" title="Highlight the last 30 seconds (c)">Clip 30s</button>' +
      '<label class="tiny mute" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="vfollow" checked> Follow along</label>' : '') +
    '<span class="spacer"></span><a class="tiny" href="' + esc(d.url) + '" target="_blank" rel="noopener">Open on Instagram</a></div></div>';
}
function startReel(){
  const el = $('#lvp'); if (!el) return;
  V.player = { getCurrentTime: () => el.currentTime || 0, seekTo: t => { el.currentTime = t; },
               playVideo: () => { const p = el.play(); if (p && p.catch) p.catch(() => {}); }, pauseVideo: () => el.pause() };
  const on = () => { V.playing = !el.paused && !el.ended; R.lastActive = Date.now(); };
  ['play', 'playing', 'pause', 'ended'].forEach(ev => el.addEventListener(ev, on));
  // a post that's square or wide (Instagram's feed has both) gets a frame its own shape
  el.addEventListener('loadedmetadata', () => {
    const f = el.parentNode, w = el.videoWidth, h = el.videoHeight;
    if (w && h && w > h * 0.9) { f.classList.remove('tall'); f.classList.add('wide'); f.style.aspectRatio = w + '/' + h; }
  });
  V.timer = setInterval(syncCue, 500);
}
function videoHead(d){
  if (d.reel) return reelHead(d);
  const id = ytId(d.url);
  return '<div class="vhead"><div class="vframe"><div id="ytp"></div></div><div class="vctl">' +
    '<button class="btn sm" data-vclip="30" title="Highlight the last 30 seconds (c)">Clip 30s</button>' +
    '<label class="tiny mute" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="vfollow" checked> Follow along</label><span class="spacer"></span>' +
    (id ? '<a class="tiny" href="https://yt.tiresia.xyz/watch?v=' + id + '" target="_blank" rel="noopener">Watch on Invidious</a>' : '') + '</div></div>';
}
function startPlayer(d){
  clearInterval(V.timer); V.player = null; V.cur = -1; V.playing = false;
  if (d.reel) { startReel(); return; }
  const id = ytId(d.url); if (!id) return;
  const make = () => {
    V.player = new YT.Player('ytp', { videoId: id, host: 'https://www.youtube-nocookie.com', width: '100%', height: '100%',
      playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
      events: { onStateChange: e => { V.playing = e.data === 1; R.lastActive = Date.now(); } } });
    V.timer = setInterval(syncCue, 500);
  };
  if (window.YT && window.YT.Player) make();
  else { window.onYouTubeIframeAPIReady = make; if (!document.getElementById('ytapi')) { const s = document.createElement('script'); s.id = 'ytapi'; s.src = 'https://www.youtube.com/iframe_api'; document.head.appendChild(s); } }
}
function curTime(){ try { return V.player && V.player.getCurrentTime ? V.player.getCurrentTime() : 0; } catch(e){ return 0; } }
function cueAt(t){ const d = R.doc; let best = -1; if (!d) return -1; d.blocks.forEach((b, i) => { if (b.t === 'cue' && b.ts <= t) best = i; }); return best; }
function syncCue(){
  if (C.S.route[0] !== 'read' || !R.doc || R.doc.kind !== 'video') { clearInterval(V.timer); return; }
  if (V.playing) R.lastActive = Date.now();
  const i = cueAt(curTime()); if (i === V.cur) return;
  V.cur = i; $$('#docbody .tl.now').forEach(x => x.classList.remove('now'));
  const el = $('#docbody .tl[data-li="' + i + '"]');
  if (el) { el.classList.add('now'); if (V.follow && V.playing) { const r = el.getBoundingClientRect(); const top = ($('.vhead') || { getBoundingClientRect: () => ({ bottom: 0 }) }).getBoundingClientRect().bottom; if (r.top < top + 10 || r.bottom > window.innerHeight - 60) $('#main').scrollBy({ top: r.top - top - 100, behavior: 'smooth' }); } }
}
function seek(t){ if (V.player && V.player.seekTo) { V.player.seekTo(t, true); if (!V.playing && V.player.playVideo) V.player.playVideo(); } }
async function clipVideo(sec){
  const d = R.doc, now = curTime(); if (!d) return;
  const cues = d.blocks.map((b, i) => [b, i]).filter(x => x[0].t === 'cue' && x[0].ts >= now - sec && x[0].ts <= now);
  if (!cues.length) { toast('Play the video first; Clip takes the last 30 seconds.'); return; }
  for (const [b, i] of cues) {
    const el = $('#docbody [data-i="' + i + '"]'); const txt = el ? el.textContent.replace(/^\S+\s/, b.spk ? '' : '') : b.x;
    await highlight({ b:i, s:0, e:(el ? el.textContent.length : b.x.length), text:(el ? el.textContent : b.x).trim(), t:b.ts }, false, true);
  }
  toast('Clipped ' + fmtT(cues[0][0].ts) + '–' + fmtT(now) + ' · in the Notebook and the vault');
}

/* ---------- selection and highlights ---------- */
function blockEl(n){ while (n && n.nodeType !== 1) n = n.parentNode; return n ? n.closest('#docbody [data-i]') : null; }
function getSel(){
  const sel = window.getSelection(); if (!sel || !sel.rangeCount || sel.isCollapsed) return null;
  const r = sel.getRangeAt(0); let el = blockEl(r.startContainer), el2 = blockEl(r.endContainer);
  if (!el) return null;
  const off = (blk, node, o) => { const pre = document.createRange(); pre.selectNodeContents(blk); pre.setEnd(node, o); return pre.toString().length; };
  let s = off(el, r.startContainer, r.startOffset), e;
  if (el2) e = off(el2, r.endContainer, r.endOffset); else { el2 = el; e = el.textContent.length; }
  let b = +el.dataset.i, be = +el2.dataset.i;
  if (be < b) return null;
  while (be > b && e === 0) {                         // a triple-click ends at the start of the next paragraph
    be--; const p = $('#docbody [data-i="' + be + '"]'); if (p) { el2 = p; e = p.textContent.length; }
  }
  const t1 = el.textContent, t2 = el2.textContent;
  // Whole words only, as in Readwise.
  while (s > 0 && H.isWord(t1[s - 1]) && H.isWord(t1[s])) s--;
  while (s < t1.length && /\s/.test(t1[s])) s++;
  while (e < t2.length && H.isWord(t2[e - 1]) && H.isWord(t2[e])) e++;
  while (e > 0 && /\s/.test(t2[e - 1])) e--;
  const text = spanText(b, s, be, e);
  if (text.replace(/\s/g, '').length < 2) return null;
  return { b, s, e, be: be !== b ? be : undefined, text, rect: r.getBoundingClientRect() };
}
function spanText(b, s, be, e){
  if (be == null || be === b) { const el = $('#docbody [data-i="' + b + '"]'); return el ? el.textContent.slice(s, e).trim() : ''; }
  const out = [];
  for (let i = b; i <= be; i++) {
    const el = $('#docbody [data-i="' + i + '"]'); if (!el) continue;
    const t = el.textContent; out.push((i === b ? t.slice(s) : i === be ? t.slice(0, e) : t).trim());
  }
  return out.filter(Boolean).join('\n\n');
}
function stopSel(){ H.hide(); }
// The first highlight on a Feed item saves it to the Library (the server did it): the view follows
// it to its Library copy without a reload.
function movedToLibrary(d, id){
  const old = d.id; d.id = id; d.where_ = 'library'; d.status = 'inbox';
  if (R.tts.doc === old) R.tts.doc = id;
  if (C.S.route[0] === 'read' && decodeURIComponent(C.S.route[1] || '') === old) {
    history.replaceState(null, '', '#read/' + encodeURIComponent(id)); C.S.route = (location.hash || '').slice(1).split('/');
  }
  drawReaderTop(); refreshCounts();
  toast('Saved to your Library');
}
async function highlight(info, withNote, quiet){
  const d = R.doc; if (!d || !info) return;
  window.getSelection().removeAllRanges(); H.hide();
  const blk = d.blocks[info.b]; if (info.t == null && blk && blk.ts != null) info.t = blk.ts;
  // Overlapping highlights merge into one, as in Readwise; their notes and tags come along.
  const cmp = (b1, o1, b2, o2) => (b1 - b2) || (o1 - o2);
  let b = info.b, s = info.s, be = info.be != null ? info.be : info.b, e = info.e;
  const merged = d.highlights.filter(h => {
    const p = h.pos; if (!p || p.b == null) return false;
    const hb2 = p.be != null ? p.be : p.b;
    return cmp(b, s, hb2, p.e) < 0 && cmp(p.b, p.s, be, e) < 0;
  });
  for (const h of merged) {
    const p = h.pos, hb2 = p.be != null ? p.be : p.b;
    if (cmp(p.b, p.s, b, s) < 0) { b = p.b; s = p.s; }
    if (cmp(hb2, p.e, be, e) > 0) { be = hb2; e = p.e; }
  }
  if (merged.length === 1) {
    const p = merged[0].pos;
    if (p.b === b && p.s === s && (p.be != null ? p.be : p.b) === be && p.e === e) { showHlBar(merged[0]); return; }   // inside one already
  }
  const text = merged.length ? spanText(b, s, be, e) : info.text;
  try {
    const color = merged.find(m => m.color)?.color || H.color();
    const r = await api('/api/docs/' + encodeURIComponent(d.id) + '/highlights', { method:'POST', body:JSON.stringify({ b, s, e, be: be !== b ? be : null, text, t:info.t, color, replaces: merged.map(m => m.id) }) });
    merged.forEach(m => unmark(m.id));
    const notes = merged.map(m => m.user_note).filter(Boolean);
    const h = { id:r.id, text, pos:{ b, s, e, ...(be !== b ? { be } : {}) }, user_note: notes.join('\n\n') || null, color, source:'daf', tags:[...new Set(merged.flatMap(m => m.tags || []))], fav: merged.some(m => m.fav), created: Date.now() / 1000 };
    d.highlights = d.highlights.filter(x => !merged.includes(x) && x.id !== h.id).concat(h);
    markHl(h);
    if (!d.vault_path) d.vault_path = 'Reference/clippings/…';
    drawToc();
    if (r.saved_as) movedToLibrary(d, r.saved_as);
    else if (r.save_error) toast('Highlighted, but the page wasn’t saved to the Library: ' + r.save_error);
    if (withNote) openNoteA(h);
    else { drawPanel(); if (!quiet) showHlBar(h); }
    return h;
  } catch(err){ toast(err.message); }
}
function showHlBar(h){
  const ms = $$('mark.hl[data-h="' + CSS.escape(h.id) + '"], figure.hlimg[data-h="' + CSS.escape(h.id) + '"]'); if (!ms.length) return;
  const a = ms[0].getBoundingClientRect(), z = ms[ms.length - 1].getBoundingClientRect();
  const rect = { left: Math.min(a.left, z.left), right: Math.max(a.right, z.right), top: a.top, bottom: z.bottom }; rect.width = rect.right - rect.left;
  H.show(H.hlBar(h, { kindle: h.source === 'kindle' }), rect, { h });   // one from the Kindle is removed there
}
function openNoteA(h){
  H.hide(); R.panel = 'notebook'; openPanel(); drawPanel();
  setTimeout(() => { const row = $('.hrow[data-h="' + CSS.escape(h.id) + '"]'); if (!row) return; row.scrollIntoView({ block:'center' }); const n = row.querySelector('[data-hra="note"]'); if (n) n.click(); }, 40);
}
function showHl(id){
  const ms = $$('mark.hl[data-h="' + CSS.escape(id) + '"], figure.hlimg[data-h="' + CSS.escape(id) + '"]'); if (!ms.length) { toast('That highlight isn’t in this text any more'); return; }
  ms[0].scrollIntoView({ block:'center', behavior:'smooth' });
  ms.forEach(m => m.classList.add('flash')); setTimeout(() => ms.forEach(m => m.classList.remove('flash')), 1800);
}
// quiet: no Undo toast (the pen's eraser has its own Undo); either way it answers with the way back.
async function removeHl(id, quiet){
  const d = R.doc; if (!d) return null;
  const h = d.highlights.find(x => x.id === id);
  try { await api('/api/highlights/' + encodeURIComponent(id), { method:'DELETE' }); } catch(e){ toast(e.message); return null; }
  d.highlights = d.highlights.filter(x => x.id !== id);
  unmark(id); H.hide(); drawPanel(); drawToc();
  if (!h) return null;
  const back = async () => {
    await api('/api/highlights/' + encodeURIComponent(id) + '/restore', { method:'POST' });
    if (R.doc !== d) return;
    d.highlights.push(h); if (H.picture(h.text)) markImg(h); else markHl(h); drawPanel(); drawToc();
  };
  if (!quiet) H.undo('Highlight deleted', back);
  return back;
}
// What the highlight toolbar does in the reading view.
const ACT = {
  hl: ctx => ctx.img != null ? highlightImg(ctx.img) : highlight(ctx.info),
  note: ctx => ctx.h ? openNoteA(ctx.h) : ctx.img != null ? highlightImg(ctx.img, true) : highlight(ctx.info, true),
  define: ctx => { H.hide(); const el = $('#docbody [data-i="' + ctx.info.b + '"]'); C.lookup && C.lookup(ctx.info, el ? el.textContent : '', false); },
  translate: ctx => { H.hide(); const el = $('#docbody [data-i="' + ctx.info.b + '"]'); C.lookup && C.lookup(ctx.info, el ? el.textContent : '', true); },
  ask: ctx => { H.hide(); window.getSelection().removeAllRanges(); ask('What does this passage mean here?', ctx.h ? ctx.h.text : ctx.text); },
  rm: ctx => removeHl(ctx.h.id),
  notebook: ctx => { H.hide(); R.panel = 'notebook'; openPanel(); drawPanel(); setTimeout(() => H.flash($('.hrow[data-h="' + CSS.escape(ctx.h.id) + '"]')), 40); },
  changed: h => {
    $$('mark.hl[data-h="' + CSS.escape(h.id) + '"], figure.hlimg[data-h="' + CSS.escape(h.id) + '"]').forEach(m => { m.dataset.color = h.color || 'yellow'; m.classList.toggle('has-note', !!(h.user_note || '').trim()); });
    if (R.panel === 'notebook' && R.panelOpen && !document.activeElement.closest('.rpanel')) drawPanel();
  },
  deselect: () => window.getSelection().removeAllRanges(),
  meta: () => ({ title: R.doc && R.doc.title, author: R.doc && (R.doc.author || R.doc.source) }),
};
window.addEventListener('daf-hl-changed', e => { if (C.S.route[0] === 'read' && R.doc) { const h = R.doc.highlights.find(x => x.id === e.detail.id); if (h) { Object.assign(h, e.detail); ACT.changed(h); } } });

/* ---------- read aloud (Kokoro on the server) ---------- */
function ttsBlocks(){ const d = R.doc; return d ? d.blocks.map((b, i) => [b, i]).filter(x => x[0].t !== 'img' && x[0].t !== 'pg' && (x[0].x || '').trim()).map(x => x[1]) : []; }
function startTTS(){
  const d = R.doc; if (!d) return;
  const T = R.tts;
  if (!T.audio) { T.audio = new Audio(); T.audio.addEventListener('ended', () => { if (T.playing) nextTTS(1); }); T.audio.addEventListener('error', () => { if (T.playing) { toast('Kokoro didn’t answer for that paragraph; skipping'); nextTTS(1); } }); }
  T.on = true; T.doc = d.id; T.title = d.title; T.blocks = ttsBlocks(); T.i = Math.max(0, T.blocks.indexOf(R.focus)); T.playing = true;
  if (!C.Voices.cur) C.Voices.load().then(() => { if (T.on) drawPlayer(); });
  playTTS();
}
// The paragraph's speech in the chosen voice (the voice is in the address, so a cached one in another voice isn't used).
const ttsUrl = b => '/api/tts?doc=' + encodeURIComponent(R.tts.doc) + '&b=' + b + (C.Voices.cur ? '&voice=' + encodeURIComponent(C.Voices.cur) : '');
// Another voice chosen while it reads: the paragraph starts again in it.
window.addEventListener('daf-voice', () => { const T = R.tts; if (!T.on) return; if (T.playing) playTTS(); else { if (T.audio) T.audio.removeAttribute('src'); drawPlayer(); } });
function playTTS(){
  const T = R.tts; const b = T.blocks[T.i]; if (b == null) { T.playing = false; drawPlayer(); return; }
  T.audio.src = ttsUrl(b); T.audio.playbackRate = T.rate || 1;
  T.audio.play().catch(() => {});
  if (T.unfollow) T.unfollow();
  const sp = $('#docbody [data-i="' + b + '"]'); T.unfollow = sp && R.doc && R.doc.id === T.doc ? H.follow(T.audio, sp, { scroll: true }) : null;
  const nb = T.blocks[T.i + 1]; if (nb != null) fetch(ttsUrl(nb), { credentials:'same-origin' }).catch(() => {});
  markSpeaking(); drawPlayer(); if (R.doc && R.doc.id === T.doc) drawReaderTop();
}
function nextTTS(dir){ const T = R.tts; T.i = Math.max(0, Math.min(T.blocks.length, T.i + dir)); if (T.i >= T.blocks.length) { T.playing = false; drawPlayer(); markSpeaking(); return; } playTTS(); }
function pauseTTS(){ const T = R.tts; T.playing = false; if (T.audio) T.audio.pause(); drawPlayer(); markSpeaking(); if (R.doc) drawReaderTop(); }
function resumeTTS(){ const T = R.tts; T.playing = true; if (T.audio && T.audio.src) T.audio.play().catch(() => {}); else playTTS(); drawPlayer(); if (R.doc) drawReaderTop(); }
function stopTTS(){ const T = R.tts; if (!T.on) return; T.on = false; T.playing = false; if (T.unfollow) { T.unfollow(); T.unfollow = null; } if (T.audio) { T.audio.pause(); T.audio.removeAttribute('src'); } drawPlayer(); markSpeaking(); }
function markSpeaking(){
  $$('#docbody .speaking').forEach(el => el.classList.remove('speaking'));
  const T = R.tts; if (!T.on || !R.doc || R.doc.id !== T.doc) return;
  const el = $('#docbody [data-i="' + T.blocks[T.i] + '"]');
  if (el) { el.classList.add('speaking'); if (T.playing) { const r = el.getBoundingClientRect(); if (r.top < 80 || r.bottom > window.innerHeight - 100) el.scrollIntoView({ block:'center', behavior:'smooth' }); } }
}
function drawPlayer(){
  const p = $('#player'), T = R.tts;
  if (!T.on) { p.hidden = true; document.body.classList.remove('playing'); return; }
  p.hidden = false; document.body.classList.add('playing');
  p.innerHTML = '<div class="pt"><b>' + esc(shortTitle(T.title)) + '</b><span class="mute">Read aloud by Kokoro on the server · ¶ ' + Math.min(T.i + 1, T.blocks.length) + ' of ' + T.blocks.length + '</span></div>' +
    '<button class="btn sm" data-tts="prev" aria-label="Previous paragraph">‹ ¶</button><button class="round" data-tts="play" aria-label="' + (T.playing ? 'Pause' : 'Play') + '">' + (T.playing ? ICON.pause : ICON.play) + '</button><button class="btn sm" data-tts="next" aria-label="Next paragraph">¶ ›</button>' +
    '<button class="btn sm" data-tts="rate">' + (T.rate || 1) + '×</button><button class="btn sm" data-tts="voice" aria-label="Voice: ' + esc(C.Voices.cur ? C.Voices.label(C.Voices.cur) : 'choose one') + '">' + esc(C.Voices.cur ? C.Voices.name(C.Voices.cur) : 'Voice') + '</button>' + (R.doc && R.doc.id !== T.doc ? '<a class="btn sm" href="#read/' + encodeURIComponent(T.doc) + '">Back to it</a>' : '') + '<button class="ib" data-tts="close" aria-label="Close">' + ICON.close + '</button>';
}

/* ---------- reading time ---------- */
// Beats made offline wait in localStorage and go with their own time when the network is back.
// They go through app.js's outbox now, with the others (each with its own id, so none counts twice).
function sendBeat(b){ api('/api/read/beat', { method:'POST', body:JSON.stringify(b) }).catch(() => {}); }
// Beats kept by the older queue (daf.beatq) join the outbox once.
(() => { const q = store.get('beatq', []); if (q.length && C.outbox) { q.forEach(b => C.outbox.add('/api/read/beat', { method: 'POST', body: JSON.stringify(b) })); store.set('beatq', []); } })();
// Keep the Library's Inbox and Later readable offline: fetch their text quietly, a few at a time.
const prefetched = new Set();
function prefetchDocs(items){
  if (!navigator.onLine || !('serviceWorker' in navigator)) return;
  const todo = items.filter(d => (d.kind === 'article' || d.kind === 'tweet') && !prefetched.has(d.id)).slice(0, 30);
  let i = 0;
  const next = () => { const d = todo[i++]; if (!d) return; prefetched.add(d.id);
    fetch('/api/docs/' + encodeURIComponent(d.id) + '?prefetch=1', { credentials:'same-origin' }).catch(() => {}).finally(() => setTimeout(next, 400)); };
  setTimeout(next, 1500);
}
setInterval(() => {
  const T = R.tts, viewing = C.S.route[0] === 'read' && R.doc && !document.hidden && (Date.now() - R.lastActive < 90000 || (R.doc.kind === 'video' && V.playing));
  const id = T.on && T.playing ? T.doc : viewing ? R.doc.id : null;
  if (id) sendBeat({ doc_id:id, seconds:15, at:Math.floor(Date.now() / 1000) });
  const c = $('#counting'); if (c) c.classList.toggle('off', !id);
}, 15000);
['mousemove', 'keydown', 'touchstart', 'wheel'].forEach(ev => document.addEventListener(ev, () => { R.lastActive = Date.now(); }, { passive:true }));

/* ---------- Aa ---------- */
// The Aa menu, shared by articles and books (opts.book adds the book-only rows).
const TYPEFACES = [['serif', 'Source Serif', "'Source Serif 4'"], ['literata', 'Literata', "'Literata'"], ['frank', 'Frank Ruhl Libre', "'Frank Ruhl Libre'"],
  ['atkinson', 'Atkinson Hyperlegible', "'Atkinson Hyperlegible'"], ['sans', 'Figtree', "'Figtree'"]];
// A book can keep its own settings (BookOrbit does this): typeface, size, spacing, width, layout,
// justification. The theme stays the app's.
const ownKey = () => { const id = R.aaBook && C.curBook && C.curBook(); return id ? 'bookType.' + id : null; };
C.typeFor = id => { const g = store.get('type', {}), o = id ? store.get('bookType.' + id, null) : null; return o ? Object.assign({}, g, o, { theme: g.theme }) : g; };
function openAa(anchor, opts){
  opts = opts || (C.S.route[0] === 'ebook' ? { book: true } : {});
  R.aaBook = !!opts.book;
  const own = ownKey() && store.get(ownKey(), null);
  const p = $('#pop'), r = anchor.getBoundingClientRect(), t = own ? C.typeFor(C.curBook()) : store.get('type', {});
  const seg = (k, list, cur) => '<div class="seg">' + list.map(o => '<button class="' + ((cur || list[0][0]) === o[0] ? 'on' : '') + '" data-type="' + k + '" data-v="' + o[0] + '">' + o[1] + '</button>').join('') + '</div>';
  const step = (k, label, val, d, fmt) => '<div class="stepper"><span>' + label + '</span><div><button class="btn sm" data-type="' + k + '" data-v="-' + d + '" aria-label="Less">−</button><span class="num">' + fmt(val) + '</span><button class="btn sm" data-type="' + k + '" data-v="' + d + '" aria-label="More">+</button></div></div>';
  const faces = (C.Themes ? C.Themes.faces() : TYPEFACES).concat(opts.book ? [['book', 'The book’s own', 'inherit', 'This book']] : []);
  const cur = t.font || 'serif';
  let lastGroup = null;
  const faceBtn = f => (f[3] && f[3] !== lastGroup ? '<span class="facegrp">' + esc(lastGroup = f[3]) + '</span>' : '') +
    '<button class="face' + (cur === f[0] ? ' on' : '') + '" data-type="font" data-v="' + esc(f[0]) + '" style="font-family:' + f[2].replace(/"/g, '') + ',serif">' + esc(f[1]) + '<i></i></button>';
  const TH = C.Themes, th = TH ? TH.get() : { mode: 'system' }, fam = TH ? (TH.FAMILIES.find(f => f.id === (TH.isDark() ? th.dark : th.light)) || {}).name : '';
  p.innerHTML = '<span class="lbl">Theme · ' + esc(fam || '') + ' <a class="aamore" href="#prefs/appearance">More themes</a></span>' + seg('thmode', [['system', 'Auto'], ['light', 'Light'], ['dark', 'Dark']], th.mode) +
    '<span class="lbl">Typeface</span><div class="faces">' + faces.map(faceBtn).join('') + '</div>' +
    step('size', 'Font size', t.size || 20, 1, v => v + 'px') +
    step('spacing', 'Line spacing', t.spacing || 1.6, 1, v => v.toFixed(1)) +
    step('measure', 'Line width', t.measure || 38, 3, v => v <= 32 ? 'Narrow' : v >= 44 ? 'Wide' : 'Medium') +
    (opts.book ? '<span class="lbl">Layout</span>' + seg('flow', [['scrolled', 'Scroll'], ['paginated', 'Pages']], t.flow || 'scrolled') +
      '<label class="aaline"><input type="checkbox" data-type="justify"' + (t.justify ? ' checked' : '') + '> Justify the text</label>' +
      '<label class="aaline"><input type="checkbox" data-type="own"' + (own ? ' checked' : '') + '> Just for this book</label>' : '');
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 300, r.left)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
}

/* ---------- ⌘K ---------- */
let palItems = [], palIdx = 0, palT = null;
function openPalette(){
  const p = $('#palette'); $('#scrim').hidden = false; p.hidden = false;
  p.innerHTML = '<input id="palq" placeholder="Search articles, books, highlights and the vault, or go somewhere" aria-label="Search" autocomplete="off"><div class="pres" id="pres"></div>';
  $('#palq').focus(); palResults('');
}
async function palResults(q){
  const cmds = [['Today', '#today'], ['Daily review', '#review'], ['All feeds', '#feed'], ['Articles', '#library/article'], ['Videos', '#library/video'], ['Books', '#books'], ['Highlights', '#highlights'], ['Preferences', '#prefs'],
    ['Import from another app', '#prefs/import'], ['Keyboard shortcuts', '#prefs/keys'], ['AI settings', '#prefs/ai'], ['Morning email', '#prefs/digest'], ['Library tags', '#prefs/tags'], ['Tips', '#prefs/tips']]
    .filter(c => !q || c[0].toLowerCase().includes(q.toLowerCase()));
  palItems = cmds.map(c => ({ label:c[0], sub:'Go to', go:c[1] }));
  [['Send feedback', () => C.Feedback && C.Feedback.open()], ['What’s new', () => C.Tips && C.Tips.news()], ['Undo', undoLast], ['Add a link, a book or a PDF', () => openAdd()]]
    .filter(c => !q || c[0].toLowerCase().includes(q.toLowerCase()) || (c[0] === 'Send feedback' && /bug|idea|report|problem/i.test(q)))
    .forEach(c => palItems.push({ label:c[0], sub:'Do', run:c[1] }));
  if (q.trim().length >= 2) {
    try {
      const r = await api('/api/search?q=' + encodeURIComponent(q));
      if (($('#palq') || {}).value !== q) return;
      r.docs.forEach(d => palItems.push({ label:d.title, sub:(d.where_ === 'feed' ? 'Feed' : 'Library') + ' · ' + (d.source || ''), go:'#read/' + encodeURIComponent(d.id), rtl:rtl(d.title) }));
      (r.text || []).forEach(d => palItems.push({ label:d.title, snip:d.snip, sub:'In the text · ' + (d.where_ === 'feed' ? 'Feed' : 'Library') + (d.source ? ' · ' + d.source : ''), go:'#read/' + encodeURIComponent(d.id) + '/q:' + encodeURIComponent(q.trim()), rtl:rtl(d.title) }));
      r.books.forEach(b => palItems.push({ label:b.title, sub:'Book · ' + (b.author || ''), go:'#book/' + encodeURIComponent(b.id) }));
      r.highlights.forEach(h => palItems.push({ label:H.picture(h.text) ? 'A picture' + (H.picture(h.text).alt ? ': ' + H.picture(h.text).alt : '') : h.text, sub:'Highlight · ' + shortTitle(h.title || ''), go:(h.book_id || '').startsWith('cal:') ? '#book/' + encodeURIComponent(h.book_id) : '#read/' + encodeURIComponent(h.book_id), serif:true, rtl:rtl(h.text) }));
      (r.vault || []).forEach(v => palItems.push({ label:v.title, sub:'Vault · ' + (v.folder || '/') + (v.snippet ? ' · ' + v.snippet : ''), href:v.open, rtl:rtl(v.title) }));
    } catch(e){}
  }
  palIdx = 0;
  const pres = $('#pres'); if (!pres) return;
  pres.innerHTML = palItems.length ? palItems.map((x, i) => '<button class="pi' + (i === 0 ? ' on' : '') + '" data-pi="' + i + '">' + (x.snip ? '<span class="pcol">' : '') + '<span class="pl"' + (x.rtl ? ' dir="rtl"' : '') + (x.serif ? ' style="font-family:var(--serif)"' : '') + '>' + esc(x.label) + '</span>' +
    (x.snip ? '<span class="psnip">' + esc(x.snip).replace(/\u0002/g, '<mark>').replace(/\u0003/g, '</mark>') + '</span></span>' : '') + '<span class="s">' + esc(x.sub) + '</span></button>').join('') : '<div class="empty" style="margin:20px auto"><b>Nothing matches</b></div>';
}
function closePalette(){ $('#palette').hidden = true; if ($('#modal').hidden) $('#scrim').hidden = true; }
function palGo(i){ const x = palItems[i]; closePalette(); if (!x) return; if (x.run) { x.run(); return; } if (x.href) { location.href = x.href; return; } location.hash = x.go.slice(1); }

/* ---------- views ---------- */
C.sendBeat = sendBeat; C.openAa = openAa;
C.Reader = { getSel, highlight, removeHl, moved: movedToLibrary };   // for the pen (ink.js)
C.views.podcasts = async () => {
  R.doc = null;
  $('#main').innerHTML = '<div class="top"><h1>Podcasts</h1><span class="spacer"></span><span class="mute tiny">From AntennaPod · never counted toward the hour</span></div><div class="page" id="podpage"><span class="mute">Loading…</span></div>';
  const p = await api('/api/podcasts');
  let h = '';
  if (!p.subs.length) h += '<section class="card"><h2>AntennaPod isn’t syncing yet</h2><p class="mute" style="margin:0">Set it up in Preferences → Podcasts. Then share any episode from AntennaPod to Ezer with its position, and Daf transcribes the minute before it into a highlight.</p><a class="btn" href="#prefs" style="align-self:flex-start">Preferences</a></section>';
  h += '<section class="card"><div class="cardh"><h2>Clips</h2><span class="mute tiny">' + p.clips.length + '</span></div>' + (p.clips.length ? p.clips.map(c => { const pos = (() => { try { return JSON.parse(c.pos).t; } catch(e){ return null; } })(); return '<div class="hlc"><q>' + esc(c.text) + '</q><div class="meta tiny mute">' + esc(c.title || '') + (c.author ? ' · ' + esc(c.author) : '') + (pos != null ? ' · ' + fmtT(pos) : '') + ' · ' + epochDate(c.created) + '</div></div>'; }).join('') : '<p class="mute" style="margin:0">None yet. In AntennaPod: Share → “with position” → Signal → Ezer.</p>') + '</section>';
  if (p.recent.length) h += '<section class="card"><h2>Listened lately</h2>' + p.recent.map(r => '<div class="nrow"><b>' + esc(r.title || 'Podcast') + '</b><span class="mute tiny">' + esc(r.author || '') + ' · ' + Math.round(r.seconds / 60) + ' min · ' + epochDate(r.start) + '</span></div>').join('') + '</section>';
  if (p.subs.length) h += '<section class="card"><h2>Subscriptions</h2>' + p.subs.map(x => '<div class="nrow"><b>' + esc(x.title || x.url) + '</b></div>').join('') + '<span class="mute tiny">Last sync ' + ago(p.last_sync) + '</span></section>';
  $('#podpage').innerHTML = h;
};
C.views.feed = args => { R.doc = null; R.view = null; R.tag = null; return listView('feed', args[0] ? decodeURIComponent(args[0]) : null); };   // a Library tag doesn't follow into the Feed
C.views.library = args => { R.doc = null; R.view = null; R.tag = null; return args[0] ? listView('library', args[0]) : homeView(); };
// A saved view: a list with its tab, tag and order, kept in settings so every device has it.
C.views.view = async args => {
  R.doc = null;
  if (!R.views) await loadViews();
  const v = (R.views || []).find(x => x.id === decodeURIComponent(args[0] || ''));
  if (!v) { location.hash = 'library'; return; }
  R.view = Object.assign({}, v, { filter: Object.assign({}, v.filter || {}) }); R.viewDirty = false; R.tag = v.tag || null;
  if (v.tab) R.tabs[v.where === 'feed' ? 'feed' : 'library'] = v.tab;
  return listView(v.where, v.arg || null);
};
async function loadViews(){ try { R.views = (await api('/api/views')).views; } catch(e){ R.views = []; } C.renderSide(); }
async function saveViews(list){ R.views = (await api('/api/views', { method:'PUT', body:JSON.stringify({ views:list }) })).views; C.renderSide(); }
loadViews();

/* ---------- the Library home: shelves of cards ---------- */
const SHELVES = [['continue', 'Continue reading', 'Books and articles you’re partway through'], ['recent', 'Recently added', 'Saved in the past week, not archived'],
  ['quick', 'Quick reads', 'Ten minutes or less'], ['long', 'Long reads', 'Half an hour or more'], ['highlighted', 'Recently highlighted', 'Highlighted in the past three weeks'], ['feed', 'New in the Feed', 'Unseen, newest first']];
function ringSVG(p){ const r = 7, c = 2 * Math.PI * r, f = Math.max(0, Math.min(1, (p || 0) / 100)); return '<svg class="mring" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="' + r + '" fill="none" stroke="var(--active)" stroke-width="2.5"/><circle cx="9" cy="9" r="' + r + '" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-dasharray="' + (c * f).toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 9 9)" stroke-linecap="round"/></svg>'; }
function homeCard(c){
  const t = c.kind === 'tweet' ? tweetParts(c) : { title: c.title };
  const img = c.type === 'book' ? (c.has_cover ? '<img src="/api/cover/' + encodeURIComponent(c.id) + '" alt="" loading="lazy">' : '<span class="htile" style="background:hsl(' + hue(c.title) + ' 32% 42%)">' + esc(shortTitle(c.title)) + '</span>')
    : c.thumb ? '<img src="' + esc(c.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement(\'span\'), { className: \'htile\', textContent: this.alt }))">'
    : '<span class="htile" style="background:hsl(' + hue(c.source || c.title) + ' 28% 45%)">' + esc((c.source || '').slice(0, 24)) + '</span>';
  const kind = c.type === 'book' ? 'Book' : (KIND[c.kind] || 'Article').replace(/s$/, '');
  return '<a class="hcard' + (c.type === 'book' ? ' book' : '') + '" href="' + esc(c.href) + '"><span class="himg">' + img + '</span>' +
    '<span class="hk">' + esc(c.type === 'book' ? 'Book' : (c.source || kind)) + '</span><b' + dirAttr(t.title) + '>' + esc(c.type === 'book' ? shortTitle(t.title) : t.title) + '</b>' +
    '<span class="hm"><span class="mute">' + esc(c.author || '') + '</span><span class="spacer"></span>' + (c.highlights ? '<span class="mute">' + c.highlights + ' hl</span> ' : '') +
    (c.progress ? ringSVG(c.progress) : '') + '<span class="mute">' + (c.mins ? c.mins + ' min' : c.progress ? Math.round(c.progress) + '%' : '') + '</span></span></a>';
}
async function homeView(){
  $('#main').innerHTML = '<div class="top"><h1>Home</h1><span class="spacer"></span><button class="btn sm" data-home="config">Configure</button></div><div class="page home" id="homepage"><span class="mute">Loading…</span></div>';
  const h = await C.swr('/api/home');
  const hidden = store.get('homeHidden', []);
  const html = SHELVES.filter(s => !hidden.includes(s[0]) && (h[s[0]] || []).length).map(s =>
    '<section class="shelf"><div class="shelfh"><h2>' + s[1] + '</h2><span class="mute tiny">' + s[2] + '</span></div><div class="shelfrow">' + h[s[0]].map(homeCard).join('') + '</div></section>').join('');
  $('#homepage').innerHTML = html || '<p class="mute">Nothing here yet. Save something to the Library, or open a book.</p>';
}
function homeConfig(anchor){
  const hidden = store.get('homeHidden', []), p = $('#pop'), r = anchor.getBoundingClientRect();
  p.innerHTML = '<span class="lbl">Show on Home</span>' + SHELVES.map(s => '<label class="aaline"><input type="checkbox" data-shelf="' + s[0] + '"' + (hidden.includes(s[0]) ? '' : ' checked') + '> ' + s[1] + '</label>').join('');
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 300, r.right - 280)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
}
document.addEventListener('click', e => {
  const hc = e.target.closest('[data-home]'); if (hc) { homeConfig(hc); return; }
  const sh = e.target.closest('[data-shelf]');
  if (sh) { const hidden = new Set(store.get('homeHidden', [])); sh.checked ? hidden.delete(sh.dataset.shelf) : hidden.add(sh.dataset.shelf); store.set('homeHidden', [...hidden]); homeView(); }
});
// Opened from a full-text search: the first place the words appear, marked for a moment.
function findInDoc(q){
  const body = $('#docbody'); if (!body || !q) return;
  const words = q.toLowerCase().split(/\s+/).filter(Boolean); if (!words.length) return;
  const w = words.slice().sort((a, b) => b.length - a.length)[0];
  const walk = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    const i = n.data.toLowerCase().indexOf(w);
    if (i < 0) continue;
    const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + w.length);
    const m = document.createElement('mark'); m.className = 'findmark';
    try { r.surroundContents(m); } catch(e){ return; }
    m.scrollIntoView({ block: 'center' });
    setTimeout(() => { const t = document.createTextNode(m.textContent); m.replaceWith(t); t.parentNode && t.parentNode.normalize(); }, 4000);
    return;
  }
}
C.views.read = args => {
  H.active = ACT;
  const last = args[args.length - 1] || '';
  if (last.startsWith('q:') && args.length > 1) {
    const id = decodeURIComponent(args.slice(0, -1).join('/')), q = decodeURIComponent(last.slice(2));
    if (R.doc && R.doc.id === id && $('#docbody')) { findInDoc(q); return; }
    return readView(id).then(() => setTimeout(() => findInDoc(q), 200));
  }
  if (last.startsWith('hl:') && args.length > 1) {
    const id = decodeURIComponent(args.slice(0, -1).join('/')), hid = decodeURIComponent(last.slice(3));
    if (R.doc && R.doc.id === id && $('#docbody')) { showHl(hid); return; }
    return readView(id).then(() => setTimeout(() => showHl(hid), 150));
  }
  return readView(decodeURIComponent(args.join('/')));
};

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target;
  const pop = $('#pop');
  if (!pop.hidden && C.S.popAtClick != null && pop.innerHTML === C.S.popAtClick && !t.closest('#pop') && !t.closest('[data-ract="aa"]')) pop.hidden = true;
  const tab = t.closest('[data-tab]'); if (tab) { const key = R.list && R.list.where === 'feed' ? 'feed' : 'library'; R.tabs[key] = tab.dataset.tab; R.sel = null; listView(R.list.where, R.list.arg); return; }
  const da = t.closest('[data-dact]'); if (da) { e.stopPropagation(); docAct(da.dataset.dact, da.dataset.id); return; }
  const bk = t.closest('[data-bulk]'); if (bk) { bulkAct(bk.dataset.bulk); return; }
  const fu = t.closest('[data-funset]');
  if (fu) { const k = fu.dataset.funset; setFilter(k === 'len' ? { minlen: 0, maxlen: 0 } : { [k]: 0 }); return; }
  const pk = t.closest('[data-pick]'); if (pk) { e.preventDefault(); pick(pk.dataset.pick); return; }
  const row = t.closest('.row[data-doc]');
  if (row && !t.closest('.hov') && (e.metaKey || e.ctrlKey || e.shiftKey || R.selecting || R.multi.size)) {
    e.preventDefault();
    const id = row.dataset.doc;
    if (e.shiftKey && (R.anchor || R.sel)) {
      const xs = visibleItems().map(d => d.id), a = xs.indexOf(R.anchor || R.sel), b = xs.indexOf(id);
      if (a >= 0 && b >= 0) { xs.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(x => R.multi.add(x)); R.anchor = id; drawRows(); return; }
    }
    pick(id); return;
  }
  if (row && !t.closest('.hov')) { location.hash = 'read/' + encodeURIComponent(row.dataset.doc); return; }
  const ra = t.closest('[data-ract]');
  if (ra) {
    const a = ra.dataset.ract;
    if (a === 'lfilter') { openFilter(ra); return; }
    if (a === 'updview' && R.view) {
      const v = R.view;
      saveViews((R.views || []).map(x => x.id === v.id ? Object.assign({}, x, { filter: v.filter || {}, sort: v.sort || x.sort }) : x)).then(() => { R.viewDirty = false; toast('View saved'); drawFChips(); }).catch(err => toast(err.message));
      return;
    }
    if (a === 'saveview') {
      const L = R.list; if (!L) return;
      const key = L.where === 'feed' ? 'feed' : 'library', tab = R.tabs[key], sort = store.get('sort.' + key, 'new');
      const base = L.where === 'feed' ? (L.arg || 'Feed') : L.arg === KIND_STAR ? 'Shortlist' : KIND[L.arg] || 'Library';
      const name = prompt('Name this view', base + (R.tag ? ' · ' + R.tag : '') + (tab && tab !== 'inbox' && tab !== 'unseen' ? ' · ' + tab : ''));
      if (!name || !name.trim()) return;
      const id = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 20) + '-' + Date.now().toString(36).slice(-3);
      saveViews((R.views || []).concat([{ id, name: name.trim(), where: L.where, arg: L.arg || '', tab, tag: R.tag || '', sort, filter: Object.assign({}, curFilter()) }])).then(() => { toast('Saved in the sidebar'); location.hash = 'view/' + encodeURIComponent(id); }).catch(err => toast(err.message));
      return;
    }
    if (a === 'rmview' && R.view) {
      const v = R.view;
      if (!confirm('Remove the view “' + v.name + '”? The documents stay where they are.')) return;
      saveViews((R.views || []).filter(x => x.id !== v.id)).then(() => { R.view = null; toast('View removed'); location.hash = v.where === 'feed' ? 'feed' : 'library/' + (v.arg || 'article'); }).catch(err => toast(err.message));
      return;
    }
    if (a === 'selmode') { R.selecting = !R.selecting; if (!R.selecting) R.multi.clear(); ra.classList.toggle('on', R.selecting); ra.textContent = R.selecting ? 'Done' : 'Select'; drawRows(); return; }
    if (a === 'back') { stopSel(); leaveDoc(R.doc); }
    else if (a === 'prevdoc' || a === 'nextdoc') { const nb = R.doc && neighbor(R.doc.id, a === 'nextdoc' ? 1 : -1); if (nb) location.hash = 'read/' + encodeURIComponent(nb.id); }
    else if (a === 'aa') openAa(ra);
    else if (a === 'panel') { R.panelOpen = !R.panelOpen; const g = $('.rvgrid'); if (g) g.classList.toggle('withpanel', R.panelOpen); drawReaderTop(); }
    else if (a === 'listen') { const T = R.tts; if (T.on && T.doc === R.doc.id) { T.playing ? pauseTTS() : resumeTTS(); } else startTTS(); }
    else if (a === 'more') openMore(ra);
    else if (a === 'lmore') openListMore(ra);
    else if (a === 'full' && R.doc) loadFull(R.doc.id, ra);
    else if (a === 'sources') openSources();
    return;
  }
  const mo = t.closest('[data-more]'); if (mo) { moreAct(mo.dataset.more); return; }
  const lm = t.closest('[data-lm]'); if (lm) { listMoreAct(lm.dataset.lm); return; }
  const sg = t.closest('[data-src]'); if (sg) { C.closeModal(); const v = sg.dataset.src; R.view = null; location.hash = v ? 'feed/' + encodeURIComponent(v) : 'feed'; return; }
  const sf = t.closest('[data-srcfold]');
  if (sf) { const o = store.get('srcOpen', {}), box = sf.closest('.sfold'), on = !box.classList.contains('open'); o[sf.dataset.srcfold] = on; store.set('srcOpen', o); box.classList.toggle('open', on); sf.setAttribute('aria-expanded', on); return; }
  const se = t.closest('[data-srcedit]'); if (se) { openFeedEdit(se.dataset.srcedit); return; }
  const fe = t.closest('[data-fe]'); if (fe) { feedEditAct(fe.dataset.fe, fe.dataset.id); return; }
  const ty = t.closest('[data-type]');
  if (ty) {
    const k = ty.dataset.type, v = ty.dataset.v, ok = ownKey();
    if (k === 'thmode' && C.Themes) { C.Themes.set({ mode: v }); openAa($('[data-ract="aa"]') || $('[data-bk="aa"]') || ty, { book: R.aaBook }); return; }
    if (k === 'own' && ok) {
      if (ty.checked) store.set(ok, Object.assign({}, store.get('type', {}), { theme: undefined }));
      else { try { localStorage.removeItem('daf.' + ok); } catch(e){} }
      applyType(); openAa($('[data-bk="aa"]') || ty, { book: true }); return;
    }
    const key = ok && store.get(ok, null) && k !== 'theme' ? ok : 'type';
    const tp = key === 'type' ? store.get('type', {}) : C.typeFor(C.curBook());
    if (k === 'size') tp.size = Math.max(14, Math.min(32, (tp.size || 20) + (+v)));
    else if (k === 'measure') tp.measure = Math.max(26, Math.min(56, (tp.measure || 38) + (+v)));
    else if (k === 'spacing') tp.spacing = Math.round(Math.max(1.2, Math.min(2.2, (tp.spacing || 1.6) + (+v) / 10)) * 10) / 10;
    else if (k === 'justify') tp.justify = ty.checked;
    else tp[k] = v;
    if (key !== 'type') delete tp.theme;
    store.set(key, tp); applyType(); openAa($('[data-ract="aa"]') || $('[data-bk="aa"]') || ty, { book: R.aaBook }); return;
  }
  const pt = t.closest('[data-ptab]'); if (pt) { R.panel = pt.dataset.ptab; drawPanel(); return; }
  const sm = t.closest('[data-summ]');
  if (sm) {
    const id = sm.dataset.summ; sm.disabled = true; sm.textContent = 'Summarizing… (about 15 seconds)';
    api('/api/docs/' + encodeURIComponent(id) + '/summary', { method:'POST' }).then(r => {
      for (const d of [R.doc, ...(R.list ? R.list.items : [])]) if (d && d.id === id) d.ai_summary = r.ai_summary;
      if (C.S.route[0] === 'read') drawPanel(); else drawRows();
    }).catch(err => { toast(err.message); sm.disabled = false; sm.textContent = 'Summarize'; });
    return;
  }
  const de = t.closest('[data-dtagedit]');
  if (de) { tagDoc(de.dataset.dtagedit, de); return; }
  const dt = t.closest('[data-dtag]'); if (dt) { R.tag = dt.dataset.dtag || null; if (C.S.route[0] === 'library' && R.list) drawRows(); else { location.hash = 'library/article'; } return; }
  const jp = t.closest('[data-jump]'); if (jp) { const fig = $('#docbody figure[data-img="' + (+jp.dataset.jump) + '"]'); if (fig) fig.scrollIntoView({ block:'center', behavior:'smooth' }); else setFocus(+jp.dataset.jump, true); return; }   // a picture isn't a paragraph to focus
  const aq = t.closest('[data-askq]'); if (aq) { ask(aq.dataset.askq); return; }
  const tt = t.closest('[data-tts]');
  if (tt) { const a = tt.dataset.tts, T = R.tts; if (a === 'play') T.playing ? pauseTTS() : resumeTTS(); else if (a === 'next') nextTTS(1); else if (a === 'prev') nextTTS(-1); else if (a === 'close') stopTTS(); else if (a === 'voice') C.Voices.menu(tt); else if (a === 'rate') { T.rate = (T.rate || 1) >= 2 ? 1 : (T.rate || 1) + 0.25; if (T.audio) T.audio.playbackRate = T.rate; drawPlayer(); } return; }
  const tl = t.closest('[data-tlang]'); if (tl) { setTL(tl.dataset.tlang); return; }
  if (t.closest('[data-tlcycle]')) { const order = ['both', 'he', 'en'], cur = store.get('torahLang', 'both'); setTL(order[(order.indexOf(cur) + 1) % 3]); return; }
  const sk = t.closest('[data-seek]'); if (sk) { seek(+sk.dataset.seek); return; }
  const vc = t.closest('[data-vclip]'); if (vc) { clipVideo(+vc.dataset.vclip); return; }
  const tr = t.closest('[data-tr]');
  if (tr && R.doc) { const d = R.doc; api('/api/docs/' + encodeURIComponent(d.id) + '/transcript', { method:'POST', body:JSON.stringify({ whisper: tr.dataset.tr === 'whisper' }) }).then(() => { $('#trstatus').innerHTML = 'Working on it on the server' + (tr.dataset.tr === 'whisper' ? ' (whisper takes a while for a long video)' : '') + '. This page fills in when it’s ready.'; pollTranscript(d.id); }).catch(err => toast(err.message)); return; }
  const pi = t.closest('[data-pi]'); if (pi) { palGo(+pi.dataset.pi); return; }
  const act = t.closest('[data-act]');
  if (act && act.dataset.act === 'palette') { openPalette(); return; }
  if (act && act.dataset.act === 'add') { $('#side').classList.remove('open'); openAdd(); return; }
  if (act && act.dataset.act === 'cats') { store.set('catsOpen', !store.get('catsOpen', true)); C.renderSide(); return; }
  if (act && act.dataset.act === 'expirefr') { act.disabled = true; api('/api/feed/expire', { method:'POST' }).then(() => { toast('Marked read in FreshRSS'); refreshCounts(); listView(R.list.where, R.list.arg); }).catch(err => { toast(err.message); act.disabled = false; }); return; }
  const mk = t.closest('mark.hl');
  if (mk && !getSel() && R.doc) { const h = R.doc.highlights.find(x => x.id === mk.dataset.h); if (h) { showHlBar(h); return; } }
  const fig = R.doc && C.S.route[0] === 'read' && t.closest('#docbody figure[data-img]');
  if (fig && !getSel() && !t.closest('a')) { pickImg(fig); return; }
  if (!t.closest('#selbar') && !t.closest('#pop')) { stopSel(); if (R.imgSel != null) { R.imgSel = null; $$('#docbody figure.picked').forEach(x => x.classList.remove('picked')); } }
  const blk = t.closest('#docbody [data-i]'); if (blk && !getSel() && !t.closest('a')) setFocus(+blk.dataset.i, false);
});
// Selecting a passage highlights it at once (auto highlight, as in Readwise); one word gets Define
// instead, and holding Alt selects without highlighting.
document.addEventListener('mouseup', e => {
  if (C.S.route[0] !== 'read' || e.target.closest('#selbar') || e.target.closest('#pop') || e.target.closest('button') || e.target.closest('.rpanel') || e.target.closest('.toc')) return;
  setTimeout(() => {
    const info = getSel(); if (!info) return;
    if (H.auto() && /\s/.test(info.text) && !e.altKey) { highlight(info); return; }
    H.show(H.selBar({ text: info.text }), info.rect, { kind:'sel', text: info.text, info });
  }, 10);
});
document.addEventListener('touchend', e => {
  if (C.S.route[0] !== 'read' || e.target.closest('#selbar') || e.target.closest('.rpanel')) return;
  setTimeout(() => { const info = getSel(); if (info) H.show(H.selBar({ text: info.text }), info.rect, { kind:'sel', text: info.text, info }); }, 400);
});
// Phones: dragging the handles changes the words with no touchend on the page, so the bar follows
// the selection itself; and when the page scrolls, a selection's bar goes with its words while a
// highlight's goes away.
let selT = null;
document.addEventListener('selectionchange', () => {
  if (C.S.route[0] !== 'read' || !H.touch()) return;
  clearTimeout(selT);
  selT = setTimeout(() => {
    const info = getSel();
    if (!info) { if (H.ctx && H.ctx.kind === 'sel') H.hide(); return; }
    if (H.visible() && H.ctx && H.ctx.kind === 'sel' && H.ctx.text === info.text) { H.place(info.rect); return; }
    H.show(H.selBar({ text: info.text }), info.rect, { kind:'sel', text: info.text, info });
  }, 500);
});
document.addEventListener('scroll', e => {
  if (C.S.route[0] !== 'read' || !H.visible() || Date.now() - (H.shownAt || 0) < 400) return;
  if (e.target.closest && e.target.closest('.rpanel, .toc, #pop, #selbar')) return;
  const info = H.ctx && H.ctx.kind === 'sel' ? getSel() : null;
  if (info) H.place(info.rect); else H.hide();
}, true);
let hoverT = null;
document.addEventListener('mouseover', e => {
  if (!['feed', 'library', 'view'].includes(C.S.route[0])) return;
  const r = e.target.closest('.row[data-doc]'); if (!r || r.dataset.doc === R.sel) return;
  clearTimeout(hoverT); hoverT = setTimeout(() => selectRow(r.dataset.doc), 90);
});
let noteT = {};
document.addEventListener('input', e => {
  const t = e.target;
  if (t.id === 'palq') { clearTimeout(palT); palT = setTimeout(() => palResults(t.value), 180); return; }
  if (t.id === 'docnote' && R.doc) { clearTimeout(noteT.doc); const d = R.doc; noteT.doc = setTimeout(() => api('/api/docs/' + encodeURIComponent(d.id) + '/note', { method:'PUT', body:JSON.stringify({ note:t.value }) }).then(() => toast('Saved to the vault note')).catch(err => toast(err.message)), 900); return; }
  if (t.dataset.note && R.doc && C.S.route[0] === 'read') {
    const id = t.dataset.note; const h = R.doc.highlights.find(x => x.id === id); if (h) h.user_note = t.value;
    const m = $$('mark[data-h="' + id + '"]'); m.forEach(x => x.classList.toggle('has-note', !!t.value.trim()));
    e.stopImmediatePropagation();
    clearTimeout(noteT[id]); noteT[id] = setTimeout(() => api('/api/highlights/' + encodeURIComponent(id) + '/note', { method:'PUT', body:JSON.stringify({ note:t.value }) }).then(() => toast('Note saved to the vault')).catch(err => toast(err.message)), 900);
  }
}, true);
function pollTranscript(id){
  setTimeout(async () => {
    if (!R.doc || R.doc.id !== id) return;
    try { const st = await api('/api/docs/' + encodeURIComponent(id) + '/transcript');
      if (st.ready || (st.page && ['done', 'failed'].includes(st.page.status) && !st.pdf) || (st.reel && ['done', 'failed'].includes(st.reel.status))) { readView(id); return; }
      const j = st.pdf || st.whisper || st.captions;
      if (j && j.status === 'failed') { $('#trstatus').innerHTML = 'That didn’t work: ' + esc(j.error || '') + ' <button class="btn sm" data-tr="whisper">Transcribe on the server instead</button>'; return; }
    } catch(e){}
    pollTranscript(id);
  }, 5000);
}
document.addEventListener('change', e => { if (e.target.id === 'vfollow') V.follow = e.target.checked;
  if (e.target.matches('[data-srchide]')) { store.set('srcHideEmpty', e.target.checked); if (R.sources && $('#srcs')) $('#srcs').innerHTML = sourcesHTML(R.sources); }
  if (e.target.id === 'fefolder') { const n = $('#fenew'); n.hidden = !e.target.selectedOptions[0].dataset.new; if (!n.hidden) n.focus(); } if (e.target.id === 'tagf') { R.tag = e.target.value || null; drawRows(); } if (e.target.id === 'lsort' && R.list) { if (R.view) { R.view.sort = e.target.value; R.viewDirty = true; } else store.set('sort.' + (R.list.where === 'feed' ? 'feed' : 'library'), e.target.value); listView(R.list.where, R.list.arg); } });
document.addEventListener('submit', e => {
  if (e.target.id !== 'askf') return; e.preventDefault();
  const v = ($('#askin') || {}).value; if (v && v.trim()) ask(v.trim());
});
document.addEventListener('keydown', e => {
  const tag = (e.target.tagName || '').toLowerCase(), typing = tag === 'input' || tag === 'textarea' || tag === 'select';
  if ((e.metaKey || e.ctrlKey) && (e.key.toLowerCase() === 'k' || e.code === 'KeyK')) { e.preventDefault(); $('#palette').hidden ? openPalette() : closePalette(); return; }
  if (!$('#palette').hidden) {
    const items = $$('#pres .pi');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); palIdx = Math.max(0, Math.min(items.length - 1, palIdx + (e.key === 'ArrowDown' ? 1 : -1))); items.forEach((x, i) => x.classList.toggle('on', i === palIdx)); if (items[palIdx]) items[palIdx].scrollIntoView({ block:'nearest' }); }
    else if (e.key === 'Enter') { e.preventDefault(); palGo(palIdx); }
    else if (e.key === 'Escape') closePalette();
    return;
  }
  if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
  if ((tag === 'button' || tag === 'a') && (e.key === ' ' || e.key === 'Enter')) return;
  const v = C.S.route[0], k = e.key, is = (scope, a) => K.is(e, scope, a);
  if (v === 'ebook') return;            // the book reader has its own keys (book.js)
  if (v === 'feed' || v === 'library' || v === 'view') {
    if (is('list', 'search')) { e.preventDefault(); openPalette(); return; }
    if (k === '?') { e.preventDefault(); K.sheet('list'); return; }
    if (is('list', 'undo')) { e.preventDefault(); undoLast(); return; }
    const L = R.list; if (!L) return; const xs = visibleItems(), i = xs.findIndex(d => d.id === R.sel);
    const go = n => { if (n) { selectRow(n.id); const r = $('.row[data-doc="' + CSS.escape(n.id) + '"]'); if (r) r.scrollIntoView({ block:'nearest' }); } };
    const multi = R.multi.size, feed = L.where === 'feed';
    if (is('list', 'next')) { e.preventDefault(); go(xs[Math.min(xs.length - 1, i + 1)]); }
    else if (is('list', 'prev')) { e.preventDefault(); go(xs[Math.max(0, i - 1)]); }
    else if (is('list', 'select') && R.sel) { e.preventDefault(); pick(R.sel); }
    else if (k === 'Escape' && multi) { bulkAct('none'); }
    else if (is('list', 'archive') && multi) bulkAct(feed ? (R.tabs.feed === 'seen' ? 'unseen' : 'seen') : R.tabs.library === 'archive' ? 'inbox' : 'archive');
    else if (is('list', 'later') && multi && !feed && R.tabs.library === 'inbox') bulkAct('later');
    else if (is('list', 'delete') && multi) bulkAct('deleted');
    else if (is('list', 'open') && R.sel) location.hash = 'read/' + encodeURIComponent(R.sel);
    else if (is('list', 'archive') && R.sel) docAct(feed ? 'seen' : 'archive', R.sel);
    else if (is('list', 'later') && R.sel && !feed) docAct('later', R.sel);
    else if (is('list', 'save') && R.sel && feed) docAct('save', R.sel);
    else if (is('list', 'star') && R.sel && !feed) docAct('star', R.sel);
    else if (is('list', 'delete') && R.sel) docAct('delete', R.sel);
    else if (is('list', 'tag') && R.sel) { e.preventDefault(); tagDoc(R.sel, $('.row[data-doc="' + CSS.escape(R.sel) + '"]')); }
    return;
  }
  if (v === 'read' && R.doc && R.doc.kind === 'video' && V.player) {
    if (k === ' ') { e.preventDefault(); V.playing ? V.player.pauseVideo() : V.player.playVideo(); return; }
    if (k === 'c') { e.preventDefault(); clipVideo(30); return; }
    if (k === 'ArrowRight') { e.preventDefault(); seek(curTime() + 10); return; }
    if (k === 'ArrowLeft') { e.preventDefault(); seek(Math.max(0, curTime() - 10)); return; }
  }
  if (is('list', 'search')) { e.preventDefault(); openPalette(); return; }     // Search everything, wherever you are
  if (v === 'read' && R.doc) {
    const d = R.doc, lib = d.where_ === 'library', feed = d.where_ === 'feed';
    if (is('article', 'nextdoc') || is('article', 'prevdoc')) { e.preventDefault(); const nb = neighbor(d.id, is('article', 'nextdoc') ? 1 : -1); if (nb) location.hash = 'read/' + encodeURIComponent(nb.id); return; }
    const more = ['aloud', 'docnote', 'reset', 'copy', 'meta'].find(a => is('article', a));
    if (more) { e.preventDefault(); moreAct({ aloud:'listen', docnote:'note', reset:'reset', copy:'copy', meta:'meta' }[more]); return; }
    if (k === '?') { e.preventDefault(); showKeys(); return; }
    if (is('article', 'focus') && C.Focus) { e.preventDefault(); C.Focus.toggle(); return; }
    if (k === 'Escape' && !$('#pop').hidden) { $('#pop').hidden = true; return; }
    if (k === 'Escape') { if (!$('#selbar').hidden) { stopSel(); return; } leaveDoc(d); return; }
    if (is('article', 'star') && lib) { e.preventDefault(); docAct('star', d.id); }
    else if (is('article', 'more')) { e.preventDefault(); const b = $('[data-ract="more"]'); if (b) openMore(b); }
    else if (is('article', 'open') && d.url) { e.preventDefault(); moreAct('open'); }
    else if (is('article', 'next')) { e.preventDefault(); setFocus('+', true); }
    else if (is('article', 'prev')) { e.preventDefault(); setFocus('-', true); }
    else if (is('article', 'highlight') || is('article', 'note')) {
      e.preventDefault();
      const withNote = is('article', 'note'), info = getSel();
      if (info) highlight(info, withNote);
      else if (R.imgSel != null) highlightImg(R.imgSel, withNote);
      else { const b = d.blocks[R.focus]; if (b && b.t !== 'img') { const el = $('#docbody [data-i="' + R.focus + '"]'); const txt = el ? el.textContent : b.x; highlight({ b:R.focus, s:0, e:txt.length, text:txt.trim() }, withNote); } }
    }
    else if (is('article', 'listen')) { const T = R.tts; if (T.on && T.doc === d.id) { T.playing ? pauseTTS() : resumeTTS(); } else startTTS(); }
    else if (is('article', 'toc')) { R.toc = !R.toc; const g = $('.rvgrid'); if (g) g.classList.toggle('notoc', !R.toc); }
    else if (is('article', 'panel')) { R.panelOpen = !R.panelOpen; const g = $('.rvgrid'); if (g) g.classList.toggle('withpanel', R.panelOpen); drawReaderTop(); }
    else if (is('article', 'archive')) docAct(feed ? 'seen' : 'archive', d.id);
    else if (is('article', 'later') && lib) docAct('later', d.id);
    else if (is('article', 'save') && feed) docAct('save', d.id);
    else if (is('article', 'delete')) docAct('delete', d.id);
    else if (is('article', 'undo')) { e.preventDefault(); undoLast(); }
    else if (is('article', 'tag')) { e.preventDefault(); tagDoc(d.id, $('[data-ract="more"]') || $('#rtop')); }
  }
});
window.addEventListener('hashchange', () => { if (C.S.route[0] !== 'read') { R.doc = null; stopSel(); } });
$('#scrim').addEventListener('click', closePalette);
refreshCounts();
})();
