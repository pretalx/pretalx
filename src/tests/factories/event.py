# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import factory
from django_scopes import scopes_disabled

from pretalx.event.models import Event, Organiser, Team, TeamInvite
from pretalx.event.models.event import (
    EventExtraLink,
    default_display_settings,
    default_feature_flags,
    default_mail_settings,
    default_review_settings,
)
from pretalx.submission.models import CfP


class OrganiserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organiser

    name = factory.Sequence(lambda n: f"Organiser {n}")
    slug = factory.Sequence(lambda n: f"organiser-{n}")


class CfPFactory(factory.django.DjangoModelFactory):
    """Updates the existing CfP created by Event.build_initial_data().

    Used as a RelatedFactory on EventFactory so that
    ``EventFactory(cfp__deadline=..., cfp__fields={...})`` works.
    """

    class Meta:
        model = CfP

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        event = kwargs.pop("event")
        cfp = event.cfp
        update_fields = []
        for key, value in kwargs.items():
            if key in ("fields", "settings"):
                getattr(cfp, key).update(value)
            else:
                setattr(cfp, key, value)
            update_fields.append(key)
        if update_fields:
            cfp.save(update_fields=update_fields)
        return cfp


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Event {n}")
    slug = factory.Sequence(lambda n: f"event-{n}")
    organiser = factory.SubFactory(OrganiserFactory)
    date_from = factory.LazyFunction(dt.date.today)
    date_to = factory.LazyAttribute(lambda o: o.date_from + dt.timedelta(days=2))
    email = "orga@orga.org"
    is_public = True
    feature_flags = factory.Transformer(
        {}, transform=lambda overrides: {**default_feature_flags(), **overrides}
    )
    mail_settings = factory.Transformer(
        {}, transform=lambda overrides: {**default_mail_settings(), **overrides}
    )
    display_settings = factory.Transformer(
        {}, transform=lambda overrides: {**default_display_settings(), **overrides}
    )
    review_settings = factory.Transformer(
        {}, transform=lambda overrides: {**default_review_settings(), **overrides}
    )
    cfp = factory.RelatedFactory(CfPFactory, factory_related_name="event")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Event.save() calls build_initial_data() which queries scoped
        models, so we need scopes disabled during creation."""
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)

    @factory.post_generation
    def review_phase(self, create, extracted, **kwargs):  # noqa: N805
        """Update the auto-created active review phase.

        Usage: ``EventFactory(review_phase__can_tag_submissions="use_tags")``
        """
        if not create or not kwargs:
            return
        with scopes_disabled():
            phase = self.active_review_phase
            for key, value in kwargs.items():
                setattr(phase, key, value)
            phase.save(update_fields=list(kwargs.keys()))

    @factory.post_generation
    def score_category(self, create, extracted, **kwargs):  # noqa: N805
        """Update the auto-created default score category.

        Usage: ``EventFactory(score_category__required=True)``
        """
        if not create or not kwargs:
            return
        with scopes_disabled():
            category = self.score_categories.first()
            for key, value in kwargs.items():
                setattr(category, key, value)
            category.save(update_fields=list(kwargs.keys()))


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    organiser = factory.SubFactory(OrganiserFactory)
    name = factory.Sequence(lambda n: f"Team {n}")
    can_change_submissions = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class TeamInviteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TeamInvite

    team = factory.SubFactory(TeamFactory)
    email = factory.Sequence(lambda n: f"invite{n}@example.com")


class EventExtraLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "event.EventExtraLink"

    event = factory.SubFactory(EventFactory)
    label = factory.Sequence(lambda n: f"Link {n}")
    url = factory.Sequence(lambda n: f"https://example.com/link-{n}")
    role = "footer"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(EventExtraLink, *args, **kwargs)
