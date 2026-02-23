import factory
from django_scopes import scopes_disabled

from pretalx.submission.models import Review, Submission
from tests.factories.event import EventFactory
from tests.factories.person import UserFactory


class SubmissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Submission

    event = factory.SubFactory(EventFactory)
    title = factory.Sequence(lambda n: f"Submission {n}")
    submission_type = factory.LazyAttribute(lambda o: o.event.cfp.default_type)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review

    submission = factory.SubFactory(SubmissionFactory)
    user = factory.SubFactory(UserFactory)
    text = factory.Sequence(lambda n: f"Review text {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)
