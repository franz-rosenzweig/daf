"""Which reader is in charge of the Feed: FreshRSS (sources/freshrss.py), or Daf itself
(sources/rss.py) once import_freshrss has run (settings.feed_reader = "daf"). Both have the same
functions, so the rest of Daf asks this module and doesn't care which it is."""
from .. import config


def daf():
    return config.load_settings().get("feed_reader") == "daf"


def get():
    from . import freshrss, rss
    return rss if daf() else freshrss


def name():
    return "Daf" if daf() else "FreshRSS"
