"""Django settings for the plugin tests: pretalx's own settings, pointed at a
throwaway SQLite database and a known plugin configuration."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="pretix-sso-tests-")
_cfg = os.path.join(_tmp, "pretalx.cfg")
with open(_cfg, "w") as f:
    f.write(
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
"""
    )
os.environ["PRETALX_CONFIG_FILE"] = _cfg
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
