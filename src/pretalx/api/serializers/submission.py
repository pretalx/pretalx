# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Moesch

from pathlib import Path

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import serializers
from rest_framework.serializers import HiddenField, SerializerMethodField

from pretalx.api.documentation import extend_schema_field
from pretalx.api.serializers.defaults import CurrentEventDefault
from pretalx.api.serializers.fields import UploadedFileField
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.person.models import User
from pretalx.submission.domain.submission import apply_field_changes, create_submission
from pretalx.submission.domain.submission_type import (
    apply_submission_type_field_changes,
)
from pretalx.submission.domain.track import apply_track_field_changes
from pretalx.submission.models import (
    AttendeeSignup,
    QuestionTarget,
    Resource,
    Submission,
    SubmissionInvitation,
    SubmissionType,
    Tag,
    Track,
)
from pretalx.submission.validators.submission import validate_slot_count


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
    is_public = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Resource
        fields = ("resource", "link", "description", "is_public")

    def create(self, validated_data):
        validated_data["link"] = validated_data.get("link") or ""
        return super().create(validated_data)


@register_serializer(versions=CURRENT_VERSIONS)
class TagSerializer(PretalxSerializer):
    event = HiddenField(default=CurrentEventDefault())

    class Meta:
        model = Tag
        fields = ("id", "tag", "description", "color", "is_public", "event")
        # Tag.clean() reports duplicates on the `tag` field; suppress DRF's
        # auto unique validator to avoid the message firing twice.
        validators = []


@register_serializer(versions=CURRENT_VERSIONS)
class SubmissionTypeSerializer(PretalxSerializer):
    event = HiddenField(default=CurrentEventDefault())

    class Meta:
        model = SubmissionType
        fields = (
            "id",
            "name",
            "default_duration",
            "deadline",
            "requires_access_code",
            "attendee_signup_required",
            "event",
        )

    def update(self, instance, validated_data):
        old_values = {field: getattr(instance, field) for field in validated_data}
        instance = super().update(instance, validated_data)
        changed_fields = {
            field
            for field, old in old_values.items()
            if getattr(instance, field) != old
        }
        apply_submission_type_field_changes(instance, changed_fields)
        return instance


@register_serializer(versions=CURRENT_VERSIONS)
class TrackSerializer(PretalxSerializer):
    event = HiddenField(default=CurrentEventDefault())

    class Meta:
        model = Track
        fields = (
            "id",
            "name",
            "description",
            "color",
            "position",
            "requires_access_code",
            "attendee_signup_required",
            "event",
        )

    def update(self, instance, validated_data):
        old_values = {field: getattr(instance, field) for field in validated_data}
        instance = super().update(instance, validated_data)
        changed_fields = {
            field
            for field, old in old_values.items()
            if getattr(instance, field) != old
        }
        apply_track_field_changes(instance, changed_fields)
        return instance


@register_serializer(versions=CURRENT_VERSIONS)
class SubmissionInvitationSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = SubmissionInvitation
        fields = ("id", "email", "created", "updated")
        read_only_fields = ("id", "created", "updated")


@register_serializer(versions=CURRENT_VERSIONS)
class AttendeeSignupSerializer(PretalxSerializer):
    name = serializers.CharField(source="attendee.user.name", read_only=True)
    email = serializers.EmailField(source="attendee.user.email", read_only=True)

    class Meta:
        model = AttendeeSignup
        fields = ("id", "name", "email", "state", "position", "created", "updated")
        read_only_fields = fields


@register_serializer(versions=CURRENT_VERSIONS)
class SubmissionSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    submission_type = serializers.PrimaryKeyRelatedField(
        queryset=SubmissionType.objects.none(), required=True
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
    signup_status = serializers.CharField(read_only=True, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.event:
            return
        self.fields["submission_type"].queryset = self.event.submission_types.all()
        self.fields["track"].queryset = self.event.tracks.all()
        self.fields["tags"].child_relation.queryset = self.event.tags.all()

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
        speakers = obj.sorted_speakers
        if serializer := self.get_extra_flex_field("speakers", speakers):
            return serializer.data
        return [s.code for s in speakers]

    @extend_schema_field(list[int])
    def get_answers(self, obj):
        questions = self.context.get("questions", [])
        if not questions:
            return []
        question_pks = {
            q.pk for q in questions if q.target == QuestionTarget.SUBMISSION
        }
        # Use prefetched answers, filter in Python to avoid busting prefetch cache
        answers = sorted(
            [a for a in obj.answers.all() if a.question_id in question_pks],
            key=lambda a: a.question.position,
        )
        if serializer := self.get_extra_flex_field("answers", answers):
            return serializer.data
        return [a.pk for a in answers]

    @extend_schema_field(list[int])
    def get_slots(self, obj):
        schedule = self.context.get("schedule")
        if not schedule:
            return []
        public_slots = self.context.get("public_slots", True)
        # Use prefetched slots, filter in Python to avoid busting prefetch cache
        slots = [s for s in obj.slots.all() if s.schedule_id == schedule.pk]
        if public_slots:
            slots = [s for s in slots if s.is_visible]
        if serializer := self.get_extra_flex_field("slots", slots):
            return serializer.data
        return [s.pk for s in slots]

    @extend_schema_field(list[int])
    def get_resources(self, obj):
        public_resources = self.context.get("public_resources", True)
        # Use prefetched resources, filter in Python to avoid busting prefetch cache
        resources = [r for r in obj.resources.all() if r.url]
        if public_resources:
            resources = [r for r in resources if r.is_public]
        resources.sort(key=lambda r: r.link or "")
        if serializer := self.get_extra_flex_field("resources", resources):
            return serializer.data
        return [r.pk for r in resources]

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
            "attendee_signup_required",
            "attendee_signup_capacity",
            "signup_status",
            "content_locale",
            "do_not_record",
            "image",
            "resources",
            "slots",
            "answers",
        ]
        read_only_fields = ("code", "state", "signup_status")
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
    anonymised_data = serializers.JSONField(source="anonymised", required=False)
    assigned_reviewers = serializers.SlugRelatedField(
        slug_field="code", queryset=User.objects.none(), required=False, many=True
    )
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    invitations = serializers.SerializerMethodField()
    event = HiddenField(default=CurrentEventDefault())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reviews"].required = False
        if self.event:
            self.fields[
                "assigned_reviewers"
            ].child_relation.queryset = self.event.reviewers
            if "content_locale" in self.fields:
                required = self.fields["content_locale"].required
                self.fields["content_locale"] = serializers.ChoiceField(
                    choices=[(loc, loc) for loc in self.event.content_locales],
                    required=required,
                )

    @extend_schema_field(list[int])
    def get_invitations(self, obj):
        invitations = obj.invitations.all()
        if serializer := self.get_extra_flex_field("invitations", invitations):
            return serializer.data
        return [i.pk for i in invitations]

    def validate_slot_count(self, value):
        validate_slot_count(value, event=self.event)
        return value

    def _store_image(self, submission, image):
        # ``image`` is a FieldFile pointing at the API upload cache (see
        # UploadedFileField); ``image.save`` routes the bytes through
        # ``Submission.image.upload_to`` so they land at the proper
        # ``{event.slug}/submissions/{code}/`` path.
        submission.image.save(Path(image.name).name, image, save=True)
        submission.process_image("image")

    def create(self, validated_data):
        image = validated_data.pop("image", None)
        tags = validated_data.pop("tags", None) or ()
        assigned_reviewers = validated_data.pop("assigned_reviewers", None)
        if "get_duration" in validated_data:
            validated_data["duration"] = validated_data.pop("get_duration")
        if not validated_data.get("content_locale"):
            validated_data["content_locale"] = self.event.locale

        submission = create_submission(
            submission=Submission(**validated_data),
            user=self.context["request"].user,
            orga=True,
            tags=tags,
        )
        if assigned_reviewers is not None:
            submission.assigned_reviewers.set(assigned_reviewers)
        if image:
            self._store_image(submission, image)
        return submission

    def update(self, instance, validated_data):
        image = validated_data.pop("image", None)
        if "get_duration" in validated_data:
            validated_data["duration"] = validated_data.pop("get_duration")
        changed_fields = {
            field
            for field, value in validated_data.items()
            if getattr(instance, field, object()) != value
        }

        submission = super().update(instance, validated_data)

        if image:
            self._store_image(submission, image)
        apply_field_changes(submission, changed_fields)
        return submission

    class Meta(SubmissionSerializer.Meta):
        fields = [
            *SubmissionSerializer.Meta.fields,
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
            "event",
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


@register_serializer()
class SubmissionReviewerSerializer(SubmissionSerializer):
    """Limited version of the SubmissionOrgaSerializer that includes
    the appropriate internal fields, but uses the default public speaker
    serializer to avoid leaking information like speaker email addresses.
    """

    class Meta(SubmissionSerializer.Meta):
        fields = [
            *SubmissionSerializer.Meta.fields,
            "pending_state",
            "is_featured",
            "notes",
            "internal_notes",
            "created",
            "updated",
        ]
