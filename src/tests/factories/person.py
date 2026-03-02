# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import factory
from django_scopes import scopes_disabled

from pretalx.person.models import SpeakerProfile, User
from pretalx.person.models.auth_token import UserApiToken
from pretalx.person.models.information import SpeakerInformation
from pretalx.person.models.picture import ProfilePicture
from pretalx.person.models.preferences import UserEventPreferences
from tests.factories.event import EventFactory


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Sequence(lambda n: f"User {n}")
    locale = "en"
    timezone = "UTC"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "testpassword!")
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)


class SpeakerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpeakerProfile

    user = factory.SubFactory(UserFactory)
    event = factory.SubFactory(EventFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class UserApiTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserApiToken
        skip_postgeneration_save = True

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Token {n}")
    endpoints = factory.LazyFunction(dict)

    @factory.post_generation
    def events(self, create, extracted, **kwargs):
        if not create or not extracted:
            return
        self.events.add(*extracted)


class SpeakerInformationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpeakerInformation

    event = factory.SubFactory(EventFactory)
    title = factory.Sequence(lambda n: f"Info {n}")
    text = "Important information for speakers."

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class UserEventPreferencesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserEventPreferences

    user = factory.SubFactory(UserFactory)
    event = factory.SubFactory(EventFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class ProfilePictureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProfilePicture

    user = factory.SubFactory(UserFactory)
