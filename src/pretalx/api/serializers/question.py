# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import exceptions
from rest_framework.serializers import (
    CharField,
    HiddenField,
    PrimaryKeyRelatedField,
    SlugRelatedField,
)

from pretalx.api.serializers.defaults import CurrentEventDefault
from pretalx.api.serializers.fields import UploadedFileField
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.question import replace_question_options
from pretalx.submission.models import (
    Answer,
    AnswerOption,
    Question,
    QuestionTarget,
    QuestionVariant,
    Review,
    Submission,
    SubmissionType,
    Track,
)


@register_serializer(versions=CURRENT_VERSIONS)
class AnswerOptionSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    question = PrimaryKeyRelatedField(read_only=True)
    identifier = CharField(required=False, allow_blank=True)

    class Meta:
        model = AnswerOption
        fields = ("id", "question", "answer", "position", "identifier")
        expandable_fields = {
            "question": (
                "pretalx.api.serializers.question.QuestionSerializer",
                {"read_only": True, "omit": ["options"]},
            )
        }


# This serializer exists mostly for documentation purposes, as otherwise
# drf_spectacular will not pick up that questions can be set on create,
# but not changed on update. And if we have a separate serializer already,
# we might as well use it to isolate the create action fully.
@register_serializer(versions=CURRENT_VERSIONS)
class AnswerOptionCreateSerializer(AnswerOptionSerializer):
    question = PrimaryKeyRelatedField(read_only=False, queryset=Question.objects.none())
    identifier = CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = kwargs.get("context", {}).get("request")
        if request and hasattr(request, "event"):
            self.fields["question"].queryset = request.event.questions(
                manager="all_objects"
            ).filter(variant__in=[QuestionVariant.CHOICES, QuestionVariant.MULTIPLE])
        else:
            self.fields["question"].queryset = Question.objects.none()

    class Meta(AnswerOptionSerializer.Meta):
        expandable_fields = None
        # Skip UniqueTogetherValidator since identifier is auto-generated
        validators = []


@register_serializer(versions=CURRENT_VERSIONS)
class QuestionSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    identifier = CharField(required=False, allow_blank=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "identifier",
            "question",
            "help_text",
            "default_answer",
            "variant",
            "target",
            "deadline",
            "freeze_after",
            "question_required",
            "position",
            "tracks",
            "submission_types",
            "options",
            "min_length",
            "max_length",
            "min_number",
            "max_number",
            "min_date",
            "max_date",
            "min_datetime",
            "max_datetime",
            "icon",
        )
        expandable_fields = {
            # If we ever add answers to the expandable fields, we need to
            # make sure that we respect the limit_teams field on the question,
            # as organisers may have view and edit rights on the question itself,
            # but not on the question answers.
            "options": (
                "pretalx.api.serializers.question.AnswerOptionSerializer",
                {
                    "many": True,
                    "read_only": True,
                    "fields": ("id", "answer", "position", "identifier"),
                },
            ),
            "tracks": (
                "pretalx.api.serializers.submission.TrackSerializer",
                {"many": True, "read_only": True},
            ),
            "submission_types": (
                "pretalx.api.serializers.submission.SubmissionTypeSerializer",
                {"many": True, "read_only": True},
            ),
        }


# Just for documentation purposes, as the docs will otherwise pick up the reduced
# fields also for the primary AnswerOptionSerializer, for some unholy reason.
class NestedAnswerOptionSerializer(AnswerOptionSerializer):
    pass


@register_serializer(versions=CURRENT_VERSIONS)
class QuestionOrgaSerializer(QuestionSerializer):
    options = NestedAnswerOptionSerializer(
        many=True, required=False, fields=("id", "answer", "position")
    )
    event = HiddenField(default=CurrentEventDefault())

    class Meta(QuestionSerializer.Meta):
        fields = (
            *QuestionSerializer.Meta.fields,
            "active",
            "is_public",
            "contains_personal_data",
            "is_visible_to_reviewers",
            "event",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = kwargs.get("context", {}).get("request")
        if request and hasattr(request, "event"):
            self.fields["tracks"].child_relation.queryset = request.event.tracks.all()
            self.fields[
                "submission_types"
            ].child_relation.queryset = request.event.submission_types.all()
        else:
            self.fields["tracks"].child_relation.queryset = Track.objects.none()
            self.fields[
                "submission_types"
            ].child_relation.queryset = SubmissionType.objects.none()

    def create(self, validated_data):
        options_data = validated_data.pop("options", None)
        question = super().create(validated_data)
        if options_data:
            replace_question_options(question=question, options_data=options_data)
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop("options", None)
        question = super().update(instance, validated_data)
        if options_data is not None:
            replace_question_options(question=question, options_data=options_data)
        return question


@register_serializer(versions=CURRENT_VERSIONS)
class AnswerSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    question = PrimaryKeyRelatedField(read_only=True)
    submission = SlugRelatedField(slug_field="code", read_only=True, required=False)
    person = SlugRelatedField(
        slug_field="code", read_only=True, required=False, source="speaker"
    )
    review = PrimaryKeyRelatedField(read_only=True, required=False)
    answer_file = UploadedFileField(required=False)

    class Meta:
        model = Answer
        fields = (
            "id",
            "question",
            "answer",
            "answer_file",
            "submission",
            "review",
            "person",
            "options",
        )
        expandable_fields = {
            "question": (
                "pretalx.api.serializers.question.QuestionSerializer",
                {"read_only": True, "omit": ("options",)},
            ),
            "options": (
                "pretalx.api.serializers.question.AnswerOptionSerializer",
                {"many": True, "read_only": True, "omit": ("question",)},
            ),
            "person": (
                "pretalx.api.serializers.speaker.SpeakerSerializer",
                {"read_only": True, "omit": ("answers",)},
            ),
            # submissions and reviews are currently not expandable due to permissions
            # concerns: We’d have to make sure that users with access to e.g. some
            # submission answers and some review answers would only see the ones from
            # their assigned tracks or submissions.
        }


@register_serializer(versions=CURRENT_VERSIONS)
class AnswerCreateSerializer(AnswerSerializer):
    # Validation lives inline rather than in submission/validators/: the API
    # is currently the only entry point that accepts arbitrary answer payloads
    # (the CfP/orga flows go through dedicated per-question forms), so there
    # is no second caller to share with. Keeping the rules here also avoids
    # having to translate between the model's ``speaker`` field and this
    # serializer's API-facing ``person`` field.

    # Map QuestionTarget to the user-facing input-field name on this serializer.
    # The corresponding model attribute is resolved via ``self.fields[name].source``.
    _INPUT_FIELDS = {
        QuestionTarget.SUBMISSION: "submission",
        QuestionTarget.SPEAKER: "person",
        QuestionTarget.REVIEWER: "review",
    }

    question = PrimaryKeyRelatedField(queryset=Question.objects.none())
    submission = SlugRelatedField(
        queryset=Submission.objects.none(),
        slug_field="code",
        required=False,
        allow_null=True,
    )
    person = SlugRelatedField(
        queryset=SpeakerProfile.objects.none(),
        slug_field="code",
        required=False,
        allow_null=True,
        source="speaker",
    )
    review = PrimaryKeyRelatedField(
        queryset=Review.objects.none(), required=False, allow_null=True
    )
    options = PrimaryKeyRelatedField(
        queryset=AnswerOption.objects.none(), required=False, many=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request or not getattr(request, "event", None):
            return
        self.fields["question"].queryset = questions_for_user(
            request.event, request.user
        )
        self.fields["submission"].queryset = request.event.submissions.all()
        self.fields["person"].queryset = request.event.submitters
        self.fields["review"].queryset = request.event.reviews.all()
        self.fields["options"].child_relation.queryset = AnswerOption.objects.filter(
            question__event=request.event
        )

    def validate(self, data):
        question = self.get_with_fallback(data, "question")

        if question.variant in (QuestionVariant.CHOICES, QuestionVariant.MULTIPLE):
            options = self.get_with_fallback(data, "options")
            if not options:
                raise exceptions.ValidationError(
                    {
                        "options": "This field is required for choice or multiple-choice question."
                    }
                )
            for option in options:
                if option.question != question:
                    raise exceptions.ValidationError(
                        {
                            "options": f"Option {option.pk} does not belong to question {question.pk}."
                        }
                    )

        target = question.target
        required_input = self._INPUT_FIELDS[target]
        if not self.get_with_fallback(data, self.fields[required_input].source):
            raise exceptions.ValidationError(
                {required_input: f"This field is required for {target} questions."}
            )
        for other_target, other_input in self._INPUT_FIELDS.items():
            if other_target == target:
                continue
            if self.get_with_fallback(data, self.fields[other_input].source):
                raise exceptions.ValidationError(
                    {other_input: f"Cannot set {other_input} for {target} question."}
                )

        return data

    class Meta(AnswerSerializer.Meta):
        expandable_fields = None
