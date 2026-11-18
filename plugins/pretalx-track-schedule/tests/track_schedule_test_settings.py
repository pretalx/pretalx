"""Django settings for the plugin tests: pretalx's own settings, pointed at a
throwaway SQLite database and a known plugin configuration."""

import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="track-schedule-tests-")
_cfg = Path(_tmp) / "pretalx.cfg"
_cfg.write_text(
    f"""[filesystem]
data = {_tmp}
[database]
backend = sqlite3
name = {_tmp}/db.sqlite3
[site]
url = https://pretalx.example.invalid
debug = True
[redis]
location = False
""",
    encoding="utf-8",
)
os.environ["PRETALX_CONFIG_FILE"] = str(_cfg)

from pretalx.settings import *  # noqa: E402, F401, F403

# run-tests.sh puts the plugin source on the path without installing it, so
# pretalx does not find it through its entry point
if "pretalx_track_schedule" not in PLUGINS:  # noqa: F405
    PLUGINS.append("pretalx_track_schedule")  # noqa: F405
    INSTALLED_APPS.append("pretalx_track_schedule")  # noqa: F405

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# pretalx keeps sessions in a separate Redis cache by default
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# No Celery broker: background tasks (mails, image processing) run inline
CELERY_TASK_ALWAYS_EAGER = True
