/* Daf's taste: About this demo, Reset, and downloads made here. It runs after the app's own scripts
   (tools/build_taste.py puts it there); demo.js answers the app's calls and leaves out the places
   that need the server, from the app's first drawing on. */
(function(){
'use strict';
const C = window.DafCore, $ = s => document.querySelector(s);

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
