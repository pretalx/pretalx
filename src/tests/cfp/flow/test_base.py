# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.forms import CharField, FileField, Form, ValidationError
from django.http import QueryDict
from django.utils.datastructures import MultiValueDict
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import BaseCfPStep, CfPFlow, FormFlowStep, InfoStep, ProfileStep
from pretalx.submission.models import QuestionTarget, SubmissionStates
from tests.cfp.flow._helpers import make_cfp_session, make_resolver
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)
from tests.utils import make_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_base_cfp_step_priority_defaults_to_100():
    assert BaseCfPStep(event=None).priority == 100


@pytest.mark.django_db
def test_base_cfp_step_is_applicable_returns_true_by_default():
    assert BaseCfPStep(event=None).is_applicable(request=None) is True


@pytest.mark.django_db
def test_base_cfp_step_done_is_noop():
    assert BaseCfPStep(event=None).done(request=None) is None


def test_base_cfp_step_get_next_applicable_returns_next():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_a._next = step_b

    assert step_a.get_next_applicable(request=None) is step_b


def test_base_cfp_step_get_next_applicable_skips_non_applicable():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_c = BaseCfPStep(event=None)
    step_b.is_applicable = lambda req: False
    step_b._next = step_c
    step_a._next = step_b

    assert step_a.get_next_applicable(request=None) is step_c


@pytest.mark.parametrize(
    "method", ("get_next_applicable", "get_prev_applicable"), ids=("next", "prev")
)
def test_base_cfp_step_get_next_prev_applicable_returns_none_without_neighbor(method):
    assert getattr(BaseCfPStep(event=None), method)(request=None) is None


def test_base_cfp_step_get_prev_applicable_returns_previous():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_b._previous = step_a

    assert step_b.get_prev_applicable(request=None) is step_a


def test_base_cfp_step_get_prev_applicable_skips_non_applicable():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_c = BaseCfPStep(event=None)
    step_b.is_applicable = lambda req: False
    step_b._previous = step_a
    step_c._previous = step_b

    assert step_c.get_prev_applicable(request=None) is step_a


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_builds_correct_url():
    """get_step_url builds /event-slug/submit/tmpid/step/ URLs."""
    event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event, resolver_match=make_resolver(event=event.slug, step="old")
    )

    url = step.get_step_url(request)

    assert f"/{event.slug}/submit/abc123/info/" in url


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_merges_query_params():
    event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event,
        path="/?access_code=XYZ",
        resolver_match=make_resolver(event=event.slug, step="old"),
    )

    url = step.get_step_url(request, query={"draft": "1"})

    assert "access_code=XYZ" in url
    assert "draft=1" in url


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_removes_false_query_params():
    event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event,
        path="/?draft=1&access_code=XYZ",
        resolver_match=make_resolver(event=event.slug, step="old"),
    )

    url = step.get_step_url(request, query={"draft": False})

    assert "draft" not in url
    assert "access_code=XYZ" in url


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_no_query_string_when_all_removed():
    """When all GET params are removed via False, no query string is appended."""
    event = EventFactory()
    flow = CfPFlow(event)
    step = flow.steps_dict["info"]
    request = make_request(
        event,
        path="/?draft=1",
        resolver_match=make_resolver(event=event.slug, step="old"),
    )

    url = step.get_step_url(request, query={"draft": False})

    assert "?" not in url


@pytest.mark.django_db
def test_base_cfp_step_get_next_url_returns_url_when_next_exists():
    event = EventFactory()
    QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    flow = CfPFlow(event)
    info_step = flow.steps_dict["info"]
    request = make_request(
        event,
        resolver_match=make_resolver(event=event.slug, step="info"),
        session=make_cfp_session(
            data={"info": {"submission_type": event.cfp.default_type.pk}}
        ),
    )

    url = info_step.get_next_url(request)

    assert f"/{event.slug}/submit/abc123/questions/" in url


@pytest.mark.parametrize(
    "method", ("get_next_url", "get_prev_url"), ids=("next", "prev")
)
def test_base_cfp_step_get_next_prev_url_returns_none_without_neighbor(method):
    assert (
        getattr(BaseCfPStep(event=None), method)(request=make_request(event=None))
        is None
    )


@pytest.mark.django_db
def test_base_cfp_step_get_prev_url_returns_url_when_prev_exists():
    event = EventFactory()
    flow = CfPFlow(event)
    questions_step = flow.steps_dict["questions"]
    request = make_request(
        event, resolver_match=make_resolver(event=event.slug, step="questions")
    )

    url = questions_step.get_prev_url(request)

    assert f"/{event.slug}/submit/abc123/info/" in url
    assert "draft" not in url


@pytest.mark.django_db
def test_form_flow_step_set_data_serializes_to_session():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    step.set_data({"name": "Alice", "biography": "A speaker"})

    assert step.cfp_session["data"]["profile"]["name"] == "Alice"
    assert step.cfp_session["data"]["profile"]["biography"] == "A speaker"


@pytest.mark.django_db
def test_form_flow_step_set_data_skips_file_fields():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request
    file_obj = SimpleNamespace(file=True)

    step.set_data({"name": "Alice", "avatar": file_obj})

    assert "avatar" not in step.cfp_session["data"]["profile"]
    assert step.cfp_session["data"]["profile"]["name"] == "Alice"


@pytest.mark.django_db
def test_form_flow_step_get_form_data_returns_session_data():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(data={"profile": {"name": "Alice"}}),
    )
    step.request = request

    assert step.get_form_data() == {"name": "Alice"}


@pytest.mark.django_db
def test_form_flow_step_get_form_data_returns_empty_when_no_data():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    assert step.get_form_data() == {}


@pytest.mark.django_db
def test_form_flow_step_get_form_initial_returns_session_initial():
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(initial={"profile": {"name": "Default"}}),
    )
    step.request = request

    assert step.get_form_initial() == {"name": "Default"}


@pytest.mark.django_db
def test_form_flow_step_get_form_data_deep_copies():
    """Modifying returned data does not affect session."""
    event = EventFactory()
    step = ProfileStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(data={"profile": {"name": "Alice"}}),
    )
    step.request = request

    result = step.get_form_data()
    result["name"] = "Bob"

    assert step.cfp_session["data"]["profile"]["name"] == "Alice"


def test_form_flow_step_annotate_stored_filenames_noop_without_files():
    step = ProfileStep(event=None)
    file_field = FileField()
    file_field.help_text = "Original help"
    form = SimpleNamespace(fields={"avatar": file_field})

    step._annotate_stored_filenames(form, None)

    assert file_field.help_text == "Original help"


def test_form_flow_step_annotate_stored_filenames_adds_help_text():
    step = ProfileStep(event=None)
    file_field = FileField()
    file_field.help_text = ""
    form = SimpleNamespace(fields={"avatar": file_field})

    stored_file = SimpleNamespace(name="photo.jpg")

    step._annotate_stored_filenames(form, {"avatar": stored_file})

    assert "photo.jpg" in file_field.help_text
    assert "stored-file-indicator" in file_field.help_text


def test_form_flow_step_annotate_stored_filenames_preserves_help_text():
    step = ProfileStep(event=None)
    file_field = FileField()
    file_field.help_text = "Max 5MB"
    form = SimpleNamespace(fields={"avatar": file_field})

    stored_file = SimpleNamespace(name="photo.jpg")

    step._annotate_stored_filenames(form, {"avatar": stored_file})

    assert "Max 5MB" in file_field.help_text
    assert "photo.jpg" in file_field.help_text


def test_form_flow_step_annotate_stored_filenames_skips_non_file_fields():
    step = ProfileStep(event=None)
    char_field = CharField()
    char_field.help_text = ""
    form = SimpleNamespace(fields={"name": char_field})

    stored_file = SimpleNamespace(name="file.txt")

    step._annotate_stored_filenames(form, {"name": stored_file})

    assert "file.txt" not in char_field.help_text


@pytest.mark.django_db
def test_form_flow_step_config_reads_from_event():
    event = EventFactory(
        cfp__settings={
            "flow": json.dumps({"steps": {"info": {"icon": "rocket", "fields": []}}})
        }
    )

    step = InfoStep(event=event)

    assert step.config.get("icon") == "rocket"


@pytest.mark.django_db
def test_form_flow_step_config_returns_empty_without_config():
    event = EventFactory()

    assert InfoStep(event=event).config == {}


@pytest.mark.django_db
def test_form_flow_step_title_uses_config():
    event = EventFactory(
        cfp__settings={
            "flow": json.dumps(
                {"steps": {"info": {"title": "Custom Title", "fields": []}}}
            )
        }
    )

    assert InfoStep(event=event).title.data["en"] == "Custom Title"


@pytest.mark.django_db
def test_form_flow_step_title_falls_back_to_default():
    event = EventFactory()

    title = InfoStep(event=event).title
    assert isinstance(title, LazyI18nString)
    assert title.data["en"]  # has a non-empty default


@pytest.mark.django_db
def test_form_flow_step_text_uses_config():
    event = EventFactory(
        cfp__settings={
            "flow": json.dumps(
                {"steps": {"info": {"text": "Custom Text", "fields": []}}}
            )
        }
    )

    assert InfoStep(event=event).text.data["en"] == "Custom Text"


@pytest.mark.django_db
def test_form_flow_step_get_form_kwargs_includes_event():
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    assert step.get_form_kwargs()["event"] == event


@pytest.mark.django_db
def test_form_flow_step_get_form_kwargs_includes_field_configuration():
    event = EventFactory(
        cfp__settings={
            "flow": json.dumps({"steps": {"info": {"fields": [{"key": "title"}]}}})
        }
    )
    step = InfoStep(event=event)
    request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )
    step.request = request

    config = step.get_form_kwargs()["field_configuration"]
    assert len(config) == 1
    assert config[0]["key"] == "title"


@pytest.mark.django_db
def test_form_flow_step_get_form_post_merges_stored_files():
    event = EventFactory()
    session = make_cfp_session()

    # Phase 1: store a file via set_files on a GET request
    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {"image": SimpleUploadedFile("image.png", b"\x89PNG", content_type="image/png")}
    )

    # Phase 2: fresh step (clears cached_property), POST request reusing same session
    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        "title=Test&submission_type=" + str(event.cfp.default_type.pk)
    )
    step.request = request

    form = step.get_form()

    assert form.files["image"].name == "image.png"


@pytest.mark.django_db
def test_form_flow_step_is_valid_false_when_set_files_raises():
    class _AttachmentForm(Form):
        attachment = FileField(required=False)

        def __init__(self, *args, event=None, field_configuration=None, **kwargs):
            super().__init__(*args, **kwargs)

    class _AttachmentStep(FormFlowStep):
        identifier = "info"
        form_class = _AttachmentForm
        template_name = "cfp/event/submission_base.html"

    event = EventFactory()
    step = _AttachmentStep(event=event)

    tmp_file = TemporaryUploadedFile("slides.pdf", "application/pdf", 4, "utf-8")
    tmp_file.write(b"%PDF")
    tmp_file.seek(0)
    Path(tmp_file.temporary_file_path()).unlink()

    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    request.POST = QueryDict("")
    request._files = MultiValueDict({"attachment": [tmp_file]})
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    error_messages = [
        m for m in get_messages(request) if m.level == message_constants.ERROR
    ]
    assert len(error_messages) == 1


@pytest.mark.django_db
def test_form_flow_step_set_files_raises_when_tmp_file_missing():
    """If the upload's backing temp file has vanished between request parsing
    and storage (OS temp-reaper, race, etc.), set_files must raise a
    ValidationError rather than propagating FileNotFoundError."""
    event = EventFactory()
    step = InfoStep(event=event)
    step.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    tmp_file = TemporaryUploadedFile("slides.pdf", "application/pdf", 4, "utf-8")
    tmp_file.write(b"%PDF")
    tmp_file.seek(0)
    Path(tmp_file.temporary_file_path()).unlink()

    with pytest.raises(ValidationError):
        step.set_files({"resource-0-resource": tmp_file})

    assert step.cfp_session["files"].get("info", {}) == {}


@pytest.mark.django_db
def test_form_flow_step_set_files_persists_on_success():
    event = EventFactory()
    step = InfoStep(event=event)
    step.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    step.set_files(
        {"image": SimpleUploadedFile("image.png", b"\x89PNG", content_type="image/png")}
    )

    assert "image" in step.cfp_session["files"]["info"]


@pytest.mark.django_db
def test_form_flow_step_get_files_drops_missing_stored_file():
    """If a previously stored session file has been cleaned up from disk,
    get_files must drop that entry from the session and continue, instead
    of raising FileNotFoundError when opening the missing path."""
    event = EventFactory()
    step = InfoStep(event=event)
    step.request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            files={
                "info": {
                    "image": {
                        "tmp_name": "does-not-exist.pdf",
                        "name": "slides.pdf",
                        "content_type": "application/pdf",
                        "size": 4,
                        "charset": "utf-8",
                    }
                }
            }
        ),
    )

    result = step.get_files()

    assert result is None
    assert step.cfp_session["files"]["info"] == {}


@pytest.mark.django_db
def test_dedraft_mixin_returns_draft_for_authenticated_speaker():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    speaker = SpeakerFactory(user=user, event=event)
    submission.speakers.add(speaker)
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(code=submission.code),
    )
    step.request = request

    assert step.dedraft_submission == submission


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_for_anonymous():
    event = EventFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    step = InfoStep(event=event)
    request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(code=submission.code),
    )
    step.request = request

    assert step.dedraft_submission is None


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_without_code():
    event = EventFactory()
    UserFactory()
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=UserFactory(),
        resolver_match=make_resolver(),
        session=make_cfp_session(),
    )
    step.request = request

    assert step.dedraft_submission is None


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_for_non_draft():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    speaker = SpeakerFactory(user=user, event=event)
    submission.speakers.add(speaker)
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(code=submission.code),
    )
    step.request = request

    assert step.dedraft_submission is None


@pytest.mark.django_db
def test_dedraft_mixin_returns_none_for_wrong_speaker():
    event = EventFactory()
    user = UserFactory()
    other_user = UserFactory()
    submission = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    other_speaker = SpeakerFactory(user=other_user, event=event)
    submission.speakers.add(other_speaker)
    step = InfoStep(event=event)
    request = make_request(
        event,
        user=user,
        resolver_match=make_resolver(),
        session=make_cfp_session(code=submission.code),
    )
    step.request = request

    assert step.dedraft_submission is None
