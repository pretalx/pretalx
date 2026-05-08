# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.mail.domain.template import template_for_event

pytestmark = [pytest.mark.django_db]


def test_template_for_event_returns_existing(event):
    with scope(event=event):
        existing = event.mail_templates.get(role="submission.state.accepted")
        template = template_for_event(event, role="submission.state.accepted")
        assert template == existing
        assert template.event == event


def test_template_for_event_creates_when_missing(event):
    with scope(event=event):
        event.mail_templates.filter(role="submission.state.accepted").delete()
        template = template_for_event(event, role="submission.state.accepted")

        assert template.role == "submission.state.accepted"
        assert template.event == event
        assert template.pk is not None


def test_event_get_mail_template_delegates(event):
    with scope(event=event):
        existing = event.mail_templates.get(role="submission.state.accepted")
        assert event.get_mail_template("submission.state.accepted") == existing
