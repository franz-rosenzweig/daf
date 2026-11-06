/* Preferences → Reader apps (daf/greader.py): what Read You, NetNewsWire, Reeder, newsboat and the
   rest sign in to Daf's Feed with, through the Google Reader API: the server's address, the API's
   address, the username, and an API password of its own. The password is shown once, when it's made,
   and only until the card is drawn again. Labels only: docs/reader-apps.md says how each app is set up. */
(function(){
const C = window.DafCore, { $, esc, api, toast } = C;

const row = (label, value) => '<div class="prow grrow"><div class="d"><b>' + esc(label) + '</b><code class="tok">' + esc(value) + '</code></div>' +
  '<button class="btn sm" data-gr="copy" data-v="' + esc(value) + '" aria-label="Copy ' + esc(label) + '">Copy</button></div>';

async function prefs(card, got){
  card = card || $('#gracard'); if (!card) return;
  const s = got || await api('/api/greader'), pw = got && got.password;
  const when = [s.made ? 'Made ' + C.epochDate(s.made) : '', s.used ? 'Used ' + C.ago(s.used) : ''].filter(Boolean).join(' · ');
  card.innerHTML = '<h2>Reader apps</h2>' + row('Server', s.server) + row('Google Reader API', s.api) + row('Username', s.user) +
    '<div class="prow grrow"><div class="d"><b>API password</b>' +
      (pw ? '<input class="field tok grpw" id="grpw" readonly value="' + esc(pw) + '" aria-label="API password" autocomplete="off" spellcheck="false">'
        : s.has_password && when ? '<span>' + esc(when) + '</span>' : '') + '</div>' +
      '<div class="gracts">' + (pw ? '<button class="btn sm primary" data-gr="copy" data-v="' + esc(pw) + '">Copy</button>' : '') +
        '<button class="btn sm" data-gr="make">' + (s.has_password ? 'New password' : 'Make a password') + '</button>' +
        (s.has_password ? '<button class="btn sm" data-gr="remove">Remove</button>' : '') + '</div></div>';
  if (pw) { const f = $('#grpw'); if (f) { f.focus(); f.select(); } }
}

async function copy(text){
  try { await navigator.clipboard.writeText(text); toast('Copied'); return; } catch(e){}
  const t = document.createElement('textarea'); t.value = text; t.setAttribute('readonly', ''); t.style.cssText = 'position:fixed;opacity:0;top:0';
  document.body.appendChild(t); t.select();
  try { document.execCommand('copy'); toast('Copied'); } catch(e){ toast('Couldn’t copy'); }
  t.remove();
}

document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-gr]'); if (!b) return;
  const a = b.dataset.gr, card = $('#gracard');
  try {
    if (a === 'copy') { await copy(b.dataset.v); return; }
    if (a === 'make') {
      if (card.querySelector('[data-gr="remove"]') && !confirm('Replace the API password?')) return;
      prefs(card, await api('/api/greader/password', { method: 'POST' }));
    }
    if (a === 'remove') {
      if (!confirm('Remove the API password?')) return;
      prefs(card, await api('/api/greader/password', { method: 'DELETE' }));
    }
  } catch(err){ toast(err.message); }
});

C.ReaderApps = { prefs };
})();
