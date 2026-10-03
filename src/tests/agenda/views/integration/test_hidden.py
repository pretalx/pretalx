# SPDX-FileCopyrightText: 2026-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.orga.forms.export import ScheduleExportForm
from pretalx.person.models.auth_token import ENDPOINTS
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.domain.submission import apply_field_changes
from pretalx.submission.interfaces.forms.submission import SubmissionOrgaForm
from pretalx.submission.models import SubmissionStates
from tests.factories import SubmissionFactory, TalkSlotFactory, UserApiTokenFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def hidden(event, talk_slot):
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, is_hidden=True
    )
    TalkSlotFactory(submission=submission)
    freeze_schedule(talk_slot.schedule, "v1", notify_speakers=False)
    return submission


def test_hidden_schedule(client, event, talk_slot, hidden):
    response = client.get(event.urls.schedule_nojs)

    assert response.status_code == 200
    content = response.content.decode()
    assert talk_slot.submission.title in content
    assert hidden.title not in content
    assert client.get(hidden.urls.public).status_code == 404


@pytest.mark.parametrize("authenticated", (False, True))
def test_hidden_api(client, event, organiser_user, hidden, authenticated):
    with scopes_disabled():
        token = UserApiTokenFactory(
            user=organiser_user,
            limit_events=[event],
            endpoints=dict.fromkeys(ENDPOINTS, ["list", "retrieve"]),
        )
    headers = {"Authorization": f"Token {token.token}"} if authenticated else {}

    response = client.get(event.api_urls.submissions, headers=headers)
    assert response.status_code == 200
    assert (hidden.code in response.content.decode()) == authenticated


@pytest.mark.unit
def test_hidden_release(event, published_talk_slot):
    submission = published_talk_slot.submission
    for version, is_hidden in (("v2", True), ("v3", False)):
        previous = event.current_schedule
        submission.is_hidden = is_hidden
        submission.save(update_fields=["is_hidden"])
        apply_field_changes(submission, {"is_hidden"})
        wip = event.wip_schedule
        assert wip.talks.get(submission=submission).is_visible is not is_hidden
        assert previous.talks.get(submission=submission).is_visible is is_hidden

        # Releases also correct stale WIP visibility.
        wip.talks.filter(submission=submission).update(is_visible=is_hidden)
        released, _ = freeze_schedule(wip, version, notify_speakers=False)

        assert released.talks.get(submission=submission).is_visible is not is_hidden
        assert previous.talks.get(submission=submission).is_visible is is_hidden


@pytest.mark.unit
@pytest.mark.parametrize(
    ("is_hidden", "is_featured"),
    ((False, False), (True, False), (True, True), (False, True)),
)
def test_hidden_form(event, talk_slot, is_hidden, is_featured):
    submission = talk_slot.submission
    form = SubmissionOrgaForm(
        event=event,
        instance=submission,
        data={
            "title": submission.title,
            "abstract": "Abstract",
            "submission_type": submission.submission_type_id,
            "content_locale": "en",
            "is_hidden": is_hidden,
            "is_featured": is_featured,
        },
    )

    assert form.is_valid(), form.errors
    form.save()
    talk_slot.refresh_from_db()
    assert talk_slot.is_visible is not is_hidden
    assert bool(form["is_featured"].help_text) == (is_hidden and is_featured)


@pytest.mark.parametrize(
    "change", ("is_hidden", "start", "end", "room", "add", "remove")
)
def test_hidden_schedule_warning(
    client, event, organiser_user, published_talk_slot, change
):
    submission = published_talk_slot.submission
    client.force_login(organiser_user)
    warning = "Release a new schedule to publish these changes."
    assert warning not in client.get(submission.orga_urls.base).content.decode()
    with scopes_disabled():
        slots = event.wip_schedule.talks.filter(submission=submission)
        if change == "is_hidden":
            submission.is_hidden = True
            submission.save(update_fields=["is_hidden"])
            apply_field_changes(submission, {"is_hidden"})
        elif change == "add":
            TalkSlotFactory(
                submission=submission,
                room=published_talk_slot.room,
                start=published_talk_slot.start,
                end=published_talk_slot.end,
            )
        elif change == "remove":
            slots.delete()
        else:
            slots.update(**{change: None})
    assert warning in client.get(submission.orga_urls.base).content.decode()
    with scopes_disabled():
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
    assert warning not in client.get(submission.orga_urls.base).content.decode()


def test_hidden_orga(client, event, organiser_user, hidden):
    client.force_login(organiser_user)
    for value in ("true", "false"):
        response = client.get(event.orga_urls.submissions, {"is_hidden": value})
        assert response.status_code == 200
        content = response.content.decode()
        assert (hidden.title in content) == (value == "true")
        assert ("fa-eye-slash" in content) == (value == "true")
    response = client.get(f"/orga/event/{event.slug}/schedule/api/talks/")
    assert response.status_code == 200
    talk = next(t for t in response.json()["talks"] if t["code"] == hidden.code)
    assert talk["is_hidden"] is True
    with scopes_disabled():
        form = ScheduleExportForm(event=event, user=organiser_user)
        data = form.get_data(event.submissions.filter(pk=hidden.pk), ["is_hidden"], [])
    assert data == [{"ID": hidden.code, str(form.fields["is_hidden"].label): True}]


def test_hidden_public_exceptions(client, event, hidden):
    with scopes_disabled():
        event.feature_flags.update(
            show_featured="always", submission_public_review=True
        )
        event.save(update_fields=["feature_flags"])
        hidden.is_featured = True
        hidden.save(update_fields=["is_featured"])

    for url in (event.urls.featured, hidden.urls.public, hidden.urls.review):
        response = client.get(url)
        assert response.status_code == 200
        assert hidden.title in response.content.decode()
