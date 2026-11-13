/* Preferences → AniList (daf/anilist.py): the sign-in manga-track.py sets your manga progress on
   AniList with, every hour. Make an API client on AniList once (its redirect URL is Daf's /anilist),
   paste its id, Connect; it lasts a year, and Connect again renews it. */
(function(){
const C = window.DafCore, { $, esc, api, toast } = C;

const day = t => new Date(t * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });

async function prefs(card){
  const s = await api('/api/anilist');
  const soon = s.expires_at && s.expires_at - Date.now() / 1000 < 21 * 86400;
  const state = s.expired ? '<b style="color:var(--bad)">Expired</b> on ' + esc(day(s.expires_at))
    : s.connected ? 'Connected as <b>' + esc((s.user || {}).name || '') + '</b>, until ' + esc(day(s.expires_at)) + (soon ? ' · <b>expires soon</b>' : '')
    : 'Not connected';
  // the tracker's last run (manga-track.py's last-run.json); a run that couldn't sign in says so here
  const lr = s.last_run, failed = lr && lr.error && s.connected && !s.expired;
  const run = lr && (lr.summary || failed) ? '<div class="prow"><div class="d"><b>Last update</b><span>' + esc(C.ago(lr.at)) + ': ' +
    (failed ? '<b style="color:var(--bad)">' + esc(lr.error) + '</b>' : esc(lr.summary)) + '</span></div></div>' : '';
  card.innerHTML = '<h2>AniList</h2>' +
    '<div class="prow"><div class="d"><b>Sign-in</b><span>' + state + '</span></div>' +
      (s.client_id ? '<div style="display:flex;gap:8px">' + (s.connected && !s.expired ? '<button class="btn sm" data-al="forget">Forget it</button>' : '') +
        '<a class="btn sm primary" href="' + esc(s.authorize) + '">' + (s.connected ? 'Connect again' : 'Connect AniList') + '</a></div>' : '') + '</div>' + run +
    '<details class="steps"' + (s.client_id ? '' : ' open') + '><summary>The AniList client (once)</summary><ol>' +
      '<li>On AniList, open <a href="https://anilist.co/settings/developer" target="_blank" rel="noopener">Settings → Developer</a> and press <b>Create New Client</b>.</li>' +
      '<li>Name it <b>Daf</b>, and for the Redirect URL paste <code>' + esc(s.redirect) + '</code> <button class="linkbtn" data-al="copy" data-v="' + esc(s.redirect) + '">Copy</button> exactly as it is.</li>' +
      '<li>Save, then paste its <b>Client ID</b> (a number) here.</li></ol>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap"><input class="field" id="alcid" inputmode="numeric" placeholder="Client ID" value="' + esc(s.client_id || '') + '" style="width:12em"><button class="btn sm" data-al="save">Save</button></div></details>';
}

document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-al]'); if (!b) return;
  const a = b.dataset.al;
  try {
    if (a === 'copy') { await navigator.clipboard.writeText(b.dataset.v); toast('Copied'); return; }
    if (a === 'save') { await api('/api/anilist', { method: 'PUT', body: JSON.stringify({ client_id: ($('#alcid') || {}).value || '' }) }); toast('Saved'); }
    if (a === 'forget') { await api('/api/anilist', { method: 'DELETE' }); toast('Signed out'); }
    prefs($('#alcard'));
  } catch(err){ toast(err.message); }
});

C.AniList = { prefs };
})();
