"""Run Daf: the API and web app on 127.0.0.1 and the Tailscale IP, plus the sync loop."""
import logging
import socket

import uvicorn

from . import config
from . import media
from .app import app, start_sync_thread


def _bind(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    return s


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sockets = [_bind(h, config.PORT) for h in config.HOSTS]
    start_sync_thread()
    media.start_worker()
    server = uvicorn.Server(uvicorn.Config(app, log_level="info", proxy_headers=False, access_log=False))
    server.run(sockets=sockets)


if __name__ == "__main__":
    main()
