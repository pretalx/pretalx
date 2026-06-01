# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import CurrentUserDefault, HiddenField, SlugRelatedField

from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.serializers.question import AnswerSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.person.models import User
from pretalx.submission.domain.review import update_review_score
from pretalx.submission.models import (
    Review,
    ReviewScore,
    ReviewScoreCategory,
    Submission,
)
from pretalx.submission.validators.review import (
    validate_review_scores_present,
    validate_review_scores_unique_categories,
)


@register_serializer(versions=CURRENT_VERSIONS)
class ReviewScoreCategorySerializer(PretalxSerializer):
    class Meta:
        model = ReviewScoreCategory
        fields = (
            "id",
            "name",
            "weight",
            "required",
            "active",
            "limit_tracks",
            "is_independent",
        )
        expandable_fields = {
            "limit_tracks": (
                "pretalx.api.serializers.submission.TrackSerializer",
                {"read_only": True, "many": True},
            )
        }


@register_serializer(versions=CURRENT_VERSIONS)
class ReviewScoreSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = ReviewScore
        fields = ("id", "category", "value", "label")
        expandable_fields = {
            "category": (
                "pretalx.api.serializers.review.ReviewScoreCategorySerializer",
                {"read_only": True},
            )
        }


@register_serializer(versions=CURRENT_VERSIONS)
class ReviewerSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = User
        fields = ("code", "name", "email")


@register_serializer(versions=CURRENT_VERSIONS)
class ReviewWriteSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    submission = SlugRelatedField(slug_field="code", queryset=Submission.objects.none())
    user = HiddenField(default=CurrentUserDefault())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["answers"].required = False
        self.fields["score"].read_only = True
        if self.event:
            scores_field = self.fields["scores"]
            # ReviewSerializer (read-only) overrides scores with a nested
            # serializer that has no child_relation, so guard before accessing.
            if hasattr(scores_field, "child_relation"):
                scores_field.child_relation.queryset = ReviewScore.objects.filter(
                    category__event=self.event
                )
            self.fields["text"].required = self.event.review_settings["text_mandatory"]
            self.fields["scores"].required = self.event.review_settings[
                "score_mandatory"
            ]
        if submissions := self.context.get("submissions"):
            self.fields["submission"].queryset = submissions

    class Meta:
        model = Review
        fields = ["id", "submission", "text", "score", "scores", "answers", "user"]
        read_only_fields = ("submission",)
        expandable_fields = {
            "submission": (
                "pretalx.api.serializers.submission.SubmissionSerializer",
                {"read_only": True, "omit": ("slots",)},
            ),
            "answers": (
                "pretalx.api.serializers.question.AnswerSerializer",
                {"read_only": True, "many": True},
            ),
            "user": (
                "pretalx.api.serializers.review.ReviewerSerializer",
                {"read_only": True},
            ),
            "scores": (
                "pretalx.api.serializers.review.ReviewScoreSerializer",
                {"read_only": True, "many": True},
            ),
        }

    def validate_scores(self, value):
        validate_review_scores_unique_categories(value)
        validate_review_scores_present(self.event, value)
        return value

    def validate_submission(self, value):
        if self.event.reviews.filter(
            user=self.context["request"].user, submission=value
        ).exists():
            raise ValidationError("You have already reviewed this submission.")
        return value

    def create(self, validated_data):
        instance = super().create(validated_data)
        if instance.scores.exists():
            update_review_score(instance)
        return instance

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        has_scores = "scores" in validated_data
        instance = super().update(instance, validated_data)
        if has_scores:
            update_review_score(instance)
        return instance


@register_serializer(versions=CURRENT_VERSIONS)
class ReviewSerializer(ReviewWriteSerializer):
    scores = ReviewScoreSerializer(many=True)
    user = SlugRelatedField(slug_field="code", read_only=True)
    answers = AnswerSerializer(read_only=True, many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        self._hide_reviewer_identity = bool(
            request
            and self.event
            and not request.user.has_perm(
                "submission.list_reviewers_review", self.event
            )
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self._hide_reviewer_identity:
            data.pop("user", None)
        return data

    class Meta(ReviewWriteSerializer.Meta):
        fields = ReviewWriteSerializer.Meta.fields
