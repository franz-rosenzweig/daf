"""One login for the owner (username + password), signed cookies for the browser, bearer tokens
for devices (the Kindle, the phone, AntennaPod).

auth.json lives in STATE, outside the vault and outside git:
    {"user": "reader", "salt": hex, "hash": hex, "secret": hex}
Changing the password replaces the secret, which signs out every browser at once.
Device tokens are stored only as SHA-256 hashes in the devices table.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from . import config

COOKIE = "daf"
COOKIE_DAYS = 365


def _scrypt(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _load():
    try:
        return json.loads(config.AUTH_PATH.read_text())
    except (FileNotFoundError, ValueError):
        return None


DEFAULT_USER = "reader"     # only for a new install: an auth.json that names a user keeps it


def _save(data):
    config.STATE.mkdir(parents=True, exist_ok=True)
    tmp = config.AUTH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.chmod(0o600)
    tmp.replace(config.AUTH_PATH)


def set_password(password, user=None, rotate=False):
    """New password (and username, if given). rotate=True also signs out every browser."""
    old = _load() or {}
    salt = secrets.token_bytes(16)
    _save({"user": (user or old.get("user") or DEFAULT_USER).strip().lower(),
           "salt": salt.hex(), "hash": _scrypt(password, salt).hex(),
           "secret": secrets.token_hex(32) if rotate or not old.get("secret") else old["secret"]})


def set_user(user):
    a = _load() or {}
    a["user"] = user.strip().lower()
    _save(a)


def sign_out_everywhere():
    a = _load() or {}
    a["secret"] = secrets.token_hex(32)
    _save(a)


def username():
    return (_load() or {}).get("user") or DEFAULT_USER


def has_password():
    return bool((_load() or {}).get("hash"))


def check_password(password):
    a = _load()
    if not a or not a.get("hash"):
        return False
    return hmac.compare_digest(_scrypt(password, bytes.fromhex(a["salt"])).hex(), a["hash"])


def check_login(user, password):
    """Both must match; the password is checked either way, so a wrong name takes as long."""
    ok_pw = check_password(password)
    ok_user = hmac.compare_digest((user or "").strip().lower().encode(), username().encode())
    return ok_pw and ok_user


def _sign(payload):
    a = _load() or {}
    key = bytes.fromhex(a.get("secret", "00"))
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def make_cookie():
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + COOKIE_DAYS * 86400}).encode())
    return payload.decode() + "." + _sign(payload)


def check_cookie(value):
    if not value or "." not in value:
        return False
    payload, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload.encode()), sig):
        return False
    try:
        return json.loads(base64.urlsafe_b64decode(payload))["exp"] > time.time()
    except (ValueError, KeyError):
        return False


def new_device_token(conn, name):
    token = secrets.token_urlsafe(24)
    conn.execute("INSERT INTO devices (token_hash, name, created) VALUES (?, ?, ?)",
                 (hashlib.sha256(token.encode()).hexdigest(), name, int(time.time())))
    return token


def check_device(conn, token):
    if not token:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute("SELECT name FROM devices WHERE token_hash = ?", (h,)).fetchone()
    if row:
        conn.execute("UPDATE devices SET last_seen = ? WHERE token_hash = ?", (int(time.time()), h))
        return row["name"]
    return None
