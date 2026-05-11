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
    copy_event_data,
    create_event,
    initialise_event,
    shred_event,
)
from pretalx.event.models import Event, Organiser
from pretalx.mail.enums import MailTemplateRoles
from pretalx.mail.models import MailTemplate
from pretalx.person.models import SpeakerInformation
from pretalx.person.models.preferences import UserEventPreferences
from pretalx.schedule.models import Schedule
from pretalx.schedule.models.slot import TalkSlot
from pretalx.submission.models import Submission
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
    SpeakerInformationFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TrackFactory,
    UserEventPreferencesFactory,
    UserFactory,
)

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


def test_create_event_writes_locale_arrays():
    """``locales`` populates both locale_array and content_locale_array."""
    organiser = OrganiserFactory()

    event = create_event(
        organiser=organiser, locales=["en", "de"], slug="evt", **_common_fields()
    )

    assert event.locale_array == "en,de"
    assert event.content_locale_array == "en,de"


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
    """create_event hydrates a usable event: CfP, WIP schedule, mail
    templates, review phases, and score categories."""
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
    """initialise_event creates one score category with three scores (No/Maybe/Yes)."""
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


def test_copy_event_data_copies_attributes(event):
    other_event = EventFactory(
        organiser=event.organiser,
        primary_color="#ff0000",
        locale="de",
        locale_array="de,en",
        feature_flags={"testing": True},
    )

    copy_event_data(event=event, source=other_event)

    assert event.primary_color == "#ff0000"
    assert event.locale == "de"
    assert event.feature_flags == other_event.feature_flags


def test_copy_event_data_does_not_copy_custom_domain(event):
    """copy_event_data does not copy custom_domain, preserving the
    target event's domain configuration."""
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
    """copy_event_data clones non-auto-created mail templates from the
    source event and recreates role-based templates via initialise_event."""
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
    """copy_event_data clones rooms and their availabilities, shifting
    availability times by the date delta between events."""
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


def test_copy_event_data_skips_rooms_when_target_has_rooms(event):
    """copy_event_data does not copy rooms when the target event already
    has rooms, to avoid duplicating manually configured rooms."""
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
    """copy_event_data copies hierarkey settings from the source event,
    excluding file-based settings."""
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
    """copy_event_data copies review phases from the source event, shifting
    start/end dates by the delta between event date_from values and
    deactivating all phases."""
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
            position=0,
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
    """shred_event deletes the event and all related data including submissions,
    speakers, rooms, slots, questions, answers, reviews, feedback, resources,
    tracks, tags, mail templates, and schedules."""
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
    """The audit-log row written by shred_event must be committed before
    the atomic delete phase begins, so it persists even when the delete
    phase raises an exception."""
    organiser = event.organiser
    organiser_ct = ContentType.objects.get_for_model(Organiser)

    with (
        patch(
            "pretalx.event.domain.event._shred_event_data",
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
