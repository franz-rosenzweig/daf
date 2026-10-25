/* Focus mode: an article, a book or a PDF on the whole screen, and nothing else. The sidebar, the
   reader's bar and the book's footer go; in the Android app the status and navigation bars go too
   and the screen stays on (dafShell.screen, as the manga reader has it); in a browser the window
   goes full screen. The edges bring back what's needed: the top or the bottom edge the bar (and
   the book's footer), the left edge the contents, the right edge the side panel. Back, Esc or the
   bar's [ ] button leave it. It stays on for the next thing opened until it's left. */
(function(){
'use strict';
const C = window.DafCore;
const { $ } = C;
const root = document.documentElement;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.focus.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
                set(k, v){ try { localStorage.setItem('daf.focus.' + k, JSON.stringify(v)); } catch(e){} } };
const VIEWS = ['read', 'ebook', 'pdf'];
const F = { want: store.get('on', false), on: false, barT: 0, full: false };
const reading = () => VIEWS.includes(document.body && document.body.dataset.view);
const scope = () => document.body.dataset.view === 'ebook' ? 'book' : 'article';
const shellScreen = on => { try { if (window.dafShell && dafShell.can && dafShell.can('screen')) { dafShell.screen({ immersive: on, awake: on }).catch(() => {}); return true; } } catch(e){} return false; };

const ICON = {
  enter: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 7.5v-4h4M12.5 3.5h4v4M16.5 12.5v4h-4M7.5 16.5h-4v-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  leave: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 3.5v4h-4M16.5 7.5h-4v-4M12.5 16.5v-4h4M3.5 12.5h4v4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
// The [ ] button, for the readers' bars (reader.js, book.js, pdfview.js).
function button(sc){
  const tip = C.Keys ? C.Keys.tip(sc || 'article', 'focus') : '';
  const label = F.on ? 'Leave focus mode' : 'Focus mode';
  return '<button class="ib" data-focus title="' + label + tip + '" aria-label="' + label + '">' + (F.on ? ICON.leave : ICON.enter) + '</button>';
}
const redrawButtons = () => document.querySelectorAll('[data-focus]').forEach(b => { b.outerHTML = button(scope()); });

function apply(on){
  if (on === F.on) return;
  F.on = on;
  root.classList.toggle('focus', on);
  root.classList.remove('fbar', 'ftoc', 'fpanel');
  document.body.classList.remove('bookbare', 'btocsheet', 'bpanelsheet');
  edges(on);
  if (!shellScreen(on) && !on && F.full && document.fullscreenElement) { F.full = false; document.exitFullscreen().catch(() => {}); }
  redrawButtons();
  window.dispatchEvent(new Event('resize'));          // the book's pages and the ink lay out again
}
// The reader opened or closed: focus comes with it if it's wanted.
function sync(){ apply(F.want && reading()); }
function toggle(){
  F.want = !F.on; store.set('on', F.want);
  if (F.want && reading() && !root.classList.contains('shell') && document.fullscreenEnabled && !document.fullscreenElement) {
    document.documentElement.requestFullscreen().then(() => { F.full = true; }).catch(() => {});
  }
  apply(F.want && reading());
}

/* ---------- the edges ---------- */
function edges(on){
  let e = $('#fedges');
  if (!on) { if (e) e.remove(); return; }
  if (e) return;
  e = document.createElement('div'); e.id = 'fedges';
  e.innerHTML = '<div class="fedge t" data-fe="bar" title="Show the bar"></div><div class="fedge b" data-fe="bar"></div>' +
    '<div class="fedge l" data-fe="toc" title="Contents"></div><div class="fedge r" data-fe="panel" title="Side panel"></div><div class="fscrim" data-fe="close" hidden></div>';
  e.addEventListener('click', ev => {
    const k = ev.target.dataset.fe;
    if (k === 'bar') bar(!root.classList.contains('fbar'));
    else if (k === 'toc') drawer('ftoc');
    else if (k === 'panel') drawer('fpanel');
    else if (k === 'close') close();
  });
  document.body.appendChild(e);
}
// The bar (and the book's footer), for a few seconds or until the page is touched; kept while its
// menus are open.
function bar(on){
  clearTimeout(F.barT);
  root.classList.toggle('fbar', !!on);
  if (on) F.barT = setTimeout(function again(){ if ($('#pop') && !$('#pop').hidden) F.barT = setTimeout(again, 2000); else root.classList.remove('fbar'); }, 4500);
}
function drawer(which){
  const open = !root.classList.contains(which);
  root.classList.remove('ftoc', 'fpanel', 'fbar');
  if (open) root.classList.add(which);
  const s = $('#fedges .fscrim'); if (s) s.hidden = !open;
}
// Whatever focus mode has open: a drawer, then the bar. Answers whether there was one.
function close(){
  const had = root.classList.contains('ftoc') || root.classList.contains('fpanel') || root.classList.contains('fbar');
  root.classList.remove('ftoc', 'fpanel', 'fbar');
  const s = $('#fedges .fscrim'); if (s) s.hidden = true;
  return had;
}
// Esc: what's open, then focus mode itself.
function escape(){ if (!F.on) return false; if (!close()) toggle(); return true; }

document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('[data-focus]');
  if (t) { e.preventDefault(); toggle(); return; }
  if (!F.on) return;
  // a chapter or a heading chosen in the contents drawer: the drawer goes once it's there
  if (root.classList.contains('ftoc') && e.target.closest && e.target.closest('.toc [data-jump], .toc .tocit, .toc .sres')) setTimeout(close, 60);
});
// A touch on the page puts the bar away again.
document.addEventListener('pointerdown', e => {
  if (!F.on || !root.classList.contains('fbar')) return;
  if (e.target.closest && e.target.closest('.rv > .top, .pdfv > .top, .bookfoot, #pop, #fedges, .inkpal, .inkpop, #selbar, .modal')) return;
  bar(false);
}, true);
document.addEventListener('keydown', e => {
  if (!F.on || e.key !== 'Escape' || e.defaultPrevented) return;
  if (['#pop', '#selbar', '#modal', '#palette'].some(s => $(s) && !$(s).hidden)) return;
  if (/input|textarea|select/i.test((e.target.tagName || ''))) return;
  e.preventDefault(); e.stopImmediatePropagation(); escape();
}, true);
// A browser's own Esc out of full screen leaves focus mode too.
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && F.full) { F.full = false; if (F.on) toggle(); } });
const watch = () => { new MutationObserver(sync).observe(document.body, { attributes: true, attributeFilter: ['data-view'] }); sync(); };
if (document.body) watch(); else document.addEventListener('DOMContentLoaded', watch);

C.Focus = { button, toggle, on: () => F.on, bar: () => bar(!root.classList.contains('fbar')), close, escape };
})();
