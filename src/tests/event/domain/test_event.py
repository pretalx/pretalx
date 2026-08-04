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
    TalkSlotFactory,
    TeamFactory,
    TrackFactory,
    UserEventPreferencesFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _common_fields():
    return {
        "name": "Test Event",
        "timezone": "UTC",
        "email": "test@example.com",
        "locale": "en",
        "date_from": dt.date(2025, 6, 10),
        "date_to": dt.date(2025, 6, 12),
    }


def test_create_event_lowercases_slug():
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser, locales=["en"], slug="MixedCase", **_common_fields()
    )

    assert event.slug == "mixedcase"
    assert Event.objects.get(pk=event.pk).slug == "mixedcase"


def test_create_event_writes_locales():
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser, locales=["en", "de"], slug="evt", **_common_fields()
    )

    assert event.locales == ["en", "de"]
    assert event.content_locales == ["en", "de"]


def test_create_event_passes_through_extra_fields():
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser,
        locales=["en"],
        slug="evt",
        primary_color="#ff0000",
        **_common_fields(),
    )

    assert event.primary_color == "#ff0000"


def test_create_event_initialises_event():
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser, locales=["en"], slug="evt", **_common_fields()
    )

    with scope(event=event):
        assert event.cfp.event == event
        assert event.schedules.filter(version__isnull=True).exists()
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)
        assert event.review_phases.count() == 2
        assert event.score_categories.count() == 1


def test_create_event_logs_action_when_user_passed():
    organiser = OrganiserFactory()
    user = UserFactory()

    event = create_event(
        organiser=organiser, locales=["en"], user=user, slug="evt", **_common_fields()
    )

    with scope(event=event):
        assert (
            event.logged_actions().filter(action_type="pretalx.event.create").exists()
        )


def test_post_create_event_sets_cfp_deadline(event):
    deadline = dt.datetime(2025, 7, 1, 12, 0)
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)

    post_create_event(event, user=user, deadline=deadline)

    with scope(event=event):
        assert event.cfp.deadline == deadline.replace(tzinfo=event.tz)


def test_post_create_event_writes_display_settings(event):
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)

    post_create_event(event, user=user, display_settings={"header_pattern": "topo"})

    event.refresh_from_db()
    assert event.display_settings["header_pattern"] == "topo"


def test_post_create_event_skips_empty_display_setting_values(event):
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)
    original = dict(event.display_settings)

    post_create_event(event, user=user, display_settings={"header_pattern": ""})

    event.refresh_from_db()
    assert event.display_settings == original


def test_post_create_event_creates_creator_team_when_user_lacks_umbrella_rights(event):
    user = UserFactory()
    initial_team_count = event.organiser.teams.count()

    post_create_event(event, user=user)

    assert event.organiser.teams.count() == initial_team_count + 1
    new_team = event.organiser.teams.exclude(
        pk__in=event.organiser.teams.filter(all_events=True).values("pk")
    ).latest("pk")
    assert new_team.can_change_event_settings
    assert new_team.can_change_submissions
    assert not new_team.all_events
    assert user in new_team.members.all()
    assert event in new_team.limit_events.all()


def test_post_create_event_skips_creator_team_when_user_has_umbrella_rights(event):
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)
    initial_team_count = event.organiser.teams.count()

    post_create_event(event, user=user)

    assert event.organiser.teams.count() == initial_team_count


def test_post_create_event_processes_logo_when_present(event):
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)
    event.logo = "fake/path.png"

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        post_create_event(event, user=user)

    mock_process.assert_called_once_with("logo")


def test_post_create_event_skips_logo_processing_when_absent(event):
    user = UserFactory()
    TeamFactory(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).members.add(user)
    event.logo = None

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        post_create_event(event, user=user)

    mock_process.assert_not_called()


def test_initialise_event_creates_cfp(event):
    with scope(event=event):
        assert event.cfp.event == event
        assert event.cfp.default_type.event == event


def test_initialise_event_creates_wip_schedule(event):
    with scope(event=event):
        assert event.schedules.filter(version__isnull=True).exists()


def test_initialise_event_creates_mail_templates(event):
    with scope(event=event):
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)


def test_initialise_event_creates_review_phases(event):
    with scope(event=event):
        assert event.review_phases.count() == 2


def test_initialise_event_creates_score_categories(event):
    with scope(event=event):
        assert event.score_categories.count() == 1
        category = event.score_categories.first()
        assert category.scores.count() == 3


def test_initialise_event_is_idempotent(event):
    with scope(event=event):
        template_count = event.mail_templates.count()
        schedule_count = event.schedules.count()

        initialise_event(event)

        assert event.mail_templates.count() == template_count
        assert event.schedules.count() == schedule_count


def test_initialise_event_recreates_after_deletion(event):
    with scope(event=event):
        event.cfp.delete()
        event.mail_templates.all().delete()
        initialise_event(event)

        assert event.cfp.event == event
        assert event.cfp.default_type.event == event
        assert event.mail_templates.count() == len(MailTemplateRoles.choices)


def test_initialise_event_reuses_existing_submission_type(event):
    with scope(event=event):
        existing_type = event.cfp.default_type
        event.cfp.delete()

    event = refresh(event)
    with scope(event=event):
        initialise_event(event)

        assert event.cfp.default_type == existing_type
        assert SubmissionType.objects.filter(event=event).count() == 1


def test_copy_event_data_copies_attributes(event):
    other_event = EventFactory(
        organiser=event.organiser,
        primary_color="#ff0000",
        locale="de",
        locales=["de", "en"],
        feature_flags={"testing": True},
    )

    copy_event_data(event=event, source=other_event)

    assert event.primary_color == "#ff0000"
    assert event.locale == "de"
    assert event.feature_flags == other_event.feature_flags


def test_copy_event_data_does_not_copy_custom_domain(event):
    other_event = EventFactory(
        organiser=event.organiser, custom_domain="https://custom.example.org"
    )

    copy_event_data(event=event, source=other_event)

    assert event.custom_domain is None


def test_copy_event_data_respects_skip_attributes(event):
    other_event = EventFactory(
        organiser=event.organiser,
        primary_color="#ff0000",
        feature_flags={"testing": True},
    )

    original_flags = event.feature_flags.copy()
    copy_event_data(event=event, source=other_event, skip_attributes=["feature_flags"])

    assert event.feature_flags == original_flags
    assert event.primary_color == "#ff0000"


def test_copy_event_data_copies_submission_types(event):
    other_event = EventFactory(organiser=event.organiser)
    SubmissionTypeFactory(event=other_event, name="Workshop")

    with scope(event=other_event):
        source_type_count = other_event.submission_types.count()

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        assert event.submission_types.count() == source_type_count


def test_copy_event_data_copies_tracks(event):
    other_event = EventFactory(organiser=event.organiser)
    TrackFactory(event=other_event, name="Security")

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        track_names = [str(t.name) for t in event.tracks.all()]
        assert track_names == ["Security"]


def test_copy_event_data_copies_mail_templates(event):
    other_event = EventFactory(organiser=event.organiser)
    MailTemplateFactory(
        event=other_event, subject="Custom Template", is_auto_created=False, role=None
    )

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        subjects = [str(t.subject) for t in event.mail_templates.all()]
        assert "Custom Template" in subjects


def test_copy_event_data_copies_extra_links(event):
    other_event = EventFactory(organiser=event.organiser)
    EventExtraLinkFactory(
        event=other_event, label="Blog", url="https://blog.example.com", role="footer"
    )

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        links = list(event.extra_links.all())
        assert len(links) == 1
        assert str(links[0].label) == "Blog"
        assert links[0].url == "https://blog.example.com"


def test_copy_event_data_copies_rooms_and_availabilities(event):
    other_event = EventFactory(
        organiser=event.organiser,
        date_from=dt.date(2025, 1, 1),
        date_to=dt.date(2025, 1, 3),
    )
    room = RoomFactory(event=other_event, name="Main Hall")
    avail = AvailabilityFactory(event=other_event, room=room)
    event.rooms.all().delete()

    copy_event_data(event=event, source=other_event)

    delta = event.date_from - other_event.date_from
    with scope(event=event):
        rooms = list(event.rooms.all())
        assert len(rooms) == 1
        assert str(rooms[0].name) == "Main Hall"
        copied_avail = rooms[0].availabilities.first()
        assert copied_avail is not None
        assert copied_avail.start == avail.start + delta
        assert copied_avail.end == avail.end + delta


def test_copy_event_data_omits_hidden_rooms(event):
    other_event = EventFactory(organiser=event.organiser)
    RoomFactory(event=other_event, name="Main Hall")
    RoomFactory(event=other_event, name="Attic", hidden=True)
    event.rooms.all().delete()

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        assert [str(room.name) for room in event.rooms.all()] == ["Main Hall"]


def test_copy_event_data_skips_rooms_when_target_has_rooms(event):
    other_event = EventFactory(organiser=event.organiser)
    RoomFactory(event=other_event, name="Source Room")
    RoomFactory(event=event, name="Existing Room")

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        room_names = [str(r.name) for r in event.rooms.all()]
        assert "Existing Room" in room_names
        assert "Source Room" not in room_names


def test_copy_event_data_copies_questions_with_options_and_tracks(event):
    other_event = EventFactory(organiser=event.organiser)
    track = TrackFactory(event=other_event, name="DevTrack")
    sub_type = SubmissionTypeFactory(event=other_event, name="Lightning")
    question = QuestionFactory(
        event=other_event,
        question="What is your experience level?",
        variant="choices",
        target="submission",
    )
    AnswerOptionFactory(question=question, answer="Beginner")
    AnswerOptionFactory(question=question, answer="Expert")
    question.tracks.add(track)
    question.submission_types.add(sub_type)

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        questions = list(event.questions.all())
        assert len(questions) == 1
        copied_q = questions[0]
        assert str(copied_q.question) == "What is your experience level?"
        assert copied_q.options.count() == 2
        assert copied_q.tracks.count() == 1
        assert copied_q.submission_types.count() == 1


def test_copy_event_data_does_not_copy_question_answers(event):
    other_event = EventFactory(organiser=event.organiser)
    question = QuestionFactory(
        event=other_event,
        question="Dietary needs?",
        variant="choices",
        target="speaker",
    )
    AnswerOptionFactory(question=question, answer="Vegan")
    sub = SubmissionFactory(event=other_event)
    AnswerFactory(question=question, answer="Vegan", submission=sub)

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        copied_q = event.questions.first()
        assert copied_q is not None
        assert str(copied_q.question) == "Dietary needs?"
        assert Answer.objects.filter(question=copied_q).count() == 0


def test_copy_event_data_copies_speaker_information(event):
    other_event = EventFactory(organiser=event.organiser)
    track = TrackFactory(event=other_event, name="InfoTrack")
    sub_type = SubmissionTypeFactory(event=other_event, name="Workshop")
    info = SpeakerInformationFactory(
        event=other_event, title="Travel Info", text="We cover travel costs."
    )
    info.limit_tracks.add(track)
    info.limit_types.add(sub_type)

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        infos = list(event.information.all())
        assert len(infos) == 1
        copied_info = infos[0]
        assert str(copied_info.title) == "Travel Info"
        assert copied_info.limit_tracks.count() == 1
        assert copied_info.limit_types.count() == 1


def test_copy_event_data_copies_user_preferences(event):
    user = UserFactory()
    other_event = EventFactory(organiser=event.organiser)
    UserEventPreferencesFactory(
        user=user, event=other_event, preferences={"theme": "dark"}
    )

    copy_event_data(event=event, source=other_event)

    prefs = UserEventPreferences.objects.filter(event=event, user=user).first()
    assert prefs is not None
    assert prefs.preferences == {"theme": "dark"}


def test_copy_event_data_copies_score_categories_with_tracks(event):
    other_event = EventFactory(organiser=event.organiser)
    track = TrackFactory(event=other_event, name="ScoreTrack")
    other_event.score_categories.all().delete()
    category = ReviewScoreCategoryFactory(event=other_event, name="Quality")
    category.limit_tracks.add(track)
    ReviewScoreFactory(category=category, value=0, label="Bad")
    ReviewScoreFactory(category=category, value=1, label="Good")

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        categories = list(event.score_categories.all())
        assert len(categories) == 1
        quality_cat = categories[0]
        assert str(quality_cat.name) == "Quality"
        assert quality_cat.scores.count() == 2
        assert quality_cat.limit_tracks.count() == 1


def test_copy_event_data_copies_hierarkey_settings(event):
    other_event = EventFactory(organiser=event.organiser)
    other_event.settings.custom_value = "test123"

    copy_event_data(event=event, source=other_event)

    assert event.settings.custom_value == "test123"


def test_copy_event_data_copies_cfp_deadline(event):
    deadline = tz_now() + dt.timedelta(days=30)
    other_event = EventFactory(organiser=event.organiser, cfp__deadline=deadline)

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        assert event.cfp.deadline == deadline


def test_copy_event_data_copies_review_phases_with_date_shift(event):
    other_event = EventFactory(
        organiser=event.organiser,
        date_from=dt.date(2025, 1, 1),
        date_to=dt.date(2025, 1, 3),
    )

    delta = event.date_from - other_event.date_from
    with scope(event=other_event):
        other_event.review_phases.all().delete()
        phase_start = tz_now()
        phase_end = tz_now() + dt.timedelta(days=14)
        ReviewPhaseFactory(
            event=other_event,
            name="Source Phase",
            start=phase_start,
            end=phase_end,
            is_active=True,
        )

    copy_event_data(event=event, source=other_event)

    with scope(event=event):
        phases = list(event.review_phases.all())
        assert len(phases) == 1
        phase = phases[0]
        assert str(phase.name) == "Source Phase"
        assert phase.is_active is False
        assert phase.start == phase_start + delta
        assert phase.end == phase_end + delta


def _reload(event):
    return Event.objects.get(pk=event.pk)


def test_apply_date_edit_moves_wip_slots():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    original_start = slot.start
    old_event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_date_edit(event, old_event)

    slot.refresh_from_db()
    assert slot.start == original_start + dt.timedelta(days=1)


def test_apply_date_edit_leaves_published_slots_alone():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    released = ScheduleFactory(event=event, version="v1")
    published_slot = TalkSlotFactory(submission=sub, schedule=released)
    wip_slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    published_original_start = published_slot.start
    wip_original_start = wip_slot.start
    old_event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_date_edit(event, old_event)

    published_slot.refresh_from_db()
    wip_slot.refresh_from_db()
    assert published_slot.start == published_original_start
    assert wip_slot.start == wip_original_start + dt.timedelta(days=1)


def test_apply_date_edit_shortening_deschedules_outside_talks():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 14))
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 14, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 14, 11, 0, tzinfo=dt.UTC),
    )
    old_event = _reload(event)

    event.date_to = dt.date(2024, 6, 12)
    apply_date_edit(event, old_event)

    slot.refresh_from_db()
    assert slot.start is None
    assert slot.end is None
    assert slot.room is None


def test_apply_date_edit_shortening_deletes_outside_availabilities():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 14))
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
    # Need a WIP slot so apply_date_edit does not short-circuit on the
    # "no scheduled talks" guard.
    sub = SubmissionFactory(event=event)
    TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    old_event = _reload(event)

    event.date_to = dt.date(2024, 6, 12)
    apply_date_edit(event, old_event)

    assert Availability.objects.filter(pk=inside.pk).exists()
    assert not Availability.objects.filter(pk=outside.pk).exists()


def test_apply_date_edit_no_slots_does_nothing():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    old_event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_date_edit(event, old_event)  # must not raise


def test_apply_date_edit_only_end_extended_does_not_move_slots():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    original_start = slot.start
    old_event = _reload(event)

    event.date_to = dt.date(2024, 6, 14)
    apply_date_edit(event, old_event)

    slot.refresh_from_db()
    assert slot.start == original_start


def test_apply_date_edit_moves_availabilities_by_delta():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    avail = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 17, 0, tzinfo=dt.UTC),
    )
    original_start = avail.start
    original_end = avail.end
    old_event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_date_edit(event, old_event)

    avail.refresh_from_db()
    assert avail.start == original_start + dt.timedelta(days=1)
    assert avail.end == original_end + dt.timedelta(days=1)


def test_apply_timezone_edit_preserves_apparent_local_time():
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
    old_event = _reload(event)
    event = _reload(event)  # drop cached tz
    event.timezone = "Europe/Berlin"

    apply_timezone_edit(event, old_event)

    slot.refresh_from_db()
    # 10:00 UTC was 10:00 wall-clock under UTC; preserving the wall
    # clock under Berlin (UTC+2 in June) means 08:00 UTC.
    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


def test_apply_timezone_edit_moves_published_slots_too():
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
    TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 10, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 11, 0, tzinfo=dt.UTC),
    )
    old_event = _reload(event)
    event = _reload(event)
    event.timezone = "Europe/Berlin"

    apply_timezone_edit(event, old_event)

    published_slot.refresh_from_db()
    assert published_slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


def test_apply_timezone_edit_no_slots_does_nothing():
    event = EventFactory(timezone="UTC")
    old_event = _reload(event)
    event = _reload(event)
    event.timezone = "Europe/Berlin"

    apply_timezone_edit(event, old_event)  # must not raise


def test_apply_timezone_edit_same_offset_does_not_move():
    event = EventFactory(
        date_from=dt.date(2024, 6, 10),
        date_to=dt.date(2024, 6, 12),
        timezone="Europe/Berlin",
    )
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(
        submission=sub,
        schedule=event.wip_schedule,
        start=dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
    )
    old_event = _reload(event)
    event = _reload(event)
    event.timezone = "Europe/Paris"

    apply_timezone_edit(event, old_event)

    slot.refresh_from_db()
    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


def test_apply_timezone_edit_moves_availabilities():
    event = EventFactory(
        date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12), timezone="UTC"
    )
    sub = SubmissionFactory(event=event)
    TalkSlotFactory(
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
    event = _reload(event)
    event.timezone = "Europe/Berlin"

    apply_timezone_edit(event, old_event)

    avail.refresh_from_db()
    assert avail.start == dt.datetime(2024, 6, 10, 7, 0, tzinfo=dt.UTC)
    assert avail.end == dt.datetime(2024, 6, 10, 15, 0, tzinfo=dt.UTC)


def test_apply_event_changes_persists_event():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    event = _reload(event)
    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)

    apply_event_changes(event, {"date_from", "date_to"})

    event.refresh_from_db()
    assert event.date_from == dt.date(2024, 6, 11)
    assert event.date_to == dt.date(2024, 6, 13)


def test_apply_event_changes_invokes_apply_date_edit():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    sub = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=sub, schedule=event.wip_schedule)
    original_start = slot.start
    event = _reload(event)

    event.date_from = dt.date(2024, 6, 11)
    event.date_to = dt.date(2024, 6, 13)
    apply_event_changes(event, {"date_from", "date_to"})

    slot.refresh_from_db()
    assert slot.start == original_start + dt.timedelta(days=1)


def test_apply_event_changes_invokes_apply_timezone_edit():
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

    event.timezone = "Europe/Berlin"
    apply_event_changes(event, {"timezone"})

    slot.refresh_from_db()
    assert slot.start == dt.datetime(2024, 6, 10, 8, 0, tzinfo=dt.UTC)


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


def test_apply_event_changes_processes_image_when_field_changed():
    event = EventFactory()

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        apply_event_changes(event, {"logo"})

    mock_process.assert_called_once_with("logo")


def test_apply_event_changes_skips_image_when_field_not_changed():
    event = EventFactory()

    with patch("pretalx.event.models.event.Event.process_image") as mock_process:
        apply_event_changes(event, {"date_from"})

    mock_process.assert_not_called()


def test_apply_event_changes_writes_custom_css():
    event = EventFactory()
    css = "body { color: rebeccapurple; }"

    apply_event_changes(event, {"custom_css_text"}, custom_css_text=css)

    event.refresh_from_db()
    assert event.custom_css.read().decode() == css


def test_apply_event_changes_skips_css_when_field_not_changed():
    event = EventFactory()

    apply_event_changes(event, {"date_from"}, custom_css_text="body { color: red; }")

    event.refresh_from_db()
    assert not event.custom_css


def test_apply_event_changes_skips_css_when_text_is_none():
    event = EventFactory()

    apply_event_changes(event, {"custom_css_text"}, custom_css_text=None)

    event.refresh_from_db()
    assert not event.custom_css


def test_shred_event_deletes_event(event):
    pk = event.pk
    shred_event(event)
    assert not Event.objects.filter(pk=pk).exists()


def test_shred_event_deletes_related_data(event):
    with scope(event=event):
        sub = SubmissionFactory(event=event)
        template_pks = list(event.mail_templates.values_list("pk", flat=True))

    shred_event(event)

    assert not Submission.all_objects.filter(pk=sub.pk).exists()
    assert not MailTemplate.objects.filter(pk__in=template_pks).exists()


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


def test_activate_event_sets_public_and_logs():
    event = EventFactory(is_public=False)
    user = UserFactory()

    exceptions, extra = activate_event(event, user=user)

    event.refresh_from_db()
    assert event.is_public
    assert exceptions == []
    assert extra == []
    with scope(event=event):
        assert (
            event.logged_actions().filter(action_type="pretalx.event.activate").exists()
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


def test_activate_event_collects_string_messages_from_plugins(register_signal_handler):
    event = EventFactory(is_public=False)
    user = UserFactory()

    def responder(signal, sender, **kwargs):
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


def test_deactivate_event_clears_public_and_logs():
    event = EventFactory(is_public=True)
    user = UserFactory()

    deactivate_event(event, user=user)

    event.refresh_from_db()
    assert not event.is_public
    with scope(event=event):
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.event.deactivate")
            .exists()
        )


def test_move_full_event_shifts_event_dates():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    new_start = dt.date(2024, 6, 15)

    move_full_event(event, new_start)

    event.refresh_from_db()
    assert event.date_from == new_start
    assert event.date_to == dt.date(2024, 6, 17)


def test_move_full_event_shifts_all_slots_across_schedules():
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

    move_full_event(event, dt.date(2024, 6, 13))

    published_slot.refresh_from_db()
    wip_slot.refresh_from_db()
    assert published_slot.start == dt.datetime(2024, 6, 13, 10, 0, tzinfo=dt.UTC)
    assert wip_slot.start == dt.datetime(2024, 6, 14, 10, 0, tzinfo=dt.UTC)


def test_move_full_event_shifts_availabilities():
    event = EventFactory(date_from=dt.date(2024, 6, 10), date_to=dt.date(2024, 6, 12))
    avail = AvailabilityFactory(
        event=event,
        start=dt.datetime(2024, 6, 10, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 6, 10, 17, 0, tzinfo=dt.UTC),
    )

    move_full_event(event, dt.date(2024, 6, 17))

    avail.refresh_from_db()
    assert avail.start == dt.datetime(2024, 6, 17, 9, 0, tzinfo=dt.UTC)
    assert avail.end == dt.datetime(2024, 6, 17, 17, 0, tzinfo=dt.UTC)


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
