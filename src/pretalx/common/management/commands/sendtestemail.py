# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.management.base import BaseCommand

from pretalx.common.mail import mail_send_task


class Command(BaseCommand):
    help = "Send a test email through pretalx's mail_send_task to verify email configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            nargs="+",
            help="One or more email addresses to send a test email to.",
        )

    def handle(self, *args, **options):
        for address in options["email"]:
            try:
                mail_send_task.apply(
                    kwargs={
                        "to": [address],
                        "subject": "pretalx test email",
                        "body": "This is a test email from pretalx to verify your email configuration is working correctly.",
                        "html": None,
                    }
                )
                self.stdout.write(self.style.SUCCESS(f"Test email sent to {address}"))
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Failed to send test email to {address}: {e}")
                )
