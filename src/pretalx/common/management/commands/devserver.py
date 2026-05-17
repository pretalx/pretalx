# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""``runserver`` plus the frontend (Vite) dev server.

We do not override runserver directly, because we need
``whitenoise.runserver_nostatic`` to win the override game, so that
development serves static files through whitenoise exactly like
production.

When ``VITE_DEV_MODE`` is set, additionally starts the Vite dev server
(``npm start``) for HMR; otherwise it is a plain ``runserver``.
"""

import atexit
import os
from pathlib import Path
from subprocess import Popen, TimeoutExpired

from django.conf import settings
from django.core.management.commands.runserver import Command as Parent
from django.utils.autoreload import DJANGO_AUTORELOAD_ENV


class Command(Parent):
    def handle(self, *args, **options):
        if not settings.VITE_DEV_MODE:
            super().handle(*args, **options)
            return

        # Django's autoreloader runs handle() in two processes: the watching
        # parent and the reloaded child (the latter has RUN_MAIN=true). Start
        # the Vite dev server only in the parent, so a single long-lived
        # server survives Django code reloads instead of being respawned (and
        # clashing on its port) on every change. Reap it via atexit so it does
        # not outlive runserver.
        if os.environ.get(DJANGO_AUTORELOAD_ENV) != "true":
            frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
            vite_server = Popen(["npm", "start"], cwd=frontend_dir)  # noqa: S607 -- npm is commonly installed in user paths

            def cleanup():
                vite_server.terminate()
                try:
                    vite_server.wait(timeout=5)
                except TimeoutExpired:
                    vite_server.kill()

            atexit.register(cleanup)

        super().handle(*args, **options)
