# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.forms import CharField, FileField, Form, ValidationError
from django.http import QueryDict
from django.utils.datastructures import MultiValueDict
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import BaseCfPStep, CfPFlow, FormFlowStep, InfoStep, ProfileStep
from pretalx.common.forms.fields import ImageField
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


def test_base_cfp_step_navigation_skips_non_applicable_steps():
    step_a = BaseCfPStep(event=None)
    step_b = BaseCfPStep(event=None)
    step_c = BaseCfPStep(event=None)
    step_a._next = step_b
    step_b._previous = step_a
    step_b._next = step_c
    step_c._previous = step_b
    lone = BaseCfPStep(event=None)
    request = make_request(event=None)

    assert step_a.get_next_applicable(request) is step_b
    assert step_c.get_prev_applicable(request) is step_b
    assert lone.get_next_applicable(request) is None
    assert lone.get_prev_applicable(request) is None
    assert lone.get_next_url(request) is None
    assert lone.get_prev_url(request) is None
    assert lone.done(request) is None

    step_b.is_applicable = lambda req: False

    assert step_a.get_next_applicable(request) is step_c
    assert step_c.get_prev_applicable(request) is step_a


@pytest.mark.django_db
def test_base_cfp_step_get_step_url_merges_query_params():
    event = EventFactory()
    step = CfPFlow(event).steps_dict["info"]

    def step_url(path, query=None):
        request = make_request(
            event, path=path, resolver_match=make_resolver(event=event.slug, step="old")
        )
        return step.get_step_url(request, query=query)

    base = f"/{event.slug}/submit/abc123/info/"
    assert step_url("/") == base
    assert (
        step_url("/?access_code=XYZ", {"draft": "1"})
        == f"{base}?access_code=XYZ&draft=1"
    )
    assert (
        step_url("/?draft=1&access_code=XYZ", {"draft": False})
        == f"{base}?access_code=XYZ"
    )
    assert step_url("/?draft=1", {"draft": False}) == base


@pytest.mark.django_db
def test_base_cfp_step_get_next_and_prev_url():
    event = EventFactory()
    QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    flow = CfPFlow(event)
    session = make_cfp_session(
        data={"info": {"submission_type": event.cfp.default_type.pk}}
    )
    info_request = make_request(
        event,
        resolver_match=make_resolver(event=event.slug, step="info"),
        session=session,
    )
    questions_request = make_request(
        event, resolver_match=make_resolver(event=event.slug, step="questions")
    )

    assert (
        flow.steps_dict["info"].get_next_url(info_request)
        == f"/{event.slug}/submit/abc123/questions/"
    )
    assert (
        flow.steps_dict["questions"].get_prev_url(questions_request)
        == f"/{event.slug}/submit/abc123/info/"
    )


@pytest.mark.django_db
def test_form_flow_step_set_data_serializes_non_file_fields_to_session():
    event = EventFactory()
    step = ProfileStep(event=event)
    step.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    step.set_data(
        {
            "name": "Alice",
            "biography": "A speaker",
            "avatar": SimpleNamespace(file=True),
        }
    )

    assert step.cfp_session["data"]["profile"] == {
        "name": "Alice",
        "biography": "A speaker",
    }


@pytest.mark.django_db
def test_form_flow_step_get_form_data_and_initial_copy_session():
    event = EventFactory()
    step = ProfileStep(event=event)
    step.request = make_request(
        event,
        resolver_match=make_resolver(),
        session=make_cfp_session(
            data={"profile": {"name": "Alice"}},
            initial={"profile": {"name": "Default"}},
        ),
    )
    empty_step = ProfileStep(event=event)
    empty_step.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    data = step.get_form_data()
    data["name"] = "Bob"

    assert data == {"name": "Bob"}
    assert step.cfp_session["data"]["profile"] == {"name": "Alice"}
    assert step.get_form_initial() == {"name": "Default"}
    assert empty_step.get_form_data() == {}


def test_form_flow_step_annotate_stored_filenames_names_held_file_fields_only():
    step = ProfileStep(event=None)
    file_field = ImageField()
    char_field = CharField()
    form = SimpleNamespace(fields={"avatar": file_field, "name": char_field})

    step._annotate_stored_filenames(form, None)
    assert file_field.widget.stored_filename is None

    step._annotate_stored_filenames(
        form,
        {
            "avatar": SimpleNamespace(name="photo.jpg"),
            "name": SimpleNamespace(name="x"),
        },
    )
    assert file_field.widget.stored_filename == "photo.jpg"
    assert getattr(char_field.widget, "stored_filename", None) is None


@pytest.mark.django_db
def test_form_flow_step_reads_header_and_fields_from_config():
    event = EventFactory(
        cfp__settings={
            "flow": json.dumps(
                {
                    "steps": {
                        "info": {
                            "icon": "rocket",
                            "title": "Custom Title",
                            "text": "Custom Text",
                            "fields": [{"key": "title"}],
                        }
                    }
                }
            )
        }
    )
    step = InfoStep(event=event)
    step.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    assert step.config["icon"] == "rocket"
    assert step.title == LazyI18nString({"en": "Custom Title"})
    assert step.text == LazyI18nString({"en": "Custom Text"})
    kwargs = step.get_form_kwargs()
    assert kwargs["event"] == event
    assert kwargs["field_configuration"] == [{"key": "title"}]


@pytest.mark.django_db
def test_form_flow_step_falls_back_to_defaults_without_config():
    step = InfoStep(event=EventFactory())

    assert step.config == {}
    assert isinstance(step.title, LazyI18nString)
    assert step.title.data["en"]


@pytest.mark.django_db
def test_form_flow_step_get_form_uses_stored_file():
    event = EventFactory()
    session = make_cfp_session()

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {"image": SimpleUploadedFile("image.png", b"\x89PNG", content_type="image/png")}
    )
    assert step.cfp_session["files"]["info"]["image"]["name"] == "image.png"

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    form = step.get_form()

    assert form.is_bound is False
    assert form.fields["image"].widget.stored_filename == "image.png"

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        "title=Test&submission_type=" + str(event.cfp.default_type.pk)
    )
    step.request = request
    form = step.get_form()

    assert form.is_bound is True
    assert form.files["image"].name == "image.png"


@pytest.mark.parametrize(
    ("post", "expected"),
    (
        ("avatar-clear=on", True),
        ("avatar_action=remove", True),
        ("avatar_action=select_3", True),
        ("avatar_action=upload", False),
        ("avatar_action=keep", False),
        ("", False),
    ),
)
def test_form_flow_step_is_cleared(post, expected):
    step = ProfileStep(event=None)
    step.request = make_request(None, method="post")
    step.request.POST = QueryDict(post)

    assert step._is_cleared("avatar") is expected


@pytest.mark.django_db
def test_form_flow_step_is_valid_drops_cleared_upload():
    event = EventFactory()
    session = make_cfp_session()

    step = InfoStep(event=event)
    step.request = make_request(event, resolver_match=make_resolver(), session=session)
    step.set_files(
        {"image": SimpleUploadedFile("image.png", b"\x89PNG", content_type="image/png")}
    )

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict(
        f"image-clear=on&submission_type={event.cfp.default_type.pk}"
    )
    request._files = MultiValueDict()
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    assert step.cfp_session["files"]["info"] == {}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("title_valid", "image_valid", "expected_name"),
    ((False, True, "photo.png"), (True, False, None)),
    ids=("kept_when_other_field_invalid", "dropped_when_own_field_invalid"),
)
def test_form_flow_step_is_valid_persists_upload_unless_own_field_invalid(
    make_image, title_valid, image_valid, expected_name
):
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    post = "submission_type=" + str(event.cfp.default_type.pk)
    if title_valid:
        post = "title=Test&" + post
    request.POST = QueryDict(post)
    image = (
        make_image("photo.png")
        if image_valid
        else SimpleUploadedFile("evil.png", b"not an image", content_type="image/png")
    )
    request._files = MultiValueDict({"image": [image]})
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    stored = step.cfp_session["files"].get("info", {}).get("image")
    assert (stored["name"] if stored else None) == expected_name


@pytest.mark.django_db
def test_form_flow_step_is_valid_ignores_file_posted_under_text_field():
    event = EventFactory()
    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    request.POST = QueryDict("submission_type=" + str(event.cfp.default_type.pk))
    request._files = MultiValueDict(
        {
            "notes": [
                SimpleUploadedFile(
                    "payload.html", b"<script>alert(1)</script>", "text/html"
                )
            ]
        }
    )
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    assert step.cfp_session["files"] == {}


@pytest.mark.django_db
def test_form_flow_step_is_valid_does_not_restore_stored_upload(make_image):
    event = EventFactory()
    session = make_cfp_session()

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict("submission_type=" + str(event.cfp.default_type.pk))
    request._files = MultiValueDict({"image": [make_image("photo.png")]})
    request._messages = FallbackStorage(request)
    step.request = request
    step.is_valid()
    stored = dict(step.cfp_session["files"]["info"]["image"])

    step = InfoStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=session
    )
    request.POST = QueryDict("submission_type=" + str(event.cfp.default_type.pk))
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    assert step.cfp_session["files"]["info"]["image"] == stored


def _vanished_temporary_upload():
    tmp_file = TemporaryUploadedFile("slides.pdf", "application/pdf", 4, "utf-8")
    tmp_file.write(b"%PDF")
    tmp_file.seek(0)
    Path(tmp_file.temporary_file_path()).unlink()
    return tmp_file


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
        _title = "Attachment"
        _text = ""

    event = EventFactory()
    step = _AttachmentStep(event=event)
    request = make_request(
        event, method="post", resolver_match=make_resolver(), session=make_cfp_session()
    )
    request.POST = QueryDict("")
    request._files = MultiValueDict({"attachment": [_vanished_temporary_upload()]})
    request._messages = FallbackStorage(request)
    step.request = request

    assert step.is_valid() is False
    assert list(get_messages(request)) == []
    assert step.get_context_data()["form"].errors == {
        "attachment": ["Your file upload could not be processed. Please try again."]
    }


@pytest.mark.django_db
def test_form_flow_step_set_files_raises_when_tmp_file_missing():
    event = EventFactory()
    step = InfoStep(event=event)
    step.request = make_request(
        event, resolver_match=make_resolver(), session=make_cfp_session()
    )

    with pytest.raises(ValidationError):
        step.set_files({"resource-0-resource": _vanished_temporary_upload()})

    assert step.cfp_session["files"].get("info", {}) == {}


@pytest.mark.django_db
def test_form_flow_step_get_files_drops_missing_stored_file():
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
def test_dedraft_mixin_returns_own_draft_only():
    event = EventFactory()
    user = UserFactory()
    speaker = SpeakerFactory(user=user, event=event)
    draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    draft.speakers.add(speaker)
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    submitted.speakers.add(speaker)
    other_draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
    other_draft.speakers.add(SpeakerFactory(event=event))

    def dedraft(user=None, **session):
        step = InfoStep(event=event)
        step.request = make_request(
            event,
            user=user,
            resolver_match=make_resolver(),
            session=make_cfp_session(**session),
        )
        return step.dedraft_submission

    assert dedraft(user=user, code=draft.code) == draft
    assert dedraft(code=draft.code) is None
    assert dedraft(user=user) is None
    assert dedraft(user=user, code=submitted.code) is None
    assert dedraft(user=user, code=other_draft.code) is None
