import factory
from django_scopes import scopes_disabled

from pretalx.submission.models import (
    Feedback,
    Review,
    ReviewScore,
    ReviewScoreCategory,
    Submission,
    SubmissionType,
    SubmitterAccessCode,
    Tag,
    Track,
)
from pretalx.submission.models.comment import SubmissionComment
from pretalx.submission.models.question import Answer, AnswerOption, Question
from pretalx.submission.models.resource import Resource
from pretalx.submission.models.review import ReviewPhase
from tests.factories.event import EventFactory
from tests.factories.person import UserFactory


class SubmissionTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubmissionType

    event = factory.SubFactory(EventFactory)
    name = factory.Sequence(lambda n: f"Type {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


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


class TrackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Track

    event = factory.SubFactory(EventFactory)
    name = factory.Sequence(lambda n: f"Track {n}")
    color = "#00ff00"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Question

    event = factory.SubFactory(EventFactory)
    question = factory.Sequence(lambda n: f"Question {n}")
    variant = "string"
    target = "submission"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class AnswerOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnswerOption

    question = factory.SubFactory(QuestionFactory)
    answer = factory.Sequence(lambda n: f"Option {n}")

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


class AnswerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Answer

    question = factory.SubFactory(QuestionFactory)
    submission = factory.SubFactory(SubmissionFactory)
    answer = factory.Sequence(lambda n: f"Answer {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class FeedbackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Feedback

    talk = factory.SubFactory(SubmissionFactory)
    review = "Great talk!"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class ResourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Resource

    submission = factory.SubFactory(SubmissionFactory)
    link = factory.Sequence(lambda n: f"https://example.com/resource-{n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag

    event = factory.SubFactory(EventFactory)
    tag = factory.Sequence(lambda n: f"Tag {n}")
    color = "#ff0000"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class ReviewPhaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReviewPhase

    event = factory.SubFactory(EventFactory)
    name = factory.Sequence(lambda n: f"Phase {n}")
    position = 0

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class ReviewScoreCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReviewScoreCategory

    event = factory.SubFactory(EventFactory)
    name = factory.Sequence(lambda n: f"Category {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class ReviewScoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReviewScore

    category = factory.SubFactory(ReviewScoreCategoryFactory)
    value = factory.Sequence(lambda n: n)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class SubmitterAccessCodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubmitterAccessCode

    event = factory.SubFactory(EventFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)


class SubmissionCommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubmissionComment

    submission = factory.SubFactory(SubmissionFactory)
    user = factory.SubFactory(UserFactory)
    text = factory.Sequence(lambda n: f"Comment {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with scopes_disabled():
            return super()._create(model_class, *args, **kwargs)
