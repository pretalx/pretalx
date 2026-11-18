"""Django settings for the plugin tests: pretalx's own settings, pointed at a
throwaway SQLite database and a known plugin configuration."""

import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="pretix-sso-tests-")
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
[plugin:pretalx_pretix_sso]
issuer = https://pretix.example.invalid/org/
client_id = test-client
client_secret = test-secret
api_token = test-token
""",
    encoding="utf-8",
)
os.environ["PRETALX_CONFIG_FILE"] = str(_cfg)
# Settings from the environment would override the config above
for key in list(os.environ):
    if key.startswith("PRETALX_PRETIX_SSO_"):
        del os.environ[key]

from pretalx.settings import *  # noqa: E402, F401, F403

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# pretalx keeps sessions in a separate Redis cache by default
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
