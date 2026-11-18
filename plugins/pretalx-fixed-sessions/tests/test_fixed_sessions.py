import json
import re

import pytest
from django.core.management import call_command

from pretalx_fixed_sessions.models import FixedSession


def _list_url(event):
    return f"/orga/event/{event.slug}/settings/p/fixed-sessions/"


def test_migrations_match_models():
    call_command("makemigrations", "pretalx_fixed_sessions", "--check", "--dry-run")


def test_save_overwrites_speaker_content(event, core_type, speaker, make_proposal):
    proposal = make_proposal(
        event, "My own title", speaker, state="submitted", submission_type=core_type,
        abstract="mine", description="mine too",
    )
    proposal.refresh_from_db()
    assert proposal.title == "Intro to Contact Staff"
    assert proposal.abstract == "Fixed abstract"
    assert proposal.description == "Fixed description"

    proposal.title = "Edited by the speaker"
    proposal.save()
    proposal.refresh_from_db()
    assert proposal.title == "Intro to Contact Staff"


def test_write_in_type_is_untouched(event, core_type, speaker, make_proposal):
    proposal = make_proposal(event, "Write-in", speaker, abstract="mine")
    proposal.refresh_from_db()
    assert (proposal.title, proposal.abstract) == ("Write-in", "mine")


def test_disabled_plugin_does_nothing(event, core_type, speaker, make_proposal):
    from pretalx.event.domain.plugins import disable_plugin

    disable_plugin(event, "pretalx_fixed_sessions")
    proposal = make_proposal(event, "Mine", speaker, submission_type=core_type)
    proposal.refresh_from_db()
    assert proposal.title == "Mine"


def test_optional_fields_only_set_when_given(event, core_type, speaker, make_proposal):
    from pretalx.submission.models import Track

    proposal = make_proposal(
        event, "x", speaker, submission_type=core_type, do_not_record=True
    )
    proposal.refresh_from_db()
    assert proposal.do_not_record is True and proposal.track is None

    track = Track.objects.create(event=event, name="Staff")
    core_type.fixed_session.track = track
    core_type.fixed_session.do_not_record = False
    core_type.fixed_session.save()
    proposal.save()
    proposal.refresh_from_db()
    assert proposal.track == track and proposal.do_not_record is False


def test_orga_edit_applies_to_existing_proposals(
    event, core_type, orga, speaker, make_proposal, client_for
):
    proposal = make_proposal(event, "x", speaker, submission_type=core_type)
    response = client_for(orga).post(
        f"{_list_url(event)}{core_type.pk}/",
        {"title": "New title", "abstract": "New abstract", "description": "",
         "do_not_record": "unknown"},
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    proposal.refresh_from_db()
    assert (proposal.title, proposal.abstract, proposal.description) == (
        "New title", "New abstract", "",
    )
    assert event.logged_actions().filter(
        action_type="pretalx_fixed_sessions.applied"
    ).exists()


def test_orga_make_existing_type_core(event, orga, speaker, make_proposal, client_for):
    write_in = event.cfp.default_type
    proposal = make_proposal(event, "Speaker title", speaker)
    client = client_for(orga)
    page = client.get(f"{_list_url(event)}{write_in.pk}/")
    assert page.status_code == 200
    response = client.post(
        f"{_list_url(event)}{write_in.pk}/",
        {"title": "Now core", "abstract": "", "description": "d", "do_not_record": "unknown"},
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.title == "Now core"


def test_orga_create_core_session(event, orga, client_for):
    response = client_for(orga).post(
        f"{_list_url(event)}new/",
        {"name": "Consent 101", "default_duration": "90", "title": "Consent 101",
         "abstract": "a", "description": "d", "do_not_record": "true"},
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    fixed = FixedSession.objects.get(submission_type__event=event)
    assert str(fixed.submission_type.name) == "Consent 101"
    assert fixed.submission_type.default_duration == 90
    assert fixed.do_not_record is True


def test_orga_remove_makes_write_in(event, core_type, orga, speaker, make_proposal, client_for):
    response = client_for(orga).post(
        f"{_list_url(event)}{core_type.pk}/", {"action": "remove"}
    )
    assert response.status_code == 302
    assert not FixedSession.objects.filter(submission_type=core_type).exists()
    proposal = make_proposal(event, "Mine", speaker, submission_type=core_type)
    proposal.refresh_from_db()
    assert proposal.title == "Mine"


def test_list_page(event, core_type, orga, client_for):
    page = client_for(orga).get(_list_url(event))
    assert page.status_code == 200
    assert "Intro to Contact Staff" in page.content.decode()


def test_settings_nav_link(event, orga, client_for):
    page = client_for(orga).get(f"/orga/event/{event.slug}/settings/")
    assert _list_url(event) in page.content.decode()


def test_speaker_cannot_open_orga_pages(event, speaker, client_for):
    assert client_for(speaker).get(_list_url(event)).status_code in (403, 404)


def test_orga_pages_404_without_plugin(event, orga, client_for):
    from pretalx.event.domain.plugins import disable_plugin

    disable_plugin(event, "pretalx_fixed_sessions")
    assert client_for(orga).get(_list_url(event)).status_code == 404


def _has_attr(html, name, value):
    """pretalx minifies its HTML, so attribute quotes may be dropped."""
    return re.search(rf'{name}=["\']?{re.escape(str(value))}(["\'\s>])', html) is not None


def _fixed_data(html):
    match = re.search(r'<script id="?fixed-sessions-data"?[^>]*>(.*?)</script>', html, re.S)
    return json.loads(match.group(1)) if match else None


def test_cfp_wizard_gets_script(event, core_type, speaker, client_for):
    client = client_for(speaker)
    response = client.get(f"/{event.slug}/submit/", follow=True)
    html = response.content.decode()
    assert response.status_code == 200
    # form.js relies on these ids
    assert _has_attr(html, "id", "id_title")
    assert _has_attr(html, "id", "id_submission_type")
    assert _fixed_data(html) == {
        str(core_type.pk): {
            "title": "Intro to Contact Staff",
            "abstract": "Fixed abstract",
            "description": "Fixed description",
        }
    }
    assert "pretalx_fixed_sessions/form.js" in html


def test_speaker_edit_keeps_fixed_content(
    event, core_type, speaker, make_proposal, client_for
):
    proposal = make_proposal(
        event, "x", speaker, state="submitted", submission_type=core_type
    )
    client = client_for(speaker)
    url = f"/{event.slug}/me/submissions/{proposal.code}/"
    page = client.get(url)
    html = page.content.decode()
    assert page.status_code == 200
    assert _has_attr(html, "data-current-type", core_type.pk)
    assert _has_attr(html, "id", "id_title")

    response = client.post(
        url,
        {
            "title": "Speaker's title",
            "submission_type": core_type.pk,
            "abstract": "Speaker's abstract",
            "description": "Speaker's description",
            "notes": "a note",
            "content_locale": "en",
        },
    )
    assert response.status_code == 302, response.content.decode()[:3000]
    proposal.refresh_from_db()
    assert proposal.title == "Intro to Contact Staff"
    assert proposal.abstract == "Fixed abstract"
    assert proposal.notes == "a note"


@pytest.mark.parametrize("page", ["/{slug}/", "/{slug}/cfp"])
def test_other_cfp_pages_have_no_script(event, core_type, client_for, page):
    html = client_for().get(page.format(slug=event.slug), follow=True).content.decode()
    assert "fixed-sessions-data" not in html
