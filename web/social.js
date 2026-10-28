/* Preferences → Instagram (daf/social.py): the signed-in session Daf fetches reels with. Whether
   it's there and when it was last renewed, the switch that lets the browser extension keep it fresh,
   the reels waiting for it, and Forget. */
(function(){
const C = window.DafCore, { $, esc, api, toast } = C;

function ago(t){
  if (!t) return '';
  const m = Math.round((Date.now() / 1000 - t) / 60);
  if (m < 2) return 'just now';
  if (m < 90) return m + ' minutes ago';
  const h = Math.round(m / 60);
  if (h < 36) return h + ' hours ago';
  return Math.round(h / 24) + ' days ago';
}
// The Android app signs in itself (InstagramActivity): Instagram's own page in a window of its own.
const app = () => !!(window.dafShell && window.dafShell.can && window.dafShell.can('instagram'));
const BY = { web: 'this page', browser: 'the browser extension', safari: 'Safari' };
const by = n => BY[n] || (/^android/.test(n || '') ? 'the Android app' : /^mac/.test(n || '') ? 'the Mac app' : n || '');

async function prefs(card){
  const s = await api('/api/instagram');
  const state = s.expired ? '<b style="color:var(--bad)">Instagram turned the sign-in away</b> ' + esc(ago(s.expired)) + '. Renew it below.'
    : s.signed_in ? 'Signed in. Renewed ' + esc(ago(s.updated)) + (s.by ? ' by ' + esc(by(s.by)) : '') + '.'
    : 'Not signed in yet. Reels need it: Instagram shows almost nothing to a visitor.';
  card.innerHTML = '<h2>Instagram</h2>' +
    '<p class="mute" style="margin-top:0">Share a reel to Daf (or save its link) and Daf keeps the video, its caption and a transcript you can highlight. ' +
    'To fetch it, Daf uses your own Instagram sign-in, kept on your server and nowhere else.</p>' +
    '<div class="prow"><div class="d"><b>Sign-in</b><span>' + state + '</span></div><div style="display:flex;gap:8px">' +
      (s.signed_in ? '<button class="btn sm" data-ig="forget">Forget it</button>' : '') +
      (app() ? '<button class="btn sm primary" data-ig="signin">' + (s.signed_in ? 'Sign in again' : 'Sign in to Instagram') + '</button>' : '') + '</div></div>' +
    '<div class="prow"><div class="d"><b>Keep Daf signed in from my browser</b><span>When you’re on instagram.com in a browser with the Daf extension, it sends Instagram’s sign-in to Daf whenever it has changed, so Daf’s never runs out. Only instagram.com’s cookies, only to your Daf.</span></div>' +
      '<input type="checkbox" class="sw" data-ig="browser" aria-label="Keep Daf signed in from my browser"' + (s.from_browser ? ' checked' : '') + '></div>' +
    (s.waiting ? '<div class="prow"><div class="d"><b>Waiting</b><span>' + s.waiting + (s.waiting === 1 ? ' reel is' : ' reels are') + ' waiting for a sign-in. ' + (s.signed_in && !s.expired ? (s.waiting === 1 ? 'It’s on its way.' : 'They’re on their way.') : (s.waiting === 1 ? 'It comes in by itself' : 'They come in by themselves') + ' once Daf has one.') + '</span></div></div>' : '') +
    '<details class="steps"><summary>How to sign Daf in</summary><ol>' +
      '<li>Turn on “Keep Daf signed in from my browser” above.</li>' +
      '<li>In Zen, Firefox or Fennec with the Daf extension, open <a href="https://www.instagram.com/" target="_blank" rel="noopener">instagram.com</a> and sign in if it asks.</li>' +
      '<li>That’s all: this card says “Signed in” a moment later. If Instagram ever turns it away, visiting instagram.com again renews it.</li></ol></details>';
}

document.addEventListener('change', async e => {
  const t = e.target.closest && e.target.closest('[data-ig="browser"]'); if (!t) return;
  try { await api('/api/instagram', { method: 'PUT', body: JSON.stringify({ from_browser: t.checked }) });
    toast(t.checked ? 'The extension keeps Daf signed in to Instagram' : 'The extension won’t send Instagram’s sign-in'); }
  catch(err){ toast(err.message); t.checked = !t.checked; }
});
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-ig="forget"], [data-ig="signin"]'); if (!b) return;
  try {
    if (b.dataset.ig === 'signin') { if (await window.dafShell.instagram()) toast('Signed in to Instagram'); }
    else { await api('/api/instagram/cookies', { method: 'DELETE' }); toast('Daf forgot the Instagram sign-in'); }
    prefs($('#igcard'));
  } catch(err){ toast(err.message); }
});

C.Social = { prefs };
})();
