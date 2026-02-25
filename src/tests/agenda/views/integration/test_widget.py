import pytest
from django.urls import reverse
from django_scopes import scopes_disabled

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

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("show_schedule", "show_widget_if_not_public", "expected"),
    ((True, False, 200), (True, True, 200), (False, False, 404), (False, True, 200)),
    ids=[
        "schedule_visible",
        "schedule_and_widget_visible",
        "both_hidden",
        "widget_override",
    ],
)
def test_widget_data_visibility(
    client,
    public_event_with_schedule,
    show_schedule,
    show_widget_if_not_public,
    expected,
):
    """Widget data endpoint respects show_schedule and show_widget_if_not_public flags."""
    event = public_event_with_schedule
    event.feature_flags["show_schedule"] = show_schedule
    event.feature_flags["show_widget_if_not_public"] = show_widget_if_not_public
    event.save()

    response = client.get(event.urls.schedule_widget_data, follow=True)

    assert response.status_code == expected


@pytest.mark.django_db
def test_widget_data_returns_schedule_json(client, public_event_with_schedule):
    """Widget data returns JSON schedule data with CORS headers."""
    event = public_event_with_schedule

    response = client.get(event.urls.schedule_widget_data, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Access-Control-Allow-Origin"] == "*"
    data = response.json()
    assert len(data["talks"]) == 1


@pytest.mark.django_db
def test_widget_data_options_returns_cors_headers(client, public_event_with_schedule):
    """OPTIONS request returns CORS headers without content."""
    event = public_event_with_schedule

    response = client.options(event.urls.schedule_widget_data)

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "*"
    assert response["Access-Control-Allow-Headers"] == "authorization,content-type"


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_widget_data_bogus_version_falls_back_to_current(
    client, public_event_with_schedule
):
    """Bogus version falls back to current schedule."""
    event = public_event_with_schedule

    response = client.get(f"{event.urls.schedule_widget_data}?v=nonexistent")

    assert response.status_code == 200
    data = response.json()
    assert len(data["talks"]) == 1


@pytest.mark.django_db
def test_widget_data_wip_anonymous_denied(client, public_event_with_schedule):
    """Anonymous users cannot access the WIP schedule."""
    event = public_event_with_schedule

    response = client.get(f"{event.urls.schedule_widget_data}?v=wip")

    assert response.status_code == 404


@pytest.mark.django_db
def test_widget_data_wip_orga_allowed(orga_client):
    """Organisers can access the WIP schedule."""
    client, event = orga_client

    response = client.get(f"{event.urls.schedule_widget_data}?v=wip")

    assert response.status_code == 200
    assert "talks" in response.json()


@pytest.mark.django_db
def test_widget_data_no_schedule_returns_404(client, event):
    """Returns 404 when no schedule exists (even with permissions)."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.feature_flags["show_widget_if_not_public"] = True
    event.save()

    response = client.get(event.urls.schedule_widget_data, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("show_schedule", "show_widget_if_not_public", "expected"),
    ((True, False, 200), (True, True, 200), (False, False, 404), (False, True, 200)),
    ids=[
        "schedule_visible",
        "schedule_and_widget_visible",
        "both_hidden",
        "widget_override",
    ],
)
def test_widget_script_visibility(
    client,
    public_event_with_schedule,
    show_schedule,
    show_widget_if_not_public,
    expected,
):
    """Widget script respects visibility flags."""
    event = public_event_with_schedule
    event.feature_flags["show_schedule"] = show_schedule
    event.feature_flags["show_widget_if_not_public"] = show_widget_if_not_public
    event.save()

    response = client.get(event.urls.schedule_widget_script, follow=True)

    assert response.status_code == expected


@pytest.mark.django_db
def test_widget_script_returns_javascript(client, public_event_with_schedule):
    """Widget script serves JavaScript content."""
    event = public_event_with_schedule

    response = client.get(event.urls.schedule_widget_script, follow=True)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert len(response.content) > 0


@pytest.mark.django_db
def test_event_css_no_color(client, event):
    """Event CSS without primary color returns minimal CSS."""
    response = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    content = response.content.decode()
    assert "--color-primary" not in content
    assert content == ":root {  }"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("color", "expect_dark_text"),
    (
        ("#000000", False),
        ("#0000ff", False),
        ("#800000", False),
        ("#3aa57c", False),
        ("#ffffff", True),
        ("#ffff00", True),
        ("#00ffff", True),
    ),
    ids=["black", "blue", "maroon", "pretalx_green", "white", "yellow", "cyan"],
)
def test_event_css_with_color(client, event, color, expect_dark_text):
    """Event CSS includes primary color variable and conditionally dark text override."""
    event.primary_color = color
    event.save()

    response = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/css"
    content = response.content.decode()
    assert f"--color-primary: {color}" in content
    if expect_dark_text:
        assert "--color-text-on-primary: var(--color-text)" in content
    else:
        assert "--color-text-on-primary" not in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("color", "expect_dark_text"),
    (("#3aa57c", False), ("#ffffff", True)),
    ids=["no_dark_text", "with_dark_text"],
)
def test_event_css_orga_target(client, event, color, expect_dark_text):
    """Orga target adds '-event' postfix to CSS variable names."""
    event.primary_color = color
    event.save()

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


@pytest.mark.django_db
def test_event_css_etag_changes_with_color(client, event):
    """ETag changes when the color changes, reflecting the dark text state."""
    event.primary_color = "#000000"
    event.save()

    response1 = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))
    etag1 = response1.get("ETag")

    event.primary_color = "#ffffff"
    event.save()

    response2 = client.get(reverse("agenda:event.css", kwargs={"event": event.slug}))
    etag2 = response2.get("ETag")

    assert etag1 != etag2


@pytest.mark.django_db
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
        event = EventFactory(is_public=True)
        event.feature_flags["show_schedule"] = True
        event.save()
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
    data = response.json()
    assert len(data["talks"]) == item_count
