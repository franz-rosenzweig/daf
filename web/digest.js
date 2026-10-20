/* Preferences → Morning email (daf/digest.py): what came into the Library in the last day, with
   its summaries, from your Proton address to itself at the hour you pick. */
(function(){
const C = window.DafCore, { $, esc, api, toast, ago } = C;
let G = null;
const hour = h => (h % 12 || 12) + ':00 ' + (h < 12 ? 'am' : 'pm');

function draw(card){
  const d = G.digest, last = G.last;
  if (!G.configured) { card.innerHTML = '<h2>Morning email</h2><p class="mute" style="margin:0">Needs Proton Mail Bridge on morten (the office agent’s PROTON_USER and PROTON_BRIDGE_PASSWORD).</p>'; return; }
  card.innerHTML = '<h2>Morning email</h2>' +
    '<p class="mute" style="margin:0">What you saved to the Library in the last day, each with its summary, and how much waits in the Feed. It comes from daf@tiresia.xyz, and only on a day something came in.</p>' +
    '<div class="prow"><div class="d"><b>Send it</b><span>' + (last && last.sent ? 'The last one went ' + ago(last.at) + ' with ' + last.new + ' new.' : last && last.error ? 'The last one didn’t go: ' + esc(last.error) : 'Right now it would have ' + G.now.new + ' new' + (G.now.feed ? ' and ' + G.now.feed + ' in the Feed' : '') + '.') + '</span></div>' +
      '<input type="checkbox" class="sw" id="dgon"' + (d.on ? ' checked' : '') + ' aria-label="Send the morning email"></div>' +
    '<div class="prow"><div class="d"><b>At</b><span>In your home time zone.</span></div><select class="field" id="dghour" style="width:auto">' +
      [4, 5, 6, 7, 8, 9, 10, 11, 12].map(h => '<option value="' + h + '"' + (h === d.hour ? ' selected' : '') + '>' + hour(h) + '</option>').join('') + '</select></div>' +
    '<div class="prow"><div class="d"><b>The Feed too</b><span>How many new posts, by folder.</span></div><input type="checkbox" class="sw" id="dgfeed"' + (d.feed ? ' checked' : '') + ' aria-label="Include the Feed"></div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap"><a class="btn sm" href="/api/digest/preview" target="_blank" rel="noopener">See it</a><button class="btn sm" data-dg="send">Send one now</button></div>';
}
async function put(body, said){
  try { const r = await api('/api/digest', { method: 'PUT', body: JSON.stringify(body) }); G.digest = r.digest; toast(said); }
  catch(e){ toast(e.message); }
  draw($('#digestcard'));
}
document.addEventListener('change', e => {
  if (e.target.id === 'dgon') put({ on: e.target.checked }, e.target.checked ? 'The morning email is on, at ' + hour(G.digest.hour) : 'No morning email');
  if (e.target.id === 'dghour') put({ hour: +e.target.value }, 'At ' + hour(+e.target.value));
  if (e.target.id === 'dgfeed') put({ feed: e.target.checked }, e.target.checked ? 'With the Feed' : 'Without the Feed');
});
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-dg="send"]'); if (!b) return;
  b.disabled = true; b.textContent = 'Sending…';
  try { const r = await api('/api/digest/send', { method: 'POST' }); toast('Sent: ' + r.subject); }
  catch(err){ toast(err.message); }
  b.disabled = false; b.textContent = 'Send one now';
});

C.Digest = { prefs: async card => { G = await api('/api/digest'); draw(card); } };
})();
