/* Safari only (build.sh puts it before background.js in dist/safari): the Daf app hands over Daf's
   address and a token of its own (the device "safari"), so there's nothing to paste. The app makes
   the token with the sign-in in its window; the extension's native half (mac/DafSafari) passes it
   on. A token Daf no longer knows is swapped for a new one the same way. */
(() => {
  const X = globalThis.browser || globalThis.chrome;
  if (!X || !X.runtime || !X.runtime.sendNativeMessage) return;
  const ask = msg => X.runtime.sendNativeMessage('xyz.tiresia.daf', msg);   // Safari sends it to this app whatever the name
  let busy = false;
  async function connect(tries, stale){
    if (busy) return; busy = true;
    try {
      for (let i = 0; i < tries; i++) {
        const s = await X.storage.local.get({ token: '' });
        if (s.token && s.token !== stale) return;
        let r = null;
        try { r = await ask(stale ? { op: 'connect', stale } : { op: 'connect' }); } catch (e) { /* the app isn't there */ }
        if (r && r.token) { await X.storage.local.set({ url: r.url, token: r.token }); return; }
        await new Promise(ok => setTimeout(ok, 2000));
      }
    } finally { busy = false; }
  }
  X.runtime.onInstalled.addListener(() => connect(20));
  if (X.runtime.onStartup) X.runtime.onStartup.addListener(() => connect(3));
  connect(1);
  // background.js asks again when Daf answers 401 to the token it has
  globalThis.dafSafariReconnect = stale => connect(15, stale);
})();
