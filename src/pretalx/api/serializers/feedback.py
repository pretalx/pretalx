# SPDX-FileCopyrightText: 2025-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework.serializers import SlugRelatedField

from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.submission.models import Submission
from pretalx.submission.models.feedback import Feedback


@register_serializer(versions=CURRENT_VERSIONS)
class FeedbackSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    talk = SlugRelatedField(slug_field="code", queryset=Submission.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request or not getattr(request, "event", None):
            return
        self.fields["talk"].queryset = request.event.talks.all()

    class Meta:
        model = Feedback
        fields = [
            "id",
            "talk",
            "review",
            "rating",
        ]
        read_only_fields = ("talk",)

    def create(self, validated_data):
        instance = super().create(validated_data)
        return instance
