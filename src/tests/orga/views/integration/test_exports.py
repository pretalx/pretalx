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
            "locale": "en",
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
            "locale": "*",
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
        data={"name": "Planted", "serializer": "csv", "locale": "en"},
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
            "locale": "en",
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
        assert export.locale == "en"
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


def test_table_exports_are_scoped_to_their_event(client):
    event = EventFactory()
    other = EventFactory(organiser=event.organiser)
    with scopes_disabled():
        orga = make_orga_user(event, can_change_event_settings=True)
        export = TableExportFactory(event=other)
    client.force_login(orga)

    response = client.get(f"{event.orga_urls.exports}{export.pk}/run/")

    assert response.status_code == 404
