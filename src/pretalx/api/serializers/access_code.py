# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_flex_fields.utils import is_expanded
from rest_framework.relations import PrimaryKeyRelatedField

from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.serializers.submission import SubmissionTypeSerializer, TrackSerializer
from pretalx.api.versions import CURRENT_VERSION, DEV_PREVIEW, register_serializer
from pretalx.submission.models import SubmitterAccessCode
from pretalx.submission.models.track import Track
from pretalx.submission.models.type import SubmissionType


@register_serializer(versions=[DEV_PREVIEW])
class SubmitterAccessCodeSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = SubmitterAccessCode
        fields = (
            "id",
            "code",
            "tracks",
            "submission_types",
            "valid_until",
            "maximum_uses",
            "redeemed",
            "internal_notes",
        )
        expandable_fields = {
            "tracks": (
                "pretalx.api.serializers.submission.TrackSerializer",
                {"read_only": True, "many": True},
            ),
            "submission_types": (
                "pretalx.api.serializers.submission.SubmissionTypeSerializer",
                {"read_only": True, "many": True},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = kwargs.get("context", {}).get("request")
        if request and hasattr(request, "event"):
            self.fields["tracks"].child_relation.queryset = request.event.tracks.all()
            self.fields[
                "submission_types"
            ].child_relation.queryset = request.event.submission_types.all()

    def create(self, validated_data):
        validated_data["event"] = getattr(self.context.get("request"), "event", None)
        return super().create(validated_data)


@register_serializer(
    versions=[CURRENT_VERSION], class_name="SubmitterAccessCodeSerializer"
)
class V1SubmitterAccessCodeSerializer(PretalxSerializer):
    track = PrimaryKeyRelatedField(
        queryset=Track.objects.none(), required=False, allow_null=True
    )
    submission_type = PrimaryKeyRelatedField(
        queryset=SubmissionType.objects.none(), required=False, allow_null=True
    )

    class Meta:
        model = SubmitterAccessCode
        fields = (
            "id",
            "code",
            "track",
            "submission_type",
            "valid_until",
            "maximum_uses",
            "redeemed",
            "internal_notes",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = kwargs.get("context", {}).get("request")
        if request and hasattr(request, "event"):
            self.fields["track"].queryset = request.event.tracks.all()
            self.fields[
                "submission_type"
            ].queryset = request.event.submission_types.all()

    def to_representation(self, instance):
        """We cannot use flex fields here because our data structure changed,
        so we handle expansion manually for the duration of our v1 support."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        track = instance.tracks.all().first()
        submission_type = instance.submission_types.all().first()

        if track and request and is_expanded(request, "track"):
            data["track"] = TrackSerializer(track, context=self.context).data
        else:
            data["track"] = track.pk if track else None

        if submission_type and request and is_expanded(request, "submission_type"):
            data["submission_type"] = SubmissionTypeSerializer(
                submission_type, context=self.context
            ).data
        else:
            data["submission_type"] = submission_type.pk if submission_type else None

        return data

    def create(self, validated_data):
        track = validated_data.pop("track", None)
        submission_type = validated_data.pop("submission_type", None)
        validated_data["event"] = getattr(self.context.get("request"), "event", None)
        instance = super().create(validated_data)
        if track:
            instance.tracks.set([track])
        if submission_type:
            instance.submission_types.set([submission_type])
        return instance

    def update(self, instance, validated_data):
        track = validated_data.pop("track", None)
        submission_type = validated_data.pop("submission_type", None)
        instance = super().update(instance, validated_data)
        if track is not None:
            instance.tracks.set([track])
        elif "track" in self.initial_data:
            instance.tracks.clear()
        if submission_type is not None:
            instance.submission_types.set([submission_type])
        elif "submission_type" in self.initial_data:
            instance.submission_types.clear()
        return instance
