# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import factory
from django.utils.timezone import now
from django_scopes import scopes_disabled

from tests.factories.event import EventFactory
from tests.factories.person import UserFactory
from tests.factories.submission import SubmissionFactory


class CachedFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "common.CachedFile"

    filename = factory.Sequence(lambda n: f"file-{n}.zip")
    content_type = "application/zip"
    expires = factory.LazyFunction(lambda: now() + dt.timedelta(hours=1))


class ActivityLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "common.ActivityLog"

    event = factory.SubFactory(EventFactory)
    person = factory.SubFactory(UserFactory)
    content_object = factory.SubFactory(SubmissionFactory)
    action_type = "pretalx.submission.create"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)
