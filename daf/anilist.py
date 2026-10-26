"""AniList: Daf keeps the sign-in that manga reading goes to AniList with.

/srv/docker/manga-import/manga-track.py works out, every hour, how far each manga series has been
read (Komga's read state: the Kindle, Daf's manga reader, Komga itself) and sets that progress on
AniList. It used to do that through Suwayomi's AniList login; since Suwayomi's retirement
(2026-10-26) the sign-in lives here, in STATE/anilist/token.json (mode 600, never logged), and the
script reads it from there.

Signing in is AniList's own "implicit grant": Nathan makes an API client once on AniList (its
redirect URL is Daf's /anilist page) and gives Daf its id; Connect AniList sends him to AniList,
which sends him back to /anilist with a token that lasts a year; the page hands it to Daf. Renewing
is the same button.
"""
import json
import os
import time
import urllib.request

from . import config

DIR = config.STATE / "anilist"
TOKEN = DIR / "token.json"
API = "https://graphql.anilist.co"
UA = "Daf/1.0 (personal reading app)"      # AniList's front door turns Python's own User-Agent away (403)


def _gql(token, query, variables=None):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": "Bearer " + token, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    if d.get("errors"):
        raise ValueError(d["errors"][0].get("message") or "AniList said no")
    return d["data"]


def client_id():
    return str((config.load_settings().get("anilist") or {}).get("client_id") or "").strip()


def set_client_id(cid):
    s = config.load_settings()
    s["anilist"] = {"client_id": str(cid or "").strip()[:20]}
    config.save_settings(s)


def authorize_url():
    cid = client_id()
    return f"https://anilist.co/api/v2/oauth/authorize?client_id={cid}&response_type=token" if cid else None


def save_token(access_token, expires_in=None):
    """Checks the token with AniList (whose account is it?) and keeps it."""
    access_token = str(access_token or "").strip()
    if not access_token:
        raise ValueError("No token came back from AniList")
    viewer = _gql(access_token, "{ Viewer { id name } }")["Viewer"]
    DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DIR, 0o700)
    data = {"access_token": access_token, "user": viewer,
            "expires_at": int(time.time()) + int(expires_in or 365 * 86400), "saved": int(time.time())}
    tmp = TOKEN.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.chmod(tmp, 0o600)
    tmp.replace(TOKEN)
    return status()


def forget():
    TOKEN.unlink(missing_ok=True)
    return status()


def status():
    try:
        t = json.loads(TOKEN.read_text())
    except (FileNotFoundError, ValueError):
        t = None
    out = {"client_id": client_id(), "connected": bool(t), "user": (t or {}).get("user"),
           "expires_at": (t or {}).get("expires_at"), "saved": (t or {}).get("saved")}
    out["expired"] = bool(t and t.get("expires_at") and t["expires_at"] < time.time())
    out["redirect"] = config.public_url().rstrip("/") + "/anilist"
    try:
        log = (config.STATE.parent / "manga-import" / "last-run.json")
        out["last_run"] = json.loads(log.read_text()) if log.exists() else None
    except ValueError:
        out["last_run"] = None
    return out


# The page AniList sends you back to, with the token in the address's #fragment (which never reaches
# a server). It hands the token to Daf, signed in, and goes on to Preferences → AniList.
CALLBACK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AniList · Daf</title><style>body{font:16px system-ui,sans-serif;margin:15vh auto;max-width:28em;padding:0 20px;color:#3a2f22;background:#f6efe3}</style></head>
<body><p id="s">Connecting AniList…</p><script>
(async () => {
  const p = new URLSearchParams(location.hash.slice(1)), s = document.getElementById('s');
  history.replaceState(null, '', '/anilist');
  if (!p.get('access_token')) { s.textContent = 'AniList didn’t send a sign-in back. Go back to Daf and try Connect AniList again.'; return; }
  try {
    const r = await fetch('/api/anilist/token', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: p.get('access_token'), expires_in: p.get('expires_in') }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.statusText);
    location.replace('/#prefs/anilist');
  } catch (e) { s.textContent = 'Daf couldn’t keep the AniList sign-in: ' + e.message + '. Are you signed in to Daf in this browser?'; }
})();
</script></body></html>"""
