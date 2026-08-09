# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import pytest
from django.utils import timezone

from pretalx.orga.tables.speaker import SpeakerInformationTable, SpeakerTable
from pretalx.person.models import SpeakerProfile
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    return EventFactory()


@pytest.mark.parametrize(
    ("use_tracks", "expected"),
    (
        (True, ["title", "limit_types", "limit_tracks", "resource"]),
        (False, ["title", "limit_types", "resource"]),
    ),
)
@pytest.mark.django_db
def test_speaker_information_table_default_columns(use_tracks, expected):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    if use_tracks:
        TrackFactory(event=event)
    info = SpeakerInformationFactory(event=event)
    table = SpeakerInformationTable([info], event=event, user=UserFactory.build())

    assert table.default_columns == expected


@pytest.mark.parametrize("use_tracks", (True, False))
@pytest.mark.django_db
def test_speaker_information_table_limit_tracks_excluded_by_feature(use_tracks):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    if use_tracks:
        TrackFactory(event=event)
    info = SpeakerInformationFactory(event=event)
    table = SpeakerInformationTable([info], event=event, user=UserFactory.build())

    assert ("limit_tracks" in table.exclude) != use_tracks


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("profile_kwargs", "expected_email", "expected_locale"),
    (
        (
            {"user": None, "email": "contact@example.com", "locale": "de"},
            "contact@example.com",
            "de",
        ),
        ({"user": None}, None, "en"),
    ),
    ids=("managed-with-contact-data", "managed-bare"),
)
def test_speaker_table_email_and_locale_use_effective_values(
    profile_kwargs, expected_email, expected_locale
):
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, **profile_kwargs)
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    row = table.rows[0]

    assert row.get_cell_value("email") == expected_email
    assert row.get_cell_value("locale") == expected_locale


@pytest.mark.django_db
def test_speaker_table_render_invite_status_without_pending_invitation(event):
    speaker = SpeakerFactory(event=event, user=None, email="mail@example.com")
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    assert table.render_invite_status(speaker, speaker.invitation_sent) == "—"


@pytest.mark.django_db
def test_speaker_table_render_invite_status_pending_without_date(event):
    speaker = SpeakerFactory(
        event=event, user=None, email="mail@example.com", invitation_token="tok"
    )
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    assert table.render_invite_status(speaker, speaker.invitation_sent) == "Invited"


@pytest.mark.django_db
def test_speaker_table_render_invite_status_pending_with_date(event):
    speaker = SpeakerFactory(
        event=event,
        user=None,
        email="mail@example.com",
        invitation_token="tok",
        invitation_sent=timezone.now(),
    )
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    result = table.render_invite_status(speaker, speaker.invitation_sent)

    assert result.startswith("Invited ")
    assert result != "Invited"


@pytest.mark.django_db
def test_speaker_table_render_invite_status_without_event_skips_tz_conversion():
    event = EventFactory()
    speaker = SpeakerFactory(
        event=event,
        user=None,
        email="mail@example.com",
        invitation_token="tok",
        invitation_sent=timezone.now(),
    )
    table = SpeakerTable([speaker], user=UserFactory.build())

    result = table.render_invite_status(speaker, speaker.invitation_sent)

    assert result.startswith("Invited ")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("profile_kwargs", "expected"),
    (({"user": None, "email": "mail@example.com"}, "Managed"), ({}, "Self-managed")),
    ids=("managed", "self-managed"),
)
def test_speaker_table_render_speaker_type(event, profile_kwargs, expected):
    speaker = SpeakerFactory(event=event, **profile_kwargs)
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    assert table.render_speaker_type(speaker) == expected


@pytest.mark.django_db
def test_speaker_table_email_ordering_matches_effective_email():
    event = EventFactory()
    override = SpeakerFactory(
        event=event, user=UserFactory(email="zzz@example.com"), email="aaa@example.com"
    )
    account = SpeakerFactory(event=event, user=UserFactory(email="mmm@example.com"))
    managed = SpeakerFactory(event=event, user=None, email="ccc@example.com")

    column = SpeakerTable.base_columns["email"]
    ordered, modified = column.order(
        SpeakerProfile.objects.filter(event=event), is_descending=False
    )

    assert modified is True
    assert list(ordered) == [override, managed, account]


@pytest.mark.django_db
def test_speaker_table_locale_ordering_matches_effective_locale():
    event = EventFactory(locales=["en", "de"], locale="en")
    de_managed = SpeakerFactory(event=event, user=None, locale="de")
    en_account = SpeakerFactory(event=event, user=UserFactory(locale="en"))

    column = SpeakerTable.base_columns["locale"]
    ordered, modified = column.order(
        SpeakerProfile.objects.filter(event=event), is_descending=False
    )

    assert modified is True
    assert list(ordered) == [de_managed, en_account]


@pytest.mark.django_db
def test_speaker_table_invite_status_ordering_uses_pending_invitations_only():
    event = EventFactory()
    early = SpeakerFactory(
        event=event,
        user=None,
        email="early@example.com",
        invitation_token="tok1",
        invitation_sent=timezone.now() - dt.timedelta(days=2),
    )
    late = SpeakerFactory(
        event=event,
        user=None,
        email="late@example.com",
        invitation_token="tok2",
        invitation_sent=timezone.now(),
    )
    retracted = SpeakerFactory(
        event=event,
        user=None,
        email="retracted@example.com",
        invitation_sent=timezone.now() - dt.timedelta(days=5),
    )

    column = SpeakerTable.base_columns["invite_status"]
    ordered, modified = column.order(
        SpeakerProfile.objects.filter(event=event), is_descending=False
    )

    assert modified is True
    invited = [speaker for speaker in ordered if speaker in (early, late)]
    assert invited == [early, late]
    assert retracted in list(ordered)


@pytest.mark.django_db
def test_speaker_table_name_ordering_matches_display_name():
    event = EventFactory()
    account = SpeakerFactory(event=event, name="", user=UserFactory(name="Anna"))
    managed = SpeakerFactory(event=event, user=None, name="Mia")
    override = SpeakerFactory(event=event, name="Zoe", user=UserFactory(name="Bea"))

    column = SpeakerTable.base_columns["name"]
    ordered, modified = column.order(
        SpeakerProfile.objects.filter(event=event), is_descending=False
    )

    assert modified is True
    assert list(ordered) == [account, managed, override]


@pytest.mark.django_db
def test_speaker_table_speaker_type_ordering():
    event = EventFactory()
    self_managed = SpeakerFactory(event=event)
    managed = SpeakerFactory(event=event, user=None)

    column = SpeakerTable.base_columns["speaker_type"]
    ordered, modified = column.order(
        SpeakerProfile.objects.filter(event=event), is_descending=False
    )

    assert modified is True
    assert list(ordered) == [managed, self_managed]


@pytest.mark.django_db
def test_speaker_table_has_email_ordering():
    event = EventFactory()
    reachable = SpeakerFactory(event=event, user=None, email="mail@example.com")
    unreachable = SpeakerFactory(event=event, user=None)

    column = SpeakerTable.base_columns["has_email"]
    ordered, modified = column.order(
        SpeakerProfile.objects.filter(event=event), is_descending=False
    )

    assert modified is True
    assert list(ordered) == [unreachable, reachable]
