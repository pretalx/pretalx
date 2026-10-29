# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import re
from pathlib import Path

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail as djmail
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.common.domain.queries.log import actions_by
from pretalx.common.log import LOG_NAMES, serialize_setting_value
from pretalx.common.models.log import ActivityLog
from pretalx.event.models import Event
from pretalx.event.validators import event as event_validators
from pretalx.mail.smtp import CustomSMTPBackend
from pretalx.orga.signals import activate_event
from pretalx.person.enums import EmailVerificationState
from pretalx.person.models import User
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    OrganiserFactory,
    QuestionFactory,
    ReviewScoreCategoryFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TeamInviteFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def get_settings_form_data(event):
    data = {
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
        "header-links-TOTAL_FORMS": 0,
        "header-links-INITIAL_FORMS": 0,
        "header-links-MIN_NUM_FORMS": 0,
        "header-links-MAX_NUM_FORMS": 1000,
        "footer-links-TOTAL_FORMS": 0,
        "footer-links-INITIAL_FORMS": 0,
        "footer-links-MIN_NUM_FORMS": 0,
        "footer-links-MAX_NUM_FORMS": 1000,
    }
    # Reflect every checkbox the form renders so a default POST doesn't
    # silently flip one off.
    for flag, values in (
        ("show_schedule", event.feature_flags),
        ("use_feedback", event.feature_flags),
        ("use_tracks", event.feature_flags),
        ("present_multiple_times", event.feature_flags),
        ("attendee_signup", event.feature_flags),
        ("meta_noindex", event.display_settings),
    ):
        if values.get(flag):
            data[flag] = "on"
    return data


def _update_logs(event):
    with scopes_disabled():
        return ActivityLog.objects.filter(
            event=event, action_type="pretalx.event.update"
        ).order_by("timestamp")


def test_event_detail_denied_without_access(client, event):
    response = client.get(event.orga_urls.settings)
    assert response.status_code == 302
    assert "/login/" in response.url

    client.force_login(UserFactory())
    response = client.get(event.orga_urls.settings)
    assert response.status_code == 404


def test_event_detail_get_and_post(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    old_date_from = event.date_from
    old_date_to = event.date_to

    response = client.get(event.orga_urls.settings)
    assert response.status_code == 200
    assert str(event.name) in response.content.decode()

    response = client.post(
        event.orga_urls.settings, get_settings_form_data(event), follow=True
    )
    assert response.status_code == 200
    assert _update_logs(event).count() == 0
    with scopes_disabled():
        assert event.extra_links.count() == 0

    data = get_settings_form_data(event)
    data["footer-links-TOTAL_FORMS"] = 1
    data["footer-links-0-label"] = "A Link"
    data["footer-links-0-url"] = "not-a-url"
    response = client.post(event.orga_urls.settings, data, follow=True)
    assert response.status_code == 200
    assert _update_logs(event).count() == 0
    with scopes_disabled():
        assert event.extra_links.count() == 0

    data = get_settings_form_data(event)
    data["date_from"] = "2022-10-10"
    data["date_to"] = "2022-10-09"
    response = client.post(event.orga_urls.settings, data, follow=True)
    assert response.status_code == 200
    event.refresh_from_db()
    assert (event.date_from, event.date_to) == (old_date_from, old_date_to)
    assert _update_logs(event).count() == 0

    data = get_settings_form_data(event)
    data["footer-links-TOTAL_FORMS"] = 1
    data["footer-links-0-label_0"] = "Imprint"
    data["footer-links-0-url"] = "https://example.org/imprint"
    response = client.post(event.orga_urls.settings, data, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.extra_links.count() == 1
    assert _update_logs(event).get().data is None

    data = get_settings_form_data(event)
    data["email"] = "newemail@example.com"
    data["meta_noindex"] = "on"
    response = client.post(event.orga_urls.settings, data, follow=True)
    assert response.status_code == 200
    event.refresh_from_db()
    assert event.email == "newemail@example.com"
    with scopes_disabled():
        assert event.extra_links.count() == 1
    log = _update_logs(event).filter(data__isnull=False).get()
    assert log.data["changes"]["email"]["new"] == "newemail@example.com"
    assert log.data["changes"]["display_settings.meta_noindex"] == {
        "old": False,
        "new": True,
    }
    assert "display_settings" not in log.data["changes"]


def test_event_detail_custom_css(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    assert not event.custom_css
    cases = (
        ("src/tests/fixtures/malicious.css", False),
        ("src/tests/conftest.py", False),
        ("src/tests/fixtures/custom.css", True),
    )

    for path, allowed in cases:
        data = get_settings_form_data(event)
        with Path(path).open() as f:
            data["custom_css"] = f
            client.post(event.orga_urls.settings, data, follow=True)
        event.refresh_from_db()
        assert bool(event.custom_css) == allowed, path

    event.custom_css.save("custom.css", ContentFile(b"body {\n  color: red;\n}\n"))
    data = get_settings_form_data(event)
    data["custom_css_text"] = "body {\r\n  color: red;\r\n}"
    data["custom_css-clear"] = "on"
    client.post(event.orga_urls.settings, data, follow=True)
    event.refresh_from_db()
    assert not event.custom_css

    for path, allowed in cases:
        data = get_settings_form_data(event)
        with Path(path).open() as f:
            data["custom_css_text"] = f.read()
        client.post(event.orga_urls.settings, data, follow=True)
        event.refresh_from_db()
        assert bool(event.custom_css) == allowed, path


def test_event_detail_custom_domain(client, event, monkeypatch):
    # Monkeypatch: the form resolves the custom domain and the main domain
    # to compare them, which would make a real network request in tests.
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    def post_domain(domain):
        data = get_settings_form_data(event)
        data["custom_domain"] = domain
        response = client.post(event.orga_urls.settings, data, follow=True)
        assert response.status_code == 200
        event.refresh_from_db()
        return response

    def unavailable(host):
        raise OSError

    def mismatching(host):
        return {"example.org": ("example.org", {"9.9.9.9"})}.get(
            host, (host, {"1.2.3.4"})
        )

    monkeypatch.setattr(event_validators, "_resolve_host", unavailable)
    post_domain("https://example.org")
    assert not event.custom_domain

    monkeypatch.setattr(event_validators, "_resolve_host", mismatching)
    response = post_domain("https://example.org")
    assert event.custom_domain == "https://example.org"
    assert "does not appear to point" in response.content.decode()

    monkeypatch.setattr(
        event_validators, "_resolve_host", lambda host: (host, {"127.0.0.1"})
    )
    for domain, expected in (
        ("example.com", "https://example.com"),
        ("http://example.net", "https://example.net"),
        ("HTTPS://Example.io/", "https://example.io"),
    ):
        post_domain(domain)
        assert event.custom_domain == expected, domain


def test_event_detail_remove_relevant_locales_rejected(client):
    event = EventFactory(
        locales=["en", "de"], content_locales=["en", "de"], locale="de"
    )
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = get_settings_form_data(event)
    data["locales"] = "en"
    data["content_locales"] = "en"
    data["locale"] = "de"

    client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    assert len(event.locales) == 2


def test_event_live_toggle(client):
    event = EventFactory(is_public=False)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    def logged(action):
        with scopes_disabled():
            return ActivityLog.objects.filter(
                event=event, action_type=f"pretalx.event.{action}"
            ).count()

    for action, is_public, activations, deactivations in (
        ("deactivate", False, 0, 0),
        ("activate", True, 1, 0),
        ("activate", True, 1, 0),
        ("deactivate", False, 1, 1),
    ):
        response = client.post(event.orga_urls.live, {"action": action}, follow=True)

        assert response.status_code == 200
        event.refresh_from_db()
        assert event.is_public is is_public
        assert (logged("activate"), logged("deactivate")) == (
            activations,
            deactivations,
        )


def test_event_live_plugin_blocks_activation(client, register_signal_handler):
    event = EventFactory(is_public=False)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    def blocker(signal, sender, **kwargs):
        raise Exception("It's not safe to go alone take this")  # noqa: TRY002 -- intentional generic exception to simulate plugin error

    register_signal_handler(activate_event, blocker)
    response = client.post(event.orga_urls.live, {"action": "activate"}, follow=True)

    assert response.status_code == 200
    event.refresh_from_db()
    assert not event.is_public
    assert "not safe to go alone" in response.content.decode()


def test_event_live_activate_shows_plugin_messages(client, register_signal_handler):
    event = EventFactory(is_public=False, plugins="tests.dummy_app")
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


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_history_query_count(
    client, event, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_event_settings=True)
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        ActivityLogFactory.create_batch(
            item_count,
            event=event,
            person=user,
            content_object=submission,
            action_type="pretalx.submission.update",
        )
    client.force_login(user)
    ContentType.objects.clear_cache()

    with django_assert_num_queries(15):
        response = client.get(event.orga_urls.history)

    assert response.status_code == 200


def test_event_history_with_uninstalled_plugin_model(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    stale_type = ContentType.objects.create(app_label="ghost_plugin", model="ghost")
    with scopes_disabled():
        ActivityLog.objects.create(
            event=event,
            person=user,
            content_type=stale_type,
            object_id=1,
            action_type="pretalx.submission.update",
        )
    client.force_login(user)

    response = client.get(event.orga_urls.history)

    assert response.status_code == 200
    assert str(LOG_NAMES["pretalx.submission.update"]) in response.content.decode()


def test_event_history_pagination(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.history)
    assert response.status_code == 200
    content = response.content.decode()
    assert 'class="pagination' not in content
    assert "Show per page" not in content

    with scopes_disabled():
        ActivityLogFactory(event=event, person=user)

    for page in ("last", "9999", "99999999999999999999"):
        response = client.get(event.orga_urls.history + f"?page={page}")
        assert response.status_code == 404, page


def test_event_history_detail_shows_changes(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    with scopes_disabled():
        question = QuestionFactory(event=event)
        submission = SubmissionFactory(event=event)
        log = submission.log_action(
            "pretalx.submission.update",
            person=user,
            orga=True,
            old_data={"title": "Old Title"},
            new_data={"title": "New Title"},
        )
        key = f"question-{question.pk}"
        question_log = submission.log_action(
            "pretalx.submission.update",
            person=user,
            orga=True,
            old_data={key: "Blue"},
            new_data={key: "Red"},
        )
    client.force_login(user)

    response = client.get(f"/orga/event/{event.slug}/history/{log.pk}/", follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "<del>Old</del> Title" in content
    assert "<ins>New</ins> Title" in content

    response = client.get(
        f"/orga/event/{event.slug}/history/{question_log.pk}/", follow=True
    )
    assert response.status_code == 200
    assert str(question.question) in response.content.decode()


def test_event_history_detail_scoping(client, event):
    with scopes_disabled():
        other_event = EventFactory()
        user = make_orga_user(other_event, can_change_event_settings=True)
        log = ActivityLogFactory(
            event=event,
            person=user,
            content_object=event,
            action_type="pretalx.event.update",
        )
    client.force_login(user)

    url = f"/orga/event/{other_event.slug}/history/{log.pk}/"
    response = client.get(url)

    assert response.status_code == 404


def _build_review_settings_data(event):
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
        "scores-0-is_independent": category.is_independent,
        "scores-0-weight": str(category.weight),
        "scores-0-required": category.required,
        "scores-0-active": category.active,
        "aggregate_method": event.review_settings["aggregate_method"],
        "score_format": event.review_settings["score_format"],
        "review_help_text_0": str(event.settings.review_help_text),
    }
    # Reflect every checkbox the form renders so a default POST doesn't
    # silently flip one off.
    for setting, values in (
        ("use_submission_comments", event.feature_flags),
        ("score_mandatory", event.review_settings),
        ("text_mandatory", event.review_settings),
    ):
        if values[setting]:
            data[setting] = "on"
    for score in scores:
        data[f"scores-0-value_{score.id}"] = score.value
        data[f"scores-0-label_{score.id}"] = score.label or ""
    return data


def test_event_review_settings_post_saves_changes(client, event, monkeypatch):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    default_help_text = serialize_setting_value(
        event.settings.review_help_text, event.locales
    )
    recalc_calls = []
    monkeypatch.setattr(
        "pretalx.orga.views.event.task_recalculate_review_scores.apply_async",
        lambda **kw: recalc_calls.append(kw),
    )

    response = client.post(
        event.orga_urls.review_settings, _build_review_settings_data(event), follow=True
    )
    assert response.status_code == 200
    with scope(event=event):
        assert event.review_phases.count() == 2
        assert event.score_categories.count() == 1
    assert _update_logs(event).get().data is None

    data = _build_review_settings_data(event)
    data["phase-0-name"] = "Renamed Phase"
    data["scores-0-name_0"] = "Renamed Category"
    response = client.post(event.orga_urls.review_settings, data, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.review_phases.filter(name="Renamed Phase").exists()
        assert event.score_categories.filter(name__contains="Renamed Category").exists()
        assert event.score_categories.count() == 1
    assert _update_logs(event).count() == 2
    assert recalc_calls == []

    data = _build_review_settings_data(event)
    data["scores-0-weight"] = "5"
    response = client.post(event.orga_urls.review_settings, data, follow=True)
    assert response.status_code == 200
    assert [call["kwargs"] for call in recalc_calls] == [{"event_id": event.pk}]
    with scope(event=event):
        assert event.score_categories.get().weight == 5

    data = _build_review_settings_data(event)
    data["aggregate_method"] = "mean"
    data["review_help_text_0"] = "Be nice"
    del data["use_submission_comments"]
    response = client.post(event.orga_urls.review_settings, data, follow=True)
    assert response.status_code == 200
    changes = _update_logs(event).last().data["changes"]
    assert changes["review_settings.aggregate_method"] == {
        "old": "median",
        "new": "mean",
    }
    assert changes["feature_flags.use_submission_comments"] == {
        "old": True,
        "new": False,
    }
    assert changes["settings.review_help_text"] == {
        "old": default_help_text,
        "new": {"en": "Be nice"},
    }


def test_event_review_settings_add_phase(client, event):
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
    with scope(event=event):
        assert event.review_phases.count() == 3
        assert event.review_phases.filter(name="New Phase").exists()


def test_event_review_settings_delete_phase(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    data = _build_review_settings_data(event)
    with scope(event=event):
        other_phase = event.review_phases.exclude(
            pk=event.active_review_phase.pk
        ).first()
    data["phase-1-DELETE"] = "on"
    data["phase-0-end"] = ""

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    with scope(event=event):
        assert event.review_phases.count() == 1
        assert not event.review_phases.filter(pk=other_phase.pk).exists()


def test_event_review_settings_score_categories(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scopes_disabled():
        extra_cat = ReviewScoreCategoryFactory(event=event, is_independent=True)

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
    with scope(event=event):
        assert event.score_categories.count() == 1
        assert not event.score_categories.filter(pk=extra_cat.pk).exists()

    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-1-name_0"] = "Ephemeral Category"
    data["scores-1-weight"] = "1"
    data["scores-1-DELETE"] = "on"
    response = client.post(event.orga_urls.review_settings, data, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.score_categories.count() == 1

    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-1-name_0"] = "New Category"
    data["scores-1-weight"] = "1"
    response = client.post(event.orga_urls.review_settings, data, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.score_categories.count() == 2
        new_cat = event.score_categories.get(name__contains="New Category")

    data = _build_review_settings_data(event)
    data["scores-TOTAL_FORMS"] = "2"
    data["scores-INITIAL_FORMS"] = "2"
    data["scores-1-name_0"] = "New Category"
    data["scores-1-id"] = new_cat.id
    data["scores-1-weight"] = "1"
    data["scores-1-DELETE"] = "on"
    response = client.post(event.orga_urls.review_settings, data, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert event.score_categories.count() == 1
        assert not event.score_categories.filter(pk=new_cat.pk).exists()


@pytest.mark.parametrize(
    ("overrides", "error"),
    (
        ({"phase-0-start": "lalala"}, "Enter a valid date/time."),
        (
            {"phase-0-name": "Should Not Save", "phase-0-can_tag_submissions": "hahah"},
            "Select a valid choice.",
        ),
        (
            {
                "phase-TOTAL_FORMS": 3,
                "phase-0-end": "",
                "phase-1-start": "",
                "phase-1-end": "",
                "phase-2-name": "New Phase",
                "phase-2-start": now().strftime("%Y-%m-%d"),
                "phase-2-end": (now() - dt.timedelta(days=7)).strftime("%Y-%m-%d"),
                "phase-2-can_see_other_reviews": "always",
                "phase-2-can_tag_submissions": "use_tags",
                "phase-2-proposal_visibility": "all",
            },
            "The end of a phase has to be after its start.",
        ),
        (
            {
                "phase-0-end": "",
                "phase-1-start": "2000-02-01 12:00:00",
                "phase-1-end": "2000-02-02 12:00:00",
            },
            "Only the last review phase may be open-ended.",
        ),
        (
            {
                "phase-0-end": "2000-01-01 12:00:00",
                "phase-1-start": "",
                "phase-1-end": "2000-02-02 12:00:00",
            },
            "All review phases except for the first one need a start date.",
        ),
        (
            {
                "phase-0-end": "2000-03-01 12:00:00",
                "phase-1-start": "2000-01-01 12:00:00",
                "phase-1-end": "2000-04-01 12:00:00",
            },
            "Please make sure that review phases do not overlap, then save again.",
        ),
    ),
    ids=(
        "invalid_phase_date",
        "invalid_can_tag",
        "phase_end_before_start",
        "open_ended_non_last_phase",
        "missing_start_non_first_phase",
        "overlapping_phases",
    ),
)
def test_event_review_settings_invalid_phases_rejected(client, event, overrides, error):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scope(event=event):
        phases = {
            (phase.pk, phase.name, phase.start, phase.end)
            for phase in event.review_phases.all()
        }
    data = _build_review_settings_data(event)
    data.update(overrides)

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    assert error in response.content.decode()
    with scope(event=event):
        assert {
            (phase.pk, phase.name, phase.start, phase.end)
            for phase in event.review_phases.all()
        } == phases


@pytest.mark.parametrize(
    ("overrides", "error"),
    (
        ({"scores-0-name_0": "", "scores-0-weight": "not-a-number"}, "Enter a number."),
        (
            {"scores-0-is_independent": "on"},
            "You need to keep at least one non-independent score category!",
        ),
    ),
    ids=("invalid_scores_formset", "only_independent_category"),
)
def test_event_review_settings_invalid_scores_rejected(client, event, overrides, error):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scope(event=event):
        category = event.score_categories.get()
        category_state = (category.name, category.weight, category.is_independent)
    data = _build_review_settings_data(event)
    data.update(overrides)

    response = client.post(event.orga_urls.review_settings, data, follow=True)

    assert response.status_code == 200
    assert error in response.content.decode()
    with scope(event=event):
        category = event.score_categories.get()
        assert (category.name, category.weight, category.is_independent) == (
            category_state
        )


def test_phase_activate_and_deactivate(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scope(event=event):
        phase = event.active_review_phase
        other_phase = event.review_phases.exclude(pk=phase.pk).first()

    response = client.post(other_phase.urls.activate, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert Event.objects.get(pk=event.pk).active_review_phase == other_phase

    response = client.post(other_phase.urls.activate, follow=True)
    assert response.status_code == 200
    with scope(event=event):
        assert Event.objects.get(pk=event.pk).active_review_phase is None
        assert not event.review_phases.filter(is_active=True).exists()


def test_event_mail_settings(client, event, monkeypatch):
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
    with scopes_disabled():
        assert (
            Event.objects.get(pk=event.pk).mail_settings["mail_from"] != "foo@bar.com"
        )

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "foo@bar.com",
            "smtp_host": "localhost",
            "smtp_password": "hunter2",
            "smtp_port": "25",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        mail_settings = Event.objects.get(pk=event.pk).mail_settings
    assert mail_settings["mail_from"] == "foo@bar.com"
    assert mail_settings["smtp_port"] == 25
    log = _update_logs(event).latest("timestamp")
    assert log.data["changes"]["mail_settings.mail_from"] == {
        "old": "",
        "new": "foo@bar.com",
    }
    assert "mail_settings.smtp_password" not in log.data["changes"]

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
    with scopes_disabled():
        assert (
            Event.objects.get(pk=event.pk).mail_settings["mail_from"]
            == "test@example.com"
        )

    monkeypatch.setattr(CustomSMTPBackend, "test", lambda self, from_addr: None)
    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "custom@example.com",
            "smtp_host": "localhost",
            "smtp_password": "",
            "smtp_port": "25",
            "smtp_use_custom": "1",
            "test": "1",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert (
            Event.objects.get(pk=event.pk).mail_settings["mail_from"]
            == "custom@example.com"
        )
    content = response.content.decode()
    assert "connection attempt" in content.lower() or "successful" in content.lower()

    response = client.post(
        event.orga_urls.mail_settings,
        {
            "mail_from": "default@example.com",
            "smtp_host": "localhost",
            "smtp_password": "",
            "smtp_port": "25",
            "test": "1",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert (
            Event.objects.get(pk=event.pk).mail_settings["mail_from"]
            == "default@example.com"
        )
    content = response.content.decode()
    assert "checkbox" in content.lower() or "contact" in content.lower()


def test_event_mail_settings_test_smtp_crash_keeps_saved_settings(
    client, event, monkeypatch
):
    def explode(self, from_addr):
        raise ValueError("boom")

    monkeypatch.setattr(CustomSMTPBackend, "test", explode)
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    with pytest.raises(ValueError, match="boom"):
        client.post(
            event.orga_urls.mail_settings,
            {
                "mail_from": "test@example.com",
                "smtp_host": "localhost",
                "smtp_password": "",
                "smtp_port": "25",
                "test": "1",
            },
        )

    event = Event.objects.get(pk=event.pk)
    assert event.mail_settings["mail_from"] == "test@example.com"


@pytest.mark.parametrize(
    ("state", "expected_promote_logs"),
    ((EmailVerificationState.VERIFIED, 0), (EmailVerificationState.LEGACY, 1)),
    ids=("already_verified", "legacy_promotes"),
)
def test_invitation_view_accept_via_inline_login_promotes_without_mail(
    client, event, state, expected_promote_logs
):
    with scopes_disabled():
        user = UserFactory(password="testpassword!", email_verification_state=state)
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email=user.email.upper())
    initial_count = team.members.count()
    djmail.outbox = []

    response = client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}),
        {"login_email": user.email, "login_password": "testpassword!"},
        follow=True,
    )

    assert response.status_code == 200
    assert team.members.count() == initial_count + 1
    assert team.members.filter(pk=user.pk).exists()
    assert team.invites.count() == 0
    assert djmail.outbox == []
    user.refresh_from_db()
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    with scopes_disabled():
        assert (
            actions_by(user)
            .filter(action_type="pretalx.user.email.verification.promote")
            .count()
            == expected_promote_logs
        )


def test_invitation_view_register(client, event):
    with scopes_disabled():
        existing_user = UserFactory()
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="Match@Example.COM")
    initial_count = team.members.count()
    djmail.outbox = []
    url = reverse("orga:invitation.view", kwargs={"code": invite.token})

    response = client.get(
        reverse("orga:invitation.view", kwargs={"code": "invalidtoken123"})
    )
    assert response.status_code == 404

    for data in (
        {
            "register_name": "Fail User",
            "register_email": invite.email,
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!WRONG",
        },
        {
            "register_email": existing_user.email,
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!",
        },
        {
            "register_email": invite.email,
            "register_password": "password",
            "register_password_repeat": "password",
        },
    ):
        response = client.post(url, data, follow=True)
        assert response.status_code == 200
        assert team.members.count() == initial_count
        assert team.invites.count() == 1

    response = client.post(
        url,
        {
            "register_name": "Matching User",
            "register_email": "match@example.com",
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!",
        },
        follow=True,
    )
    assert response.status_code == 200
    user = User.objects.get(email="match@example.com")
    assert user.email_verification_state == EmailVerificationState.VERIFIED
    assert team.members.count() == initial_count + 1
    assert team.members.filter(pk=user.pk).exists()
    assert team.invites.count() == 0
    assert djmail.outbox == []
    with scopes_disabled():
        assert (
            actions_by(user)
            .filter(action_type="pretalx.user.email.verification.promote")
            .count()
            == 1
        )

    response = client.get(url)
    assert response.status_code == 404


def test_invitation_view_register_mismatched_address_sends_verification_mail(
    client, event
):
    with scopes_disabled():
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email="invited@example.com")
    djmail.outbox = []

    client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}),
        {
            "register_name": "Other User",
            "register_email": "other@example.com",
            "register_password": "f00baar!",
            "register_password_repeat": "f00baar!",
        },
        follow=True,
    )

    user = User.objects.get(email="other@example.com")
    assert user.email_verification_state == EmailVerificationState.UNVERIFIED
    assert team.members.filter(pk=user.pk).exists()
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["other@example.com"]


@pytest.mark.parametrize(
    ("invite_email", "expected_state"),
    (
        ("member@example.com", EmailVerificationState.VERIFIED),
        ("someone-else@example.com", EmailVerificationState.LEGACY),
    ),
    ids=("match_promotes", "mismatch_keeps_state"),
)
def test_invitation_view_logged_in_user_promotes_only_on_match(
    client, event, invite_email, expected_state
):
    with scopes_disabled():
        user = UserFactory(
            email="member@example.com",
            email_verification_state=EmailVerificationState.LEGACY,
        )
        team = TeamFactory(organiser=event.organiser, all_events=True)
        invite = TeamInviteFactory(team=team, email=invite_email)
    initial_count = team.members.count()
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        reverse("orga:invitation.view", kwargs={"code": invite.token}), follow=True
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email_verification_state == expected_state
    assert team.members.count() == initial_count + 1
    assert team.members.filter(pk=user.pk).exists()
    assert team.invites.count() == 0
    assert djmail.outbox == []


def test_event_delete_by_admin(client, event):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    event_pk = event.pk

    response = client.get(event.orga_urls.delete)
    assert response.status_code == 200
    content = response.content.decode()
    assert f"Event: {event.name}" in content
    assert f'href="{event.orga_urls.settings}"' in content

    response = client.post(event.orga_urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert not Event.objects.filter(pk=event_pk).exists()


def test_event_delete_non_admin_gets_404(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.delete, follow=True)

    assert response.status_code == 404
    assert Event.objects.filter(pk=event.pk).exists()


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


def test_event_detail_change_date_and_timezone_shift_slots(
    client, event, published_talk_slot
):
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

    event.refresh_from_db()
    data = get_settings_form_data(event)
    data["timezone"] = "Europe/Moscow"
    response = client.post(event.orga_urls.settings, data, follow=True)
    assert response.status_code == 200
    talk_slot.refresh_from_db()
    assert talk_slot.start != old_released_start


def test_event_detail_post_enables_attendee_signup(client, event):
    user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)
    with scope(event=event):
        track = TrackFactory(event=event)
        submission_type = SubmissionTypeFactory(event=event)

    data = get_settings_form_data(event)
    data["attendee_signup"] = "on"
    data["signup_domains"] = "Company.Example,partner.example"
    data["attendee_signup_tracks"] = [track.pk]
    data["attendee_signup_types"] = [submission_type.pk]

    client.post(event.orga_urls.settings, data, follow=True)

    event.refresh_from_db()
    track.refresh_from_db()
    submission_type.refresh_from_db()
    assert event.feature_flags["attendee_signup"] is True
    assert event.attendee_signup_settings == {
        "signup_domains": ["company.example", "partner.example"]
    }
    assert track.attendee_signup_required is True
    assert submission_type.attendee_signup_required is True


def test_event_review_settings_page(client, event):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=True
    )
    with scopes_disabled():
        reviewer_question = QuestionFactory(event=event, target="reviewer")
        session_question = QuestionFactory(event=event, target="submission")
    client.force_login(user)

    response = client.get(event.orga_urls.review_settings)
    assert response.status_code == 200
    content = response.content.decode()
    assert re.findall(r'<input\s+role="tab"[^>]*id="tab-([a-z]+)"', content) == [
        "general",
        "scores",
        "phases",
        "questions",
    ]
    assert '<a role="tab"' not in content
    assert 'id="tabpanel-questions"' in content
    assert str(reviewer_question.question) in content
    assert str(session_question.question) not in content
    assert event.cfp.urls.new_reviewer_question in content

    response = client.get(
        event.orga_urls.review_settings,
        headers={
            "HX-Request": "true",
            "HX-Target": "table-content-QuestionTable-reviews",
        },
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert str(reviewer_question.question) in content
    assert "tabpanel-questions" not in content
    assert response["HX-Push-Url"] == event.orga_urls.review_settings


def test_event_review_settings_reviewer_panel_visible_without_submission_access(
    client, event
):
    user = make_orga_user(
        event, can_change_event_settings=True, can_change_submissions=False
    )
    with scopes_disabled():
        reviewer_question = QuestionFactory(event=event, target="reviewer")
    client.force_login(user)

    response = client.get(event.orga_urls.review_settings)

    assert response.status_code == 200
    content = response.content.decode()
    assert str(reviewer_question.question) in content
    # Without access to responses, the field links to its edit page, not to
    # the detail page that shows answers.
    assert reviewer_question.urls.edit in content
    assert f'href="{reviewer_question.urls.base}"' not in content


def test_event_review_settings_denied_without_settings_permission(client, event):
    user = make_orga_user(
        event, can_change_event_settings=False, can_change_submissions=True
    )
    with scopes_disabled():
        QuestionFactory(event=event, target="reviewer")
    client.force_login(user)

    response = client.get(event.orga_urls.review_settings)

    assert response.status_code == 404


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_review_settings_reviewer_panel_query_count(
    client, event, item_count, django_assert_num_queries
):
    user = make_orga_user(event, can_change_event_settings=True)
    with scopes_disabled():
        for _index in range(item_count):
            QuestionFactory(event=event, target="reviewer")
    client.force_login(user)

    with django_assert_num_queries(21):
        response = client.get(event.orga_urls.review_settings)

    assert response.status_code == 200


def test_event_wizard_shows_organiser_step_when_there_is_something_to_copy(client):
    with scopes_disabled():
        event = EventFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=event.organiser,
            can_create_events=True,
            can_change_event_settings=True,
            all_events=True,
        )
        team.members.add(user)
    client.force_login(user)

    response = client.get("/orga/event/new/")

    assert response.status_code == 200
    assert list(response.context["form"].fields) == ["organiser", "copy_from_event"]


def test_event_wizard_skips_organiser_step_when_nothing_to_decide(client):
    with scopes_disabled():
        organiser = OrganiserFactory()
        user = UserFactory()
        team = TeamFactory(
            organiser=organiser,
            can_create_events=True,
            can_change_event_settings=True,
            all_events=True,
        )
        team.members.add(user)
        foreign_event = EventFactory()
        foreign_team = TeamFactory(
            organiser=foreign_event.organiser,
            can_change_event_settings=True,
            all_events=True,
        )
        foreign_team.members.add(user)
    client.force_login(user)

    response = client.get("/orga/event/new/")

    assert response.status_code == 200
    assert list(response.context["form"].fields) == ["locales", "locale", "timezone"]


def test_event_wizard_denies_access_without_any_organiser(client):
    user = UserFactory(is_administrator=True)
    client.force_login(user)

    response = client.get("/orga/event/new/")

    assert response.status_code == 403


def test_event_wizard_denies_access_without_event_creation_permission(client):
    with scopes_disabled():
        OrganiserFactory()
        user = UserFactory()
    client.force_login(user)

    response = client.get("/orga/event/new/")

    assert response.status_code == 404


def test_event_wizard_copy_choices_follow_the_chosen_organiser(client):
    with scopes_disabled():
        user = UserFactory(is_administrator=True)
        first_event = EventFactory()
        second_event = EventFactory()
        empty_organiser = OrganiserFactory()
    client.force_login(user)

    response = client.post(
        reverse("orga:event.create.copy_choices"),
        {"organiser-organiser": second_event.organiser.pk},
    )
    assert response.status_code == 200
    field = response.context["form"].fields["copy_from_event"]
    assert list(field.queryset) == [second_event]

    response = client.post(
        reverse("orga:event.create.copy_choices"), {"organiser-organiser": "not-a-pk"}
    )
    assert response.status_code == 200
    field = response.context["form"].fields["copy_from_event"]
    assert list(field.queryset) == [first_event]

    response = client.post(
        reverse("orga:event.create.copy_choices"),
        {"organiser-organiser": empty_organiser.pk},
    )
    assert response.status_code == 200
    assert "copy_from_event" not in response.context["form"].fields
