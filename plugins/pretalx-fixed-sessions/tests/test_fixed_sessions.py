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
        event,
        "My own title",
        speaker,
        state="submitted",
        submission_type=core_type,
        abstract="mine",
        description="mine too",
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
        {
            "title": "New title",
            "abstract": "New abstract",
            "description": "",
            "do_not_record": "unknown",
        },
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    proposal.refresh_from_db()
    assert (proposal.title, proposal.abstract, proposal.description) == (
        "New title",
        "New abstract",
        "",
    )
    assert (
        event.logged_actions()
        .filter(action_type="pretalx_fixed_sessions.applied")
        .exists()
    )


def test_orga_make_existing_type_core(event, orga, speaker, make_proposal, client_for):
    write_in = event.cfp.default_type
    proposal = make_proposal(event, "Speaker title", speaker)
    client = client_for(orga)
    page = client.get(f"{_list_url(event)}{write_in.pk}/")
    assert page.status_code == 200
    response = client.post(
        f"{_list_url(event)}{write_in.pk}/",
        {
            "title": "Now core",
            "abstract": "",
            "description": "d",
            "do_not_record": "unknown",
        },
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.title == "Now core"


def test_orga_create_core_session(event, orga, client_for):
    response = client_for(orga).post(
        f"{_list_url(event)}new/",
        {
            "name": "Consent 101",
            "default_duration": "90",
            "title": "Consent 101",
            "abstract": "a",
            "description": "d",
            "do_not_record": "true",
        },
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    fixed = FixedSession.objects.get(submission_type__event=event)
    assert str(fixed.submission_type.name) == "Consent 101"
    assert fixed.submission_type.default_duration == 90
    assert fixed.do_not_record is True


def test_orga_remove_makes_write_in(
    event, core_type, orga, speaker, make_proposal, client_for
):
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
    return (
        re.search(rf'{name}=["\']?{re.escape(str(value))}(["\'\s>])', html) is not None
    )


def _fixed_data(html):
    match = re.search(
        r'<script id="?fixed-sessions-data"?[^>]*>(.*?)</script>', html, re.DOTALL
    )
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
            "track": "",
            "answers": {},
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


@pytest.mark.parametrize("page", ("/{slug}/", "/{slug}/cfp"))
def test_other_cfp_pages_have_no_script(event, core_type, client_for, page):
    html = client_for().get(page.format(slug=event.slug), follow=True).content.decode()
    assert "fixed-sessions-data" not in html


def test_forms_import_without_event_scope():
    """pretalx rebuild (Docker build) imports the URLconf with scopes active
    and no event; defining the forms must not query scoped models."""
    import importlib

    from django_scopes import scope
    from pretalx_fixed_sessions import forms

    with scope():
        importlib.reload(forms)


@pytest.fixture
def questions(event):
    from pretalx.submission.models import AnswerOption, Question

    def make(variant, **fields):
        return Question.objects.create(
            event=event,
            question=f"{variant}?",
            variant=variant,
            target="submission",
            **fields,
        )

    text = make("string")
    choice = make("choices")
    options = [AnswerOption.objects.create(question=choice, answer=a) for a in "ABC"]
    boolean = make("boolean")
    return {"text": text, "choice": choice, "options": options, "boolean": boolean}


@pytest.fixture
def fixed_answers(core_type, questions):
    from pretalx_fixed_sessions.models import FixedAnswer

    fixed = core_type.fixed_session
    FixedAnswer.objects.create(
        fixed_session=fixed, question=questions["text"], answer="Fixed"
    )
    choice = FixedAnswer.objects.create(
        fixed_session=fixed, question=questions["choice"], answer="B"
    )
    choice.options.set([questions["options"][1]])
    FixedAnswer.objects.create(
        fixed_session=fixed, question=questions["boolean"], answer="False"
    )
    return fixed


def _answers(submission):
    from pretalx.submission.models import Answer

    return {
        a.question.variant: (a.answer, sorted(o.answer for o in a.options.all()))
        for a in Answer.objects.filter(submission=submission)
    }


def test_fixed_answers_created_with_proposal(
    event, core_type, fixed_answers, speaker, make_proposal
):
    proposal = make_proposal(event, "x", speaker, submission_type=core_type)
    assert _answers(proposal) == {"string": ("Fixed", []), "choices": ("B", ["B"])}


def test_speaker_answers_are_overwritten(
    event, core_type, questions, fixed_answers, speaker, make_proposal
):
    from pretalx.submission.domain.question import save_answer
    from pretalx.submission.models import Answer

    proposal = make_proposal(event, "x", speaker, submission_type=core_type)
    existing = {a.question_id: a for a in Answer.objects.filter(submission=proposal)}
    # The same calls pretalx's question form makes
    save_answer(
        question=questions["text"],
        value="Mine",
        target_object=proposal,
        existing=existing[questions["text"].pk],
    )
    save_answer(
        question=questions["choice"],
        value=questions["options"][2],
        target_object=proposal,
        existing=existing[questions["choice"].pk],
    )
    save_answer(question=questions["boolean"], value=True, target_object=proposal)
    assert _answers(proposal) == {"string": ("Fixed", []), "choices": ("B", ["B"])}


def test_unfixed_questions_stay_with_speaker(
    event, core_type, questions, speaker, make_proposal
):
    from pretalx.submission.domain.question import save_answer

    proposal = make_proposal(event, "x", speaker, submission_type=core_type)
    save_answer(question=questions["text"], value="Mine", target_object=proposal)
    assert _answers(proposal) == {"string": ("Mine", [])}


def test_orga_sets_fixed_answers_and_track(
    event, core_type, questions, orga, speaker, make_proposal, client_for
):
    from pretalx.submission.models import Track

    track = Track.objects.create(event=event, name="Staff")
    proposal = make_proposal(event, "x", speaker, submission_type=core_type)
    url = f"{_list_url(event)}{core_type.pk}/"
    client = client_for(orga)
    page = client.get(url).content.decode()
    assert _has_attr(page, "name", f"answers-question_{questions['text'].pk}")

    response = client.post(
        url,
        {
            "title": "T",
            "abstract": "",
            "description": "",
            "track": track.pk,
            "do_not_record": "unknown",
            f"answers-question_{questions['text'].pk}": "Orga text",
            f"answers-question_{questions['choice'].pk}": questions["options"][0].pk,
            f"answers-question_{questions['boolean'].pk}": "true",
        },
    )
    assert response.status_code == 302, response.content.decode()[:3000]
    proposal.refresh_from_db()
    assert proposal.track == track
    assert _answers(proposal) == {
        "string": ("Orga text", []),
        "choices": ("A", ["A"]),
        "boolean": ("True", []),
    }

    # Emptied again: the speaker answers; existing answers are kept
    response = client.post(
        url,
        {
            "title": "T",
            "abstract": "",
            "description": "",
            "do_not_record": "unknown",
            f"answers-question_{questions['boolean'].pk}": "unknown",
        },
    )
    assert response.status_code == 302
    assert not core_type.fixed_session.answers.exists()
    assert _answers(proposal)["string"] == ("Orga text", [])


def test_cfp_data_has_track_and_answers(
    event, core_type, questions, fixed_answers, speaker, client_for
):
    from pretalx.submission.models import Track

    track = Track.objects.create(event=event, name="Staff")
    core_type.fixed_session.track = track
    core_type.fixed_session.save()
    html = (
        client_for(speaker).get(f"/{event.slug}/submit/", follow=True).content.decode()
    )
    data = _fixed_data(html)[str(core_type.pk)]
    assert data["track"] == str(track.pk)
    assert data["answers"] == {
        f"question_{questions['text'].pk}": "Fixed",
        f"question_{questions['choice'].pk}": str(questions["options"][1].pk),
        f"question_{questions['boolean'].pk}": False,
    }


def test_questions_step_knows_type_from_wizard(
    event, core_type, questions, fixed_answers, speaker, client_for
):
    client = client_for(speaker)
    response = client.get(f"/{event.slug}/submit/", follow=True)
    info_url = response.redirect_chain[-1][0]
    response = client.post(
        info_url,
        {
            "title": "x",
            "submission_type": core_type.pk,
            "abstract": "a",
            "description": "d",
            "content_locale": "en",
        },
        follow=True,
    )
    questions_url = response.redirect_chain[-1][0]
    assert questions_url.rstrip("/").endswith("questions"), questions_url
    html = response.content.decode()
    assert _has_attr(html, "data-current-type", core_type.pk)
    assert _has_attr(html, "name", f"question_{questions['text'].pk}")
