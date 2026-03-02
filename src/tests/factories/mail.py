# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import factory
from django_scopes import scopes_disabled

from pretalx.mail.models import MailTemplate, QueuedMail, QueuedMailStates
from tests.factories.event import EventFactory


class MailTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MailTemplate

    event = factory.SubFactory(EventFactory)
    subject = factory.Sequence(lambda n: f"Subject {n}")
    text = factory.Sequence(lambda n: f"Body text {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class QueuedMailFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QueuedMail

    event = factory.SubFactory(EventFactory)
    subject = factory.Sequence(lambda n: f"Queued Subject {n}")
    text = factory.Sequence(lambda n: f"Queued body text {n}")
    state = QueuedMailStates.DRAFT
    locale = "en"
