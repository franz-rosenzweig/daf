"""Daf: a personal Readwise for one reader's own stack. See PLAN.md."""

from . import netfix as _netfix

_netfix.install()          # name lookups one family at a time, when DAF_SERIAL_DNS=1 (netfix.py)
