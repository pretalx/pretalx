# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import exceptions
from rest_framework.serializers import (
    CharField,
    EmailField,
    SerializerMethodField,
    URLField,
)

from pretalx.api.documentation import extend_schema_field
from pretalx.api.serializers.availability import (
    AvailabilitiesMixin,
    AvailabilitySerializer,
)
from pretalx.api.serializers.fields import UploadedFileField
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import QuestionTarget


@register_serializer(versions=CURRENT_VERSIONS)
class SpeakerSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    code = CharField(read_only=True)
    name = CharField()
    avatar_url = URLField(read_only=True)
    answers = SerializerMethodField()
    submissions = SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.event and not self.event.cfp.request_avatar:
            self.fields.pop("avatar_url")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["name"] = instance.get_display_name()
        return data

    @extend_schema_field(list[str])
    def get_submissions(self, obj):
        if not self.context.get("submissions"):
            return []
        # When used as an embedded serializer (e.g. expanded speakers on the
        # submission endpoint), the context won't contain "submissions", so we
        # return [] above. When used from SpeakerViewSet, get_queryset()
        # prefetches "submissions" with the visibility-filtered queryset from
        # submissions_for_user, so .all() returns only permitted submissions.
        submissions = obj.submissions.all()
        if serializer := self.get_extra_flex_field("submissions", submissions):
            return serializer.data
        return [s.code for s in submissions]

    @extend_schema_field(list[int])
    def get_answers(self, obj):
        questions = self.context.get("questions", [])
        if not questions:
            return []
        question_pks = {q.pk for q in questions if q.target == QuestionTarget.SPEAKER}
        # Use prefetched answers, filter in Python
        answers = sorted(
            [a for a in obj.answers.all() if a.question_id in question_pks],
            key=lambda a: a.question.position,
        )
        if serializer := self.get_extra_flex_field("answers", answers):
            return serializer.data
        return [a.pk for a in answers]

    def update(self, instance, validated_data):
        availabilities_data = validated_data.pop("availabilities", None)
        speaker = super().update(instance, validated_data)
        if availabilities_data is not None:
            self._handle_availabilities(speaker, availabilities_data, field="person")
        return speaker

    class Meta:
        model = SpeakerProfile
        fields = ("code", "name", "biography", "submissions", "avatar_url", "answers")
        extra_expandable_fields = {
            "answers": (
                "pretalx.api.serializers.question.AnswerSerializer",
                {"many": True, "read_only": True},
            ),
            "submissions": (
                "pretalx.api.serializers.submission.SubmissionSerializer",
                {"many": True, "read_only": True},
            ),
        }


@register_serializer(versions=CURRENT_VERSIONS)
class SpeakerOrgaSerializer(AvailabilitiesMixin, SpeakerSerializer):
    email = EmailField(source="user.email")
    timezone = CharField(source="user.timezone", read_only=True)
    locale = CharField(source="user.locale", read_only=True)
    availabilities = AvailabilitySerializer(many=True, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.event:
            for field in ("avatar", "availabilities"):
                if field not in self.fields:
                    continue
                if not getattr(self.event.cfp, f"request_{field}"):
                    self.fields.pop(field, None)
                elif getattr(self.event.cfp, f"require_{field}"):
                    self.fields[field].required = True

    class Meta(SpeakerSerializer.Meta):
        fields = (
            *SpeakerSerializer.Meta.fields,
            "email",
            "timezone",
            "locale",
            "has_arrived",
            "availabilities",
            "internal_notes",
        )


@register_serializer(versions=CURRENT_VERSIONS)
class SpeakerUpdateSerializer(SpeakerOrgaSerializer):
    avatar = UploadedFileField(required=False)

    def update(self, instance, validated_data):
        avatar = validated_data.pop("avatar", None)
        user_fields = validated_data.pop("user", None) or {}
        instance = super().update(instance, validated_data)
        for key, value in user_fields.items():
            setattr(instance.user, key, value)
            instance.user.save(update_fields=[key])
        if avatar:
            instance.set_avatar(avatar)
        return instance

    def validate_email(self, value):
        value = value.lower()
        if (
            User.objects.exclude(pk=self.instance.pk)
            .filter(email__iexact=value)
            .exists()
        ):
            raise exceptions.ValidationError("Email already exists in system.")
        return value

    class Meta(SpeakerOrgaSerializer.Meta):
        fields = (*SpeakerOrgaSerializer.Meta.fields, "avatar")
