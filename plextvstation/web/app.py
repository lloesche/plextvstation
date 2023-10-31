import os
import cherrypy
from prometheus_client.exposition import generate_latest, CONTENT_TYPE_LATEST
from typing import Optional, Dict, Callable
from ..plex import PlexDB
from ..utils import dataclass2html_table


class WebApp:
    def __init__(
        self,
        plexdb: PlexDB,
        mountpoint: str = "/",
        health_conditions: Optional[Dict[str, Callable[[], bool]]] = None,
    ) -> None:
        self.plexdb = plexdb
        self.mountpoint = mountpoint
        local_path = os.path.abspath(os.path.dirname(__file__))
        config = {
            "tools.gzip.on": True,
            "tools.staticdir.index": "index.html",
            "tools.staticdir.on": True,
            "tools.staticdir.dir": f"{local_path}/static",
        }
        self.config = {"/": config}
        self.health_conditions = health_conditions if health_conditions is not None else {}
        if self.mountpoint not in ("/", ""):
            self.config[self.mountpoint] = config

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.allow(methods=["GET"])  # type: ignore
    def health(self) -> str:
        cherrypy.response.headers["Content-Type"] = "text/plain"
        unhealthy = [f"- {name}" for name, fn in self.health_conditions.items() if not fn()]
        if not unhealthy:
            cherrypy.response.status = 200
            return "ok\r\n"
        else:
            cherrypy.response.status = 503
            cherrypy.response.headers["Content-Type"] = "text/plain"
            return "not ok\r\n\r\n" + "\r\n".join(unhealthy) + "\r\n"

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.allow(methods=["GET"])  # type: ignore
    def metrics(self) -> bytes:
        cherrypy.response.headers["Content-Type"] = CONTENT_TYPE_LATEST
        return generate_latest()

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.allow(methods=["GET"])  # type: ignore
    def movies(self) -> str:
        cherrypy.response.headers["Content-Type"] = "text/html"
        return dataclass2html_table(self.plexdb.movies)

    @cherrypy.expose  # type: ignore
    @cherrypy.tools.allow(methods=["GET"])  # type: ignore
    def shows(self) -> str:
        cherrypy.response.headers["Content-Type"] = "text/html"
        return dataclass2html_table(self.plexdb.tv_shows)
