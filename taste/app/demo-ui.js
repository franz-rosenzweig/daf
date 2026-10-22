/* Daf's taste: what the page says about being a demo, and the places it leaves out. It runs after
   the app's own scripts (tools/build_taste.py puts it there); demo.js answers the app's calls. */
(function(){
'use strict';
const C = window.DafCore, $ = s => document.querySelector(s), esc = C.esc;

// The sidebar without the places that only work with the server behind them. Recovery isn't in the
// demo at all; the Feed, Manga, Torah and Podcasts read services on my server.
const GONE = /<button[^>]*data-go="(?:manga|torah|recovery|podcasts|library\/(?:video|tweet|pdf|email))"[^>]*>[\s\S]*?<\/button>/g;
const INFO = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 9v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="10" cy="6.3" r="1.1" fill="currentColor"/></svg>';
const nav = C.navExtra;
C.navExtra = (v, n) => nav(v, n).replace(GONE, '').replace(/<div class="navh"><span>Feed<\/span>[\s\S]*$/, '') +
  '<div class="nav demonav"><button class="nv" data-demo="about">' + INFO + '<span>About this demo</span></button></div>';

// Reached some other way (a key, the search, an old link): a word on why it isn't here.
function away(title, text){
  return () => {
    $('#main').innerHTML = '<div class="top"><h1>' + esc(title) + '</h1></div><div class="page"><section class="card demoaway"><h2>Not in the demo</h2>' +
      '<p>' + text + '</p><div class="demoacts"><a class="btn primary" href="#today">Back to Today</a><button class="btn" data-demo="about">About this demo</button></div></section></div>';
  };
}
Object.assign(C.views, {
  feed: away('Feed', 'The Feed is my RSS reader, FreshRSS, running on my server. Daf reads it from there, so there’s nothing here to read it from.'),
  torah: away('Torah', 'The Torah shelf brings in the week’s parasha from Sefaria through my server, so it can’t open here.'),
  manga: away('Manga', 'Manga come from Komga, a comics server on my machine, so there aren’t any in this demo.'),
  mread: away('Manga', 'Manga come from Komga, a comics server on my machine, so there aren’t any in this demo.'),
  podcasts: away('Podcasts', 'Podcasts arrive when AntennaPod syncs with my server, so there aren’t any here.'),
  paper: away('Paper pages', 'A photo of a marked-up paper page goes to Claude on my server, which reads out the lines I marked. That can’t happen in a browser.'),
  pdf: away('PDF', 'There are no PDFs in this demo.'),
});

// About this demo: what it is, and how to start over.
function about(){
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  const top = window.top !== window;
  m.innerHTML = '<h2>This is a demo</h2>' +
    '<p style="margin:0">It’s the real Daf, running on sample data right here in your browser: four public-domain books, three old essays about reading, and a made-up reader’s year. What you highlight, review and read stays in this browser and goes nowhere else.</p>' +
    '<p class="mute" style="margin:0">The parts that need my server are left out: the Kindle and audiobook sync, the Feed, Claude (Ask and summaries), read-aloud, and signing in.</p>' +
    '<div class="demoacts"><button class="btn" data-demo="reset">Reset the demo</button>' + (top ? '' : '<a class="btn" href="../">About Daf</a>') +
    '<span class="spacer"></span><button class="btn primary" data-act="close">Close</button></div>';
}
document.addEventListener('click', e => {
  const d = e.target.closest('[data-demo]');
  if (d) {
    e.preventDefault(); $('#side').classList.remove('open');
    if (d.dataset.demo === 'about') about();
    else if (d.dataset.demo === 'reset') { window.DafTaste.reset(); location.hash = '#today'; location.reload(); }
    return;
  }
  // Exports and downloads are made here too, from what demo.js has.
  const a = e.target.closest('a[href]');
  if (!a || !a.hasAttribute('download')) return;
  const url = new URL(a.getAttribute('href'), location.href);
  if (url.origin !== location.origin || !url.pathname.startsWith(new URL('api/', location.href).pathname)) return;
  e.preventDefault(); e.stopPropagation();
  window.DafTaste.answer(url.href).then(async r => {
    if (!r.ok) { let m = 'Not in the demo'; try { m = (await r.json()).detail || m; } catch(x){} C.toast(m); return; }
    const cd = r.headers.get('Content-Disposition') || '', name = (/filename="([^"]+)"/.exec(cd) || [])[1] || (/\/file$/.test(url.pathname) ? 'book.epub' : 'daf-export.txt');
    const href = URL.createObjectURL(await r.blob()), x = document.createElement('a');
    x.href = href; x.download = name; document.body.appendChild(x); x.click(); x.remove();
    setTimeout(() => URL.revokeObjectURL(href), 4000);
    const p = $('#pop'); if (p) p.hidden = true;
  });
}, true);

if (window.top !== window) document.documentElement.classList.add('demo-framed');
})();
