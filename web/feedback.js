/* Send feedback (⌘K, or Preferences → Feedback): a note about Daf, sent with where Daf is and what
   went wrong lately (app.js keeps the last few errors), filed as an issue on Daf's private GitHub
   repo by daf/feedback.py. Offline it waits in the outbox like any other write. */
(function(){
const C = window.DafCore, { $, esc, api, toast, ago } = C;

// Changes the offline queue set aside after Daf kept refusing them (app.js outbox.flush).
function stuck(){ try { return JSON.parse(localStorage.getItem('daf.outbox.stuck') || '[]').slice(-5).map(x => 'set aside: ' + x.method + ' ' + x.path + ' ' + JSON.stringify(x.body || {}).slice(0, 200)); } catch(e){ return []; } }
function context(){
  const route = location.hash || '#today';
  const title = (document.querySelector('.doc h1, #btitle, .top h1') || {}).textContent || '';
  const shell = window.dafShell ? 'Daf for ' + (dafShell.platform === 'mac' ? 'Mac' : 'Android') + ' ' + (dafShell.version || '') : '';
  return { route, title: title.trim().slice(0, 200), device: shell || navigator.userAgent.replace(/^Mozilla\/5\.0 /, '').slice(0, 160),
           app: (document.documentElement.dataset.sw || '') + (navigator.serviceWorker && navigator.serviceWorker.controller ? ' (service worker)' : ''),
           size: innerWidth + '×' + innerHeight + (matchMedia('(pointer:coarse)').matches ? ' touch' : ''),
           theme: (C.Themes && C.Themes.get ? JSON.stringify(C.Themes.get()) : document.documentElement.dataset.mode || ''),
           online: navigator.onLine, errors: (C.errs || []).slice(-12).concat(stuck()) };
}
function open(text){
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  const ctx = context();
  m.innerHTML = '<h2>Send feedback</h2>' +
    '<textarea class="field" id="fbtext" rows="6" placeholder="Something broken, something missing, something you’d like different…">' + esc(text || '') + '</textarea>' +
    '<details class="steps"><summary class="mute tiny">What goes with it</summary><span class="mute tiny">Where Daf is (' + esc(ctx.route) + '), this device and window, the theme, and ' +
      (ctx.errors.length ? 'the last ' + ctx.errors.length + ' things that went wrong.' : 'that nothing went wrong lately.') + ' A private title is left out.</span></details>' +
    '<span class="mute tiny">It becomes an issue on Daf’s private GitHub repo, where the next working session picks it up.</span>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button><button class="btn primary" id="fbsend">Send</button></div>';
  const t = $('#fbtext'); t.focus();
  m.onkeydown = e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $('#fbsend').click(); } };
  $('#fbsend').onclick = async () => {
    const text = $('#fbtext').value.trim(); if (!text) { $('#fbtext').focus(); return; }
    $('#fbsend').disabled = true; $('#fbsend').textContent = 'Sending…';
    try {
      const r = await api('/api/feedback', { method: 'POST', body: JSON.stringify({ text, ctx }) });
      C.closeModal();
      toast(r && r.issue ? 'Sent, thank you' : r && r.queued ? 'It goes when you’re back online' : 'Kept; it goes to GitHub on the next sync');
      if ($('#fbcard')) prefs($('#fbcard'));
    } catch(e){ toast(e.message); $('#fbsend').disabled = false; $('#fbsend').textContent = 'Send'; }
  };
}
async function prefs(card){
  const r = await api('/api/feedback');
  card.innerHTML = '<div class="cardh"><h2>Feedback</h2><button class="btn sm" data-fb="open">Send feedback</button></div>' +
    '<p class="mute" style="margin:0">Also in ⌘K. Each one becomes an issue on Daf’s GitHub repo.</p>' +
    (r.feedback.length ? '<div class="fblist">' + r.feedback.map(f => '<div class="fbrow"><span>' + esc(f.text.split('\n')[0].slice(0, 120)) + '</span><span class="mute tiny">' + ago(f.at) +
      (f.issue ? ' · <a href="' + esc(f.issue) + '" target="_blank" rel="noopener">#' + esc(f.issue.split('/').pop()) + '</a>' : f.error ? ' · waiting for GitHub' : '') + '</span></div>').join('') + '</div>' : '');
}
document.addEventListener('click', e => { if (e.target.closest('[data-fb="open"]')) open(); });

C.Feedback = { open, prefs, context };
})();
