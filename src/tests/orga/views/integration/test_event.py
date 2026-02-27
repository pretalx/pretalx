import datetime as dt
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.common.models.log import ActivityLog
from pretalx.event.models import Event
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewScoreCategoryFactory,
    SubmissionFactory,
    TeamFactory,
    TeamInviteFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


def get_settings_form_data(event):
    return {
        "name_0": event.name,
        "slug": event.slug,
        "date_from": event.date_from,
        "date_to": event.date_to,
        "email": event.email or "",
        "custom_domain": event.custom_domain or "",
        "locale": event.locale,
        "locales": ",".join(event.locales),
        "content_locales": ",".join(event.content_locales),
        "timezone": event.timezone,
        "primary_color": event.primary_color or "",
        "schedule": event.display_settings["schedule"],
        "show_featured": event.feature_flags["show_featured"],
        "use_feedback": event.feature_flags["use_feedback"],
        "header-links-TOTAL_FORMS": 0,
        "header-links-INITIAL_FORMS": 0,
        "header-links-MIN_NUM_FORMS": 0,
        "header-links-MAX_NUM_FORMS": 1000,
        "footer-links-TOTAL_FORMS": 0,
        "footer-links-INITIAL_FORMS": 0,
        "footer-links-MIN_NUM_FORMS": 0,
        "footer-links-MAX_NUM_FORMS": 1000,
    }


@pytest.mark.django_db
def test_event_detail_accessible_by_orga(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.settings)

    assert response.status_code == 200
    assert str(event.name) in response.content.decode()


@pytest.mark.django_db
def test_event_detail_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.settings)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_event_detail_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.settings)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_detail_post_updates_event(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    new_email = "newemail@example.com"
    data["email"] = new_email

    response = client.post(event.orga_urls.settings, data, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert event.email == new_email


@pytest.mark.django_db
def test_event_detail_post_end_before_start_rejected(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    old_date_from = event.date_from
    old_date_to = event.date_to
    data = get_settings_form_data(event)
    data["date_from"] = "2022-10-10"
    data["date_to"] = "2022-10-09"

    response = client.post(event.orga_urls.settings, data, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert event.date_from == old_date_from
    assert event.date_to == old_date_to


@pytest.mark.django_db
def test_event_detail_post_creates_activity_log(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["email"] = "changed@example.com"

    with scopes_disabled():
        initial_count = ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.update"
        ).count()

    client.post(event.orga_urls.settings, data, follow=True)

    with scopes_disabled():
        assert (
            ActivityLog.objects.filter(
                event=event, action_type="pretalx.event.update"
            ).count()
            == initial_count + 1
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "allowed"),
    (
        ("src/tests/fixtures/custom.css", True),
        ("src/tests/fixtures/malicious.css", False),
        ("src/tests/conftest.py", False),
    ),
)
def test_event_detail_add_custom_css(client, event, path, allowed):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    assert not event.custom_css
    data = get_settings_form_data(event)
    with Path(path).open() as f:
        data["custom_css"] = f
        client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    assert bool(event.custom_css) == allowed


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "allowed"),
    (
        ("src/tests/fixtures/custom.css", True),
        ("src/tests/fixtures/malicious.css", False),
        ("src/tests/conftest.py", False),
    ),
)
def test_event_detail_add_custom_css_as_text(client, event, path, allowed):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    with Path(path).open() as f:
        data["custom_css_text"] = f.read()
    data["slug"] = "csstest"

    client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    assert bool(event.custom_css) == allowed


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    (
        "src/tests/fixtures/custom.css",
        "src/tests/fixtures/malicious.css",
        "src/tests/conftest.py",
    ),
)
def test_event_detail_admin_can_upload_any_css(client, event, path):
    """Administrators bypass CSS sanitization."""
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    data = get_settings_form_data(event)
    with Path(path).open() as f:
        data["custom_css"] = f
        data["slug"] = "csstest"
        client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    assert event.custom_css


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("domain", "result"),
    (
        ("example.org", "https://example.org"),
        ("http://example.org", "https://example.org"),
        ("https://example.org", "https://example.org"),
    ),
)
def test_event_detail_change_custom_domain(client, event, monkeypatch, domain, result):
    # Monkeypatch: the form calls socket.gethostbyname to verify DNS resolution,
    # which would make a real network request in tests.
    from pretalx.orga.forms.event import socket  # noqa: PLC0415

    monkeypatch.setattr(socket, "gethostbyname", lambda x: True)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["custom_domain"] = domain

    client.post(event.orga_urls.settings, data, follow=True)

    event = Event.objects.get(pk=event.pk)
    assert event.custom_domain == result


@pytest.mark.django_db
def test_event_detail_unavailable_domain_rejected(client, event, monkeypatch):
    # Monkeypatch: the form calls socket.gethostbyname to verify DNS resolution,
    # which would make a real network request in tests.
    from pretalx.orga.forms.event import socket  # noqa: PLC0415

    monkeypatch.setattr(
        socket, "gethostbyname", lambda x: (_ for _ in ()).throw(OSError)
    )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["custom_domain"] = "https://example.org"

    client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    assert not event.custom_domain


@pytest.mark.django_db
def test_event_detail_remove_relevant_locales_rejected(client, event):
    """Cannot remove the locale used as the event's default locale."""
    event.locale_array = "en,de"
    event.content_locale_array = "en,de"
    event.locale = "de"
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["locales"] = "en"
    data["content_locales"] = "en"
    data["locale"] = "de"

    client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    assert len(event.locales) == 2


@pytest.mark.django_db
def test_event_live_get_accessible(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.live)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_live_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.live)

    assert response.status_code == 302


@pytest.mark.django_db
def test_event_live_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.live)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_live_activate(client, event):
    event.is_public = False
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.live, {"action": "activate"}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert event.is_public


@pytest.mark.django_db
def test_event_live_activate_creates_log(client, event):
    event.is_public = False
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    client.post(event.orga_urls.live, {"action": "activate"}, follow=True)

    with scopes_disabled():
        assert ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.activate"
        ).exists()


@pytest.mark.django_db
def test_event_live_deactivate(client, event):
    event.is_public = True
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.live, {"action": "deactivate"}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert not event.is_public


@pytest.mark.django_db
def test_event_live_deactivate_creates_log(client, event):
    event.is_public = True
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    client.post(event.orga_urls.live, {"action": "deactivate"}, follow=True)

    with scopes_disabled():
        assert ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.deactivate"
        ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "initial_public"), (("activate", True), ("deactivate", False))
)
def test_event_live_idempotent(client, event, action, initial_public):
    """Repeating activate/deactivate when already in that state is a no-op."""
    event.is_public = initial_public
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.live, {"action": action}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert event.is_public is initial_public


@pytest.mark.django_db
def test_event_live_plugin_blocks_activation(client, event, register_signal_handler):
    """When a plugin's activate_event signal raises, event stays offline."""
    from pretalx.orga.signals import activate_event  # noqa: PLC0415

    event.is_public = False
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    def blocker(signal, sender, **kwargs):
        raise Exception("It's not safe to go alone take this")  # noqa: TRY002

    register_signal_handler(activate_event, blocker)
    response = client.post(event.orga_urls.live, {"action": "activate"}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert not event.is_public
    assert "not safe to go alone" in response.content.decode()


@pytest.mark.django_db
def test_event_history_accessible(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.history)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_history_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.history)

    assert response.status_code == 302


@pytest.mark.django_db
def test_event_history_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.history)

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_event_history_query_count(
    client, event, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_event_settings=True)
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        for _ in range(item_count):
            ActivityLog.objects.create(
                event=event,
                person=user,
                content_object=submission,
                action_type="pretalx.submission.update",
            )
    client.force_login(user)

    with django_assert_num_queries(17):
        response = client.get(event.orga_urls.history)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_history_detail_shows_changes(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        log = submission.log_action(
            "pretalx.submission.update",
            person=user,
            orga=True,
            old_data={"title": "Old Title"},
            new_data={"title": "New Title"},
        )
    client.force_login(user)

    url = f"/orga/event/{event.slug}/history/{log.pk}/"
    response = client.get(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "<del>Old</del> Title" in content
    assert "<ins>New</ins> Title" in content


@pytest.mark.django_db
def test_event_history_detail_with_question_changes(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    with scopes_disabled():
        question = QuestionFactory(event=event)
        submission = SubmissionFactory(event=event)
        key = f"question-{question.pk}"
        log = submission.log_action(
            "pretalx.submission.update",
            person=user,
            orga=True,
            old_data={key: "Blue"},
            new_data={key: "Red"},
        )
    client.force_login(user)

    url = f"/orga/event/{event.slug}/history/{log.pk}/"
    response = client.get(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert str(question.question) in content


@pytest.mark.django_db
def test_event_history_detail_anonymous_redirects(client, event):
    with scopes_disabled():
        user = UserFactory()
        log = ActivityLog.objects.create(
            event=event,
            person=user,
            content_object=event,
            action_type="pretalx.event.update",
        )

    url = f"/orga/event/{event.slug}/history/{log.pk}/"
    response = client.get(url)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_event_history_detail_scoping(client, event):
    """Cannot view a log entry via another event's URL."""
    with scopes_disabled():
        other_event = EventFactory()
        user = make_orga_user(other_event, can_change_event_settings=True)
        log = ActivityLog.objects.create(
            event=event,
            person=user,
            content_object=event,
            action_type="pretalx.event.update",
        )
    client.force_login(user)

    url = f"/orga/event/{other_event.slug}/history/{log.pk}/"
    response = client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_review_settings_get_accessible(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.review_settings)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_review_settings_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.review_settings)

    assert response.status_code == 302


@pytest.mark.django_db
def test_event_review_settings_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.review_settings)

    assert response.status_code == 404


def _build_review_settings_data(event):
    """Helper to build valid review settings POST data."""
    with scope(event=event):
        active_phase = event.active_review_phase
        other_phase = event.review_phases.exclude(pk=active_phase.pk).first()
        category = event.score_categories.first()
        scores = list(category.scores.all())

    data = {
        "phase-TOTAL_FORMS": 2,
        "phase-INITIAL_FORMS": 2,
        "phase-MIN_NUM_FORMS": 0,
        "phase-MAX_NUM_FORMS": 1000,
        "phase-0-name": active_phase.name,
        "phase-0-id": active_phase.id,
        "phase-0-start": "",
        "phase-0-end": "2000-01-01 12:00:00",
        "phase-0-can_see_other_reviews": "after_review",
        "phase-0-can_tag_submissions": "use_tags",
        "phase-0-proposal_visibility": "all",
        "phase-1-name": other_phase.name,
        "phase-1-id": other_phase.id,
        "phase-1-start": "2000-02-01 12:00:00",
        "phase-1-end": "2000-02-02 12:00:00",
        "phase-1-can_see_other_reviews": "after_review",
        "phase-1-can_tag_submissions": "use_tags",
        "phase-1-proposal_visibility": "all",
        "scores-TOTAL_FORMS": "1",
        "scores-INITIAL_FORMS": "1",
        "scores-MIN_NUM_FORMS": "0",
        "scores-MAX_NUM_FORMS": "1000",
        "scores-0-name_0": str(category.name),
        "scores-0-id": category.id,
        "scores-0-weight": "1",
        "aggregate_method": event.review_settings["aggregate_method"],
        "score_format": event.review_settings["score_format"],
    }
    for score in scores:
        data[f"scores-0-value_{score.id}"] = score.value
        data[f"scores-0-label_{score.id}"] = score.label or ""
    return data


@pytest.mark.django_db
def test_event_review_settings_post_updates_phases(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-0-name"] = "Renamed Phase"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    with scope(event=event):
        assert event.review_phases.filter(name="Renamed Phase").exists()


@pytest.mark.django_db
def test_event_review_settings_post_updates_score_category(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-0-name_0"] = "Renamed Category"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.score_categories.filter(name__contains="Renamed Category").exists()
        assert event.score_categories.count() == 1


@pytest.mark.django_db
def test_event_review_settings_add_new_phase(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-TOTAL_FORMS"] = 3
    data["phase-2-name"] = "New Phase"
    data["phase-2-start"] = "2000-03-03 12:00:00"
    data["phase-2-end"] = ""
    data["phase-2-can_see_other_reviews"] = "always"
    data["phase-2-can_tag_submissions"] = "use_tags"
    data["phase-2-proposal_visibility"] = "all"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.review_phases.count() == 3


@pytest.mark.django_db
def test_event_review_settings_invalid_phase_date_rejected(client, event):
    """Invalid date in phase formset prevents saving."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-0-start"] = "lalala"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.review_phases.count() == 2


@pytest.mark.django_db
def test_event_review_settings_invalid_can_tag_rejected(client, event):
    """Invalid can_tag_submissions value prevents saving."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-0-name"] = "Should Not Save"
    data["phase-0-can_tag_submissions"] = "hahah"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert not event.review_phases.filter(name="Should Not Save").exists()


@pytest.mark.django_db
def test_event_review_settings_phase_end_before_start_rejected(client, event):
    """Phases with end date before start date are rejected."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-TOTAL_FORMS"] = 3
    data["phase-0-end"] = ""
    data["phase-1-start"] = ""
    data["phase-1-end"] = ""
    data["phase-2-name"] = "New Phase"
    data["phase-2-start"] = now().strftime("%Y-%m-%d")
    data["phase-2-end"] = (now() - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    data["phase-2-can_see_other_reviews"] = "always"
    data["phase-2-can_tag_submissions"] = "use_tags"
    data["phase-2-proposal_visibility"] = "all"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.review_phases.count() == 2


@pytest.mark.django_db
def test_event_review_settings_is_independent_validation(client, event):
    """Setting is_independent when non-independent categories exist shows error."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-0-is_independent"] = "on"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.score_categories.filter(is_independent=False).exists()


@pytest.mark.django_db
def test_phase_activate_toggles_active_phase(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scope(event=event):
        phase = event.active_review_phase
        other_phase = event.review_phases.exclude(pk=phase.pk).first()

    response = client.get(other_phase.urls.activate, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.active_review_phase == other_phase


@pytest.mark.django_db
def test_phase_deactivate(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scope(event=event):
        phase = event.active_review_phase

    response = client.get(phase.urls.activate, follow=True)

    assert response.status_code == 200
    phase.refresh_from_db()
    assert not phase.is_active


@pytest.mark.django_db
def test_event_mail_settings_get_accessible(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.mail_settings)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_mail_settings_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.mail_settings)

    assert response.status_code == 302


@pytest.mark.django_db
def test_event_mail_settings_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.mail_settings)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_mail_settings_post_updates_settings(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "foo@bar.com",
            "smtp_host": "localhost",
            "smtp_password": "",
            "smtp_port": "25",
        },
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.mail_settings["mail_from"] == "foo@bar.com"
    assert event.mail_settings["smtp_port"] == 25


@pytest.mark.django_db
def test_event_mail_settings_unencrypted_rejected(client, event):
    """Using a custom SMTP host without encryption (non-localhost) is rejected."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "foo@bar.com",
            "smtp_use_custom": True,
            "smtp_host": "foo.bar.com",
            "smtp_password": "",
            "smtp_port": "25",
        },
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.mail_settings["mail_from"] != "foo@bar.com"


@pytest.mark.django_db
def test_event_mail_settings_test_connection(client, event):
    """Posting with test=1 saves settings and attempts SMTP connection."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "foo@bar.com",
            "smtp_host": "localhost",
            "smtp_password": "",
            "smtp_port": "25",
            "smtp_use_custom": "1",
            "test": "1",
        },
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.mail_settings["mail_from"] == "foo@bar.com"


@pytest.mark.django_db
def test_invitation_view_accept_as_new_user(client, event):
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="newinvite@example.com")
    initial_count = team.members.count()

    response = client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}),
        {
            "register_name": "New User",
            "register_email": invite.email,
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert team.members.count() == initial_count + 1
    assert team.members.filter(name="New User").exists()
    assert team.invites.count() == 0


@pytest.mark.django_db
def test_invitation_view_accept_as_logged_in_user(client, event):
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team)
        user = UserFactory()
    client.force_login(user)
    initial_count = team.members.count()

    response = client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}), follow=True
    )

    assert response.status_code == 200
    assert team.members.count() == initial_count + 1
    assert team.members.filter(pk=user.pk).exists()
    assert team.invites.count() == 0


@pytest.mark.django_db
def test_invitation_view_invalid_token_returns_404(client):
    response = client.get(
        reverse("orga:invitation.view", kwargs={"code": "invalidtoken123"})
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_invitation_view_failed_registration_preserves_invite(client, event):
    """Mismatched passwords should not consume the invite."""
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="fail@example.com")
    initial_count = team.members.count()

    client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}),
        {
            "register_name": "Fail User",
            "register_email": invite.email,
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!WRONG",
        },
        follow=True,
    )

    assert team.members.count() == initial_count
    assert team.invites.count() == 1


@pytest.mark.django_db
def test_invitation_view_duplicate_email_preserves_invite(client, event):
    """Registering with an existing email does not consume the invite."""
    with scopes_disabled():
        existing_user = UserFactory()
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="dup@example.com")
    initial_count = team.members.count()

    client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}),
        {
            "register_email": existing_user.email,
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!",
        },
        follow=True,
    )

    assert team.members.count() == initial_count
    assert team.invites.count() == 1


@pytest.mark.django_db
def test_invitation_view_weak_password_preserves_invite(client, event):
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="weak@example.com")
    initial_count = team.members.count()

    client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}),
        {
            "register_email": invite.email,
            "register_password": "password",
            "register_password_repeat": "password",
        },
        follow=True,
    )

    assert team.members.count() == initial_count
    assert team.invites.count() == 1


@pytest.mark.django_db
def test_invitation_view_consumed_token_returns_404(client, event):
    """After an invite is accepted, the same token returns 404."""
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="consumed@example.com")
    token = invite.token

    client.post(
        reverse("orga:invitation.view", kwargs={"code": token}),
        {
            "register_name": "Consumed User",
            "register_email": invite.email,
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!",
        },
        follow=True,
    )

    response = client.get(reverse("orga:invitation.view", kwargs={"code": token}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_event_delete_admin_can_access(client, event):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(event.orga_urls.delete, follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_delete_admin_can_delete(client, event):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    event_pk = event.pk

    response = client.post(event.orga_urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not Event.objects.filter(pk=event_pk).exists()


@pytest.mark.django_db
def test_event_delete_non_admin_gets_404(client, event):
    """Non-administrators cannot delete events."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.delete, follow=True)

    assert response.status_code == 404
    assert Event.objects.filter(pk=event.pk).exists()


@pytest.mark.django_db
def test_event_delete_anonymous_redirects(client, event):
    response = client.post(event.orga_urls.delete)

    assert response.status_code == 302


@pytest.mark.django_db
def test_widget_settings_get_accessible(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.widget_settings)

    assert response.status_code == 200


@pytest.mark.django_db
def test_widget_settings_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.widget_settings)

    assert response.status_code == 302


@pytest.mark.django_db
def test_widget_settings_unauthorized_gets_404(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.orga_urls.widget_settings)

    assert response.status_code == 404


@pytest.mark.django_db
def test_widget_settings_post_enables_flag(client, event):
    assert not event.feature_flags["show_widget_if_not_public"]
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.widget_settings,
        {"show_widget_if_not_public": "on"},
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    assert event.feature_flags["show_widget_if_not_public"]


@pytest.mark.django_db
def test_event_detail_change_date_shifts_wip_slots(client, event, published_talk_slot):
    """Changing event dates shifts WIP schedule slots but not released slots."""
    talk_slot = published_talk_slot
    with scope(event=event):
        wip_slot = (
            event.wip_schedule.talks.all()
            .filter(submission=talk_slot.submission)
            .first()
        )
    old_released_start = talk_slot.start
    old_wip_start = wip_slot.start
    delta = dt.timedelta(days=17)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["date_from"] = (event.date_from + delta).isoformat()
    data["date_to"] = (event.date_to + delta).isoformat()

    response = client.post(event.orga_urls.settings, data, follow=True)

    assert response.status_code == 200
    talk_slot.refresh_from_db()
    wip_slot.refresh_from_db()
    assert talk_slot.start == old_released_start
    assert wip_slot.start == old_wip_start + delta


@pytest.mark.django_db
def test_event_detail_change_timezone_shifts_slots(client, event, published_talk_slot):
    old_slot_start = published_talk_slot.start
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["timezone"] = "Europe/Moscow"

    client.post(event.orga_urls.settings, data, follow=True)

    published_talk_slot.refresh_from_db()
    assert published_talk_slot.start != old_slot_start


@pytest.mark.django_db
def test_event_live_activate_with_plugins_no_blocker(client, event):
    """When a plugin is installed but doesn't block, event goes live."""
    event.is_public = False
    event.plugins = "tests.dummy_app"
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.live, {"action": "activate"}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert event.is_public


@pytest.mark.django_db
def test_event_detail_change_custom_domain_to_site_url_clears_it(
    client, event, monkeypatch, settings
):
    # Monkeypatch: the form calls socket.gethostbyname to verify DNS resolution,
    # which would make a real network request in tests.
    from pretalx.orga.forms.event import socket  # noqa: PLC0415

    monkeypatch.setattr(socket, "gethostbyname", lambda x: True)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["custom_domain"] = settings.SITE_URL

    client.post(event.orga_urls.settings, data, follow=True)

    event = Event.objects.get(pk=event.pk)
    assert event.custom_domain is None


@pytest.mark.django_db
def test_event_detail_post_invalid_footer_links_rejected(client, event):
    """When the footer links formset has invalid data, the form is rejected."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["footer-links-TOTAL_FORMS"] = 1
    data["footer-links-INITIAL_FORMS"] = 0
    data["footer-links-0-label"] = "A Link"
    data["footer-links-0-url"] = "not-a-url"

    response = client.post(event.orga_urls.settings, data, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    with scopes_disabled():
        assert event.extra_links.count() == 0


@pytest.mark.django_db
def test_event_live_activate_plugin_returns_string_message(
    client, event, register_signal_handler
):
    """When a plugin's activate_event signal returns a string, it is shown as success.
    When another plugin returns a non-string, it is silently ignored."""
    from pretalx.orga.signals import activate_event  # noqa: PLC0415

    event.is_public = False
    event.save()
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    def string_responder(signal, sender, **kwargs):
        return "Plugin activated successfully!"

    def silent_responder(signal, sender, **kwargs):
        return None

    register_signal_handler(activate_event, string_responder)
    register_signal_handler(activate_event, silent_responder)
    response = client.post(event.orga_urls.live, {"action": "activate"}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert event.is_public
    assert "Plugin activated successfully!" in response.content.decode()


@pytest.mark.django_db
def test_event_review_settings_delete_phase(client, event):
    """Deleting a review phase via the formset removes it from the database."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    with scope(event=event):
        initial_count = event.review_phases.count()
        other_phase = event.review_phases.exclude(
            pk=event.active_review_phase.pk
        ).first()
    data["phase-1-DELETE"] = "on"
    data["phase-0-end"] = ""

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.review_phases.count() == initial_count - 1
        assert not event.review_phases.filter(pk=other_phase.pk).exists()


@pytest.mark.django_db
def test_event_review_settings_open_ended_non_last_phase_rejected(client, event):
    """A non-last phase without an end date is rejected."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-0-end"] = ""
    data["phase-1-start"] = "2000-02-01 12:00:00"
    data["phase-1-end"] = "2000-02-02 12:00:00"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "open-ended" in content.lower() or "last review phase" in content.lower()


@pytest.mark.django_db
def test_event_review_settings_missing_start_non_first_phase_rejected(client, event):
    """A non-first phase without a start date is rejected."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-0-end"] = "2000-01-01 12:00:00"
    data["phase-1-start"] = ""
    data["phase-1-end"] = "2000-02-02 12:00:00"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "start date" in content.lower()


@pytest.mark.django_db
def test_event_review_settings_overlapping_phases_rejected(client, event):
    """Overlapping review phases are rejected with an error message."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["phase-0-end"] = "2000-03-01 12:00:00"
    data["phase-1-start"] = "2000-01-01 12:00:00"
    data["phase-1-end"] = "2000-04-01 12:00:00"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "overlap" in content.lower()


@pytest.mark.django_db
def test_event_review_settings_invalid_scores_formset_rejected(client, event):
    """When the scores formset is invalid, the main form is not saved."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    with scope(event=event):
        category = event.score_categories.first()
    data["scores-0-name_0"] = ""
    data["scores-0-weight"] = "not-a-number"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        category.refresh_from_db()
        assert category.weight != "not-a-number"


@pytest.mark.django_db
def test_event_review_settings_weight_change_triggers_recalculate(client, event):
    """Changing a score category's weight triggers score recalculation."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-0-weight"] = "5"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        category = event.score_categories.first()
        assert category.weight == 5


@pytest.mark.django_db
def test_event_review_settings_add_new_score_category(client, event):
    """Adding a new score category via extra formset forms works."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-1-name_0"] = "New Category"
    data["scores-1-weight"] = "1"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.score_categories.count() == 2
        assert event.score_categories.filter(name__contains="New Category").exists()


@pytest.mark.django_db
def test_event_review_settings_delete_score_category(client, event):
    """Deleting a score category removes it and its scores."""
    with scopes_disabled():
        extra_cat = ReviewScoreCategoryFactory(event=event)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-INITIAL_FORMS"] = "2"
    data["scores-1-name_0"] = str(extra_cat.name)
    data["scores-1-id"] = extra_cat.id
    data["scores-1-weight"] = "1"
    data["scores-1-DELETE"] = "on"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.score_categories.count() == 1
        assert not event.score_categories.filter(pk=extra_cat.pk).exists()


@pytest.mark.django_db
def test_event_review_settings_delete_independent_score_category(client, event):
    """Deleting an independent score category does not trigger weight recalculation."""
    with scopes_disabled():
        extra_cat = ReviewScoreCategoryFactory(event=event, is_independent=True)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-INITIAL_FORMS"] = "2"
    data["scores-1-name_0"] = str(extra_cat.name)
    data["scores-1-id"] = extra_cat.id
    data["scores-1-weight"] = "1"
    data["scores-1-is_independent"] = "on"
    data["scores-1-DELETE"] = "on"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.score_categories.count() == 1
        assert not event.score_categories.filter(pk=extra_cat.pk).exists()


@pytest.mark.django_db
def test_event_review_settings_delete_unsaved_extra_score(client, event):
    """Submitting a new score form that is also marked for deletion is a no-op."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-1-name_0"] = "Ephemeral Category"
    data["scores-1-weight"] = "1"
    data["scores-1-DELETE"] = "on"

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.score_categories.count() == 1
        assert not event.score_categories.filter(name__contains="Ephemeral").exists()


@pytest.mark.django_db
def test_event_review_settings_no_changes_still_saves(client, event):
    """Submitting review settings without any changes still succeeds."""
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    event = Event.objects.get(slug=event.slug)
    with scope(event=event):
        assert event.review_phases.count() == 2
        assert event.score_categories.count() == 1


@pytest.mark.django_db
def test_event_mail_settings_test_smtp_success_custom(client, event, monkeypatch):
    """Successful SMTP test with use_custom enabled shows custom success message."""
    from pretalx.common.mail import CustomSMTPBackend  # noqa: PLC0415

    monkeypatch.setattr(CustomSMTPBackend, "test", lambda self, from_addr: None)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "test@example.com",
            "smtp_host": "localhost",
            "smtp_password": "",
            "smtp_port": "25",
            "smtp_use_custom": "1",
            "test": "1",
        },
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.mail_settings["mail_from"] == "test@example.com"
    content = response.content.decode()
    assert "connection attempt" in content.lower() or "successful" in content.lower()


@pytest.mark.django_db
def test_event_mail_settings_test_smtp_success_not_custom(client, event, monkeypatch):
    """Successful SMTP test without use_custom shows reminder to enable it."""
    from pretalx.common.mail import CustomSMTPBackend  # noqa: PLC0415

    monkeypatch.setattr(CustomSMTPBackend, "test", lambda self, from_addr: None)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "test@example.com",
            "smtp_host": "localhost",
            "smtp_password": "",
            "smtp_port": "25",
            "test": "1",
        },
        follow=True,
    )

    assert response.status_code == 200
    event = Event.objects.get(pk=event.pk)
    assert event.mail_settings["mail_from"] == "test@example.com"
    content = response.content.decode()
    assert "checkbox" in content.lower() or "contact" in content.lower()
