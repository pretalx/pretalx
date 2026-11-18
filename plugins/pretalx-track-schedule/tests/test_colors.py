import pytest
from pretalx_track_schedule.models import ColorSettings, OptionColor


def _settings_url(event):
    return f"/orga/event/{event.slug}/settings/p/track-schedule/"


def _schedule(client, event):
    return client.get(f"/{event.slug}/p/track-schedule/", HTTP_ACCEPT="text/html")


@pytest.fixture
def orga(event):
    from pretalx.event.models import Team
    from pretalx.person.models import User

    user = User.objects.create_user(
        email="orga@example.invalid", password="x", name="Orga"
    )
    team = Team.objects.create(
        organiser=event.organiser,
        name="Orga",
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    )
    team.members.add(user)
    return user


@pytest.fixture
def difficulty(event):
    from pretalx.submission.models import AnswerOption, Question

    question = Question.objects.create(
        event=event, question="Difficulty", variant="choices", target="submission"
    )
    options = {
        name: AnswerOption.objects.create(question=question, answer=name, position=i)
        for i, name in enumerate(["Easy", "Medium", "Hard", "Mixed"])
    }
    return question, options


def _answer(proposal, question, *options):
    from pretalx.submission.models import Answer

    answer = Answer.objects.create(
        question=question,
        submission=proposal,
        answer=", ".join(o.answer for o in options),
    )
    answer.options.set(options)


@pytest.fixture
def scheduled(event, rooms, at, schedule_slot, difficulty):
    question, options = difficulty
    easy = schedule_slot("Easy one", rooms[0], at(10), at(11))
    hard = schedule_slot("Hard one", rooms[1], at(10), at(11))
    schedule_slot("Unanswered", rooms[2], at(10), at(11))
    _answer(easy, question, options["Easy"])
    _answer(hard, question, options["Hard"])
    return question, options


def test_settings_suggest_difficulty_and_apply_defaults(
    event, orga, scheduled, release, client_for
):
    question, options = scheduled
    release()
    client = client_for(orga)
    page = client.get(_settings_url(event))
    assert page.status_code == 200
    assert page.context["form"].fields["question"].initial == question

    response = client.post(_settings_url(event), {"question": question.pk})
    assert response.status_code == 302
    assert ColorSettings.objects.get(event=event).question == question
    colours = {
        str(oc.option.answer): oc.color
        for oc in OptionColor.objects.filter(option__question=question)
    }
    assert colours == {
        "Easy": "#2e9d4f",
        "Medium": "#d68a00",
        "Hard": "#c0392b",
        "Mixed": "#7d3cbf",
    }

    response = _schedule(client_for(), event)
    slots = {
        p.item.data.submission.title: p.item.data
        for _, layout in response.context["days"]
        for p in layout.sessions
    }
    assert (slots["Easy one"].ts_label, slots["Easy one"].ts_color) == (
        "Easy",
        "#2e9d4f",
    )
    assert slots["Hard one"].ts_label == "Hard"
    assert slots["Unanswered"].ts_color is None
    assert [label for label, _ in response.context["legend"]] == [
        "Easy",
        "Medium",
        "Hard",
        "Mixed",
    ]
    html = response.content.decode()
    assert "ts-chip" in html
    assert "Hard" in html


def test_change_colours(event, orga, scheduled, release, client_for):
    question, options = scheduled
    release()
    client = client_for(orga)
    client.post(_settings_url(event), {"question": question.pk})
    data = {"question": question.pk}
    data.update({f"color_{o.pk}": "#123456" for o in options.values()})
    data[f"color_{options['Easy'].pk}"] = "#ABCDEF"
    response = client.post(_settings_url(event), data)
    assert response.status_code == 302
    assert OptionColor.objects.get(option=options["Easy"]).color == "#abcdef"

    bad = {**data, f"color_{options['Easy'].pk}": "red"}
    response = client.post(_settings_url(event), bad)
    assert response.status_code == 200
    assert response.context["form"].errors


def test_multiple_answers_take_first_coloured_option(
    event, rooms, at, schedule_slot, release, client_for
):
    from pretalx.submission.models import AnswerOption, Question

    question = Question.objects.create(
        event=event, question="Level", variant="multiple_choice", target="submission"
    )
    low = AnswerOption.objects.create(question=question, answer="Low", position=0)
    high = AnswerOption.objects.create(question=question, answer="High", position=1)
    ColorSettings.objects.create(event=event, question=question)
    OptionColor.objects.create(option=low, color="#00ff00")
    OptionColor.objects.create(option=high, color="#ff0000")
    proposal = schedule_slot("Both", rooms[0], at(10), at(11))
    _answer(proposal, question, high, low)
    release()
    response = _schedule(client_for(), event)
    ((_, layout),) = response.context["days"]
    assert layout.sessions[0].item.data.ts_label == "Low"


def test_no_colour_question_keeps_track_colours(event, scheduled, release, client_for):
    release()
    response = _schedule(client_for(), event)
    assert response.context["legend"] == []
    assert "ts-chip" not in response.content.decode()


def test_settings_page_permissions(event, orga, speaker, client_for):
    from pretalx.event.domain.plugins import disable_plugin

    assert client_for(speaker).get(_settings_url(event)).status_code == 404
    page = client_for(orga).get(f"/orga/event/{event.slug}/settings/")
    assert _settings_url(event) in page.content.decode()
    disable_plugin(event, "pretalx_track_schedule")
    assert client_for(orga).get(_settings_url(event)).status_code == 404
