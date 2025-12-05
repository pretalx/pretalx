# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import exceptions
from rest_framework.serializers import SlugRelatedField

from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.submission.models import Feedback, Submission


@register_serializer(versions=CURRENT_VERSIONS)
class FeedbackWriteSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    submission = SlugRelatedField(
        slug_field="code", queryset=Submission.objects.none(), source="talk"
    )
    speaker = SlugRelatedField(
        slug_field="code",
        queryset=Submission.objects.none(),
        required=False,
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.event:
            self.fields["submission"].queryset = self.event.talks
            self.fields["speaker"].queryset = self.event.speakers

    def validate_submission(self, value):
        if not value.does_accept_feedback:
            raise exceptions.ValidationError(
                "This session does not accept feedback yet."
            )
        return value

    def validate(self, data):
        data = super().validate(data)
        speaker = data.get("speaker")
        talk = data.get("talk")
        if speaker and talk and speaker not in talk.speakers.all():
            raise exceptions.ValidationError(
                {"speaker": "This speaker is not a speaker of the given submission."}
            )
        return data

    class Meta:
        model = Feedback
        fields = [
            "id",
            "submission",
            "speaker",
            "rating",
            "review",
        ]


@register_serializer(versions=CURRENT_VERSIONS)
class FeedbackSerializer(FeedbackWriteSerializer):
    submission = SlugRelatedField(slug_field="code", read_only=True, source="talk")
    speaker = SlugRelatedField(slug_field="code", read_only=True)

    class Meta(FeedbackWriteSerializer.Meta):
        expandable_fields = {
            "submission": (
                "pretalx.api.serializers.submission.SubmissionSerializer",
                {"read_only": True, "omit": ("slots",), "source": "talk"},
            ),
            "speaker": (
                # Feedback.speaker is a User, not a SpeakerProfile
                "pretalx.api.serializers.review.ReviewerSerializer",
                {"read_only": True, "omit": ("email",)},
            ),
        }
