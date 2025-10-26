# SPDX-FileCopyrightText: 2025-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin

from pretalx.api.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.submission.models.feedback import Feedback


@register_serializer(versions=CURRENT_VERSIONS)
class FeedbackSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = Feedback
        fields = (
            "id",
            "talk",
            "speaker",
            "review",
            "rating",
        )
        expandable_fields = {
            "talk": (
                "pretalx.api.serializers.submission.SubmissionSerializer",
                {"read_only": True},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def create(self, validated_data):
        instance = super().create(validated_data)
        return instance
