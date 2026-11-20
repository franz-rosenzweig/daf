"""Fetching an address someone else chose: a feed's transcript, chapters or audio, a page's feed link,
a model's suggestion, a saved PDF. Daf only goes to public addresses for those, http or https, and
follows a redirect only to another public address, so a feed or a page can't send this server into
the machines and services around it. kindlesend.py holds the check itself (_public, _OPENER: the
rule fulltext.py and pages.py already use); this is the one door for the rest.

Addresses the owner set up (Calibre, Komga, Karakeep, Invidious) don't come through here."""
import urllib.parse
import urllib.request


class NotPublic(ValueError):
    """The address isn't a public http(s) one."""


def public_url(url):
    """True for an http(s) address whose host resolves only to public addresses."""
    from . import kindlesend
    u = urllib.parse.urlsplit(url or "")
    return u.scheme in ("http", "https") and bool(u.hostname) and kindlesend._public(u.hostname)  # noqa: SLF001


def check(url):
    if not public_url(url):
        raise NotPublic("Daf only fetches public addresses")
    return url


def open_public(req, timeout=30, opener=None):
    """urlopen for an address someone else chose: refused unless it's public, redirects re-checked.
    An opener of one's own (a feed's certificate setting) must re-check redirects the same way."""
    from . import kindlesend
    check(req.full_url if isinstance(req, urllib.request.Request) else req)
    return (opener or kindlesend._OPENER).open(req, timeout=timeout)  # noqa: SLF001
