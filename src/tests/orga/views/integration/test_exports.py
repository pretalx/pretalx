# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
from collections import defaultdict

import pytest
from bs4 import BeautifulSoup
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog, CachedFile
from pretalx.common.models.exports import TableExport
from pretalx.orga.views.exports import AdhocTableExportRun
from pretalx.submission.enums import SubmissionStates
from tests.factories import (
    CachedFileFactory,
    EventFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TableExportFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _reviewer(event):
    return make_orga_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_organiser_settings=False,
    )


def _content(response):
    return b"".join(response.streaming_content).decode("utf-8-sig")


def _browser_payload(html, form_id):
    form = BeautifulSoup(html, "lxml").find("form", id=form_id)
    data = defaultdict(list)
    for field in form.find_all(("input", "select", "textarea")):
        name = field.get("name")
        if (
            not name
            or field.has_attr("disabled")
            or field.get("type") in ("submit", "button")
        ):
            continue
        if field.name == "select":
            data[name].extend(
                option.get("value", option.get_text())
                for option in field.find_all("option")
                if option.has_attr("selected")
            )
        elif field.get("type") in ("checkbox", "radio"):
            if field.has_attr("checked"):
                data[name].append(field.get("value", "on"))
        else:
            data[name].append(field.get("value", ""))
    return dict(data)


def test_table_export_list_requires_settings_permission(client, event):
    with scopes_disabled():
        export = TableExportFactory(event=event, name="Talks")
        TableExportFactory(event=event, name="Old", table="GoneTable")
        TableExportFactory(name="Other event")
        orga = make_orga_user(event, can_change_event_settings=True)
        reviewer = _reviewer(event)

    client.force_login(reviewer)
    assert client.get(event.orga_urls.exports).status_code == 404

    client.force_login(orga)
    response = client.get(event.orga_urls.exports)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Talks" in content
    assert "Old" not in content
    assert "Other event" not in content
    assert export.urls.run in content
    assert event.orga_urls.more_exports in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_table_export_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        for _ in range(item_count):
            TableExportFactory(event=event)
        orga = make_orga_user(event, can_change_event_settings=True)
    client.force_login(orga)

    with django_assert_num_queries(14):
        response = client.get(event.orga_urls.exports)

    assert response.status_code == 200


def test_table_export_create_picks_table_first(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
    client.force_login(orga)

    response = client.get(event.orga_urls.new_export)

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="table"' in content
    assert 'value="ReviewExportTable"' in content
    assert 'value="SubmissionTable"' in content
    assert 'value="TeamTable"' not in content


def test_table_export_create_from_scratch(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    client.force_login(orga)

    form_response = client.get(event.orga_urls.new_export + "?table=SubmissionTable")
    response = client.post(
        event.orga_urls.new_export + "?table=SubmissionTable",
        data={
            "name": "Accepted talks",
            "columns": ["title", "abstract"],
            "ordering": ["-title"],
            "state": ["accepted"],
            "serializer": "csv",
            "csv_list_delimiter": "comma",
        },
    )

    assert form_response.status_code == 200
    assert 'data-column="abstract"' in form_response.content.decode()
    assert response.status_code == 302
    assert response.url == event.orga_urls.exports
    with scopes_disabled():
        export = TableExport.objects.select_related("event").get(event=event)
        assert export.name == "Accepted talks"
        assert export.columns == ["title", "abstract"]
        assert export.ordering == ["-title"]
        assert export.filters == {"state": ["accepted"]}
        assert export.serializer_options == {"delimiter": "", "list_delimiter": "comma"}
        assert ActivityLog.objects.filter(
            action_type="pretalx.table_export.create", object_id=export.pk
        ).exists()

    run = client.get(export.urls.run)

    assert run.status_code == 200
    assert run["Content-Type"] == "text/csv"
    assert (
        _content(run) == f"ID,Title,Abstract\r\n{accepted.code},{accepted.title},\r\n"
    )


def test_table_export_create_for_view_less_review_table(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        submission = SubmissionFactory(event=event, title="Reviewed")
        reviewer = _reviewer(event)
        review = ReviewFactory(submission=submission, user=reviewer, score=2)
    client.force_login(orga)

    response = client.post(
        event.orga_urls.new_export + "?table=ReviewExportTable",
        data={
            "name": "Reviews",
            "columns": ["submission_title", "score", "user_name"],
            "serializer": "json",
        },
    )

    assert response.status_code == 302
    with scopes_disabled():
        export = TableExport.objects.select_related("event").get(event=event)
    run = client.get(export.urls.run)

    assert json.loads(_content(run)) == [
        {
            "ID": review.pk,
            "submission_title": "Reviewed",
            "score": 2.0,
            "user_name": reviewer.name,
        }
    ]


def test_table_export_create_needs_a_usable_table(client, event):
    with scopes_disabled():
        orga = make_orga_user(
            event, can_change_event_settings=True, can_change_submissions=False
        )
    client.force_login(orga)

    unpermitted = client.get(event.orga_urls.new_export + "?table=SubmissionTable")
    without_table = client.post(event.orga_urls.new_export, data={"name": "x"})
    planted = client.post(
        event.orga_urls.new_export + "?table=SubmissionTable",
        data={"name": "Planted", "serializer": "csv"},
    )

    assert unpermitted.status_code == 404
    assert planted.status_code == 404
    with scopes_disabled():
        assert not TableExport.objects.filter(name="Planted").exists()
    assert without_table.status_code == 302
    assert without_table.url == event.orga_urls.new_export


def test_table_export_update_covers_full_configuration(client, event):
    event.locales = ["en", "de"]
    event.save()
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        export = TableExportFactory(event=event, name="Before", columns=["title"])
    client.force_login(orga)

    form_response = client.get(export.urls.edit)
    response = client.post(
        export.urls.edit,
        data={
            "name": "After",
            "columns": ["state", "title"],
            "ordering": ["state"],
            "state": ["rejected"],
            "serializer": "json",
        },
    )

    assert form_response.status_code == 200
    assert response.status_code == 302
    with scopes_disabled():
        export.refresh_from_db()
        assert export.name == "After"
        assert export.columns == ["state", "title"]
        assert export.ordering == ["state"]
        assert export.filters == {"state": ["rejected"]}
        assert export.serializer == "json"
        assert export.serializer_options == {}
        log = ActivityLog.objects.get(
            action_type="pretalx.table_export.update", object_id=export.pk
        )
        assert log.data["changes"]["name"] == {"old": "Before", "new": "After"}


@pytest.mark.parametrize(
    ("filters", "titles"),
    (
        ({}, ["Active", "Rejected"]),
        ({"state": ["confirmed"]}, []),
        ({"state": ["rejected"]}, ["Rejected"]),
    ),
    ids=("unfiltered", "filter_without_rows", "filter_with_rows"),
)
def test_table_export_editor_no_op_save_keeps_the_row_set(
    client, event, filters, titles
):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        SubmissionFactory(event=event, title="Active", state=SubmissionStates.SUBMITTED)
        SubmissionFactory(
            event=event, title="Rejected", state=SubmissionStates.REJECTED
        )
        export = TableExportFactory(
            event=event, name="Report", columns=["title"], filters=filters
        )
    client.force_login(orga)
    before = _content(client.get(export.urls.run))

    form_page = client.get(export.urls.edit)
    response = client.post(
        export.urls.edit,
        data=_browser_payload(form_page.content.decode(), "table-export-form"),
    )

    assert response.status_code == 302, response.context["form"].errors
    after = _content(client.get(export.urls.run))
    assert after == before
    assert sorted(row.split(",")[1] for row in after.splitlines()[1:]) == titles


def test_table_export_stale_run_redirects_with_message(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        export = TableExportFactory(event=event, table="GoneTable")
    client.force_login(orga)

    assert client.get(export.urls.edit).status_code == 404
    assert client.get(export.urls.delete).status_code == 404
    response = client.get(export.urls.run)

    assert response.status_code == 302
    assert response.url == event.orga_urls.exports
    messages = list(get_messages(response.wsgi_request))
    assert [message.level for message in messages] == [message_constants.ERROR]


def test_table_export_delete(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        export = TableExportFactory(event=event)
    client.force_login(orga)

    confirm = client.get(export.urls.delete)
    response = client.post(export.urls.delete)

    assert confirm.status_code == 200
    assert response.status_code == 302
    with scopes_disabled():
        assert not TableExport.objects.filter(pk=export.pk).exists()
        assert ActivityLog.objects.filter(
            action_type="pretalx.table_export.delete", event=event
        ).exists()


def test_table_export_run_uses_runner_permissions(client, event):
    with scopes_disabled():
        admin = make_orga_user(event, can_change_event_settings=True)
        limited = make_orga_user(
            event,
            can_change_event_settings=True,
            can_change_submissions=False,
            is_reviewer=True,
        )
        SubmissionFactory(event=event, title="Talk")
        export = TableExportFactory(event=event, columns=["title", "internal_notes"])
    client.force_login(admin)
    admin_response = client.get(export.urls.run)
    client.force_login(limited)
    limited_response = client.get(export.urls.run)

    assert _content(admin_response).splitlines()[0] == "ID,Title,Internal notes"
    assert _content(limited_response).splitlines()[0] == "ID,Title"


def test_table_export_list_hides_tables_the_user_may_not_see(client, event):
    with scopes_disabled():
        limited = make_orga_user(
            event, can_change_event_settings=True, can_change_submissions=False
        )
        mail_dump = TableExportFactory(
            event=event, name="Mail queue dump", table="OutboxMailTable"
        )
        TableExportFactory(event=event, name="Vanished report", table="GoneTable")
    client.force_login(limited)

    response = client.get(event.orga_urls.exports)

    content = response.content.decode()
    assert "Mail queue dump" not in content
    assert "Vanished report" not in content
    assert client.get(mail_dump.urls.run).status_code == 404


def test_table_export_run_from_toolbar(client, event):
    with scopes_disabled():
        reviewer = _reviewer(event)
        speaker = SpeakerFactory(event=event, name="Ada")
        accepted = SubmissionFactory(
            event=event, title="Accepted", state=SubmissionStates.ACCEPTED
        )
        accepted.speakers.add(speaker)
        SubmissionFactory(
            event=event, title="Rejected", state=SubmissionStates.REJECTED
        )
    client.force_login(reviewer)

    response = client.post(
        event.orga_urls.export_run,
        data={
            "table": "ReviewTable",
            "filters": "state=accepted&sort=-title",
            "columns": ["title", "speakers"],
            "serializer": "csv",
            "csv_list_delimiter": "comma",
            "save": "on",
            "name": "Mine",
        },
    )

    as_json = client.post(
        event.orga_urls.export_run,
        data={
            "table": "ReviewTable",
            "filters": "state=accepted",
            "columns": ["title", "speakers"],
            "serializer": "json",
        },
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert (
        _content(response) == f"ID,Title,Speakers\r\n{accepted.code},Accepted,Ada\r\n"
    )
    assert as_json["Content-Type"] == "application/json"
    assert json.loads(_content(as_json)) == [
        {"ID": accepted.code, "title": "Accepted", "speakers": ["Ada"]}
    ]
    with scopes_disabled():
        assert not TableExport.objects.exists()


def test_table_export_save_from_toolbar_creates_new_export_each_time(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
    client.force_login(orga)
    data = {
        "table": "SubmissionTable",
        "filters": "state=accepted",
        "columns": ["title"],
        "serializer": "csv",
        "csv_list_delimiter": "newline",
        "save": "1",
        "name": "Accepted",
        "next": event.orga_urls.submissions,
    }

    first = client.post(event.orga_urls.export_run, data=data)
    second = client.post(
        event.orga_urls.export_run, data={**data, "columns": ["title", "state"]}
    )

    assert first.status_code == 302
    assert first.url == event.orga_urls.exports
    assert second.status_code == 302
    with scopes_disabled():
        exports = list(TableExport.objects.filter(event=event).order_by("pk"))
        assert [export.name for export in exports] == ["Accepted", "Accepted"]
        assert [export.columns for export in exports] == [["title"], ["title", "state"]]
        assert exports[0].filters == {"state": ["accepted"]}
        actions = list(
            ActivityLog.objects.filter(
                object_id__in=[export.pk for export in exports]
            ).values_list("action_type", flat=True)
        )
    assert actions == ["pretalx.table_export.create", "pretalx.table_export.create"]


@pytest.mark.parametrize(
    "data",
    ({"table": "OutboxMailTable"}, {"table": "NoSuchTable"}),
    ids=("unpermitted_table", "unknown_table"),
)
def test_table_export_run_404s_without_permission(client, event, data):
    with scopes_disabled():
        reviewer = _reviewer(event)
    client.force_login(reviewer)

    response = client.post(
        event.orga_urls.export_run, data={"serializer": "csv", **data}
    )

    assert response.status_code == 404
    with scopes_disabled():
        assert not TableExport.objects.exists()


@pytest.mark.parametrize(
    ("next_url", "target"),
    (("{submissions}", "submissions"), ("https://evil.example/", "base")),
    ids=("own_page", "foreign_host"),
)
def test_table_export_run_invalid_form_redirects_back_with_error(
    client, event, next_url, target
):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_submissions=True)
    client.force_login(orga)

    response = client.post(
        event.orga_urls.export_run,
        data={
            "table": "SubmissionTable",
            "serializer": "xml",
            "next": next_url.format(submissions=event.orga_urls.submissions),
        },
    )

    assert response.status_code == 302
    assert response.url == getattr(event.orga_urls, target)
    messages = list(get_messages(response.wsgi_request))
    assert [message.level for message in messages] == [message_constants.ERROR]


def test_table_export_run_get_without_task_redirects(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        reviewer = _reviewer(event)
    client.force_login(orga)
    orga_response = client.get(event.orga_urls.export_run)
    client.force_login(reviewer)
    reviewer_response = client.get(event.orga_urls.export_run)

    assert orga_response.status_code == 302
    assert orga_response.url == event.orga_urls.exports
    assert reviewer_response.status_code == 302
    assert reviewer_response.url == event.orga_urls.base


def test_table_export_run_polls_cached_file(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_submissions=True)
    client.force_login(orga)
    salt = f"{AdhocTableExportRun.__module__}.{AdhocTableExportRun.__qualname__}"
    with scopes_disabled():
        cached_file = CachedFileFactory(
            filename="talks.csv",
            content_type="text/csv",
            session_key=f"{client.session.session_key}!{salt}",
        )
        cached_file.file.save("talks.csv", ContentFile(b"ID,Title\r\n"))

    response = client.get(f"{event.orga_urls.export_run}?cached_file={cached_file.id}")

    assert response.status_code == 200
    assert _content(response) == "ID,Title\r\n"


def test_list_views_offer_export_control_by_permission(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        reviewer = _reviewer(event)
    client.force_login(orga)
    orga_pages = {
        url_attr: client.get(getattr(event.orga_urls, url_attr)).content.decode()
        for url_attr in ("submissions", "speakers", "reviews", "outbox", "feedback")
    }
    client.force_login(reviewer)
    reviewer_content = client.get(event.orga_urls.reviews).content.decode()

    assert all("table-export-form" in content for content in orga_pages.values())
    orga_content = orga_pages["submissions"]
    assert 'data-column="abstract"' in orga_content
    assert "export-save" in orga_content
    assert f'href="{event.orga_urls.exports}"' in orga_content
    assert event.orga_urls.more_exports not in orga_content
    assert "Export reviews" not in orga_content
    assert "speakers/export/" not in orga_content
    assert "table-export-form" in reviewer_content
    assert 'data-column="duration"' in reviewer_content
    assert 'data-column="internal_notes"' not in reviewer_content
    assert "export-save" not in reviewer_content
    assert event.orga_urls.more_exports not in reviewer_content
    assert f'href="{event.orga_urls.exports}"' not in reviewer_content
    assert f'href="{event.orga_urls.stats}"' in reviewer_content


def test_export_control_absent_on_per_object_and_non_event_tables(client, event):
    with scopes_disabled():
        orga = make_orga_user(
            event, can_change_event_settings=True, can_change_teams=True
        )
        submission = SubmissionFactory(event=event)
        submission.speakers.add(SpeakerFactory(event=event))
    client.force_login(orga)
    teams_url = reverse(
        "orga:organiser.teams.list", kwargs={"organiser": event.organiser.slug}
    )

    feedback = client.get(submission.orga_urls.feedback, follow=True)
    teams = client.get(teams_url)

    assert feedback.status_code == 200
    assert "table-export-form" not in feedback.content.decode()
    assert teams.status_code == 200
    assert "table-export-form" not in teams.content.decode()


def test_old_export_urls_are_gone(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
    client.force_login(orga)

    statuses = [
        client.get(event.orga_urls.base + path).status_code
        for path in ("speakers/export/", "reviews/export/", "schedule/export/")
    ]

    assert statuses == [404, 404, 404]


def test_more_exports_page_lists_exporters(client, event):
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
    client.force_login(orga)

    response = client.get(event.orga_urls.more_exports)

    assert response.status_code == 200
    content = response.content.decode()
    assert "XML (frab compatible)" in content
    assert "schedule/export/schedule.xml" not in content
    assert "schedule/export/speakers.csv" in content
    assert event.orga_urls.html_export_trigger in content
    assert event.orga_urls.exports in content
    assert "first released schedule version" in content
    assert "Authorization: Token" not in content


def test_html_export_trigger_drops_cached_file(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    without_file = client.post(event.orga_urls.html_export_trigger)
    with scopes_disabled():
        cached_file = CachedFileFactory()
        event.cache.set("schedule_export_cached_file", str(cached_file.id), None)
    response = client.post(event.orga_urls.html_export_trigger)

    assert without_file.status_code == 302
    assert without_file.url == event.orga_urls.html_export_download
    assert response.status_code == 302
    assert response.url == event.orga_urls.html_export_download
    with scopes_disabled():
        assert not CachedFile.objects.filter(id=cached_file.id).exists()
        assert event.cache.get("schedule_export_cached_file") is None


def test_html_export_download_after_release(client, published_talk_slot):
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    more_exports = client.get(event.orga_urls.more_exports).content.decode()
    unknown = client.get(
        event.orga_urls.html_export_download, data={"cached_file": "nonexistent"}
    )
    response = client.get(event.orga_urls.html_export_download, follow=True)
    with scopes_disabled():
        filenames = list(CachedFile.objects.values_list("filename", flat=True))
        stale_file = CachedFileFactory()
    event.cache.set("schedule_export_cached_file", str(stale_file.id), None)
    after_stale = client.get(event.orga_urls.html_export_download, follow=True)

    assert "schedule/export/schedule.xml" in more_exports
    assert "first released schedule version" not in more_exports
    assert unknown.status_code == 302
    assert unknown.url == event.orga_urls.more_exports
    assert [message.level for message in get_messages(unknown.wsgi_request)] == [
        message_constants.ERROR
    ]
    assert response.status_code == 200
    assert filenames == [f"{event.slug}_schedule.zip"]
    assert after_stale.status_code == 200
    assert event.cache.get("schedule_export_cached_file") != str(stale_file.id)


def test_html_export_download_serves_cached_file(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        cached_file = CachedFileFactory()
        cached_file.file.save("test.zip", ContentFile(b"fake zip content"))
        event.cache.set("schedule_export_cached_file", str(cached_file.id), None)
    client.force_login(user)

    response = client.get(event.orga_urls.html_export_download)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"


def test_table_exports_are_scoped_to_their_event(client):
    event = EventFactory()
    other = EventFactory(organiser=event.organiser)
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        export = TableExportFactory(event=other)
    client.force_login(orga)

    response = client.get(f"{event.orga_urls.exports}{export.pk}/run/")

    assert response.status_code == 404
