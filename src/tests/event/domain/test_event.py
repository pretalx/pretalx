# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.common.models import ActivityLog
from pretalx.event.domain.event import (
    activate_event,
    activation_blockers,
    apply_date_edit,
    apply_event_changes,
    apply_timezone_edit,
    copy_event_data,
    create_event,
    deactivate_event,
    initialise_event,
    move_full_event,
    post_create_event,
    shred_event,
)
from pretalx.event.models import Event, Organiser
from pretalx.mail.enums import MailTemplateRoles
from pretalx.mail.models import MailTemplate
from pretalx.orga.signals import activate_event as activate_event_signal
from pretalx.person.models import SpeakerInformation
from pretalx.person.models.preferences import UserEventPreferences
from pretalx.schedule.models import Availability, Schedule
from pretalx.schedule.models.slot import TalkSlot
from pretalx.submission.models import Submission, SubmissionType
from pretalx.submission.models.feedback import Feedback
from pretalx.submission.models.question import Answer, Question
from pretalx.submission.models.resource import Resource
from pretalx.submission.models.tag import Tag
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    AvailabilityFactory,
    EventExtraLinkFactory,
    EventFactory,
    MailTemplateFactory,
    OrganiserFactory,
    QuestionFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserEventPreferencesFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("with_user", (True, False), ids=("logged", "unlogged"))
def test_create_event_persists_fields_initialises_and_logs(with_user):
    organiser = OrganiserFactory()
    user = UserFactory() if with_user else None

    event = create_event(
        organiser=organiser,
        locales=["en", "de"],
        user=user,
        slug="MixedCase",
        primary_color="#ff0000",
        name="Test Event",
        timezone="UTC",
        email="test@example.com",
        locale="en",
        date_from=dt.date(2025, 6, 10),
        date_to=dt.date(2025, 6, 12),
    )

    event = refresh(event)
    assert event.slug == "mixedcase"
    assert event.locales == ["en", "de"]
    assert event.content_locales == ["en", "de"]
    assert event.primary_color == "#ff0000"
    with scope(event=event):
        assert event.cfp.event == event
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)
        assert (
            event.logged_actions().filter(action_type="pretalx.event.create").exists()
            is with_user
        )


def test_post_create_event_with_umbrella_rights_writes_settings_without_team(event):
    deadline = dt.datetime(2025, 7, 1, 12, 0)
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)
    original_display = dict(event.display_settings)
    team_count = event.organiser.teams.count()
    event.logo = "fake/path.png"

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        post_create_event(
            event,
            user=user,
            deadline=deadline,
            display_settings={"header_pattern": "topo", "header_image": ""},
        )

    mock_process.assert_called_once_with("logo")
    event.refresh_from_db(fields=["display_settings"])
    with scope(event=event):
        assert event.cfp.deadline == deadline.replace(tzinfo=event.tz)
    assert event.display_settings == {**original_display, "header_pattern": "topo"}
    assert event.organiser.teams.count() == team_count


@pytest.mark.parametrize(
    "display_settings", (None, {"header_pattern": ""}), ids=("absent", "empty_values")
)
def test_post_create_event_without_umbrella_rights_creates_creator_team(
    event, display_settings
):
    user = UserFactory()
    initial_team_count = event.organiser.teams.count()
    original_display = dict(event.display_settings)
    event.logo = None

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        post_create_event(event, user=user, display_settings=display_settings)

    mock_process.assert_not_called()
    event.refresh_from_db(fields=["display_settings"])
    assert event.display_settings == original_display
    assert event.organiser.teams.count() == initial_team_count + 1
    new_team = event.organiser.teams.exclude(
        pk__in=event.organiser.teams.filter(all_events=True).values("pk")
    ).latest("pk")
    assert new_team.can_change_event_settings
    assert new_team.can_change_submissions
    assert not new_team.all_events
    assert list(new_team.members.all()) == [user]
    assert list(new_team.limit_events.all()) == [event]


def test_initialise_event_creates_supporting_data(event):
    with scope(event=event):
        assert event.cfp.event == event
        assert event.cfp.default_type.event_id == event.pk
        assert event.schedules.filter(version__isnull=True).exists()
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)
        assert event.review_phases.count() == 2
        category = event.score_categories.get()
        assert category.scores.count() == 3


def test_initialise_event_is_idempotent_and_recreates_deleted_parts(event):
    with scope(event=event):
        template_count = event.mail_templates.count()
        schedule_count = event.schedules.count()
        existing_type = event.cfp.default_type

        initialise_event(event)

        assert event.mail_templates.count() == template_count
        assert event.schedules.count() == schedule_count

        event.cfp.delete()
        event.mail_templates.all().delete()

    event = refresh(event)
    with scope(event=event):
        initialise_event(event)

        assert event.cfp.default_type == existing_type
        assert SubmissionType.objects.filter(event=event).count() == 1
        assert event.mail_templates.count() == template_count


def test_copy_event_data_copies_configuration(event):
    user = UserFactory()
    deadline = tz_now() + dt.timedelta(days=30)
    source = EventFactory(
        organiser=event.organiser,
        primary_color="#ff0000",
        locale="de",
        locales=["de", "en"],
        feature_flags={"testing": True},
        custom_domain="https://custom.example.org",
        mail_settings={"signature": "-- The Team", "reply_to": "team@example.org"},
        attendee_signup_settings={"signup_domains": ["example.org"]},
        cfp__deadline=deadline,
    )
    source.settings.custom_value = "test123"
    MailTemplateFactory(
        event=source, subject="Custom Template", is_auto_created=False, role=None
    )
    EventExtraLinkFactory(
        event=source, label="Blog", url="https://blog.example.com", role="footer"
    )
    TagFactory(event=source, tag="Sponsored", color="#00ff00", is_public=True)
    TagFactory(event=source, tag="Keynote")
    UserEventPreferencesFactory(user=user, event=source, preferences={"theme": "dark"})

    copy_event_data(event=event, source=source)

    event = refresh(event)
    assert event.primary_color == "#ff0000"
    assert event.locale == "de"
    assert event.feature_flags == source.feature_flags
    assert event.custom_domain is None
    assert event.mail_settings["signature"] == "-- The Team"
    assert event.mail_settings["reply_to"] == "team@example.org"
    assert event.attendee_signup_settings["signup_domains"] == ["example.org"]
    assert event.settings.custom_value == "test123"
    with scope(event=event):
        assert event.cfp.deadline == deadline
        assert [
            str(t.subject) for t in event.mail_templates.filter(role__isnull=True)
        ] == ["Custom Template"]
        assert event.mail_templates.count() == len(MailTemplateRoles.choices) + 1
        link = event.extra_links.get()
        assert (str(link.label), link.url, link.role) == (
            "Blog",
            "https://blog.example.com",
            "footer",
        )
        tags = {t.tag: t for t in event.tags.all()}
    assert set(tags) == {"Sponsored", "Keynote"}
    assert tags["Sponsored"].color == "#00ff00"
    assert tags["Sponsored"].is_public is True
    with scope(event=source):
        assert source.tags.count() == 2
    prefs = UserEventPreferences.objects.get(event=event, user=user)
    assert prefs.preferences == {"theme": "dark"}


def test_copy_event_data_copies_structure_and_remaps_track_and_type_links(event):
    source = EventFactory(organiser=event.organiser)
    track = TrackFactory(event=source, name="Security")
    TrackFactory(event=source, name="Design")
    foreign_track = TrackFactory(event=EventFactory(organiser=event.organiser))
    sub_type = SubmissionTypeFactory(event=source, name="Workshop")
    team = TeamFactory(organiser=event.organiser, all_events=False)
    team.limit_events.add(source)
    team.limit_tracks.add(track, foreign_track)
    untracked_team = TeamFactory(organiser=event.organiser, all_events=False)
    untracked_team.limit_events.add(source)
    question = QuestionFactory(
        event=source,
        question="What is your experience level?",
        variant="choices",
        target="submission",
    )
    AnswerOptionFactory(question=question, answer="Beginner")
    AnswerOptionFactory(question=question, answer="Expert")
    question.tracks.add(track)
    question.submission_types.add(sub_type)
    AnswerFactory(
        question=question, answer="Expert", submission=SubmissionFactory(event=source)
    )
    info = SpeakerInformationFactory(
        event=source, title="Travel Info", text="We cover travel costs."
    )
    info.limit_tracks.add(track)
    info.limit_types.add(sub_type)
    source.score_categories.all().delete()
    category = ReviewScoreCategoryFactory(event=source, name="Quality")
    category.limit_tracks.add(track)
    ReviewScoreFactory(category=category, value=0, label="Bad")
    ReviewScoreFactory(category=category, value=1, label="Good")
    with scope(event=source):
        source_type_count = source.submission_types.count()

    copy_event_data(event=event, source=source, teams=[team, untracked_team])

    with scope(event=event):
        assert event.submission_types.count() == source_type_count
        copied_type = event.submission_types.get(name="Workshop")
        assert sorted(str(t.name) for t in event.tracks.all()) == ["Design", "Security"]
        copied_track = event.tracks.get(name="Security")
        copied_q = event.questions.get()
        assert str(copied_q.question) == "What is your experience level?"
        assert sorted(o.answer for o in copied_q.options.all()) == [
            "Beginner",
            "Expert",
        ]
        assert list(copied_q.tracks.all()) == [copied_track]
        assert list(copied_q.submission_types.all()) == [copied_type]
        assert Answer.objects.filter(question=copied_q).count() == 0
        copied_info = event.information.get()
        assert str(copied_info.title) == "Travel Info"
        assert list(copied_info.limit_tracks.all()) == [copied_track]
        assert list(copied_info.limit_types.all()) == [copied_type]
        quality = event.score_categories.get()
        assert str(quality.name) == "Quality"
        assert sorted(quality.scores.values_list("value", "label")) == [
            (0, "Bad"),
            (1, "Good"),
        ]
        assert list(quality.limit_tracks.all()) == [copied_track]
    assert set(team.limit_events.all()) == {source, event}
    assert set(team.limit_tracks.all()) == {track, foreign_track, copied_track}
    assert set(untracked_team.limit_events.all()) == {source, event}
    assert list(untracked_team.limit_tracks.all()) == []


def test_copy_event_data_shifts_dates_and_omits_hidden_rooms(event):
    source = EventFactory(
        organiser=event.organiser,
        date_from=dt.date(2025, 1, 1),
        date_to=dt.date(2025, 1, 3),
    )
    room = RoomFactory(event=source, name="Main Hall")
    RoomFactory(event=source, name="Attic", hidden=True)
    avail = AvailabilityFactory(event=source, room=room)
    phase_start = tz_now()
    phase_end = tz_now() + dt.timedelta(days=14)
    with scope(event=source):
        source.review_phases.all().delete()
        ReviewPhaseFactory(
            event=source,
            name="Source Phase",
            start=phase_start,
            end=phase_end,
            is_active=True,
        )
    delta = event.date_from - source.date_from

    copy_event_data(event=event, source=source)

    with scope(event=event):
        copied_room = event.rooms.get()
        assert str(copied_room.name) == "Main Hall"
        copied_avail = copied_room.availabilities.get()
        assert copied_avail.start == avail.start + delta
        assert copied_avail.end == avail.end + delta
        phase = event.review_phases.get()
        assert str(phase.name) == "Source Phase"
        assert phase.is_active is False
        assert phase.start == phase_start + delta
        assert phase.end == phase_end + delta


def test_copy_event_data_respects_skip_attributes_and_existing_rooms(event):
    source = EventFactory(
        organiser=event.organiser,
        primary_color="#ff0000",
        feature_flags={"testing": True},
    )
    RoomFactory(event=source, name="Source Room")
    RoomFactory(event=event, name="Existing Room")
    original_flags = event.feature_flags.copy()

    copy_event_data(event=event, source=source, skip_attributes=["feature_flags"])

    assert event.feature_flags == original_flags
    assert event.primary_color == "#ff0000"
    with scope(event=event):
        assert [str(r.name) for r in event.rooms.all()] == ["Existing Room"]


def _reload(event):
    return Event.objects.get(pk=event.pk)


def test_apply_date_edit_moves_wip_slots_and_availabilities_not_published():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    released = ScheduleFactory(event=event, version="v1")
    published_slot = TalkSlotFactory(submission=sub, schedule=released)
    wip_slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    avail = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 17, 0, tzinfo=dt.UTC),
    )
    published_original_start = published_slot.start
    wip_original_start = wip_slot.start
    old_event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_date_edit(event, old_event)

    published_slot.refresh_from_db()
    wip_slot.refresh_from_db()
    avail.refresh_from_db()
    assert published_slot.start == published_original_start
    assert wip_slot.start == wip_original_start + dt.timedelta(days=1)
    assert avail.start == dt.datetime(2024, 6, 11, 9, 0, tzinfo=dt.UTC)
    assert avail.end == dt.datetime(2024, 6, 11, 17, 0, tzinfo=dt.UTC)


def test_apply_date_edit_shortening_deschedules_and_deletes_outside_range():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 14))
    sub = SubmissionFactory(event=event)
    inside_slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    outside_slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 14, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 14, 11, 0, tzinfo=dt.UTC),
    )
    inside = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 17, 0, tzinfo=dt.UTC),
    )
    outside = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 14, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 14, 17, 0, tzinfo=dt.UTC),
    )
    old_event = _reload(event)

    event.date_to = dt.date(2024, 6, 12)
    apply_date_edit(event, old_event)

    inside_slot.refresh_from_db()
    outside_slot.refresh_from_db()
    assert inside_slot.start == dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC)
    assert (outside_slot.start, outside_slot.end, outside_slot.room) == (
        None,
        None,
        None,
    )
    assert Availability.objects.filter(pk=inside.pk).exists()
    assert not Availability.objects.filter(pk=outside.pk).exists()


def test_apply_date_edit_without_slots_or_with_extended_end_moves_nothing():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    old_event = _reload(event)
    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)

    apply_date_edit(event, old_event)

    event = _reload(event)
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    original_start = slot.start
    event.date_to = dt.date(2024, 6, 14)

    apply_date_edit(event, old_event)

    slot.refresh_from_db()
    assert slot.start == original_start


def test_apply_timezone_edit_preserves_apparent_local_time_across_schedules():
    event = EventFactory(
        date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12), timezone="UTC"
    )
    sub = SubmissionFactory(event=event)
    released = ScheduleFactory(event=event, version="v1")
    published_slot = TalkSlotFactory(
        submission=sub,
        schedule=released,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    wip_slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    avail = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 17, 0, tzinfo=dt.UTC),
    )
    old_event = _reload(event)
    event = _reload(event)  # drop cached tz
    event.timezone = "Europe/Berlin"

    apply_timezone_edit(event, old_event)

    published_slot.refresh_from_db()
    wip_slot.refresh_from_db()
    avail.refresh_from_db()
    # 10:00 UTC was 10:00 wall-clock under UTC; preserving the wall
    # clock under Berlin (UTC+2 in June) means 08:00 UTC.
    assert wip_slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)
    assert published_slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)
    assert avail.start == dt.datetime(2024, 6, 10, 7, 0, tzinfo=dt.UTC)
    assert avail.end == dt.datetime(2024, 6, 10, 15, 0, tzinfo=dt.UTC)


def test_apply_timezone_edit_without_slots_or_same_offset_moves_nothing():
    event = EventFactory(
        date_from=dt.date(2024, 6, 10),
        date_to=dt.date(2024, 6, 12),
        timezone="Europe/Berlin",
    )
    old_event = _reload(event)
    event = _reload(event)
    event.timezone = "Europe/Paris"

    apply_timezone_edit(event, old_event)

    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
    )

    apply_timezone_edit(event, old_event)

    slot.refresh_from_db()
    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


def test_apply_event_changes_persists_and_shifts_listed_fields():
    event = EventFactory(
        date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12), timezone="UTC"
    )
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    event.timezone = "Europe/Berlin"
    apply_event_changes(event, {"date_from", "date_to", "timezone"})

    event.refresh_from_db()
    slot.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 11)
    assert event.date_to == dt.date(2024, 6, 13)
    assert event.timezone == "Europe/Berlin"
    assert slot.start == dt.datetime(2024, 6, 11, 8, 0, tzinfo=dt.UTC)


def test_apply_event_changes_does_not_shift_when_field_not_listed():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    original_start = slot.start
    event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_event_changes(event, set())

    event.refresh_from_db()
    slot.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 11)
    assert slot.start == original_start


@pytest.mark.parametrize(
    ("changed", "processed"),
    (({"logo"}, True), ({"date_from"}, False)),
    ids=("image_changed", "image_unchanged"),
)
def test_apply_event_changes_processes_image_only_when_changed(changed, processed):
    event = EventFactory()

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        apply_event_changes(event, changed)

    assert mock_process.call_args_list == ([(("logo",),)] if processed else [])


def test_shred_event_deletes_all_related_data(populated_event):
    event = populated_event
    pk = event.pk

    shred_event(event)

    assert not Event.objects.filter(pk=pk).exists()
    assert not Submission.all_objects.filter(event_id=pk).exists()
    assert not TalkSlot.objects.filter(schedule__event_id=pk).exists()
    assert not Feedback.objects.filter(talk__event_id=pk).exists()
    assert not Resource.objects.filter(submission__event_id=pk).exists()
    assert not Answer.objects.filter(question__event_id=pk).exists()
    assert not Question.all_objects.filter(event_id=pk).exists()
    assert not Tag.objects.filter(event_id=pk).exists()
    assert not SpeakerInformation.objects.filter(event_id=pk).exists()
    assert not MailTemplate.objects.filter(event_id=pk).exists()
    assert not Schedule.objects.filter(event_id=pk).exists()


def test_shred_event_audit_log_survives_delete_failure(event):
    organiser = event.organiser
    organiser_ct = ContentType.objects.get_for_model(Organiser)

    with (
        patch(
            "pretalx.event.domain.event.transaction.atomic",
            side_effect=RuntimeError("simulated delete failure"),
        ),
        pytest.raises(RuntimeError, match="simulated delete failure"),
    ):
        shred_event(event)

    assert ActivityLog.objects.filter(
        action_type="pretalx.event.delete",
        content_type=organiser_ct,
        object_id=organiser.pk,
    ).exists()


def test_activate_then_deactivate_event_toggles_public_and_logs(
    register_signal_handler,
):
    event = EventFactory(is_public=False)
    user = UserFactory()
    checks = []

    def responder(signal, sender, check=None, **kwargs):
        checks.append(check)
        return "all good"

    def silent(signal, sender, **kwargs):
        return None

    register_signal_handler(activate_event_signal, responder)
    register_signal_handler(activate_event_signal, silent)

    exceptions, extra = activate_event(event, user=user)

    event.refresh_from_db()
    assert event.is_public
    assert exceptions == []
    assert extra == ["all good"]
    assert checks == [False]
    with scope(event=event):
        assert (
            event.logged_actions().filter(action_type="pretalx.event.activate").exists()
        )

    deactivate_event(event, user=user)

    event.refresh_from_db()
    assert not event.is_public
    with scope(event=event):
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.event.deactivate")
            .exists()
        )


def test_activate_event_returns_plugin_exceptions_and_does_not_activate(
    register_signal_handler,
):
    event = EventFactory(is_public=False)
    user = UserFactory()

    def blocker(signal, sender, **kwargs):
        raise RuntimeError("nope")

    register_signal_handler(activate_event_signal, blocker)

    exceptions, extra = activate_event(event, user=user)

    event.refresh_from_db()
    assert not event.is_public
    assert len(exceptions) == 1
    assert isinstance(exceptions[0], RuntimeError)
    assert extra == []
    with scope(event=event):
        assert (
            not event.logged_actions()
            .filter(action_type="pretalx.event.activate")
            .exists()
        )


def test_activation_blockers_check_splits_exceptions_and_messages_without_activating(
    register_signal_handler,
):
    event = EventFactory(is_public=False)
    checks = []

    def blocker(signal, sender, check=False, **kwargs):
        checks.append(check)
        raise ValueError("Pay **first**")

    def informer(signal, sender, **kwargs):
        return "You have 2 more event activations left."

    register_signal_handler(activate_event_signal, blocker)
    register_signal_handler(activate_event_signal, informer)

    exceptions, messages = activation_blockers(event, check=True)

    event.refresh_from_db()
    assert [str(exception) for exception in exceptions] == ["Pay **first**"]
    assert messages == ["You have 2 more event activations left."]
    assert checks == [True]
    assert not event.is_public


def test_move_full_event_shifts_dates_all_slots_and_availabilities():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    released = ScheduleFactory(event=event, version="v1")
    published_slot = TalkSlotFactory(
        submission=sub,
        schedule=released,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    wip_slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 11, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 11, 11, 0, tzinfo=dt.UTC),
    )
    avail = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 17, 0, tzinfo=dt.UTC),
    )

    move_full_event(event, dt.date(2024, 6, 13))

    event.refresh_from_db()
    published_slot.refresh_from_db()
    wip_slot.refresh_from_db()
    avail.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 13)
    assert event.date_to == dt.date(2024, 6, 15)
    assert published_slot.start == dt.datetime(2024, 6, 13, 10, 0, tzinfo=dt.UTC)
    assert wip_slot.start == dt.datetime(2024, 6, 14, 10, 0, tzinfo=dt.UTC)
    assert avail.start == dt.datetime(2024, 6, 13, 9, 0, tzinfo=dt.UTC)
    assert avail.end == dt.datetime(2024, 6, 13, 17, 0, tzinfo=dt.UTC)


def test_move_full_event_same_date_noop():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    original_start = slot.start

    move_full_event(event, event.date_from)

    event.refresh_from_db()
    slot.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 10)
    assert slot.start == original_start
