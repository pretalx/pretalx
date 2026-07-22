# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import os
import select
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from django.core.management.commands import shell
from django.db import connection
from django_scopes import scope, scopes_disabled

from pretalx.event.models import Event


class Command(shell.Command):
    scoped_event = None

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--print-sql", action="store_true", help="Print all SQL queries."
        )
        parser.add_argument(
            "--unsafe-disable-scopes",
            action="store_true",
            help="Don’t use scoping, access data for all events.",
        )
        parser.add_argument("--event", help="Event (slug) to scope all queries to.")

    def get_auto_imports(self):
        return [
            *super().get_auto_imports(),
            "django.conf.settings",
            "django.db.models.Q",
            "django.utils.timezone.now",
        ]

    def get_namespace(self, **options):
        namespace = super().get_namespace(**options)
        if self.scoped_event:
            namespace["event"] = self.scoped_event
        return namespace

    def is_non_interactive(self, options):
        # With -c or piped stdin, Django runs the code and exits instead of
        # opening a shell, so we add no output.
        if options.get("command"):
            return True
        if sys.platform == "win32" or sys.stdin.isatty():
            return False
        with suppress(OSError, ValueError):
            return bool(select.select([sys.stdin], [], [], 0)[0])
        return False

    def handle(self, *args, **options):
        if self.is_non_interactive(options):
            options["verbosity"] = 0

        if options.pop("print_sql", None):
            connection.force_debug_cursor = True
            logger = logging.getLogger("django.db.backends")
            logger.setLevel(logging.DEBUG)
            # Further configuration for logger handler can be added here if needed
            # For example, to ensure output goes to stdout/stderr:
            if not logger.handlers:
                handler = logging.StreamHandler()
                logger.addHandler(handler)

        if options.pop("unsafe_disable_scopes", None):
            with scopes_disabled():
                return super().handle(*args, **options)

        event_slug_str = options.pop("event", None)
        if not event_slug_str:
            self.stdout.write(
                self.style.ERROR(
                    "Call this command with an --event or disable scoping with --unsafe-disable-scopes!"
                )
            )
            sys.exit(-1)

        event = Event.objects.filter(slug__iexact=event_slug_str.strip()).first()
        if not event:
            self.stdout.write(self.style.ERROR("Event not found!"))
            sys.exit(-1)
        self.scoped_event = event

        if (
            options["no_startup"]
            or os.environ.get("PYTHONSTARTUP")
            or self.is_non_interactive(options)
        ):
            # The user wants to skip startup execution or has their own startup file,
            # or we aren’t opening an interactive shell at all.
            with scope(event=event):
                return super().handle(*args, **options)

        # We’re setting the local event variable to the scoped event in a namedtempfile
        # and are setting that to os.environ
        runline = f"event = Event.objects.get(slug='{event.slug}')"
        startup_file_name = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w+", suffix=".py", delete=False
            ) as f:
                startup_file_name = f.name
                f.write(runline)
            os.environ["PYTHONSTARTUP"] = startup_file_name
            use_ipython_style = False
            interface = options.get("interface")
            if interface not in ("bpython", "python"):
                with suppress(ImportError):
                    import IPython  # noqa: F401, PLC0415 -- optional dependency

                    use_ipython_style = True

            if use_ipython_style:
                self.stdout.write(self.style.SUCCESS("In [0]: ") + "event")
                self.stdout.write(self.style.ERROR("Out[0]: ") + repr(event))
            else:
                self.stdout.write(self.style.SUCCESS(">>> event"))
                self.stdout.write(self.style.SUCCESS(repr(event)))
            self.stdout.write()

            with scope(event=event):
                return super().handle(*args, **options)
        finally:
            if (
                "PYTHONSTARTUP" in os.environ
            ):  # pragma: no branch -- only untaken on tempfile creation failure
                del os.environ["PYTHONSTARTUP"]

            if startup_file_name:
                startup_file = Path(startup_file_name)
                if startup_file.exists():
                    startup_file.unlink()

    def ipython(self, options):
        from IPython import start_ipython  # noqa: PLC0415 -- optional dependency
        from traitlets.config import Config  # noqa: PLC0415 -- optional dependency

        config = Config()
        config.TerminalIPythonApp.display_banner = False
        config.TerminalInteractiveShell.enable_tip = False
        start_ipython(argv=[], user_ns=self.get_namespace(**options), config=config)
