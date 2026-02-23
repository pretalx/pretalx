import datetime as dt

import factory
from django_scopes import scopes_disabled

from pretalx.schedule.models import Availability, Room, Schedule
from pretalx.schedule.models.slot import TalkSlot
from tests.factories.event import EventFactory


class ScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Schedule

    event = factory.SubFactory(EventFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class RoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Room

    event = factory.SubFactory(EventFactory)
    name = factory.Sequence(lambda n: f"Room {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class AvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Availability

    event = factory.SubFactory(EventFactory)
    start = factory.LazyAttribute(lambda o: o.event.datetime_from)
    end = factory.LazyAttribute(lambda o: o.event.datetime_to)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class TalkSlotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TalkSlot

    schedule = factory.LazyAttribute(lambda o: o.submission.event.wip_schedule)
    room = factory.SubFactory(
        RoomFactory, event=factory.SelfAttribute("..submission.event")
    )
    start = factory.LazyAttribute(lambda o: o.submission.event.datetime_from)
    end = factory.LazyAttribute(
        lambda o: o.submission.event.datetime_from + dt.timedelta(hours=1)
    )
    is_visible = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)
