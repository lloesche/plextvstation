import logging

log_format = "%(asctime)s|%(levelname)5s|%(process)d|%(threadName)10s  %(message)s"
logging.basicConfig(level=logging.WARNING, format=log_format)

log = logging.getLogger("plextvstation")
log.setLevel(logging.INFO)
