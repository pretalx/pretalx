# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.signals import register_fonts
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_widget_data_hidden_returns_404(client, public_event_with_schedule):
    event = public_event_with_schedule
    event.feature_flags["show_schedule"] = False
    event.feature_flags["show_widget_if_not_public"] = False
    event.save()

    response = client.get(event.urls.schedule_widget_data, follow=True)

    assert response.status_code == 404


def test_widget_data_options_returns_cors_headers(client, public_event_with_schedule):
    event = public_event_with_schedule

    response = client.options(event.urls.schedule_widget_data)

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "*"
    assert response["Access-Control-Allow-Headers"] == "authorization,content-type"


def test_widget_data_versioned(client, public_event_with_schedule):
    """Versioned schedule data returns the requested version, not the current one."""
    event = public_event_with_schedule
    # v1 is the current schedule (1 talk). Add another talk and freeze as v2,
    # making v2 current with 2 talks. Accessing ?v=v1 must still return 1 talk.
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v2", notify_speakers=False)

    response = client.get(f"{event.urls.schedule_widget_data}?v=v1")

    assert response.status_code == 200
    data = response.json()
    assert len(data["talks"]) == 1
    assert data["version"] == "v1"


def test_widget_data_bogus_version_falls_back_to_current(
    client, public_event_with_schedule
):
    event = public_event_with_schedule

    response = client.get(f"{event.urls.schedule_widget_data}?v=nonexistent")

    assert response.status_code == 200
    data = response.json()
    assert len(data["talks"]) == 1


def test_widget_data_wip_anonymous_denied(client, public_event_with_schedule):
    event = public_event_with_schedule

    response = client.get(f"{event.urls.schedule_widget_data}?v=wip")

    assert response.status_code == 404


def test_widget_data_wip_orga_allowed(client, public_event_with_schedule):
    event = public_event_with_schedule
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(f"{event.urls.schedule_widget_data}?v=wip")

    assert response.status_code == 200
    assert "talks" in response.json()


def test_widget_data_no_schedule_returns_404(client):
    event = EventFactory(feature_flags={"show_widget_if_not_public": True})

    response = client.get(event.urls.schedule_widget_data, follow=True)

    assert response.status_code == 404


def test_widget_script_hidden_returns_404(client, public_event_with_schedule):
    event = public_event_with_schedule
    event.feature_flags["show_schedule"] = False
    event.feature_flags["show_widget_if_not_public"] = False
    event.save()

    response = client.get(event.urls.schedule_widget_script, follow=True)

    assert response.status_code == 404


def test_widget_script_returns_javascript(client, public_event_with_schedule):
    event = public_event_with_schedule

    response = client.get(event.urls.schedule_widget_script, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert len(response.content) > 0


def test_event_css_no_color(client, event):
    response = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    content = response.content.decode()
    assert "--color-primary" not in content
    assert content == ""


@pytest.mark.parametrize(
    ("color", "expect_dark_text"),
    (("#000000", False), ("#ffffff", True)),
    ids=["dark_no_override", "light_with_dark_text"],
)
def test_event_css_with_color(client, color, expect_dark_text):
    event = EventFactory(primary_color=color)

    response = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    content = response.content.decode()
    assert f"--color-primary: {color}" in content
    if expect_dark_text:
        assert "--color-text-on-primary: var(--color-text)" in content
    else:
        assert "--color-text-on-primary" not in content


@pytest.mark.parametrize(
    ("color", "expect_dark_text"),
    (("#3aa57c", False), ("#ffffff", True)),
    ids=["no_dark_text", "with_dark_text"],
)
def test_event_css_orga_target(client, color, expect_dark_text):
    event = EventFactory(primary_color=color)

    response = client.get(
        reverse("agenda:event.css", kwargs={"event": event.slug}) + "?target=orga"
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert f"--color-primary-event: {color}" in content
    if expect_dark_text:
        assert "--color-text-on-primary-event: var(--color-text)" in content
    else:
        assert "--color-text-on-primary-event" not in content


def test_event_css_etag_changes_with_color(client):
    event = EventFactory(primary_color="#000000")

    response1 = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))
    etag1 = response1.get("ETag")

    event.primary_color = "#ffffff"
    event.save()

    response2 = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))
    etag2 = response2.get("ETag")

    assert etag1 != etag2


@pytest.mark.parametrize("item_count", (1, 3))
def test_widget_data_query_count(client, item_count, django_assert_num_queries):
    """Query count for widget data is constant regardless of talk count.

    The setup creates deliberately rich related data to surface any missing
    prefetch_related or select_related calls that would cause N+1 queries
    as data grows: each submission gets a track, answers to both a submission
    and a speaker question, and a growing number of speakers (submission i
    gets i speakers), so the total amount of related data scales
    non-linearly with item_count.
    """
    with scopes_disabled():
        event = EventFactory()
        sub_question = QuestionFactory(event=event, target="submission")
        speaker_question = QuestionFactory(event=event, target="speaker")
        for i in range(item_count):
            track = TrackFactory(event=event)
            submission = SubmissionFactory(
                event=event, state=SubmissionStates.CONFIRMED, track=track
            )
            AnswerFactory(question=sub_question, submission=submission)
            for _ in range(i + 1):
                speaker = SpeakerFactory(event=event)
                submission.speakers.add(speaker)
                AnswerFactory(
                    question=speaker_question, speaker=speaker, submission=None
                )
            TalkSlotFactory(submission=submission, is_visible=True)
        event.wip_schedule.freeze("v1", notify_speakers=False)

    with django_assert_num_queries(9):
        response = client.get(event.urls.schedule_widget_data, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Access-Control-Allow-Origin"] == "*"
    data = response.json()
    assert len(data["talks"]) == item_count


def test_event_css_with_heading_font(client, register_signal_handler):
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "TestFont",
            "text_font": "",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return {
            "TestFont": {
                "regular": {
                    "truetype": "fonts/test-regular.ttf",
                    "woff2": "fonts/test-regular.woff2",
                }
            }
        }

    register_signal_handler(register_fonts, handler)
    response = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))

    assert response.status_code == 200
    content = response.content.decode()
    assert content.count("@font-face {") == 1
    assert content.count('font-family: "TestFont"') == 1
    root_block = content.split(":root {\n")[1].split("\n}")[0].strip()
    assert root_block == '--font-family-title: "TestFont", var(--font-fallback);'


def test_event_css_with_both_fonts(client, register_signal_handler):
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "TestFont",
            "text_font": "TestFont",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return {
            "TestFont": {
                "regular": {
                    "truetype": "fonts/test-regular.ttf",
                    "woff2": "fonts/test-regular.woff2",
                }
            }
        }

    register_signal_handler(register_fonts, handler)
    response = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))

    content = response.content.decode()
    root_block = content.split(":root {\n")[1].split("\n}")[0]
    root_lines = [line.strip() for line in root_block.strip().splitlines()]
    assert root_lines == [
        '--font-family-title: "TestFont", var(--font-fallback);',
        '--font-family: "TestFont", var(--font-fallback);',
    ]
