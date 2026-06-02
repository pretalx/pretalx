# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_flex_fields.serializers import FlexFieldsSerializerMixin
from rest_framework import serializers
from rest_framework.serializers import HiddenField

from pretalx.api.serializers.defaults import CurrentOrganiserDefault
from pretalx.api.serializers.mixins import PretalxSerializer
from pretalx.api.versions import CURRENT_VERSIONS, register_serializer
from pretalx.event.models import Event, Team, TeamInvite
from pretalx.event.validators.team import (
    TEAM_PERMISSION_FIELDS,
    validate_team_event_coverage,
    validate_team_has_permission,
)
from pretalx.person.models import User
from pretalx.submission.models import Track


@register_serializer(versions=CURRENT_VERSIONS)
class TeamMemberSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = User
        fields = ("code", "name", "email")


@register_serializer(versions=CURRENT_VERSIONS)
class TeamInviteSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    class Meta:
        model = TeamInvite
        fields = ("id", "email", "token")


@register_serializer(versions=CURRENT_VERSIONS)
class TeamSerializer(FlexFieldsSerializerMixin, PretalxSerializer):
    limit_events = serializers.SlugRelatedField(
        slug_field="slug", many=True, queryset=Event.objects.none(), required=False
    )
    limit_tracks = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Track.objects.none(), required=False
    )
    members = serializers.SlugRelatedField(
        slug_field="code", many=True, required=False, queryset=User.objects.none()
    )
    invites = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=TeamInvite.objects.none()
    )
    organiser = HiddenField(default=CurrentOrganiserDefault())

    class Meta:
        model = Team
        fields = (
            "id",
            "name",
            "members",
            "invites",
            "all_events",
            "limit_events",
            "limit_tracks",
            "can_create_events",
            "can_change_teams",
            "can_change_organiser_settings",
            "can_change_event_settings",
            "can_change_submissions",
            "is_reviewer",
            "force_hide_speaker_names",
            "organiser",
        )
        expandable_fields = {
            "limit_tracks": (
                "pretalx.api.serializers.submission.TrackSerializer",
                {"many": True},
            ),
            "members": (TeamMemberSerializer, {"many": True, "required": False}),
            "invites": (TeamInviteSerializer, {"many": True, "required": False}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = kwargs.get("context", {}).get("request")
        if request and hasattr(request, "organiser"):
            self.fields[
                "limit_events"
            ].child_relation.queryset = request.organiser.events.all()
            self.fields["limit_tracks"].child_relation.queryset = Track.objects.filter(
                event__organiser=request.organiser
            )
            self.fields["invites"].child_relation.queryset = TeamInvite.objects.filter(
                team__organiser=request.organiser
            )
        if (
            self.instance
            and not isinstance(self.instance, list)
            and not self.instance._state.adding
        ):
            self.fields[
                "limit_events"
            ].child_relation.queryset = self.instance.events.all()
            self.fields["members"].child_relation.queryset = self.instance.members.all()

    def validate(self, data):
        validate_team_event_coverage(
            all_events=self.get_with_fallback(data, "all_events"),
            limit_events=self.get_with_fallback(data, "limit_events"),
        )
        validate_team_has_permission(
            {
                field: self.get_with_fallback(data, field)
                for field in TEAM_PERMISSION_FIELDS
            }
        )
        return data
