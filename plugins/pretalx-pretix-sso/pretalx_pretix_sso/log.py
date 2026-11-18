"""Send the plugin's log messages (logins, pretix fetches, tag syncs, ...) to
stdout, in pretalx's log format, and to pretalx's log file.

pretalx's own console handler writes to stderr, and celery replaces the root
logging setup in the task worker, so the plugin's logger gets its own handlers
and does not propagate: every message is written exactly once to stdout and once
to the log file, in the web and the worker processes alike.
"""

import logging
import sys

PLUGIN_LOGGER = "pretalx_pretix_sso"
DEFAULT_FORMAT = "%(levelname)s %(asctime)s %(name)s %(module)s %(message)s"


class StdoutHandler(logging.StreamHandler):
    """Writes to the process's real stdout and flushes every record
    (StreamHandler.emit does), so lines are not held back in a buffer when
    stdout is a pipe, as it is in containers.

    sys.__stdout__ rather than sys.stdout: the celery worker replaces sys.stdout
    with a proxy that re-logs everything through celery's own handler (stderr).
    """

    def __init__(self):
        super().__init__(sys.__stdout__)

    @property
    def stream(self):
        return sys.__stdout__

    @stream.setter
    def stream(self, value):
        pass


def configure_plugin_logging():
    plugin_logger = logging.getLogger(PLUGIN_LOGGER)
    if any(isinstance(h, StdoutHandler) for h in plugin_logger.handlers):
        return  # already configured
    root = logging.getLogger()
    stdout = StdoutHandler()
    formatter = next((h.formatter for h in root.handlers if h.formatter), None)
    stdout.setFormatter(formatter or logging.Formatter(DEFAULT_FORMAT))
    plugin_logger.addHandler(stdout)
    # Keep writing to pretalx.log as well
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            plugin_logger.addHandler(handler)
    plugin_logger.setLevel(root.level or logging.INFO)
    plugin_logger.propagate = False
