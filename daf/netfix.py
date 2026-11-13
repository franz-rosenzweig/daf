"""Name lookups one family at a time (DAF_SERIAL_DNS=1).

On some networks a lookup for IPv4 alone answers at once, and one for IPv6 alone too, but glibc's
usual lookup asks both together from one socket, and one of the two answers never comes back: every
new name then waits out the resolver's five-second timeout. With DAF_SERIAL_DNS=1 in Daf's
environment, Daf asks for IPv4 and then IPv6, one after the other. Off by default."""
import ipaddress
import os
import socket

_orig = socket.getaddrinfo


def _is_ip(host):
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        return True
    except ValueError:
        return False


def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family not in (0, socket.AF_UNSPEC) or not host or not isinstance(host, str) or host == "localhost" or _is_ip(host):
        return _orig(host, port, family, type, proto, flags)
    out, err = [], None
    for fam in (socket.AF_INET, socket.AF_INET6):
        try:
            out += _orig(host, port, fam, type, proto, flags)
        except socket.gaierror as e:
            err = e
    if out:
        return out
    raise err or socket.gaierror(socket.EAI_NONAME, "Name or service not known")


def install():
    if os.environ.get("DAF_SERIAL_DNS") == "1" and socket.getaddrinfo is _orig:
        socket.getaddrinfo = getaddrinfo
