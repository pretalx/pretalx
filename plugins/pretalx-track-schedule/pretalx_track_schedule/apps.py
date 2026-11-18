import re
from importlib import metadata
from pathlib import Path

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


def _version():
    """The version from pyproject.toml, so it is only ever set there.

    Installed packages carry it in their metadata (pyproject.toml itself is not
    installed); a plain source checkout reads the file directly."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.exists():
        match = re.search(
            r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE
        )
        if match:
            return match.group(1)
    try:
        return metadata.version("pretalx-track-schedule")
    except metadata.PackageNotFoundError:
        return "unknown"


class PluginApp(AppConfig):
    name = "pretalx_track_schedule"
    verbose_name = _("Schedule by track")

    class PretalxPluginMeta:
        name = _("Schedule by track")
        author = "Wildfire Retreat"
        version = _version()
        visible = True
        description = _(
            "A public schedule page with one column per track instead of per "
            "room, at /<event>/p/track-schedule/."
        )
        category = "FEATURE"

    def ready(self):
        from . import signals  # noqa: F401
