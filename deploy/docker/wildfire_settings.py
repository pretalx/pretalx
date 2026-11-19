# ruff: noqa: INP001 -- a single module installed into site-packages by /Dockerfile
"""Django settings for this image: pretalx's own (pretalx/settings.py, which
reads pretalx.cfg and PRETALX_* variables as usual), plus overrides pretalx has
no configuration option for. Selected with DJANGO_SETTINGS_MODULE in /Dockerfile.
"""

import os

from pretalx.settings import *  # noqa: F403

# pretalx keeps PostgreSQL connections for 120 s for reuse, but Django only
# closes an expired connection when the next request or Celery task starts or
# ends. Without traffic, every gunicorn and Celery worker therefore keeps an
# idle connection open indefinitely, and an Aurora Serverless v2 cluster,
# which only pauses with no connections, never pauses. Close connections at
# the end of each request and task instead (one connect per request).
# PRETALX_DB_CONN_MAX_AGE overrides, e.g. 120 for pretalx's default.
DATABASES["default"]["CONN_MAX_AGE"] = int(  # noqa: F405
    os.environ.get("PRETALX_DB_CONN_MAX_AGE", "0")
)
