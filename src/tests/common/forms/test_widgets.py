# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import re
from types import SimpleNamespace

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import ModelChoiceIteratorValue
from django.utils import timezone

from pretalx.common.forms.widgets import (
    ClearableBasenameFileInput,
    EnhancedSelect,
    GroupedSelectMultiple,
    HtmlDateInput,
    HtmlDateTimeInput,
    HtmlTimeInput,
    I18nMarkdownTextarea,
    LocaleNameTextInput,
    MarkdownWidget,
    MultiEmailInput,
    PasswordConfirmationInput,
    PasswordInput,
    PasswordStrengthInput,
    ProfilePictureWidget,
    SelectMultipleWithCount,
    SpeakerSearchSelect,
    TextInputWithAddon,
    add_attribute,
    get_count,
)
from tests.factories import (
    EventFactory,
    ProfilePictureFactory,
    SpeakerFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("attrs", "value", "expected"),
    (
        (None, "my-class", {"class": "my-class"}),
        ({"class": "existing"}, "new", {"class": "existing new"}),
        ({"class": ""}, "new", {"class": "new"}),
        ({"class": None}, "new", {"class": "new"}),
        ({"id": "foo", "class": "old"}, "new", {"id": "foo", "class": "old new"}),
    ),
    ids=[
        "none_attrs",
        "existing_value",
        "empty_value",
        "none_value",
        "preserves_other_attrs",
    ],
)
def test_add_attribute(attrs, value, expected):
    result = add_attribute(attrs, "class", value)

    assert result == expected


def test_password_input_render_produces_toggle_only():
    widget = PasswordInput()

    html = widget.render("password", "")

    assert 'class="password-input"' in html
    assert "password-toggle" in html
    assert "fa-eye" in html
    assert "password-progress" not in html
    assert "password_strength" not in html


def test_password_strength_input_render():
    widget = PasswordStrengthInput()

    html = widget.render("password", "")

    assert "password-progress-bar" in html
    assert "password_strength_bar" in html
    assert "password_strength" in html
    assert widget.attrs["autocomplete"] == "new-password"


def test_password_confirmation_input_render():
    widget = PasswordConfirmationInput(confirm_with="id_password")

    html = widget.render("password2", "")

    assert "password_strength_info" in html
    assert "label-danger" in html
    assert "password_confirmation" in html
    assert widget.attrs["data-confirm-with"] == "id_password"


def test_fake_file_exposes_stem_name_and_url():
    fake = ClearableBasenameFileInput.FakeFile(
        SimpleNamespace(name="uploads/documents/report.pdf", url="/media/report.pdf")
    )

    assert str(fake) == "report"
    assert fake.name == "uploads/documents/report.pdf"
    assert fake.url == "/media/report.pdf"


@pytest.mark.parametrize(
    ("file", "expected"),
    (
        (SimpleNamespace(name="docs/resume.pdf"), True),
        (SimpleNamespace(name=""), False),
        (None, False),
    ),
)
def test_fake_file_is_falsy_without_a_file(file, expected):
    assert bool(ClearableBasenameFileInput.FakeFile(file)) is expected


def test_clearable_basename_file_input_get_context_wraps_value_in_fake_file():
    widget = ClearableBasenameFileInput()
    file_like = SimpleNamespace(name="docs/resume.pdf", url="/media/resume.pdf")

    ctx = widget.get_context("file", file_like, {})

    assert isinstance(ctx["widget"]["value"], ClearableBasenameFileInput.FakeFile)
    assert str(ctx["widget"]["value"]) == "resume"


def test_markdown_widget_get_context_includes_preview_help():
    widget = MarkdownWidget()

    ctx = widget.get_context("content", "", {})

    assert "preview_help" in ctx
    assert "Markdown" in str(ctx["preview_help"])


def test_i18n_markdown_textarea_format_output_single_language():
    result = I18nMarkdownTextarea.format_output(
        None, ["<textarea>content</textarea>"], "id_bio"
    )

    assert "i18n-form-single-language" in result
    assert "i18n-markdown-group" in result
    assert 'id="id_bio"' in result
    assert "<textarea>content</textarea>" in result


def test_i18n_markdown_textarea_format_output_multiple_languages():
    widgets = ["<textarea>en</textarea>", "<textarea>de</textarea>"]

    result = I18nMarkdownTextarea.format_output(None, widgets, "id_bio")

    assert "i18n-form-single-language" not in result
    assert "i18n-markdown-group" in result
    assert "<textarea>en</textarea>" in result
    assert "<textarea>de</textarea>" in result


def test_i18n_markdown_textarea_format_output_escapes_id():
    result = I18nMarkdownTextarea.format_output(
        None, ["<textarea></textarea>"], '<script>alert("xss")'
    )

    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_enhanced_select_mixin_get_context_sets_enhanced_attrs():
    widget = EnhancedSelect(choices=[("a", "A")])

    ctx = widget.get_context("field", "a", {})

    assert "enhanced" in ctx["widget"]["attrs"]["class"]
    assert ctx["widget"]["attrs"]["tabindex"] == "-1"
    assert "data-required-message" in ctx["widget"]["attrs"]
    assert "data-required" not in ctx["widget"]["attrs"]
    assert "aria-required" not in ctx["widget"]["attrs"]


def test_enhanced_select_required_field_renders_no_native_required_attribute():
    class TrackForm(forms.Form):
        track = forms.ChoiceField(
            choices=(("", "---"), ("a", "A")), widget=EnhancedSelect, required=True
        )

    rendered = str(TrackForm()["track"])

    assert re.search(r"<select[^>]*\srequired[\s>=]", rendered) is None
    assert 'data-required="true"' in rendered
    assert 'aria-required="true"' in rendered


@pytest.mark.parametrize(
    ("field_param", "instance_attr", "instance_value", "data_attr"),
    (
        (
            "description_field",
            "description",
            "A helpful description",
            "data-description",
        ),
        ("color_field", "color", "#ff0000", "data-color"),
    ),
)
def test_enhanced_select_mixin_create_option_with_data_field(
    field_param, instance_attr, instance_value, data_attr
):
    instance = SimpleNamespace(**{instance_attr: instance_value})
    value = ModelChoiceIteratorValue(value="1", instance=instance)
    widget = EnhancedSelect(
        choices=[(value, "Label A")], **{field_param: instance_attr}
    )

    option = widget.create_option("field", value, "Label A", False, 0)

    assert option["attrs"][data_attr] == instance_value


def test_enhanced_select_mixin_create_option_without_matching_field():
    instance = SimpleNamespace()
    value = ModelChoiceIteratorValue(value="1", instance=instance)
    widget = EnhancedSelect(
        choices=[(value, "Label A")],
        description_field="description",
        color_field="color",
    )

    option = widget.create_option("field", value, "Label A", False, 0)

    assert "data-description" not in option["attrs"]
    assert "data-color" not in option["attrs"]


def test_enhanced_select_mixin_create_option_with_callable_color_field():
    widget = EnhancedSelect(
        choices=[("urgent", "Urgent")], color_field=lambda value: f"#{value}"
    )

    option = widget.create_option("field", "urgent", "Urgent", False, 0)

    assert option["attrs"]["data-color"] == "#urgent"


def test_enhanced_select_mixin_create_option_empty_value_no_data_attrs():
    widget = EnhancedSelect(
        choices=[("", "---"), ("a", "A")],
        description_field="description",
        color_field="color",
    )

    option = widget.create_option("field", "", "---", False, 0)

    assert "data-description" not in option["attrs"]
    assert "data-color" not in option["attrs"]


def test_get_count_from_instance_submission_count_attribute():
    value = ModelChoiceIteratorValue(
        value="1", instance=SimpleNamespace(submission_count=42)
    )

    assert get_count(value, "any label") == 42


def test_get_count_from_label_count_attribute():
    label = SimpleNamespace(count=7)

    assert get_count("plain_value", label) == 7


def test_get_count_callable_label_count():
    label = SimpleNamespace(count=lambda _: 99)

    assert get_count("plain_value", label) == 99


def test_get_count_no_count_returns_zero():
    assert get_count("plain_value", 42) == 0


def test_get_count_honors_custom_count_attr():
    value = ModelChoiceIteratorValue(value="1", instance=SimpleNamespace(mail_count=12))

    assert get_count(value, "any label", count_attr="mail_count") == 12


def test_select_multiple_with_count_uses_custom_count_attr():
    widget = SelectMultipleWithCount(
        choices=[
            (ModelChoiceIteratorValue("a", SimpleNamespace(mail_count=4)), "Alpha"),
            (ModelChoiceIteratorValue("b", SimpleNamespace(mail_count=9)), "Bravo"),
        ],
        count_attr="mail_count",
    )

    groups = widget.optgroups("field", [])
    options = groups[0][1]

    assert "Bravo (9)" in options[0]["label"]
    assert "Alpha (4)" in options[1]["label"]


def test_select_multiple_with_count_optgroups_sorts_by_count_descending():
    widget = SelectMultipleWithCount(
        choices=[
            (
                ModelChoiceIteratorValue("a", SimpleNamespace(submission_count=1)),
                "Alpha",
            ),
            (
                ModelChoiceIteratorValue("c", SimpleNamespace(submission_count=10)),
                "Charlie",
            ),
            (
                ModelChoiceIteratorValue("b", SimpleNamespace(submission_count=5)),
                "Bravo",
            ),
        ]
    )

    groups = widget.optgroups("field", [])
    options = groups[0][1]

    assert len(options) == 3
    assert "Charlie (10)" in options[0]["label"]
    assert "Bravo (5)" in options[1]["label"]
    assert "Alpha (1)" in options[2]["label"]


def test_select_multiple_with_count_optgroups_skips_zero_count():
    widget = SelectMultipleWithCount(
        choices=[
            (
                ModelChoiceIteratorValue("a", SimpleNamespace(submission_count=3)),
                "Active",
            ),
            (
                ModelChoiceIteratorValue("b", SimpleNamespace(submission_count=0)),
                "Empty",
            ),
        ]
    )

    groups = widget.optgroups("field", [])
    options = groups[0][1]

    assert len(options) == 1
    assert "Active (3)" in options[0]["label"]


def test_select_multiple_with_count_optgroups_marks_selected():
    widget = SelectMultipleWithCount(
        choices=[
            (
                ModelChoiceIteratorValue("a", SimpleNamespace(submission_count=5)),
                "Alpha",
            ),
            (
                ModelChoiceIteratorValue("b", SimpleNamespace(submission_count=3)),
                "Bravo",
            ),
        ]
    )

    groups = widget.optgroups("field", ["b"])
    options = groups[0][1]
    selected_labels = [o["label"] for o in options if o["selected"]]

    assert selected_labels == ["Bravo (3)"]


def test_select_multiple_with_count_create_option_appends_count():
    widget = SelectMultipleWithCount(choices=[])

    option = widget.create_option("field", "val", "Label", False, 0, count=7)

    assert option["label"] == "Label (7)"


def _track(value, event_name, event_id):
    event = SimpleNamespace(name=event_name, pk=event_id)
    return (
        ModelChoiceIteratorValue(value, SimpleNamespace(event=event)),
        f"Track {value}",
    )


def _group_by(track):
    return (str(track.event.name), track.event.pk)


def test_grouped_select_multiple_optgroups_groups_by_event():
    widget = GroupedSelectMultiple(
        group_by=_group_by,
        choices=[
            _track("a", "PyCon", 1),
            _track("b", "PyCon", 1),
            _track("c", "DjangoCon", 2),
        ],
    )

    groups = widget.optgroups("field", [])

    assert [(name, [o["value"] for o in opts], idx) for name, opts, idx in groups] == [
        ("PyCon", ["a", "b"], 0),
        ("DjangoCon", ["c"], 1),
    ]


def test_grouped_select_multiple_optgroups_one_group_per_event_when_ordered():
    widget = GroupedSelectMultiple(
        group_by=_group_by,
        choices=[
            _track("a", "PyCon", 1),
            _track("b", "PyCon", 1),
            _track("c", "PyCon", 2),
            _track("d", "DjangoCon", 3),
        ],
    )

    groups = widget.optgroups("field", [])

    assert [(name, [o["value"] for o in opts], idx) for name, opts, idx in groups] == [
        ("PyCon", ["a", "b"], 0),
        ("PyCon", ["c"], 1),
        ("DjangoCon", ["d"], 2),
    ]


def test_grouped_select_multiple_optgroups_index_matches_django_semantics():
    widget = GroupedSelectMultiple(
        group_by=_group_by,
        choices=[
            _track("a", "PyCon", 1),
            _track("b", "PyCon", 1),
            _track("c", "DjangoCon", 2),
        ],
    )

    groups = widget.optgroups("field", [])

    for _group_name, options, group_index in groups:
        for subindex, option in enumerate(options):
            assert option["index"] == f"{group_index}_{subindex}"


def test_grouped_select_multiple_optgroups_marks_selected():
    widget = GroupedSelectMultiple(
        group_by=_group_by, choices=[_track("a", "PyCon", 1), _track("b", "PyCon", 1)]
    )

    groups = widget.optgroups("field", ["b"])
    options = groups[0][1]

    assert [o["value"] for o in options if o["selected"]] == ["b"]


def test_grouped_select_multiple_optgroups_empty_value_yields_unnamed_group():
    widget = GroupedSelectMultiple(group_by=_group_by, choices=[(None, "---")])

    groups = widget.optgroups("field", [])

    assert groups == [(None, groups[0][1], 0)]
    assert groups[0][1][0]["value"] == ""


def test_text_input_with_addon_get_context():
    widget = TextInputWithAddon(addon_before="https://", addon_after=".com")

    ctx = widget.get_context("url", "", {})

    assert ctx["widget"]["addon_before"] == "https://"
    assert ctx["widget"]["addon_after"] == ".com"


def test_text_input_with_addon_defaults_to_none():
    widget = TextInputWithAddon()

    ctx = widget.get_context("field", "", {})

    assert ctx["widget"]["addon_before"] is None
    assert ctx["widget"]["addon_after"] is None


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (dt.date(2024, 3, 15), "2024-03-15"),
        (dt.datetime(2024, 3, 15, 10, 30), "2024-03-15"),
        ("2024-03-15", "2024-03-15"),
        (None, None),
        ("", ""),
    ),
)
def test_html_date_input_format_value(value, expected):
    widget = HtmlDateInput()

    assert widget.format_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (dt.datetime(2024, 3, 15, 10, 30), "2024-03-15T10:30"),
        ("2024-03-15T10:30", "2024-03-15T10:30"),
        (None, None),
        ("", ""),
    ),
)
def test_html_datetime_input_format_value(value, expected):
    widget = HtmlDateTimeInput()

    assert widget.format_value(value) == expected


@pytest.mark.parametrize(
    ("base_attrs", "extra_attrs", "expected"),
    (
        ({}, {"id": "id_start"}, "id_start_helptext"),
        ({"id": "custom"}, None, "custom_helptext"),
        ({}, {"id": "id_start", "aria-describedby": "other"}, "other"),
        ({"aria-describedby": "other"}, {"id": "id_start"}, "other"),
        ({}, {}, None),
    ),
    ids=[
        "from_bound_field",
        "from_widget_attrs",
        "explicit_wins",
        "widget_attrs_win",
        "no_id",
    ],
)
def test_html_datetime_input_describes_help_text(base_attrs, extra_attrs, expected):
    widget = HtmlDateTimeInput()

    attrs = widget.build_attrs(base_attrs, extra_attrs)

    assert attrs.get("aria-describedby") == expected


def test_html_datetime_input_timezone_name_strips_underscores():
    with timezone.override("America/New_York"):
        assert HtmlDateTimeInput().timezone_name == "America/New York"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (dt.datetime(2026, 2, 10, 7, 0), "2026-02-10T07:00:00+08:00"),
        ("2026-02-10T07:00", "2026-02-10T07:00:00+08:00"),
        ("2026-02-10T07:00:00+08:00", "2026-02-10T07:00:00+08:00"),
        (dt.datetime(2026, 2, 9, 23, 0, tzinfo=dt.UTC), "2026-02-10T07:00:00+08:00"),
    ),
    ids=["naive_datetime", "naive_string", "aware_string", "aware_datetime"],
)
def test_html_datetime_input_reference_datetime(value, expected):
    with timezone.override("Asia/Manila"):
        assert HtmlDateTimeInput().get_reference_datetime(value) == expected


@pytest.mark.parametrize(
    "value",
    (None, "", "tomorrow", "2026-02-30T07:00"),
    ids=["none", "empty", "unparseable", "impossible_date"],
)
def test_html_datetime_input_reference_datetime_falls_back_to_now(value):
    with timezone.override("Asia/Manila"):
        before = timezone.localtime().replace(microsecond=0)
        result = HtmlDateTimeInput().get_reference_datetime(value)
        after = timezone.localtime()

    assert before <= dt.datetime.fromisoformat(result) <= after
    assert dt.datetime.fromisoformat(result).utcoffset() == dt.timedelta(hours=8)


def test_html_datetime_input_context_carries_reference_datetime():
    with timezone.override("Asia/Manila"):
        context = HtmlDateTimeInput().get_context(
            "start", dt.datetime(2026, 2, 10, 7, 0), {}
        )

    assert context["widget"]["attrs"]["data-isodatetime"] == "2026-02-10T07:00:00+08:00"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (dt.time(14, 30), "14:30"),
        (dt.datetime(2024, 3, 15, 14, 30), "14:30"),
        ("14:30", "14:30"),
        (None, None),
        ("", ""),
    ),
)
def test_html_time_input_format_value(value, expected):
    widget = HtmlTimeInput()

    assert widget.format_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (["a@b.com", "c@d.com"], "a@b.com,c@d.com"),
        (("x@y.com",), "x@y.com"),
        ("already@string.com", "already@string.com"),
        (None, ""),
        ("", ""),
    ),
)
def test_multi_email_input_format_value(value, expected):
    widget = MultiEmailInput()

    assert widget.format_value(value) == expected


def test_multi_email_input_custom_delimiter():
    widget = MultiEmailInput(delimiter=";")

    assert widget.format_value(["a@b.com", "c@d.com"]) == "a@b.com;c@d.com"


def test_multi_email_input_use_required_attribute_returns_false():
    widget = MultiEmailInput()

    assert widget.use_required_attribute(None) is False


def test_profile_picture_widget_value_from_datadict_with_action():
    widget = ProfilePictureWidget()
    uploaded = SimpleUploadedFile("pic.png", b"content")

    result = widget.value_from_datadict(
        data={"avatar_action": "upload"}, files={"avatar": uploaded}, name="avatar"
    )

    assert result == {"action": "upload", "file": uploaded}


def test_profile_picture_widget_value_from_datadict_default_action():
    widget = ProfilePictureWidget()

    result = widget.value_from_datadict(data={}, files={}, name="avatar")

    assert result == {"action": "keep", "file": None}


def test_profile_picture_widget_use_required_attribute_returns_false():
    widget = ProfilePictureWidget()

    assert widget.use_required_attribute(initial=None) is False
    assert widget.use_required_attribute(initial="something") is False


def test_profile_picture_widget_get_context_no_user_no_picture():
    widget = ProfilePictureWidget()

    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["widget_id"] == "id_avatar"
    assert ctx["widget"]["current_picture"] is None
    assert ctx["widget"]["other_pictures"] == []


def test_profile_picture_widget_get_context_upload_only():
    widget = ProfilePictureWidget(user="any-truthy-value", upload_only=True)

    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["other_pictures"] == []


def test_profile_picture_widget_get_context_widget_id_from_name():
    widget = ProfilePictureWidget()

    ctx = widget.get_context("avatar", None, None)

    assert ctx["widget"]["widget_id"] == "avatar"


@pytest.mark.django_db
def test_profile_picture_widget_get_context_with_current_picture(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    widget = ProfilePictureWidget(current_picture=pic)

    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["current_picture"]["pk"] == pic.pk
    assert pic.avatar.url in ctx["widget"]["current_picture"]["url"]


@pytest.mark.django_db
def test_profile_picture_widget_get_context_other_pictures_single_event(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    event = EventFactory()
    profile = SpeakerFactory(user=user, event=event)
    profile.profile_picture = pic
    profile.save(update_fields=["profile_picture"])

    widget = ProfilePictureWidget(user=user)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert len(ctx["widget"]["other_pictures"]) == 1
    entry = ctx["widget"]["other_pictures"][0]
    assert entry["pk"] == pic.pk
    assert entry["label"] == str(event.name)


@pytest.mark.django_db
def test_profile_picture_widget_get_context_other_pictures_multiple_events(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    event1 = EventFactory()
    event2 = EventFactory()
    p1 = SpeakerFactory(user=user, event=event1)
    p2 = SpeakerFactory(user=user, event=event2)
    p1.profile_picture = pic
    p1.save(update_fields=["profile_picture"])
    p2.profile_picture = pic
    p2.save(update_fields=["profile_picture"])

    widget = ProfilePictureWidget(user=user)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert len(ctx["widget"]["other_pictures"]) == 1
    assert "2" in ctx["widget"]["other_pictures"][0]["label"]


@pytest.mark.django_db
def test_profile_picture_widget_get_context_other_pictures_no_events(make_image):
    user = UserFactory()
    ProfilePictureFactory(user=user, avatar=make_image())

    widget = ProfilePictureWidget(user=user)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert len(ctx["widget"]["other_pictures"]) == 1
    assert ctx["widget"]["other_pictures"][0]["label"] == ""


@pytest.mark.django_db
def test_profile_picture_widget_get_context_marks_current_picture(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    widget = ProfilePictureWidget(user=user, current_picture=pic)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    entry = ctx["widget"]["other_pictures"][0]
    assert entry["is_current"] is True


@pytest.mark.parametrize(
    ("placeholder", "expected_placeholder"),
    (("ta", "Tamil"), ("Session title", "Session title")),
    ids=("locale_code_placeholder", "form_placeholder"),
)
def test_locale_name_widget_labels_locale(placeholder, expected_placeholder):
    widget = LocaleNameTextInput(attrs={"lang": "ta"})

    attrs = widget.build_attrs(widget.attrs, {"placeholder": placeholder})

    assert str(attrs["title"]) == "Tamil"
    assert str(attrs["placeholder"]) == expected_placeholder


def test_locale_name_widget_uses_form_locale_names():
    widget = LocaleNameTextInput(attrs={"lang": "xx"})
    widget.form = SimpleNamespace(locale_names={"xx": "Plugin language"})

    attrs = widget.build_attrs(widget.attrs, {})

    assert attrs["title"] == "Plugin language"
    assert attrs["placeholder"] == "Plugin language"


def test_locale_name_widget_ignores_widgets_without_locale():
    widget = MarkdownWidget()

    attrs = widget.build_attrs({"class": "plain"}, {})

    assert attrs == {"class": "plain"}


def test_speaker_search_select_build_attrs_without_remote_url():
    widget = SpeakerSearchSelect()

    attrs = widget.build_attrs({})

    assert "data-remote-url" not in attrs
    assert attrs["multiple"] is True
