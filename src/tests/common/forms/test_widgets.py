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
    CssWidget,
    EnhancedSelect,
    GroupedSelectMultiple,
    HtmlDateInput,
    HtmlDateTimeInput,
    HtmlTimeInput,
    I18nMarkdownTextarea,
    I18nTextInput,
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


@pytest.mark.parametrize(
    ("widgets", "single"),
    (
        (["<textarea>en</textarea>"], True),
        (["<textarea>en</textarea>", "<textarea>de</textarea>"], False),
    ),
    ids=("single_language", "multiple_languages"),
)
def test_i18n_markdown_textarea_format_output(widgets, single):
    result = I18nMarkdownTextarea.format_output(None, widgets, "id_bio")

    assert ("i18n-form-single-language" in result) is single
    assert "i18n-markdown-group" in result
    assert 'id="id_bio"' in result
    for widget in widgets:
        assert widget in result


@pytest.mark.parametrize("widget_class", (I18nTextInput, I18nMarkdownTextarea))
@pytest.mark.parametrize(
    ("enabled_locales", "id_", "expected"),
    (
        (["en", "de"], "id_name", "id_name_0"),
        (["de"], "id_name", "id_name_1"),
        ([], "id_name", ""),
        (["en", "de"], "", ""),
    ),
)
def test_i18n_widget_id_for_label_targets_first_rendered_input(
    widget_class, enabled_locales, id_, expected
):
    widget = widget_class(locales=["en", "de"], field=None)
    widget.enabled_locales = enabled_locales

    assert widget.id_for_label(id_) == expected


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


@pytest.mark.parametrize(
    ("value", "label", "kwargs", "expected"),
    (
        (
            ModelChoiceIteratorValue("1", SimpleNamespace(submission_count=42)),
            "any label",
            {},
            42,
        ),
        ("plain_value", SimpleNamespace(count=7), {}, 7),
        ("plain_value", SimpleNamespace(count=lambda _: 99), {}, 99),
        ("plain_value", 42, {}, 0),
        (
            ModelChoiceIteratorValue("1", SimpleNamespace(mail_count=12)),
            "any label",
            {"count_attr": "mail_count"},
            12,
        ),
    ),
    ids=(
        "instance_submission_count",
        "label_count",
        "callable_label_count",
        "no_count",
        "custom_count_attr",
    ),
)
def test_get_count(value, label, kwargs, expected):
    assert get_count(value, label, **kwargs) == expected


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

    assert [o["label"] for o in options] == ["Bravo (9)", "Alpha (4)"]


def test_select_multiple_with_count_optgroups_sorts_marks_and_skips_empty():
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
                ModelChoiceIteratorValue("d", SimpleNamespace(submission_count=0)),
                "Empty",
            ),
            (
                ModelChoiceIteratorValue("b", SimpleNamespace(submission_count=5)),
                "Bravo",
            ),
        ]
    )

    groups = widget.optgroups("field", ["b"])
    options = groups[0][1]

    assert [(o["label"], o["selected"]) for o in options] == [
        ("Charlie (10)", False),
        ("Bravo (5)", True),
        ("Alpha (1)", False),
    ]


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

    groups = widget.optgroups("field", ["b"])

    assert [
        (name, [(o["value"], o["index"], o["selected"]) for o in opts], idx)
        for name, opts, idx in groups
    ] == [
        ("PyCon", [("a", "0_0", False), ("b", "0_1", True)], 0),
        ("DjangoCon", [("c", "1_0", False)], 1),
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


def test_grouped_select_multiple_optgroups_empty_value_yields_unnamed_group():
    widget = GroupedSelectMultiple(group_by=_group_by, choices=[(None, "---")])

    groups = widget.optgroups("field", [])

    assert groups == [(None, groups[0][1], 0)]
    assert groups[0][1][0]["value"] == ""


@pytest.mark.parametrize(
    ("kwargs", "before", "after"),
    (
        ({"addon_before": "https://", "addon_after": ".com"}, "https://", ".com"),
        ({}, None, None),
    ),
    ids=("addons", "defaults"),
)
def test_text_input_with_addon_get_context(kwargs, before, after):
    widget = TextInputWithAddon(**kwargs)

    ctx = widget.get_context("url", "", {})

    assert ctx["widget"]["addon_before"] == before
    assert ctx["widget"]["addon_after"] == after


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
    (None, "", "tomorrow", "2026-02-30T07:00", "0001-01-01T00:00:00+09:00"),
    ids=["none", "empty", "unparseable", "impossible_date", "out_of_range_offset"],
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


_uploaded = SimpleUploadedFile("pic.png", b"content")


@pytest.mark.parametrize(
    ("data", "files", "expected"),
    (
        (
            {"avatar_action": "upload"},
            {"avatar": _uploaded},
            {"action": "upload", "file": _uploaded},
        ),
        ({}, {}, {"action": "keep", "file": None}),
    ),
    ids=("with_action", "default_action"),
)
def test_profile_picture_widget_value_from_datadict(data, files, expected):
    widget = ProfilePictureWidget()

    assert widget.value_from_datadict(data=data, files=files, name="avatar") == expected


def test_profile_picture_widget_use_required_attribute_returns_false():
    widget = ProfilePictureWidget()

    assert widget.use_required_attribute(initial=None) is False
    assert widget.use_required_attribute(initial="something") is False


@pytest.mark.parametrize(
    ("attrs", "widget_id"),
    (({"id": "id_avatar"}, "id_avatar"), (None, "avatar")),
    ids=("id_from_attrs", "id_from_name"),
)
def test_profile_picture_widget_get_context_no_user_no_picture(attrs, widget_id):
    widget = ProfilePictureWidget()

    ctx = widget.get_context("avatar", None, attrs)

    assert ctx["widget"]["widget_id"] == widget_id
    assert ctx["widget"]["current_picture"] is None
    assert ctx["widget"]["other_pictures"] == []
    assert ctx["widget"]["action"] == "keep"


@pytest.mark.parametrize(
    ("stored_filename", "value", "expected_action", "expected_name"),
    (
        ("face.png", None, "upload", "face.png"),
        ("face.png", {"action": "keep", "file": None}, "upload", "face.png"),
        ("face.png", {"action": "remove", "file": None}, "remove", None),
        ("face.png", {"action": "select_7", "file": None}, "select_7", None),
        (None, {"action": "upload", "file": None}, "keep", None),
        (None, {"action": "remove", "file": None}, "remove", None),
    ),
    ids=(
        "held_upload_unbound",
        "held_upload_beats_keep",
        "recorded_remove_beats_held_upload",
        "recorded_selection_beats_held_upload",
        "upload_without_file_falls_back",
        "recorded_remove_without_held_file",
    ),
)
def test_profile_picture_widget_get_context_action(
    stored_filename, value, expected_action, expected_name
):
    widget = ProfilePictureWidget()
    widget.stored_filename = stored_filename

    ctx = widget.get_context("avatar", value, {"id": "id_avatar"})

    assert ctx["widget"]["action"] == expected_action
    assert ctx["widget"]["stored_filename"] == expected_name


@pytest.mark.django_db
def test_profile_picture_widget_get_context_action_moves_current_picture(make_image):
    user = UserFactory()
    current = ProfilePictureFactory(user=user, avatar=make_image("old.png"))
    other = ProfilePictureFactory(user=user, avatar=make_image("new.png"))
    foreign = ProfilePictureFactory(avatar=make_image("stranger.png"))
    widget = ProfilePictureWidget(user=user, current_picture=current)

    def context(action):
        return widget.get_context("avatar", {"action": action, "file": None}, None)[
            "widget"
        ]

    assert context("keep")["current_picture"]["pk"] == current.pk
    assert context("remove")["current_picture"] is None
    assert context(f"select_{foreign.pk}")["current_picture"]["pk"] == current.pk

    selected = context(f"select_{other.pk}")
    assert selected["current_picture"]["pk"] == other.pk
    assert other.avatar.url in selected["current_picture"]["url"]
    assert [(p["pk"], p["is_current"]) for p in selected["other_pictures"]] == [
        (other.pk, True),
        (current.pk, False),
    ]


def test_profile_picture_widget_get_context_upload_only():
    widget = ProfilePictureWidget(user="any-truthy-value", upload_only=True)

    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["other_pictures"] == []


@pytest.mark.django_db
def test_profile_picture_widget_get_context_lists_pictures_with_event_labels(
    make_image,
):
    user = UserFactory()
    unused = ProfilePictureFactory(user=user, avatar=make_image())
    single = ProfilePictureFactory(user=user, avatar=make_image())
    shared = ProfilePictureFactory(user=user, avatar=make_image())
    event = EventFactory()
    for picture, speaker_event in (
        (single, event),
        (shared, EventFactory()),
        (shared, EventFactory()),
    ):
        profile = SpeakerFactory(user=user, event=speaker_event)
        profile.profile_picture = picture
        profile.save(update_fields=["profile_picture"])

    widget = ProfilePictureWidget(user=user, current_picture=single)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["current_picture"]["pk"] == single.pk
    assert single.avatar.url in ctx["widget"]["current_picture"]["url"]
    assert [
        (p["pk"], p["label"], p["is_current"]) for p in ctx["widget"]["other_pictures"]
    ] == [
        (shared.pk, "2 events", False),
        (single.pk, str(event.name), True),
        (unused.pk, "", False),
    ]


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


@pytest.mark.parametrize(
    ("attrs", "expected"),
    (
        ({"id": "id_custom_css"}, ["id_custom_css", "id_custom_css_text"]),
        ({}, [None, None]),
    ),
    ids=("named_after_their_fields", "no_auto_id"),
)
def test_css_widget_subwidget_ids(attrs, expected):
    context = CssWidget().get_context("custom_css", None, attrs)

    subwidgets = context["widget"]["subwidgets"]
    assert [widget["attrs"].get("id") for widget in subwidgets] == expected
    assert [widget["name"] for widget in subwidgets] == [
        "custom_css",
        "custom_css_text",
    ]


def test_css_widget_opens_the_textarea_for_errors():
    context = CssWidget().get_context("custom_css", None, {"aria-invalid": "true"})

    assert context["widget"]["has_error"] is True


def test_css_widget_decompress_reads_the_attached_file():
    css = SimpleUploadedFile("custom.css", b"body { color: red; }\n")

    assert CssWidget().decompress(css) == [css, "body { color: red; }"]


def test_css_widget_decompress_ignores_a_file_it_cannot_read():
    css = SimpleUploadedFile("custom.css", b"\xff\xfenot utf-8")

    assert CssWidget().decompress(css) == [css, ""]
