# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

import warnings
from smtplib import SMTPResponseException

from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes import ScopedManager

from pretalx.common.models.mixins import PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.rules import can_edit_mail
from pretalx.person.models.user import User
from pretalx.submission.rules import orga_can_change_submissions


class QueuedMailQuerySet(models.QuerySet):
    def prefetch_users(self, event):
        return self.prefetch_related(
            models.Prefetch("to_users", queryset=User.objects.with_speaker_code(event))
        )

    def with_computed_state(self):
        return self.annotate(
            computed_state=models.Case(
                models.When(
                    state=QueuedMailStates.DRAFT,
                    error_data__isnull=False,
                    then=models.Value("failed"),
                ),
                default=models.F("state"),
                output_field=models.CharField(),
            )
        )


class QueuedMailManager(models.Manager.from_queryset(QueuedMailQuerySet)):
    pass


class QueuedMail(PretalxModel):
    """Emails in pretalx are rarely sent directly, hence the name QueuedMail.

    This mechanism allows organisers to make sure they send out the right
    content, and to include personal changes in emails.

    :param sent: ``None`` if the mail has not been sent yet.
    :param to_users: All known users to whom this email is addressed.
    :param to: A comma-separated list of email addresses to whom this email
        is addressed. Does not contain any email addresses known to belong
        to users.
    """

    log_prefix = "pretalx.mail"

    event = models.ForeignKey(
        to="event.Event",
        on_delete=models.PROTECT,
        related_name="queued_mails",
        null=True,
        blank=True,
    )
    template = models.ForeignKey(
        to="mail.MailTemplate",
        related_name="mails",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    to = models.CharField(
        max_length=1000,
        verbose_name=_("To"),
        help_text=_("One email address or several addresses separated by commas."),
        null=True,
        blank=True,
    )
    to_users = models.ManyToManyField(to="person.User", related_name="mails")
    reply_to = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name=_("Reply-To"),
        help_text=_("By default, the organiser address is used as Reply-To."),
    )
    cc = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name=_("CC"),
        help_text=_("One email address or several addresses separated by commas."),
    )
    bcc = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name=_("BCC"),
        help_text=_("One email address or several addresses separated by commas."),
    )
    subject = models.CharField(
        max_length=200, verbose_name=pgettext_lazy("email subject", "Subject")
    )
    text = models.TextField(verbose_name=_("Text"))
    # Set at send-time when the rendered HTML diverges from what
    # re-rendering ``text`` would produce; cleared on organiser edit.
    text_html = models.TextField(null=True, blank=True)
    sent = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent at"))
    state = models.CharField(
        max_length=10,
        choices=QueuedMailStates.choices,
        default=QueuedMailStates.DRAFT,
        db_index=True,
    )
    error_data = models.JSONField(null=True, blank=True, default=None)
    error_timestamp = models.DateTimeField(null=True, blank=True)
    locale = models.CharField(max_length=32, null=True, blank=True)
    attachments = models.JSONField(default=None, null=True, blank=True)
    submissions = models.ManyToManyField(
        to="submission.Submission", related_name="mails"
    )

    objects = ScopedManager(event="event", _manager_class=QueuedMailManager)

    class Meta:
        rules_permissions = {
            "list": orga_can_change_submissions,
            "view": orga_can_change_submissions,
            "create": orga_can_change_submissions,
            "update": can_edit_mail & orga_can_change_submissions,
            "delete": orga_can_change_submissions,
            "send": orga_can_change_submissions,
        }

    class urls(EventUrls):
        base = edit = "{self.event.orga_urls.mail}{self.pk}/"
        delete = "{base}delete"
        send = "{base}send"
        copy = "{base}copy"

    def __str__(self):
        """Help with debugging."""
        return f"QueuedMail(to={self.to}, subject={self.subject}, state={self.state})"

    @property
    def has_error(self):
        return self.state == QueuedMailStates.DRAFT and self.error_data is not None

    @property
    def body_html(self):
        # Not cached: ``MailDetailForm.save`` clears ``text_html`` on
        # organiser edits, and ``body_html`` must re-render against the
        # mutated state on the same instance.
        from pretalx.mail.domain.render import (  # noqa: PLC0415 -- thin method
            delivery_html_body,
        )

        return delivery_html_body(self)

    @cached_property
    def prefixed_subject(self):
        from pretalx.mail.domain.render import (  # noqa: PLC0415 -- thin method
            get_prefixed_subject,
        )

        event = getattr(self, "event", None)
        if not event:
            return self.subject
        return get_prefixed_subject(event, self.subject)

    def mark_sent(self):
        self.state = QueuedMailStates.SENT
        self.sent = now()
        self.error_data = None
        self.error_timestamp = None
        self.save(update_fields=["state", "sent", "error_data", "error_timestamp"])

    mark_sent.alters_data = True

    def mark_failed(self, exception):
        self.state = QueuedMailStates.DRAFT
        error_data = {"error": str(exception), "type": type(exception).__name__}
        if isinstance(exception, SMTPResponseException):
            smtp_message = exception.smtp_error
            if isinstance(smtp_message, bytes):
                smtp_message = smtp_message.decode("utf-8", errors="replace")
            error_data["smtp_code"] = exception.smtp_code
            error_data["error"] = smtp_message
        self.error_data = error_data
        self.error_timestamp = now()
        self.save(update_fields=["state", "error_data", "error_timestamp"])

    mark_failed.alters_data = True

    @warnings.deprecated(
        "QueuedMail.send is deprecated; use send_draft / send_transient "
        "from pretalx.mail.domain.send."
    )
    def send(self, requestor=None, orga: bool = True):
        """Deprecated; kept as a compatibility shim for third-party plugins.
        TODO: remove after v2026.2.0. Use the explicit dispatch helpers
        in :mod:`pretalx.mail.domain.send` instead."""
        from pretalx.mail.domain.send import (  # noqa: PLC0415 -- thin method
            send_draft,
            send_transient,
        )

        if not self._state.adding:
            send_draft(self, requestor=requestor, orga=orga)
        else:
            send_transient(self)

    send.alters_data = True
