# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import exceptions
from rest_framework.serializers import SlugRelatedField

from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import NON_LEGACY_VERSIONS, register_serializer
from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.feedback import create_feedback
from pretalx.submission.models import Feedback, Submission


@register_serializer(versions=NON_LEGACY_VERSIONS)
class FeedbackWriteSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    submission = SlugRelatedField(
        slug_field="code", queryset=Submission.objects.none(), source="talk"
    )
    speaker = SlugRelatedField(
        slug_field="code",
        queryset=SpeakerProfile.objects.none(),
        required=False,
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.event:
            self.fields["submission"].queryset = self.event.talks
            self.fields["speaker"].queryset = self.event.speakers

    def validate_submission(self, value):
        user = self.context["request"].user
        if not user.has_perm("submission.give_feedback_submission", value):
            if not user.has_perm("submission.view_public_submission", value):
                self.fields["submission"].fail(
                    "does_not_exist", slug_name="code", value=value.code
                )
            raise exceptions.ValidationError(
                "This session does not accept feedback yet."
            )
        return value

    def create(self, validated_data):
        return create_feedback(Feedback(**validated_data))

    class Meta:
        model = Feedback
        fields = ["id", "submission", "speaker", "review"]


@register_serializer(versions=NON_LEGACY_VERSIONS)
class FeedbackSerializer(FeedbackWriteSerializer):
    submission = SlugRelatedField(slug_field="code", read_only=True, source="talk")
    speaker = SlugRelatedField(slug_field="code", read_only=True)

    class Meta(FeedbackWriteSerializer.Meta):
        fields = ["id", "submission", "speaker", "review"]
        expandable_fields = {
            "submission": (
                "pretalx.api.serializers.submission.SubmissionSerializer",
                {"read_only": True, "omit": ("slots",), "source": "talk"},
            ),
            "speaker": (
                "pretalx.api.serializers.speaker.SpeakerSerializer",
                {"read_only": True},
            ),
        }
