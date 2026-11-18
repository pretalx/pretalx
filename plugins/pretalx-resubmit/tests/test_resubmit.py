import datetime as dt

import pytest
from django.utils.timezone import now
from pretalx_resubmit.models import Resubmission

from pretalx.submission.enums import SubmissionStates
from pretalx.submission.models import Submission


def _list(client, event):
    response = client.get(f"/{event.slug}/me/submissions/")
    assert response.status_code == 200
    return response.content.decode()


def _url(event, source):
    return f"/{event.slug}/p/resubmit/{source.code}/"


def test_panel_lists_own_proposals_from_same_organiser(
    event, old_event, other_organiser_event, speaker, make_proposal, client_for
):
    from pretalx.person.models import User

    make_proposal(old_event, "Mine", speaker)
    make_proposal(old_event, "My draft", speaker, state=SubmissionStates.DRAFT)
    make_proposal(other_organiser_event, "Elsewhere", speaker)
    someone = User.objects.create_user(email="x@example.invalid", name="X")
    make_proposal(old_event, "Not mine", someone)

    html = _list(client_for(speaker), event)

    assert "Resubmit a proposal from another event" in html
    assert "Mine" in html
    assert "My draft" not in html
    assert "Elsewhere" not in html
    assert "Not mine" not in html


def test_panel_hidden_when_cfp_closed(
    event, old_event, speaker, make_proposal, client_for
):
    make_proposal(old_event, "Mine", speaker)
    event.cfp.deadline = now() - dt.timedelta(days=1)
    event.cfp.save()

    assert "Resubmit a proposal" not in _list(client_for(speaker), event)
    response = client_for(speaker).get(_url(event, Submission.objects.get()))
    assert response.status_code == 302


def test_resubmit_copies_proposal(event, old_event, speaker, make_proposal, client_for):
    from pretalx.common.models import ActivityLog

    source = make_proposal(
        old_event,
        "Fire safety",
        speaker,
        abstract="An abstract",
        description="A description",
        notes="For the orga",
        internal_notes="Orga only",
        do_not_record=True,
    )
    old_profile = speaker.get_speaker(old_event)
    old_profile.biography = "My bio"
    old_profile.save()
    client = client_for(speaker)

    assert client.get(_url(event, source)).status_code == 200
    response = client.post(
        _url(event, source),
        {"submission_type": event.cfp.default_type.pk, "content_locale": "en"},
    )

    copy = Submission.objects.get(event=event)
    assert response.status_code == 302
    assert response["Location"] == copy.urls.user_base
    assert copy.state == SubmissionStates.SUBMITTED
    assert copy.code != source.code
    assert (copy.title, copy.abstract, copy.description, copy.notes) == (
        "Fire safety",
        "An abstract",
        "A description",
        "For the orga",
    )
    assert copy.do_not_record
    assert not copy.internal_notes
    assert [s.user for s in copy.speakers.all()] == [speaker]
    assert speaker.get_speaker(event).biography == "My bio"
    assert Resubmission.objects.get(submission=copy).source == source
    log = ActivityLog.objects.get(action_type="pretalx_resubmit.resubmitted")
    assert log.json_data["source_code"] == source.code
    # The original is untouched
    source.refresh_from_db()
    assert source.event == old_event
    assert source.state == SubmissionStates.REJECTED


def test_resubmit_only_once(event, old_event, speaker, make_proposal, client_for):
    source = make_proposal(old_event, "Once", speaker)
    client = client_for(speaker)
    data = {"submission_type": event.cfp.default_type.pk, "content_locale": "en"}

    client.post(_url(event, source), data)

    assert client.post(_url(event, source), data).status_code == 404
    assert Submission.objects.filter(event=event).count() == 1
    assert "Resubmit a proposal" not in _list(client, event)


def test_co_speakers_not_copied(event, old_event, speaker, make_proposal, client_for):
    from pretalx.person.models import User

    other = User.objects.create_user(email="co@example.invalid", name="Co")
    source = make_proposal(old_event, "Together", speaker, other)

    client_for(speaker).post(
        _url(event, source),
        {"submission_type": event.cfp.default_type.pk, "content_locale": "en"},
    )

    copy = Submission.objects.get(event=event)
    assert [s.user for s in copy.speakers.all()] == [speaker]


@pytest.mark.parametrize("who", ("stranger", "anonymous"))
def test_cannot_resubmit_others_proposal(
    who, event, old_event, speaker, make_proposal, client_for
):
    from pretalx.person.models import User

    source = make_proposal(old_event, "Mine", speaker)
    if who == "stranger":
        client = client_for(
            User.objects.create_user(email="s@example.invalid", name="S")
        )
        expected = 404
    else:
        client = client_for()
        expected = 302  # to the login page

    response = client.post(
        _url(event, source),
        {"submission_type": event.cfp.default_type.pk, "content_locale": "en"},
    )

    assert response.status_code == expected
    assert not Submission.objects.filter(event=event).exists()


def test_not_available_where_plugin_disabled(
    event, old_event, speaker, make_proposal, client_for
):
    source = make_proposal(event, "Newer", speaker)

    # old_event does not have the plugin enabled
    assert client_for(speaker).get(_url(old_event, source)).status_code == 404


def test_session_type_matched_by_name(
    event, old_event, speaker, make_proposal, client_for
):
    from pretalx.submission.models import SubmissionType

    SubmissionType.objects.create(event=old_event, name="Workshop", default_duration=90)
    workshop = SubmissionType.objects.create(
        event=event, name="Workshop", default_duration=60
    )
    source = make_proposal(old_event, "Hands on", speaker)
    source.submission_type = SubmissionType.objects.get(
        event=old_event, name="Workshop"
    )
    source.save()

    response = client_for(speaker).get(_url(event, source))

    assert response.context["form"]["submission_type"].initial == workshop.pk


def test_image_copied(event, old_event, speaker, make_proposal, client_for):
    import io

    from django.core.files.base import ContentFile
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buffer, format="PNG")
    source = make_proposal(old_event, "Pictured", speaker)
    source.image.save("talk.png", ContentFile(buffer.getvalue()))

    client_for(speaker).post(
        _url(event, source),
        {"submission_type": event.cfp.default_type.pk, "content_locale": "en"},
    )

    copy = Submission.objects.get(event=event)
    assert copy.image
    assert copy.image.name != source.image.name
    assert f"/{copy.code}/" in copy.image.name
    with copy.image.open("rb") as image:
        assert Image.open(image).size == (40, 30)


@pytest.mark.parametrize("page", ("", "cfp"))
def test_button_on_start_and_cfp_pages(
    page, event, old_event, speaker, make_proposal, client_for
):
    from pretalx.person.models import User

    make_proposal(old_event, "Mine", speaker)
    html = client_for(speaker).get(f"/{event.slug}/{page}").content.decode()
    assert "pretalx_resubmit/button.js" in html
    assert f"/{event.slug}/p/resubmit/" in html

    # Not for speakers with nothing to resubmit
    nobody = User.objects.create_user(email="n@example.invalid", name="N")
    html = client_for(nobody).get(f"/{event.slug}/{page}").content.decode()
    assert "pretalx_resubmit/button.js" not in html


def test_list_page(event, old_event, speaker, make_proposal, client_for):
    source = make_proposal(old_event, "Mine", speaker)

    html = client_for(speaker).get(f"/{event.slug}/p/resubmit/").content.decode()

    assert "Mine" in html
    assert _url(event, source) in html
