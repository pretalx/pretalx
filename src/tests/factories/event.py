import datetime as dt

import factory
from django_scopes import scopes_disabled

from pretalx.event.models import Event, Organiser


class OrganiserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organiser

    name = factory.Sequence(lambda n: f"Organiser {n}")
    slug = factory.Sequence(lambda n: f"organiser-{n}")


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"Event {n}")
    slug = factory.Sequence(lambda n: f"event-{n}")
    organiser = factory.SubFactory(OrganiserFactory)
    date_from = factory.LazyFunction(dt.date.today)
    date_to = factory.LazyAttribute(lambda o: o.date_from + dt.timedelta(days=2))
    email = "orga@orga.org"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Event.save() calls build_initial_data() which queries scoped
        models, so we need scopes disabled during creation."""
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)
