"""Credentials, read where they already live (like the desk does). Nothing is copied.

- FreshRSS: the homepage's HOMEPAGE_VAR_FRESHRSS_PASS (the API password the desk's
  Fever calls use) with user Franz_Rosenzweig. The vault's FRESHRSS_API_PASS was stale
  on 2026-10-09.
- Karakeep: the vault's KARAKEEP_API_KEY, else the homepage's key.
- /srv/docker/daf/daf.env, if present, overrides any of these by the same names.
"""
import re
from functools import lru_cache

from . import config

# Other .env files to read keys from, separated by ":" (DAF_SECRET_FILES), then STATE/daf.env last.
FILES = [f for f in config.setting("DAF_SECRET_FILES").split(":") if f] + [str(config.STATE / "daf.env")]


def _read(path):
    out = {}
    try:
        for line in open(path, encoding="utf-8"):
            m = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return out


@lru_cache(maxsize=1)
def env():
    merged = {}
    for f in FILES:
        merged.update(_read(f))
    return merged


def freshrss():
    e = env()
    return (e.get("DAF_FRESHRSS_USER") or "Franz_Rosenzweig",
            e.get("DAF_FRESHRSS_PASS") or e.get("HOMEPAGE_VAR_FRESHRSS_PASS") or "")


def karakeep_key():
    e = env()
    return e.get("DAF_KARAKEEP_KEY") or e.get("KARAKEEP_API_KEY") or e.get("HOMEPAGE_VAR_KARAKEEP_KEY") or ""


def claude_model():
    return env().get("DAF_CLAUDE_MODEL") or env().get("CLAUDE_MODEL") or "claude-sonnet-5-5"
