import datetime as dt
import json
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import ModelChoiceIteratorValue
from django_scopes import scopes_disabled

from pretalx.common.forms.widgets import (
    AvailabilitiesWidget,
    BiographyWidget,
    ClearableBasenameFileInput,
    ColorPickerWidget,
    EnhancedSelect,
    HtmlDateInput,
    HtmlDateTimeInput,
    HtmlTimeInput,
    I18nMarkdownTextarea,
    MarkdownWidget,
    MultiEmailInput,
    PasswordConfirmationInput,
    PasswordInput,
    PasswordStrengthInput,
    ProfilePictureWidget,
    SearchInput,
    SelectMultipleWithCount,
    TextInputWithAddon,
    ToggleChoiceWidget,
    add_attribute,
    get_count,
)
from pretalx.person.models import ProfilePicture
from tests.factories import EventFactory, SpeakerFactory, UserFactory

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
    """Base PasswordInput includes toggle button but not the extra markup
    added by subclasses."""
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


def test_biography_widget_without_suggestions():
    widget = BiographyWidget()

    ctx = widget.get_context("biography", "", {})

    assert ctx["suggestions"] == []
    assert ctx["biographies"] == {}
    assert isinstance(widget, MarkdownWidget)


def test_biography_widget_with_suggestions():
    suggestions = [
        {"id": 1, "event_name": "PyCon", "biography": "I am a **Python** developer."},
        {"id": 2, "event_name": "JSConf", "biography": "I do JavaScript too."},
    ]
    widget = BiographyWidget(suggestions=suggestions)

    ctx = widget.get_context("biography", "", {})

    assert len(ctx["suggestions"]) == 2
    assert ctx["suggestions"][0]["event_name"] == "PyCon"
    assert ctx["suggestions"][0]["id"] == "1"
    assert "biography" not in ctx["suggestions"][0]
    assert "Python" in ctx["suggestions"][0]["preview"]
    assert "**" not in ctx["suggestions"][0]["preview"]
    assert ctx["biographies"]["1"] == "I am a **Python** developer."
    assert ctx["biographies"]["2"] == "I do JavaScript too."


def test_biography_widget_truncates_long_preview():
    long_bio = "A" * 300
    widget = BiographyWidget(
        suggestions=[{"id": 1, "event_name": "Conf", "biography": long_bio}]
    )

    ctx = widget.get_context("biography", "", {})

    preview = ctx["suggestions"][0]["preview"]
    assert len(preview) == 201
    assert preview.endswith("…")


def test_biography_widget_no_ellipsis_for_short_preview():
    short_bio = "Short bio."
    widget = BiographyWidget(
        suggestions=[{"id": 1, "event_name": "Conf", "biography": short_bio}]
    )

    ctx = widget.get_context("biography", "", {})

    assert "…" not in ctx["suggestions"][0]["preview"]


def test_enhanced_select_mixin_get_context_sets_enhanced_attrs():
    widget = EnhancedSelect(choices=[("a", "A")])

    ctx = widget.get_context("field", "a", {})

    assert "enhanced" in ctx["widget"]["attrs"]["class"]
    assert ctx["widget"]["attrs"]["tabindex"] == "-1"
    assert "data-required-message" in ctx["widget"]["attrs"]


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
    """When instance lacks the description/color field, no data attribute is added."""
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
    """The empty/placeholder option should not get data attributes."""
    widget = EnhancedSelect(
        choices=[("", "---"), ("a", "A")],
        description_field="description",
        color_field="color",
    )

    option = widget.create_option("field", "", "---", False, 0)

    assert "data-description" not in option["attrs"]
    assert "data-color" not in option["attrs"]


def test_get_count_from_instance_count_attribute():
    value = ModelChoiceIteratorValue(value="1", instance=SimpleNamespace(count=42))

    assert get_count(value, "any label") == 42


def test_get_count_from_label_count_attribute():
    """When value has no instance, fall back to label.count (non-callable)."""
    label = SimpleNamespace(count=7)

    assert get_count("plain_value", label) == 7


def test_get_count_callable_label_count():
    """When label.count is callable, it's called with label as argument."""
    label = SimpleNamespace(count=lambda _: 99)

    assert get_count("plain_value", label) == 99


def test_get_count_no_count_returns_zero():
    """When neither value.instance nor label has a count, returns the default 0."""
    assert get_count("plain_value", 42) == 0


def test_select_multiple_with_count_optgroups_sorts_by_count_descending():
    widget = SelectMultipleWithCount(
        choices=[
            (ModelChoiceIteratorValue("a", SimpleNamespace(count=1)), "Alpha"),
            (ModelChoiceIteratorValue("c", SimpleNamespace(count=10)), "Charlie"),
            (ModelChoiceIteratorValue("b", SimpleNamespace(count=5)), "Bravo"),
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
            (ModelChoiceIteratorValue("a", SimpleNamespace(count=3)), "Active"),
            (ModelChoiceIteratorValue("b", SimpleNamespace(count=0)), "Empty"),
        ]
    )

    groups = widget.optgroups("field", [])
    options = groups[0][1]

    assert len(options) == 1
    assert "Active (3)" in options[0]["label"]


def test_select_multiple_with_count_optgroups_marks_selected():
    widget = SelectMultipleWithCount(
        choices=[
            (ModelChoiceIteratorValue("a", SimpleNamespace(count=5)), "Alpha"),
            (ModelChoiceIteratorValue("b", SimpleNamespace(count=3)), "Bravo"),
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


def test_search_input_get_context_sets_placeholder():
    widget = SearchInput()

    ctx = widget.get_context("q", "", {})

    assert ctx["widget"]["attrs"]["placeholder"] == "Search"


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


def test_color_picker_widget_adds_colorpicker_class():
    widget = ColorPickerWidget()

    assert "colorpicker" in widget.attrs["class"]


def test_color_picker_widget_with_existing_attrs():
    widget = ColorPickerWidget(attrs={"id": "my-color"})

    assert "colorpicker" in widget.attrs["class"]
    assert widget.attrs["id"] == "my-color"


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


def test_multi_email_input_adds_tags_input_class():
    widget = MultiEmailInput()

    assert "tags-input" in widget.attrs["class"]


def test_availabilities_widget_adds_class():
    widget = AvailabilitiesWidget()

    assert "availabilities-editor-data" in widget.attrs["class"]


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
    """With upload_only=True, other_pictures is always empty even if user is set."""
    widget = ProfilePictureWidget(user="any-truthy-value", upload_only=True)

    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["other_pictures"] == []


def test_profile_picture_widget_get_context_widget_id_from_name():
    """When attrs is None, widget_id falls back to the field name."""
    widget = ProfilePictureWidget()

    ctx = widget.get_context("avatar", None, None)

    assert ctx["widget"]["widget_id"] == "avatar"


@pytest.mark.django_db
def test_profile_picture_widget_get_context_with_current_picture(make_image):
    """When current_picture has an avatar, the context includes its URL info."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    widget = ProfilePictureWidget(current_picture=pic)

    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert ctx["widget"]["current_picture"]["pk"] == pic.pk
    assert pic.avatar.url in ctx["widget"]["current_picture"]["url"]


@pytest.mark.django_db
def test_profile_picture_widget_get_context_other_pictures_single_event(make_image):
    """A picture used in one event shows that event's name as the label."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    event = EventFactory()
    with scopes_disabled():
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
    """A picture used across multiple events shows '{count} events' label."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    event1 = EventFactory()
    event2 = EventFactory()
    with scopes_disabled():
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
    """A picture not linked to any speaker profile has an empty label."""
    user = UserFactory()
    ProfilePicture.objects.create(user=user, avatar=make_image())

    widget = ProfilePictureWidget(user=user)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    assert len(ctx["widget"]["other_pictures"]) == 1
    assert ctx["widget"]["other_pictures"][0]["label"] == ""


@pytest.mark.django_db
def test_profile_picture_widget_get_context_marks_current_picture(make_image):
    """The current picture is flagged with is_current=True in other_pictures."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    widget = ProfilePictureWidget(user=user, current_picture=pic)
    ctx = widget.get_context("avatar", None, {"id": "id_avatar"})

    entry = ctx["widget"]["other_pictures"][0]
    assert entry["is_current"] is True


@pytest.mark.parametrize(
    ("value", "expected_label", "expected_aria"),
    (("draft", "Draft", "false"), ("public", "Public", "true")),
)
def test_toggle_choice_widget_get_context_selected_choice(
    value, expected_label, expected_aria
):
    widget = ToggleChoiceWidget(choices=[("draft", "Draft"), ("public", "Public")])

    ctx = widget.get_context("visibility", value, {})

    assert ctx["widget"]["value"] == value
    assert ctx["widget"]["current_label"] == expected_label
    assert ctx["widget"]["aria_pressed"] == expected_aria
    assert json.loads(ctx["widget"]["choices_json"]) == {
        "draft": "Draft",
        "public": "Public",
    }
    assert json.loads(ctx["widget"]["values_json"]) == ["draft", "public"]


@pytest.mark.parametrize("value", (None, "nonexistent"))
def test_toggle_choice_widget_get_context_defaults_to_first_choice(value):
    widget = ToggleChoiceWidget(choices=[("a", "Alpha"), ("b", "Beta")])

    ctx = widget.get_context("field", value, {})

    assert ctx["widget"]["value"] == "a"
    assert ctx["widget"]["current_label"] == "Alpha"
    assert ctx["widget"]["aria_pressed"] == "false"


@pytest.mark.parametrize("num_choices", (0, 1, 3))
def test_toggle_choice_widget_get_context_wrong_number_of_choices(num_choices):
    choices = [(str(i), f"Choice {i}") for i in range(num_choices)]
    widget = ToggleChoiceWidget(choices=choices)

    with pytest.raises(ValueError, match="exactly 2 choices"):
        widget.get_context("field", None, {})
