# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

from pathlib import Path

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import exceptions, serializers
from rest_framework.serializers import SerializerMethodField

from pretalx.api.documentation import extend_schema_field
from pretalx.api.serializers.fields import UploadedFileField
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import (
    QuestionTarget,
    Resource,
    Submission,
    SubmissionInvitation,
    SubmissionType,
    Tag,
    Track,
)


@register_serializer()
class ResourceSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    """
    Submission resources contain a URL,
    which may point to external sites or to files uploaded to pretalx.
    """

    resource = SerializerMethodField()

    @staticmethod
    def get_resource(obj):
        return obj.url

    class Meta:
        model = Resource
        fields = ("id", "resource", "description", "is_public")


class ResourceWriteSerializer(PretalxSerializer):
    """
    Resources may not be updated, only created and deleted. Use the
    ``link`` field to provide an external link or the ``resource``
    field to provide an uploaded file.
    """

    resource = UploadedFileField(required=False, allow_null=True)
    link = serializers.URLField(
        required=False, allow_null=True, allow_blank=True, max_length=400
    )
    description = serializers.CharField(required=True, max_length=1000)
    is_public = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Resource
        fields = ("resource", "link", "description", "is_public")

    def validate(self, data):
        has_resource = data.get("resource") is not None
        has_link = bool(data.get("link"))
        if has_resource and has_link:
            raise serializers.ValidationError(
                "Provide either a link or a file, not both."
            )
        if not has_resource and not has_link:
            raise serializers.ValidationError("Provide either a link or a file.")
        return data

    def create(self, validated_data):
        validated_data["link"] = validated_data.get("link") or ""
        return super().create(validated_data)


@register_serializer(versions=CURRENT_VERSIONS)
class TagSerializer(PretalxSerializer):
    class Meta:
        model = Tag
        fields = ("id", "tag", "description", "color", "is_public")

    def create(self, validated_data):
        validated_data["event"] = self.event
        return super().create(validated_data)

    def validate_tag(self, value):
        existing_tags = self.event.tags.all()
        if self.instance and self.instance.pk:
            existing_tags = existing_tags.exclude(pk=self.instance.pk)
        if existing_tags.filter(tag=value).exists():
            raise exceptions.ValidationError("Tag already exists in event.")
        return value


@register_serializer(versions=CURRENT_VERSIONS)
class SubmissionTypeSerializer(PretalxSerializer):
    class Meta:
        model = SubmissionType
        fields = (
            "id",
            "name",
            "default_duration",
            "deadline",
            "requires_access_code",
        )

    def create(self, validated_data):
        validated_data["event"] = self.event
        return super().create(validated_data)

    def validate_name(self, value):
        existing_types = self.event.submission_types.all()
        if self.instance and self.instance.pk:
            existing_types = existing_types.exclude(pk=self.instance.pk)
        if any(str(stype.name) == str(value) for stype in existing_types):
            raise exceptions.ValidationError(
                "Submission type name already exists in event."
            )
        return value

    def update(self, instance, validated_data):
        duration_changed = (
            "duration" in validated_data
            and validated_data["duration"] != instance.duration
        )
        result = super().update(instance, validated_data)
        if duration_changed:
            instance.update_duration()
        return result


@register_serializer(versions=CURRENT_VERSIONS)
class TrackSerializer(PretalxSerializer):
    class Meta:
        model = Track
        fields = (
            "id",
            "name",
            "description",
            "color",
            "position",
            "requires_access_code",
        )

    def create(self, validated_data):
        validated_data["event"] = self.event
        return super().create(validated_data)

    def validate_name(self, value):
        existing_types = self.event.tracks.all()
        if self.instance and self.instance.pk:
            existing_types = existing_types.exclude(pk=self.instance.pk)
        if any(str(track.name) == str(value) for track in existing_types):
            raise exceptions.ValidationError("Track name already exists in event.")
        return value


@register_serializer(versions=CURRENT_VERSIONS)
class SubmissionInvitationSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = SubmissionInvitation
        fields = ("id", "email", "created", "updated")
        read_only_fields = ("id", "created", "updated")


@register_serializer(versions=CURRENT_VERSIONS)
class SubmissionSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    submission_type = serializers.PrimaryKeyRelatedField(
        queryset=SubmissionType.objects.none(),
        required=True,
    )
    track = serializers.PrimaryKeyRelatedField(
        queryset=Track.objects.none(), required=False, allow_null=True
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.none(), many=True, required=False
    )
    image = UploadedFileField(required=False)
    duration = serializers.IntegerField(
        source="get_duration",
        required=False,
        help_text="Defaults to the submission type’s duration",
    )

    # These fields are SerializerMethodFields rather than direct querysets in order
    # to dynamically filter the shown objects (e.g. only answers to public questions
    # for non-authenticated users, only the slots in the current schedule, etc.)
    # This would not be possible by just setting e.g. self.fields["speakers"].queryset:
    # the .queryset attribute serves to validate write actions, but not to limit read
    # actions!
    speakers = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    slots = serializers.SerializerMethodField()
    resources = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.event:
            return
        self.fields["submission_type"].queryset = self.event.submission_types.all()
        self.fields["track"].queryset = self.event.tracks.all()
        self.fields["tags"].queryset = self.event.tags.all()

        if not self.event.get_feature_flag("use_tracks"):
            self.fields.pop("track", None)
        request_require_fields = [
            "title",
            "abstract",
            "description",
            "notes",
            "image",
            "do_not_record",
            "content_locale",
        ]
        for field in request_require_fields:
            if field not in self.fields:
                continue
            if not getattr(self.event.cfp, f"request_{field}"):
                self.fields.pop(field, None)
            else:
                self.fields[field].required = getattr(
                    self.event.cfp, f"require_{field}"
                )

    @extend_schema_field(list[str])
    def get_speakers(self, obj):
        if not self.event:
            return []
        speaker_ids = list(obj.sorted_speakers.values_list("pk", flat=True))
        profiles = SpeakerProfile.objects.filter(
            event=self.event, user__in=speaker_ids
        ).distinct()
        if serializer := self.get_extra_flex_field("speakers", profiles):
            # Re-sort to match speaker position order
            data = serializer.data
            id_order = {uid: i for i, uid in enumerate(speaker_ids)}
            data.sort(key=lambda p: id_order.get(p.get("user"), 0))
            return data
        return obj.sorted_speakers.values_list("code", flat=True)

    @extend_schema_field(list[int])
    def get_answers(self, obj):
        questions = self.context.get("questions", [])
        qs = (
            obj.answers.filter(
                question__in=questions,
                question__event=self.event,
                question__target=QuestionTarget.SUBMISSION,
            )
            .select_related("question")
            .order_by("question__position")
        )
        if serializer := self.get_extra_flex_field("answers", qs):
            return serializer.data
        return qs.values_list("pk", flat=True)

    @extend_schema_field(list[int])
    def get_slots(self, obj):
        schedule = self.context.get("schedule")
        if not schedule:
            return []
        public_slots = self.context.get("public_slots", True)
        qs = obj.slots.filter(schedule=schedule)
        if public_slots:
            qs = qs.filter(is_visible=True)
        if serializer := self.get_extra_flex_field("slots", qs):
            return serializer.data
        return qs.values_list("pk", flat=True)

    @extend_schema_field(list[int])
    def get_resources(self, obj):
        public_resources = self.context.get("public_resources", True)
        qs = obj.active_resources
        if public_resources:
            qs = obj.public_resources
        if serializer := self.get_extra_flex_field("resources", qs):
            return serializer.data
        return qs.values_list("pk", flat=True)

    class Meta:
        model = Submission
        fields = [
            "code",
            "title",
            "speakers",
            "submission_type",
            "track",
            "tags",
            "state",
            "abstract",
            "description",
            "duration",
            "slot_count",
            "content_locale",
            "do_not_record",
            "image",
            "resources",
            "slots",
            "answers",
        ]
        read_only_fields = ("code", "state")
        expandable_fields = {
            "submission_type": (
                "pretalx.api.serializers.submission.SubmissionTypeSerializer",
                {"read_only": True},
            ),
            "tags": (
                "pretalx.api.serializers.submission.TagSerializer",
                {"many": True, "read_only": True},
            ),
            "track": (
                "pretalx.api.serializers.submission.TrackSerializer",
                {"read_only": True},
            ),
        }
        extra_expandable_fields = {
            "slots": (
                "pretalx.api.serializers.schedule.TalkSlotSerializer",
                {"many": True, "read_only": True, "omit": ("submission", "schedule")},
            ),
            "answers": (
                "pretalx.api.serializers.question.AnswerSerializer",
                {"many": True, "read_only": True},
            ),
            "speakers": (
                "pretalx.api.serializers.speaker.SpeakerSerializer",
                {"many": True, "read_only": True},
            ),
            "resources": (
                "pretalx.api.serializers.submission.ResourceSerializer",
                {"many": True, "read_only": True},
            ),
        }


@register_serializer()
class SubmissionOrgaSerializer(SubmissionSerializer):
    assigned_reviewers = serializers.SlugRelatedField(
        slug_field="code",
        queryset=User.objects.none(),
        required=False,
        many=True,
    )
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    invitations = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reviews"].required = False
        if self.event:
            self.fields["assigned_reviewers"].queryset = self.event.reviewers

    @extend_schema_field(list[int])
    def get_invitations(self, obj):
        qs = obj.invitations.all()
        if serializer := self.get_extra_flex_field("invitations", qs):
            return serializer.data
        return qs.values_list("pk", flat=True)

    def validate_content_locale(self, value):
        if self.event and value not in self.event.content_locales:
            raise serializers.ValidationError(
                f"Invalid locale. Valid choices are: {', '.join(self.event.content_locales)}"
            )
        return value

    def validate_slot_count(self, value):
        if (
            value
            and value != 1
            and not self.event.get_feature_flag("present_multiple_times")
        ):
            raise serializers.ValidationError("Slot count may only be 1 in this event.")
        return value

    def create(self, validated_data):
        tags_data = validated_data.pop("tags", [])
        image = validated_data.pop("image", None)
        validated_data["event"] = self.event
        if "get_duration" in validated_data:
            validated_data["duration"] = validated_data.pop("get_duration")
        if not validated_data.get("content_locale"):
            validated_data["content_locale"] = self.event.locale

        submission = super().create(validated_data)

        if tags_data:
            submission.tags.set(tags_data)
        if image:
            submission.image.save(Path(image.name).name, image, save=True)
            submission.save(update_fields=("image",))
            submission.process_image("image", generate_thumbnail=True)
        return submission

    def update(self, instance, validated_data):
        tags_data = validated_data.pop("tags", [])
        image = validated_data.pop("image", None)
        validated_data["event"] = self.event
        duration_changed = False
        if "get_duration" in validated_data:
            validated_data["duration"] = validated_data.pop("get_duration")
            duration_changed = validated_data["duration"] != instance.duration
        slot_count_changed = (
            "slot_count" in validated_data
            and validated_data["slot_count"] != instance.slot_count
        )
        track_changed = (
            "track" in validated_data and validated_data["track"] != instance.track
        )

        submission = super().update(instance, validated_data)

        if tags_data:
            submission.tags.set(tags_data)
        if image:
            submission.image.save(Path(image.name).name, image)
            submission.process_image("image", generate_thumbnail=True)
        if duration_changed:
            submission.update_duration()
        if slot_count_changed:
            submission.update_talk_slots()
        if track_changed:
            submission.update_review_scores()
        return submission

    class Meta(SubmissionSerializer.Meta):
        fields = SubmissionSerializer.Meta.fields + [
            "pending_state",
            "is_featured",
            "notes",
            "internal_notes",
            "invitation_token",
            "access_code",
            "review_code",
            "anonymised_data",
            "reviews",
            "assigned_reviewers",
            "is_anonymised",
            "median_score",
            "mean_score",
            "created",
            "updated",
            "invitations",
        ]
        # Reviews and assigned reviewers are currently not expandable because
        # reviewers are also receiving the ReviewerOrgaSerializer, but may
        # not be cleared to see all reviews or who is assigned to which review.
        extra_expandable_fields = SubmissionSerializer.Meta.extra_expandable_fields | {
            "speakers": (
                "pretalx.api.serializers.speaker.SpeakerOrgaSerializer",
                {"many": True, "read_only": True},
            ),
            "invitations": (
                "pretalx.api.serializers.submission.SubmissionInvitationSerializer",
                {"many": True, "read_only": True},
            ),
        }
