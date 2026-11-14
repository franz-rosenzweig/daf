/* Jobs: Calibre's "Jobs" corner at the bottom right of its main window, in All books' status bar.
   While anything runs, the button spins and says how many; it opens the list of jobs (GET
   /api/catalog/jobs: running first, then the last ones finished), each with its progress, Done,
   Failed with Calibre's words, or Stopped, and Stop for a job that goes a book at a time (POST
   /api/catalog/jobs/<id>/stop: the book it's on finishes, the rest are left). The list is asked for
   only while something runs or it's open; a write that starts a job ("daf:job", app.js api) asks
   again. C.Jobs.button() is the status bar's button. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const ICON = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7.5 5.5H16M7.5 10H16M7.5 14.5H16"/><path d="M4 5.5h.01M4 10h.01M4 14.5h.01" stroke-width="2.4"/></svg>';
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const J = { list: [], running: 0, open: false, timer: null, busy: false, again: false };
const phone = () => matchMedia('(max-width:699px)').matches;

function face(){
  return (J.running ? '<i class="jbspin" aria-hidden="true"></i>' : ICON) + '<span>Jobs</span>' + (J.running ? '<b class="jbn">' + J.running + '</b>' : '');
}
// The status bar's button; drawing it asks once whether anything is running.
function button(){
  setTimeout(refresh, 0);
  return '<button class="calsw jbbtn" id="caljobs" data-jobs="toggle" aria-haspopup="dialog" aria-expanded="' + J.open + '">' + face() + '</button>';
}
function showFace(){
  const b = $('#caljobs'); if (!b) return;
  b.innerHTML = face(); b.classList.toggle('on', !!J.running); b.setAttribute('aria-expanded', String(J.open));
}
async function refresh(){
  clearTimeout(J.timer); J.timer = null;
  if (J.busy) { J.again = true; return; }
  J.busy = true;
  try { const r = await api('/api/catalog/jobs'); J.list = r.jobs || []; J.running = r.running || 0; } catch(e){}
  J.busy = false;
  showFace();
  if (J.open) draw();
  if (J.again) { J.again = false; refresh(); return; }
  if (!document.hidden && (J.open || (J.running && $('#caljobs')))) J.timer = setTimeout(refresh, J.running ? 2000 : 6000);
}
const at = s => new Date(s * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
function row(j){
  const of = j.total > 1 ? j.done + ' of ' + j.total : '';
  let st;
  if (j.state === 'running') st = j.stopping ? 'Stopping…' : of || 'Running';
  else if (j.state === 'done') st = 'Done' + (j.failed ? ' · ' + j.failed + ' didn’t' : '');
  else if (j.state === 'stopped') st = 'Stopped' + (of ? ' · ' + of : '');
  else st = 'Failed';
  const errs = j.total > 1 ? (j.errors || []).map(e => '<li>' + (e.title ? '<b>' + esc(e.title) + '</b> ' : '') + esc(e.error || '') + '</li>').join('') : '';
  return '<div class="jbrow ' + esc(j.state) + '"><div class="jbtop"><b>' + esc(j.label) + '</b><span class="mute tiny">' + at(j.started) + '</span></div>' +
    '<div class="jbst"><span class="tiny">' + esc(st) + '</span>' +
    (j.state === 'running' && j.total > 1 ? C.bar(100 * j.done / j.total) : '') +
    (j.stoppable ? '<button class="btn sm" data-jbstop="' + esc(j.id) + '">Stop</button>' : '') + '</div>' +
    (j.state === 'failed' && j.error && !errs ? '<p class="jberr tiny">' + esc(j.error) + '</p>' : '') +
    (errs ? '<ul class="jberr tiny">' + errs + '</ul>' : '') + '</div>';
}
function draw(){
  let p = $('#jbpanel');
  if (!p) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade jbshade" id="jbshade" hidden></div><div class="jbpanel" id="jbpanel" role="dialog" aria-label="Jobs" hidden></div>'); p = $('#jbpanel'); }
  const top = p.querySelector('.jblist') ? p.querySelector('.jblist').scrollTop : 0;
  p.innerHTML = '<div class="jbhead"><h2>Jobs</h2><span class="spacer"></span><button class="ib" data-jobs="close" aria-label="Close">' + X + '</button></div>' +
    '<div class="jblist">' + (J.list.length ? J.list.map(row).join('') : '<p class="mute jbnone">No jobs</p>') + '</div>';
  p.querySelector('.jblist').scrollTop = top;
  p.hidden = false; $('#jbshade').hidden = !phone();
  const b = $('#caljobs');
  if (b && !phone()) { const r = b.getBoundingClientRect(); p.style.right = Math.max(8, innerWidth - r.right) + 'px'; p.style.bottom = (innerHeight - r.top + 6) + 'px'; }
  else { p.style.right = ''; p.style.bottom = ''; }
}
function open(){ J.open = true; draw(); showFace(); refresh(); }
function close(){
  J.open = false;
  const p = $('#jbpanel'); if (p) p.hidden = true;
  const s = $('#jbshade'); if (s) s.hidden = true;
  showFace();
}
async function stop(id, btn){
  btn.disabled = true; btn.textContent = 'Stopping…';
  try { await api('/api/catalog/jobs/' + encodeURIComponent(id) + '/stop', { method: 'POST' }); } catch(e){ toast(e.message); }
  refresh();
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  const a = t.closest('[data-jobs]');
  if (a) { if (a.dataset.jobs === 'toggle' && !J.open) open(); else close(); return; }
  const s = t.closest('[data-jbstop]'); if (s && !s.disabled) { stop(s.dataset.jbstop, s); return; }
  if (J.open && !t.closest('#jbpanel')) close();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && J.open) { e.stopPropagation(); close(); } }, true);
window.addEventListener('daf:job', () => { clearTimeout(J.timer); J.timer = setTimeout(refresh, 400); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && (J.open || $('#caljobs'))) refresh(); });
window.addEventListener('hashchange', () => { if (J.open) close(); });

C.Jobs = { button, refresh };
})();
