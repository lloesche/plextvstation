import threading
import cherrypy
from argparse import ArgumentParser
from typing import Optional, Any
from ..logging import log


class WebServer(threading.Thread):
    def __init__(
        self,
        web_app: Any,
        web_host: str = "::",
        web_port: int = 9898,
        ssl_cert: Optional[str] = None,
        ssl_key: Optional[str] = None,
        extra_config: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.name = "webserver"
        self.web_app = web_app
        self.web_host = web_host
        self.web_port = web_port
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        self.extra_config = extra_config or {}
        self.daemon = True

    @property
    def serving(self) -> bool:
        return bool(cherrypy.engine.state == cherrypy.engine.states.STARTED)

    def run(self) -> None:
        # CherryPy always prefixes its log messages with a timestamp.
        # The next line monkey patches that time method to return a
        # fixed string. So instead of having duplicate timestamps in
        # each web server related log message they are now prefixed
        # with the string 'CherryPy'.
        cherrypy.config.reset()
        cherrypy._cplogging.LogManager.time = lambda self: "CherryPy"
        cherrypy.engine.unsubscribe("graceful", cherrypy.log.reopen_files)

        # We always mount at / as well as any user configured --web-path
        cherrypy.tree.mount(
            self.web_app,
            "",
            self.web_app.config,
        )
        if self.web_app.mountpoint not in ("/", ""):
            cherrypy.tree.mount(
                self.web_app,
                self.web_app.mountpoint,
                self.web_app.config,
            )
        ssl_args = {}
        if self.ssl_cert and self.ssl_key:
            ssl_args = {
                "server.ssl_module": "builtin",
                "server.ssl_certificate": self.ssl_cert,
                "server.ssl_private_key": self.ssl_key,
            }
        cherrypy.config.update(
            {
                "global": {
                    "engine.autoreload.on": False,
                    "server.socket_host": self.web_host,
                    "server.socket_port": self.web_port,
                    "log.screen": False,
                    "log.access_file": "",
                    "log.error_file": "",
                    "tools.log_headers.on": False,
                    "tools.encode.on": True,
                    "tools.encode.encoding": "utf-8",
                    "request.show_tracebacks": False,
                    "request.show_mismatched_params": False,
                    **ssl_args,
                    **self.extra_config,
                }
            }
        )
        cherrypy.engine.start()
        cherrypy.engine.block()

    def shutdown(self) -> None:
        log.debug("Received request to shutdown http server threads")
        cherrypy.engine.exit()

    def mount(self, mountpoint: str, app: Any) -> None:
        cherrypy.tree.mount(app, mountpoint, app.config)


def add_args(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--web-host",
        dest="web_host",
        help="Web server host to listen on (default: ::)",
        default="::",
    )
    parser.add_argument(
        "--web-port",
        dest="web_port",
        help="Web server port to listen on (default: 9898)",
        default=9898,
        type=int,
    )
    parser.add_argument(
        "--web-ssl-cert",
        dest="web_ssl_cert",
        help="Web server SSL certificate file",
    )
    parser.add_argument(
        "--web-ssl-key",
        dest="web_ssl_key",
        help="Web server SSL key file",
    )
