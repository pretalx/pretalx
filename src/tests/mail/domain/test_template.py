# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_by_role_returns_existing(event):
    with scope(event=event):
        existing = event.mail_templates.get(role=MailTemplateRoles.SUBMISSION_ACCEPT)
        assert (
            mail_template_by_role(event, MailTemplateRoles.SUBMISSION_ACCEPT)
            == existing
        )


def test_mail_template_by_role_creates_from_defaults_when_missing(event):
    with scope(event=event):
        event.mail_templates.filter(role=MailTemplateRoles.SUBMISSION_ACCEPT).delete()

        template = mail_template_by_role(event, MailTemplateRoles.SUBMISSION_ACCEPT)

        assert template.role == MailTemplateRoles.SUBMISSION_ACCEPT
        assert template.event == event
        assert template.pk is not None
        assert str(template.subject)
        assert str(template.text)
