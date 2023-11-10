import sys
import logging
from threading import Event
from signal import SIGTERM
from typing import Optional
from types import FrameType
from .utils import kill_children
from .logging import log
from .config import get_config
from .args import parse_args
from .utils import make_dirs, initializer
from . import __title__ as title, __version__ as version
from .web import WebServer, add_args as web_add_args
from .web.app import WebApp
from .plex import add_args as plex_add_args, validate_args as plex_validate_args, PlexDB
from .station import load_network, save_network, Network

shutdown_event = Event()


def shutdown(sig: int, frame: Optional[FrameType]) -> None:
    log.info("Shutting down")
    shutdown_event.set()


def main() -> None:
    args = parse_args([web_add_args, plex_add_args], [plex_validate_args])
    if args.verbose:
        log.setLevel(logging.DEBUG)

    log.info(f"{title} v{version} starting up...")
    initializer(shutdown)
    config = get_config(args)
    make_dirs(config)
    network: Network = load_network(config)

    web_server = WebServer(
        WebApp(plexdb=PlexDB(args)),
        web_host=args.web_host,
        web_port=args.web_port,
        ssl_cert=args.web_ssl_cert,
        ssl_key=args.web_ssl_key,
    )
    web_server.start()

    shutdown_event.wait()
    save_network(config, network)
    web_server.shutdown()
    kill_children(SIGTERM, ensure_death=True)
    log.info("Shutdown complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
