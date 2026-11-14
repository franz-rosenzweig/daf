/* Jobs: Calibre's "Jobs" corner at the bottom right of its main window, in All books' status bar,
   and a small one on every other page while it matters: in the new look's corner beside the goal
   ring, on the phone and in the old look a little pill at the bottom right. Those show only while
   something runs or something finished in the last few minutes. While anything runs, they spin and
   say how many; they open the list of jobs (GET /api/catalog/jobs: running first, then the last
   ones finished, from before a restart too), each with its progress, Done, Failed with Calibre's
   words, Stopped or Interrupted, and Stop for a job that can stop between books (POST
   /api/catalog/jobs/<id>/stop: the book it's on finishes, the rest are left). The list is asked for
   once when Daf opens, then only while something runs or it's open; a write that starts a job
   ("daf:job", app.js api) asks again. C.Jobs.button() is the status bar's button, C.Jobs.corner()
   the corner's place (look2.js). */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const ICON = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7.5 5.5H16M7.5 10H16M7.5 14.5H16"/><path d="M4 5.5h.01M4 10h.01M4 14.5h.01" stroke-width="2.4"/></svg>';
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const RECENT = 5 * 60;                      // seconds a finished job keeps the small ones showing
const J = { list: [], running: 0, open: false, timer: null, hide: null, busy: false, again: false, anchor: null };
const phone = () => matchMedia('(max-width:699px)').matches;
const spin = '<i class="jbspin" aria-hidden="true"></i>';

function face(){
  return (J.running ? spin : ICON) + '<span>Jobs</span>' + (J.running ? '<b class="jbn">' + J.running + '</b>' : '');
}
// The jobs that finished lately (the small ones show for them), and whether one of them went wrong.
const recent = () => J.list.filter(j => j.state !== 'running' && j.ended && Date.now() / 1000 - j.ended < RECENT);
const shows = () => J.running > 0 || recent().length > 0;
function small(){
  const bad = !J.running && recent().some(j => j.state === 'failed' || j.state === 'interrupted');
  return [(J.running ? spin : ICON) + (J.running ? '<b class="jbn">' + J.running + '</b>' : ''), bad];
}
// The status bar's button; drawing it asks once whether anything is running.
function button(){
  setTimeout(refresh, 0);
  return '<button class="calsw jbbtn" id="caljobs" data-jobs="toggle" aria-haspopup="dialog" aria-expanded="' + J.open + '">' + face() + '</button>';
}
// The new look's corner: a place that's empty while there's nothing to show.
function corner(){ return '<span class="jbcorner" id="jbcorner">' + cornerHTML() + '</span>'; }
function cornerHTML(){
  if (!shows()) return '';
  const [inner, bad] = small();
  return '<button class="l2round jbround' + (bad ? ' bad' : '') + '" data-jobs="toggle" aria-haspopup="dialog" aria-label="Jobs" title="Jobs">' + inner + '</button>';
}
function showFace(){
  const b = $('#caljobs');
  if (b) { b.innerHTML = face(); b.classList.toggle('on', !!J.running); b.setAttribute('aria-expanded', String(J.open)); }
  let c = $('#jbcorner');
  const lc = $('.l2corner');
  if (!c && lc) { c = document.createElement('span'); c.className = 'jbcorner'; c.id = 'jbcorner'; lc.insertBefore(c, lc.querySelector('.l2mins')); }
  if (c) c.innerHTML = cornerHTML();
  let f = $('#jbfloat');
  if (!f && shows()) { document.body.insertAdjacentHTML('beforeend', '<button class="jbfloat" id="jbfloat" data-jobs="toggle" aria-haspopup="dialog" hidden></button>'); f = $('#jbfloat'); }
  if (f) {
    f.hidden = !shows();
    if (!f.hidden) { const [inner, bad] = small(); f.innerHTML = inner + '<span>Jobs</span>'; f.classList.toggle('bad', bad); }
  }
  // the small ones go away by themselves when the last finished job stops being recent
  clearTimeout(J.hide); J.hide = null;
  const r = recent();
  if (!J.running && r.length) J.hide = setTimeout(showFace, (Math.max(...r.map(j => j.ended)) + RECENT - Date.now() / 1000) * 1000 + 500);
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
  if (!document.hidden && (J.open || J.running)) J.timer = setTimeout(refresh, J.running ? 2000 : 6000);
}
const at = s => new Date(s * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
function row(j){
  const of = j.total > 1 ? j.done + ' of ' + j.total : '';
  let st;
  if (j.state === 'running') st = j.stopping ? 'Stopping…' : of || 'Running';
  else if (j.state === 'done') st = 'Done' + (j.failed ? ' · ' + j.failed + ' didn’t' : '');
  else if (j.state === 'stopped') st = 'Stopped' + (of ? ' · ' + of : '');
  else if (j.state === 'interrupted') st = 'Interrupted' + (of ? ' · ' + of : '');
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
  // by the button it was opened from: above one low on the screen, below one high up
  const b = J.anchor && J.anchor.isConnected && J.anchor.getClientRects().length ? J.anchor : $('#caljobs');
  p.style.right = p.style.bottom = p.style.top = '';
  if (b && !phone()) {
    const r = b.getBoundingClientRect();
    p.style.right = Math.max(8, innerWidth - r.right) + 'px';
    if (r.top > innerHeight / 2) p.style.bottom = (innerHeight - r.top + 6) + 'px';
    else { p.style.top = (r.bottom + 6) + 'px'; p.style.bottom = 'auto'; }
  }
}
function open(from){ J.open = true; J.anchor = from || null; draw(); showFace(); refresh(); }
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
  if (a) { if (a.dataset.jobs === 'toggle' && !J.open) open(a); else close(); return; }
  const s = t.closest('[data-jbstop]'); if (s && !s.disabled) { stop(s.dataset.jbstop, s); return; }
  if (J.open && !t.closest('#jbpanel')) close();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && J.open) { e.stopPropagation(); close(); } }, true);
window.addEventListener('daf:job', () => { clearTimeout(J.timer); J.timer = setTimeout(refresh, 400); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && (J.open || J.running)) refresh(); });
window.addEventListener('hashchange', () => { if (J.open) close(); setTimeout(showFace, 0); });
setTimeout(refresh, 1500);                  // once when Daf opens: a job going on from before, or from another device

C.Jobs = { button, corner, refresh };
})();
