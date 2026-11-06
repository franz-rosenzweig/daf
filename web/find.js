/* The search in a tab's top bar: Books, the Library and the Feed, Highlights, Manga, Torah, a shelf,
   Recovery, Stats, Paper pages, Sources. A button opens a field in place of the bar's title and
   buttons (the bar keeps its height, so nothing under it moves); × clears it, and Esc, the arrow
   beside it or Android's Back closes it. One for every tab, so it looks and works the same in each.

   A tab asks for it with a key, its placeholder and what to run with the words (C.Find.html), and
   reads the words back while it draws (C.Find.q). The words are kept per tab while Daf is open, so
   coming back from a book or an article finds the search as it was; going to a tab from the sidebar
   or the tab bar starts it fresh. A tab with everything on the page already filters it here
   (C.Find.match); one whose list comes in pages asks the server. */
(() => {
'use strict';
const C = window.DafCore, { esc, $ } = C;
const F = C.Find = {};
const ICON = {
  search: '<svg width="19" height="19" viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M13 13l4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  lens: '<svg class="findlens" width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M13 13l4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  back: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  clear: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
};
const state = {}, tabs = {};
let timer = null;
const st = key => state[key] || (state[key] = { open: false, q: '' });
const el = key => document.querySelector('.find[data-find="' + CSS.escape(key) + '"]');

// The bar's part of it: the button, or the field when it's open. `run` gets the words (trimmed) a
// moment after they change; `wait` is how long a moment is (longer for a tab that asks the server).
F.html = (key, label, run, wait) => {
  tabs[key] = { label, run, wait: wait || 120 };
  const s = st(key);
  if (!s.open) return '<span class="find" data-find="' + esc(key) + '"><button class="ib findgo" type="button" data-findgo aria-label="' + esc(label) + '" title="' + esc(label) + '">' + ICON.search + '</button></span>';
  return '<span class="find open" data-find="' + esc(key) + '"><button class="ib findx" type="button" data-findx aria-label="Close the search" title="Close the search (Esc)">' + ICON.back + '</button>' +
    '<span class="findbox">' + ICON.lens + '<input class="findq" type="search" dir="auto" enterkeyhint="search" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="' + esc(label) + '" aria-label="' + esc(label) + '" value="' + esc(s.q) + '">' +
    '<button class="ib findclr" type="button" data-findclr aria-label="Clear"' + (s.q ? '' : ' hidden') + '>' + ICON.clear + '</button></span></span>';
};
// The words a tab draws with: '' while its search is shut.
F.q = key => { const s = state[key]; return s && s.open ? s.q.trim() : ''; };
F.isOpen = () => !!document.querySelector('.find.open');
// Shuts the search that's open (or the given tab's), and the tab draws everything again.
F.close = key => {
  const e = key ? el(key) : document.querySelector('.find.open');
  key = key || (e && e.dataset.find);
  if (!key || !st(key).open) return false;
  const had = F.q(key);
  state[key] = { open: false, q: '' };
  if (e && tabs[key]) { e.outerHTML = F.html(key, tabs[key].label, tabs[key].run, tabs[key].wait); const b = el(key); if (b) b.querySelector('button').focus({ preventScroll: true }); }
  if (had) go(key);
  return true;
};
// A tab's own things that go with its search (a list's "All of the Library"), gone when the search is.
F.state = key => st(key);
// Sets a tab's words from outside (Highlights' "Clear filters").
F.set = (key, q) => { const s = st(key); s.q = q || ''; const i = el(key) && el(key).querySelector('.findq'); if (i) { i.value = s.q; i.parentNode.querySelector('.findclr').hidden = !s.q; } };

function open(key){
  const e = el(key), t = tabs[key]; if (!e || !t) return;
  st(key).open = true;
  e.outerHTML = F.html(key, t.label, t.run, t.wait);
  const i = el(key).querySelector('.findq');
  i.focus({ preventScroll: true }); i.setSelectionRange(i.value.length, i.value.length);
  if (F.q(key)) go(key);
}
function go(key){
  clearTimeout(timer);
  const t = tabs[key]; if (!t || !t.run) return;
  Promise.resolve().then(() => t.run(F.q(key))).catch(err => { if (err && err.message !== 'signed out') C.toast(err.message); });
}

// Matching on the page: every word somewhere in the texts, whatever its case, accents or Hebrew points.
const fold = s => String(s == null ? '' : s).normalize('NFKD').replace(/[̀-֑ͯ-ֽֿ-ׇ]/g, '').toLowerCase();
F.match = (q, ...texts) => {
  const words = fold(q).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = fold(texts.join(' '));
  return words.every(w => hay.includes(w));
};
F.none = () => '<div class="empty findnone"><b>Nothing matches</b></div>';

document.addEventListener('input', e => {
  const i = e.target; if (!i.classList || !i.classList.contains('findq')) return;
  const key = i.closest('.find').dataset.find, t = tabs[key];
  st(key).q = i.value;
  i.parentNode.querySelector('.findclr').hidden = !i.value;
  clearTimeout(timer); timer = setTimeout(() => go(key), t ? t.wait : 120);
});
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-findgo],[data-findx],[data-findclr]'); if (!b) return;
  const key = b.closest('.find').dataset.find;
  if ('findgo' in b.dataset) open(key);
  else if ('findx' in b.dataset) F.close(key);
  else {           // ×: the words go, the field stays, with the keyboard
    const i = b.parentNode.querySelector('.findq');
    st(key).q = ''; i.value = ''; b.hidden = true; i.focus({ preventScroll: true }); go(key);
  }
});
// Going to a tab from the sidebar or the tab bar starts its search fresh.
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('[data-go]')) for (const k in state) state[k] = { open: false, q: '' }; }, true);
// In the field, Esc closes it (and nothing else), and Enter or the keyboard's search key puts the
// keyboard away so the results show. Esc anywhere else closes it too, unless something is in front.
document.addEventListener('keydown', e => {
  const i = e.target;
  if (i.classList && i.classList.contains('findq')) {
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); F.close(i.closest('.find').dataset.find); }
    else if (e.key === 'Enter') { e.preventDefault(); go(i.closest('.find').dataset.find); i.blur(); }
    return;
  }
  if (e.key !== 'Escape' || !F.isOpen() || /^(input|textarea|select)$/i.test(i.tagName || '')) return;
  if (['#modal', '#pop', '#palette', '#selbar'].some(s => $(s) && !$(s).hidden)) return;
  F.close();
}, true);
})();
