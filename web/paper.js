/* Daf paper pages (Phase 7): photos of marked pages → chosen lines → highlights in the book note. */
(() => {
const C = window.DafCore, { api, esc, toast, $, $$, ago } = C;
const P = { page: null, chosen: new Set(), book: null, newTitle: null, poll: null };

const CAM = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 6.5h3l1.5-2h5l1.5 2h3v9H3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="10" cy="10.5" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
C.icons = Object.assign(C.icons || {}, { camera: CAM });

function short(t){ return String(t || '').split(':')[0]; }
function statusLine(p){
  if (p.status === 'new' || (p.job && (p.job.status === 'queued' || p.job.status === 'running'))) return 'Reading the page…';
  if (p.status === 'error') return 'Couldn’t read it';
  const n = runs(p.chosen).length;
  return n ? n + ' passage' + (n === 1 ? '' : 's') : 'No lines chosen';
}
function runs(ch){ const out = []; [...ch].sort((a, b) => a - b).forEach(i => { if (out.length && i === out[out.length - 1][out[out.length - 1].length - 1] + 1) out[out.length - 1].push(i); else out.push([i]); }); return out; }

async function upload(files){
  const ids = [];
  for (const f of files) {
    toast('Sending ' + (files.length > 1 ? (ids.length + 1) + ' of ' + files.length : 'the photo') + '…');
    const r = await fetch('/api/paper/pages', { method:'POST', body:f, headers:{ 'Content-Type': f.type || 'image/jpeg' }, credentials:'same-origin' });
    if (!r.ok) { toast('Couldn’t send that photo'); continue; }
    ids.push((await r.json()).id);
  }
  if (ids.length === 1) location.hash = '#paper/' + ids[0];
  else if (ids.length) { toast('Reading ' + ids.length + ' pages'); listView(); }
}

async function listView(){
  clearInterval(P.poll);
  $('#main').innerHTML = '<div class="top"><h1>Paper pages</h1><span class="spacer"></span><label class="btn primary">' + CAM + 'Add a page<input type="file" id="ppfile" accept="image/*" multiple hidden></label></div><div class="page" id="pplist"><span class="mute">Loading…</span></div>';
  const r = await api('/api/paper/pages');
  let h = '';
  if (!r.pages.length) h += '<section class="card"><h2>Pencil marks, kept</h2><p style="margin:0">Photograph a page you marked. Send it to Ezer with the caption <b>page</b> (or <b>page 112 middlemarch</b>), share it to Daf from the gallery, or add it here. Daf reads the page, keeps the lines you marked as highlights, and writes them into the book’s note. Anything in the margin becomes the highlight’s note.</p></section>';
  else h += '<div class="ppgrid">' + r.pages.map(p => '<a class="ppcard" href="#paper/' + esc(p.id) + '"><img src="/api/paper/pages/' + esc(p.id) + '/photo" alt="" loading="lazy"><span class="pt"><b>' + esc(p.book ? short(p.book.title) : 'Which book?') + '</b><span class="mute tiny">' + (p.page ? 'p. ' + p.page + ' · ' : '') + esc(statusLine(p)) + ' · ' + ago(p.created) + '</span></span></a>').join('') + '</div>';
  $('#pplist').innerHTML = h;
  if (r.pages.some(p => p.status === 'new')) P.poll = setInterval(() => { if (C.S.route[0] === 'paper' && !C.S.route[1]) listView(); else clearInterval(P.poll); }, 5000);
}

function bookBox(){
  const b = P.book, nt = P.newTitle;
  return '<div class="ppbook"><span class="mute tiny">Book</span>' +
    (b || nt ? '<div class="ppchosen"><b>' + esc(b ? b.title : nt) + '</b>' + (b && b.author ? '<span class="mute tiny">' + esc(b.author) + '</span>' : nt ? '<span class="mute tiny">New paper book; Daf makes its note</span>' : '') + '<button class="btn sm" data-pp="changebook">Change</button></div>'
      : '<input class="field" id="ppq" placeholder="Search your books" autocomplete="off"><div id="ppres" class="ppres"></div>') + '</div>';
}
async function searchBooks(q){
  const r = await api('/api/booksearch?q=' + encodeURIComponent(q));
  const box = $('#ppres'); if (!box) return;
  box.innerHTML = r.books.slice(0, q.trim() ? 8 : 5).map(b => '<button class="ppopt" data-ppbook="' + esc(b.id) + '" data-t="' + esc(b.title) + '" data-a="' + esc(b.author || '') + '"><b>' + esc(short(b.title)) + '</b><span class="mute tiny">' + esc(b.author || '') + '</span></button>').join('') +
    (q.trim().length > 2 ? '<button class="ppopt" data-ppnew="' + esc(q.trim()) + '"><b>New paper book: “' + esc(q.trim()) + '”</b><span class="mute tiny">Not in Calibre or the vault yet</span></button>' : '');
}
function drawLines(){
  const p = P.page, box = $('#pplines'); if (!box) return;
  const margin = {}; (p.margin || []).forEach(m => { if (Number.isInteger(m.line)) (margin[m.line] = margin[m.line] || []).push(m.text); });
  box.innerHTML = p.lines.map((l, i) => '<label class="ppl' + (P.chosen.has(i) ? ' on' : '') + '"' + (p.lang === 'he' ? ' dir="rtl" lang="he"' : '') + '><input type="checkbox" data-ppl="' + i + '"' + (P.chosen.has(i) ? ' checked' : '') + '><span>' + esc(l.text) + (l.marked ? ' <i class="pmark" title="Marked on the page">✎</i>' : '') + (margin[i] ? '<em class="pmargin">' + esc(margin[i].join('; ')) + '</em>' : '') + '</span></label>').join('');
  const n = runs(P.chosen).length;
  $('#ppcount').textContent = n ? n + ' highlight' + (n === 1 ? '' : 's') + ' from ' + P.chosen.size + ' line' + (P.chosen.size === 1 ? '' : 's') : 'Nothing chosen';
}
async function pageView(id){
  clearInterval(P.poll);
  $('#main').innerHTML = '<div class="top"><a class="ib" href="#paper" aria-label="Back">' + C.I.back + '</a><h1 id="pph">Paper page</h1></div><div class="page" id="pppage"><span class="mute">Loading…</span></div>';
  let p; try { p = await api('/api/paper/pages/' + encodeURIComponent(id)); } catch(e){ $('#pppage').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  P.page = p; P.chosen = new Set(p.chosen || []); P.book = p.book; P.newTitle = null;
  $('#pph').textContent = (p.page ? 'Page ' + p.page : 'A page') + (p.book ? ' · ' + short(p.book.title) : '');
  const reading = p.status === 'new' || (p.job && (p.job.status === 'queued' || p.job.status === 'running'));
  let right;
  if (reading) right = '<section class="card"><h2>Reading the page…</h2><p class="mute" style="margin:0">Reading the marked lines on morten. About fifteen seconds.</p></section>';
  else if (p.status === 'error') right = '<section class="card"><h2>Couldn’t read it</h2><p class="mute" style="margin:0">' + esc(p.error || '') + '</p><button class="btn" data-pp="reread" style="align-self:flex-start">Try again</button></section>';
  else right = '<section class="card ppform">' + bookBox() +
    '<div class="pprow"><label class="mute tiny" for="pppg">Page</label><input class="field" id="pppg" type="number" inputmode="numeric" value="' + (p.page || '') + '" style="width:110px"></div>' +
    '<div class="cardh"><span class="mute tiny">Tap the lines to keep. Lines next to each other become one highlight. ✎ = marked on the page.</span></div>' +
    '<div id="pplines" class="pplines"></div>' +
    '<div class="ppfoot"><span class="mute tiny" id="ppcount"></span><span class="spacer"></span><button class="btn sm" data-pp="reread">Read again</button><button class="btn sm rm" data-pp="delete">Delete</button><button class="btn primary" data-pp="save">Save</button></div></section>';
  $('#pppage').innerHTML = '<div class="pptwo"><a class="ppphoto" href="/api/paper/pages/' + esc(p.id) + '/photo" target="_blank" rel="noopener"><img src="/api/paper/pages/' + esc(p.id) + '/photo" alt="The page photo"></a><div>' + right + '</div></div>';
  if (!reading && p.status !== 'error') { drawLines(); if (!P.book) searchBooks(''); }
  if (reading) P.poll = setInterval(async () => {
    if (C.S.route[0] !== 'paper' || C.S.route[1] !== id) { clearInterval(P.poll); return; }
    const q = await api('/api/paper/pages/' + encodeURIComponent(id));
    if (q.status !== 'new' && !(q.job && (q.job.status === 'queued' || q.job.status === 'running'))) { clearInterval(P.poll); pageView(id); }
  }, 3000);
}

C.views.paper = args => args[0] ? pageView(args[0]) : listView();

document.addEventListener('change', e => {
  if (e.target.id === 'ppfile' && e.target.files.length) upload([...e.target.files]).catch(err => toast(err.message));
  const l = e.target.closest('[data-ppl]');
  if (l) { const i = +l.dataset.ppl; l.checked ? P.chosen.add(i) : P.chosen.delete(i); l.closest('.ppl').classList.toggle('on', l.checked); drawLines(); }
});
let qT = null;
document.addEventListener('input', e => { if (e.target.id === 'ppq') { clearTimeout(qT); qT = setTimeout(() => searchBooks(e.target.value), 180); } });
document.addEventListener('click', async e => {
  const t = e.target;
  const ob = t.closest('[data-ppbook]'); if (ob) { P.book = { id: ob.dataset.ppbook, title: ob.dataset.t, author: ob.dataset.a }; P.newTitle = null; $('.ppbook').outerHTML = bookBox(); return; }
  const nb = t.closest('[data-ppnew]'); if (nb) { P.book = null; P.newTitle = nb.dataset.ppnew; $('.ppbook').outerHTML = bookBox(); return; }
  const a = t.closest('[data-pp]'); if (!a || !P.page) return;
  const act = a.dataset.pp, id = P.page.id;
  if (act === 'changebook') { P.book = null; P.newTitle = null; $('.ppbook').outerHTML = bookBox(); $('#ppq').focus(); searchBooks(''); }
  else if (act === 'save') {
    if (!P.book && !P.newTitle) { toast('Choose the book first'); const q = $('#ppq'); if (q) q.focus(); return; }
    a.disabled = true;
    try {
      const r = await api('/api/paper/pages/' + encodeURIComponent(id), { method:'POST', body:JSON.stringify({ chosen:[...P.chosen], book_id:P.book ? P.book.id : null, new_title:P.newTitle, page:$('#pppg').value }) });
      toast(r.highlights ? 'Saved ' + r.highlights + ' highlight' + (r.highlights === 1 ? '' : 's') + ' · in the book’s note' : 'Saved. No lines kept from this page.');
      location.hash = '#paper';
    } catch(err){ toast(err.message); a.disabled = false; }
  }
  else if (act === 'reread') { await api('/api/paper/pages/' + encodeURIComponent(id) + '/read', { method:'POST' }); pageView(id); }
  else if (act === 'delete') { if (!confirm('Delete this page and its highlights?')) return; await api('/api/paper/pages/' + encodeURIComponent(id), { method:'DELETE' }); toast('Deleted'); location.hash = '#paper'; }
});
})();
