/* Tips and What's new.
   A tip is a small note pointing at one control the first time you reach a feature you haven't
   used: at most one each time a page opens. It goes for good once you press the control or "Got
   it", and Preferences → Tips turns them off or brings them back. What's new lists what changed
   lately; the sidebar says how many you haven't read. Both are kept on the server (/api/tips),
   so a tip seen on the Mac doesn't come back on the phone. */
(function(){
const C = window.DafCore, { $, esc, api, toast } = C;
const mac = /Mac|iPhone|iPad/.test(navigator.platform);
const touch = () => !!(window.matchMedia && matchMedia('(pointer: coarse)').matches);
const view = () => C.S.route[0] || 'today';
const android = () => document.documentElement.classList.contains('shell-android');

// One per feature: where it can show, the control it points at (stable data- attributes), the words,
// and the event that also counts as done (pressing the control always does).
const TIPS = [
  { id: 'palette', on: v => !touch() && ['today', 'library', 'feed', 'books', 'highlights'].includes(v), at: '#side [data-act="palette"]',
    text: () => 'Press ' + (mac ? '⌘K' : 'Ctrl K') + ' anywhere to search, go somewhere or run an action.', done: () => !$('#palette').hidden },
  { id: 'drop', on: v => !touch() && v === 'library', at: '#main .top h1', text: () => 'Drop links, PDFs or books anywhere here to save them.', event: 'drop' },
  { id: 'select', on: v => v === 'library', at: '[data-ract="selmode"]', text: () => 'Select several to archive, tag or delete them at once.' },
  { id: 'sources', on: v => v === 'feed', at: '[data-ract="sources"]', text: () => 'Read one feed or folder at a time.' },
  { id: 'voice', on: () => true, at: '#player:not([hidden]) [data-tts="voice"], #bplayer [data-bt="voice"]', text: () => 'Press the name to hear other voices and pick one.' },
  { id: 'listen', on: v => v === 'read', at: '[data-ract="listen"]', text: () => 'Daf reads it to you, and the time counts toward today.' },
  { id: 'article-panel', on: v => v === 'read', at: '[data-ract="panel"]', text: () => 'Your highlights, notes and Ask about this article open here.' },
  { id: 'book-aa', on: v => v === 'ebook', at: '[data-bk="aa"]', text: () => 'Change the typeface, size, theme, and scrolling or pages.' },
  { id: 'book-panel', on: v => v === 'ebook', at: '[data-bk="panel"]', text: () => 'Your highlights, notes and Ask about this book open here.' },
];

// Newest first. go: where "Show me" takes you.
const NEWS = [
  { id: '2026-10-26-anilist', date: 'Oct 26', title: 'AniList from Daf', text: 'Connect AniList in Preferences and your manga progress goes there every hour, volumes turned into chapters.', go: '#prefs/anilist' },
  { id: '2026-10-25-vault-text', date: 'Oct 25', title: 'The whole text in the vault', text: 'Highlight an article, video or podcast and its note in Obsidian gets the full text or transcript, your highlights marked in it.', go: '#highlights' },
  { id: '2026-10-25-kindle-inbox', date: 'Oct 25', title: 'The Kindle fetches its books', text: 'What you put on the Kindle comes down on its next Wi-Fi sync, into the shelf you picked.' },
  { id: '2026-10-25-add-book', date: 'Oct 25', title: 'Add a book', text: 'Find it on Hardcover, give it its file, and Calibre, Hardcover and the Kindle all get it.', go: '#books' },
  { id: '2026-10-25-reels', date: 'Oct 25', title: 'Save Instagram reels', text: 'Share a reel to Daf: it keeps the video, the caption and a transcript you can highlight.', go: '#prefs/instagram' },
  { id: '2026-10-21-kindle-covers', date: 'Oct 21', title: 'Covers come fast on the Kindle', text: 'Shelves open with every cover at once, and the next page is ready before you swipe.' },
  { id: '2026-10-21-ext-updates', date: 'Oct 21', title: 'The extension updates itself', text: 'In Firefox and Zen, from 0.5.1: install it once more from Preferences, then never again.', go: '#prefs' },
  { id: '2026-10-21-ext-ask', date: 'Oct 21', title: 'The extension asks first', text: 'Selecting text on a page shows a Highlight button; nothing saves until you press it.' },
  { id: '2026-10-20-kindle-home', date: 'Oct 20', title: 'A Home for the Kindle', text: 'Home, Shelves you can move books between, and the review on the Daf tab.' },
  { id: '2026-10-20-feed-month', date: 'Oct 20', title: 'The Feed keeps a month', text: 'Unread items stay a month now, longer if you choose.', go: '#prefs' },
  { id: '2026-10-14-library', date: 'Oct 14', title: 'Daf keeps the Library', text: 'What you save, its text and its picture now live in Daf.', go: '#library/article' },
  { id: '2026-10-14-tags', date: 'Oct 14', title: 'Tags, and a tidy-up', text: 'New saves get tags, and Preferences tidies the list with you.', go: '#prefs/tags' },
  { id: '2026-10-14-voices', date: 'Oct 14', title: 'Pick a read-aloud voice', text: 'The voice button in the read-aloud bar plays a line in each.', go: '#prefs' },
  { id: '2026-10-14-phone-bar', date: 'Oct 14', title: 'A calmer highlight bar on phones', text: 'It sits under the words, and a tap puts it away.' },
  { id: '2026-10-14-volume', date: 'Oct 14', title: 'Volume buttons, your choice', text: 'In the Android app they turn pages only if you switch that on.', go: '#prefs', only: android },
  { id: '2026-10-13-recovery', date: 'Oct 13', title: 'Recovery', text: 'The Big Book by chapter, the step 10 and 11 readings, and prayers.', go: '#recovery' },
  { id: '2026-10-13-speed', date: 'Oct 13', title: 'Faster everywhere', text: 'Daf opens from the device first, and a book downloads once.' },
  { id: '2026-10-13-email', date: 'Oct 13', title: 'A morning email', text: 'What you saved yesterday, with summaries, and how much you read.', go: '#prefs/digest' },
  { id: '2026-10-12-delete', date: 'Oct 12', title: 'Delete, with Undo', text: 'Press d to delete from the Library or an article, z to take it back.' },
  { id: '2026-10-12-import', date: 'Oct 12', title: 'Bring your old saves', text: 'From Instapaper, Pocket, Omnivore, Readwise, Raindrop and more.', go: '#prefs/import' },
  { id: '2026-10-12-keys', date: 'Oct 12', title: 'Your own keys', text: 'Change any shortcut in the reader, the lists or the review.', go: '#prefs/keys' },
  { id: '2026-10-12-ai', date: 'Oct 12', title: 'AI settings', text: 'Choose the model, and edit the prompts for summaries and Ask.', go: '#prefs/ai' },
  { id: '2026-10-12-pictures', date: 'Oct 12', title: 'Highlight pictures', text: 'Press a picture in an article, then Highlight, to keep it.' },
  { id: '2026-10-12-feedback', date: 'Oct 12', title: 'Send feedback', text: 'A note from ' + (mac ? '⌘K' : 'Ctrl K') + ' becomes an issue for the next work session.', go: '#prefs/feedback' },
  { id: '2026-10-12-forget', date: 'Oct 12', title: 'Forget my place', text: 'A book’s bookmark menu starts you over in Daf; highlights stay.' },
].filter(n => !n.only || n.only());

const T = { state: null, shown: null, viewKey: null, timers: [] };
const save = body => api('/api/tips', { method: 'POST', body: JSON.stringify(body) }).then(r => { if (r && r.seen) T.state = r; }).catch(() => {});
const unseen = () => { if (!T.state) return 0; const i = NEWS.findIndex(n => n.id === T.state.news); return i < 0 ? NEWS.length : i; };

/* ---------- a tip ---------- */
function visible(el){
  if (!el || !el.isConnected) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
  for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e); if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) return false; }
  return true;
}
// Something else has your attention: a menu, a dialog, the search, words selected or a box being typed in.
function busy(){
  const ae = document.activeElement;
  return document.hidden || !$('#modal').hidden || !$('#pop').hidden || !$('#selbar').hidden || !$('#palette').hidden || !$('#scrim').hidden ||
    (ae && (ae.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName))) || !!document.querySelector('.mread, #mread:not([hidden])');
}
// Why no tip shows now (for a test, or the console): '' when one could.
function why(){
  return !T.state ? 'not loaded' : T.state.off ? 'off' : T.shown ? 'one is up' : T.viewKey === location.hash ? 'one this view' : busy() ? 'busy' : '';
}
function check(){
  if (why()) return;
  const v = view();
  for (const t of TIPS) {
    if (T.state.seen[t.id] || !t.on(v)) continue;
    if (t.done && t.done()) { done(t); continue; }
    const el = [...document.querySelectorAll(t.at)].find(visible);
    if (el) { show(t, el); return; }
  }
}
function show(t, el){
  T.viewKey = location.hash;
  const box = document.createElement('div');
  box.className = 'tip'; box.id = 'tip'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Tip');
  box.innerHTML = '<p id="tiptext">' + esc(t.text()) + '</p><button class="btn sm" data-tipok>Got it</button><i class="tiparrow" aria-hidden="true"></i>';
  document.body.appendChild(box);
  el.classList.add('tipring'); el.setAttribute('aria-describedby', 'tiptext');
  T.shown = { t, el, box, follow: setInterval(place, 600) };
  place();
  requestAnimationFrame(() => box.classList.add('in'));
}
function place(){
  const s = T.shown; if (!s) return;
  if (!s.el.isConnected) {               // the page drew that part again: point at the new one
    const el = [...document.querySelectorAll(s.t.at)].find(visible);
    if (!el) { hide(); return; }
    s.el.classList.remove('tipring'); s.el = el; el.classList.add('tipring'); el.setAttribute('aria-describedby', 'tiptext');
  }
  if (!visible(s.el)) { hide(); return; }
  const r = s.el.getBoundingClientRect(), b = s.box, w = b.offsetWidth, h = b.offsetHeight, gap = 12;
  const below = r.bottom + gap + h <= innerHeight - 8 || r.top - gap - h < 8;
  const left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2));
  b.style.left = left + 'px';
  b.style.top = (below ? r.bottom + gap : r.top - gap - h) + 'px';
  b.classList.toggle('above', !below);
  b.style.setProperty('--ax', Math.max(14, Math.min(w - 14, r.left + r.width / 2 - left)) + 'px');
}
function hide(){
  const s = T.shown; if (!s) return;
  T.shown = null; clearInterval(s.follow);
  s.el.classList.remove('tipring'); if (s.el.getAttribute('aria-describedby') === 'tiptext') s.el.removeAttribute('aria-describedby');
  s.box.remove();
}
function done(t){
  if (!T.state || T.state.seen[t.id]) return;
  T.state.seen[t.id] = Math.floor(Date.now() / 1000);
  save({ seen: t.id });
}
function soon(...ms){ T.timers.forEach(clearTimeout); T.timers = ms.map(m => setTimeout(check, m)); }

document.addEventListener('click', e => {
  const s = T.shown;
  if (s && e.target.closest('#tip [data-tipok]')) { done(s.t); hide(); return; }
  // pressing the control is doing the thing (not for a tip whose thing is something else, like a drop)
  for (const t of TIPS) if (!t.event && T.state && !T.state.seen[t.id] && t.on(view()) && e.target.closest && e.target.closest(t.at)) { done(t); if (s && s.t === t) hide(); }
  if (T.shown && !e.target.closest('#tip')) hide();
  soon(1500);
}, true);
document.addEventListener('drop', () => { const t = TIPS.find(x => x.event === 'drop'); if (t) done(t); if (T.shown && T.shown.t === t) hide(); }, true);
window.addEventListener('keydown', e => {
  if (e.key === 'Escape' && T.shown) { hide(); e.stopImmediatePropagation(); e.preventDefault(); return; }
  if (T.shown) hide();
  setTimeout(() => { for (const t of TIPS) if (t.done && T.state && !T.state.seen[t.id] && t.done()) done(t); }, 60);   // ⌘K opened the search
}, true);
window.addEventListener('hashchange', () => { hide(); T.viewKey = null; soon(1800, 4500); });
window.addEventListener('scroll', () => { if (T.shown) place(); }, true);
window.addEventListener('resize', () => { if (T.shown) place(); });

/* ---------- What's new ---------- */
function news(){
  const was = T.state ? T.state.news : '';
  const fresh = new Set(NEWS.slice(0, unseen()).map(n => n.id));
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  m.innerHTML = '<h2>What’s new</h2><div class="newslist">' + NEWS.map(n =>
    '<div class="newsrow' + (fresh.has(n.id) ? ' fresh' : '') + '"><div class="d"><b>' + esc(n.title) + '</b><span>' + esc(n.text) + '</span><span class="mute tiny">' + esc(n.date) + (fresh.has(n.id) ? ' · new' : '') + '</span></div>' +
    (n.go ? '<button class="btn sm" data-newsgo="' + esc(n.go) + '">Show me</button>' : '') + '</div>').join('') + '</div>' +
    '<div style="display:flex;justify-content:flex-end"><button class="btn" data-act="close">Close</button></div>';
  m.onclick = e => { const g = e.target.closest('[data-newsgo]'); if (g) { C.closeModal(); location.hash = g.dataset.newsgo; } };
  if (NEWS.length && T.state && was !== NEWS[0].id) { T.state.news = NEWS[0].id; save({ news: NEWS[0].id }); C.renderSide(); }
}
document.addEventListener('click', e => { if (e.target.closest('[data-act="whatsnew"]')) { const s = $('#side'); if (s) s.classList.remove('open'); news(); } });

/* ---------- Preferences → Tips ---------- */
function prefs(card){
  const s = T.state || { off: false };
  card.innerHTML = '<h2>Tips</h2>' +
    '<div class="prow"><div class="d"><b>Tips for features you haven’t used</b><span>One small note at a time, the first time you reach something. On every device.</span></div><input type="checkbox" class="sw" id="tipson"' + (s.off ? '' : ' checked') + ' aria-label="Tips"></div>' +
    '<div class="prow"><div class="d"><b>What’s new</b><span>What changed in Daf lately.</span></div><button class="btn sm" data-act="whatsnew">Open</button></div>' +
    '<div class="prow"><div class="d"><b>See the tips again</b><span>Every tip comes back once.</span></div><button class="btn sm" id="tipsreset">Show them again</button></div>';
  card.querySelector('#tipson').onchange = e => { T.state.off = !e.target.checked; save({ off: T.state.off }); toast(T.state.off ? 'No more tips' : 'Tips on'); };
  card.querySelector('#tipsreset').onclick = () => { T.state.seen = {}; T.state.off = false; save({ reset: true, off: false }); const sw = card.querySelector('#tipson'); if (sw) sw.checked = true; toast('The tips come back, one at a time'); };
}

C.Tips = {
  prefs: card => (T.state ? Promise.resolve() : load()).then(() => prefs(card)),
  news,
  unseen,
  why, check, state: () => T.state,
  navItem: () => unseen() ? '<button class="nv" data-act="whatsnew"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5l1.8 4.6 4.7 1.9-4.7 1.9L10 15.5l-1.8-4.6L3.5 9l4.7-1.9z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg><span>What’s new</span><span class="ct">' + unseen() + '</span></button>' : '',
};
function load(){
  return api('/api/tips').then(s => { T.state = s; C.renderSide && C.S.user && C.renderSide(); soon(2500); }).catch(() => {});
}
load();
})();
