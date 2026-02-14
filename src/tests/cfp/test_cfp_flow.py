# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import HttpResponseNotAllowed
from django_scopes import scope
from i18nfield.strings import LazyI18nString

from pretalx.cfp.flow import BaseCfPStep, CfPFlow, i18n_string
from pretalx.person.forms.profile import SpeakerProfileForm
from pretalx.submission.forms.submission import InfoForm


@pytest.mark.parametrize(
    ("data", "locales", "expected"),
    (
        ("Submission", ["en"], {"en": "Submission"}),
        ("Submission", ["en", "de"], {"en": "Submission", "de": "Submission"}),
        (
            "Submission",
            ["en", "de", "xx"],
            {"en": "Submission", "de": "Submission", "xx": "Submission"},
        ),
        ({"en": "Submission"}, ["en"], {"en": "Submission"}),
        ({"en": "Submission"}, ["en", "de"], {"en": "Submission", "de": "Submission"}),
        (
            {"en": "Submission", "de": "Submission"},
            ["en"],
            {"en": "Submission", "de": "Submission"},
        ),
        (
            {"en": "Submission", "de": "Submission"},
            ["en", "de"],
            {"en": "Submission", "de": "Submission"},
        ),
        (
            {"en": "Submission", "de": "WRONG"},
            ["en", "de"],
            {"en": "Submission", "de": "WRONG"},
        ),
        (LazyI18nString({"en": "Submission"}), ["en", "de"], {"en": "Submission"}),
        (1, ["en", "de"], {"en": "", "de": ""}),
    ),
)
def test_i18n_string(data, locales, expected):
    assert i18n_string(data, locales).data == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        (None, {"steps": {}}),
        ([], {"steps": {}}),
        ({"steps": {"info": {}}}, {"steps": {"info": {"fields": []}}}),
        (
            {"steps": {"info": {"icon": "foo"}}},
            {"steps": {"info": {"fields": [], "icon": "foo"}}},
        ),
        ({"steps": {"info": {"fields": []}}}, {"steps": {"info": {"fields": []}}}),
        (
            {"steps": {"info": {"fields": [], "text": "teeext"}}},
            {"steps": {"info": {"fields": [], "text": {"en": "teeext"}}}},
        ),
        (
            {
                "steps": {
                    "info": {
                        "fields": [{"widget": "w", "key": "k", "help_text": "bar"}]
                    }
                }
            },
            {"steps": {"info": {"fields": [{"key": "k", "help_text": {"en": "bar"}}]}}},
        ),
    ),
)
@pytest.mark.django_db
def test_cfp_flow(event, data, expected):
    with scope(event=event):
        assert event.cfp.settings["flow"] == {}
        event.cfp_flow.save_config(event.cfp_flow.get_config(data))
        assert event.cfp.settings["flow"] == expected
        assert event.cfp_flow.get_config_json()


@pytest.mark.django_db
def test_cfp_flow_reset(event):
    with scope(event=event):
        event.cfp_flow.save_config(
            {"steps": {"info": {"fields": [{"key": "k", "help_text": {"en": "bar"}}]}}}
        )
        event.cfp_flow.reset()
        assert event.cfp_flow.get_config_json()
        assert event.cfp.settings["flow"] == {}


def test_base_cfp_step_attributes():
    step = BaseCfPStep(None)
    assert step.priority == 100
    assert step.done(None) is None
    assert isinstance(step.get(None), HttpResponseNotAllowed)
    assert isinstance(step.post(None), HttpResponseNotAllowed)


@pytest.mark.django_db
def test_cfp_form_mixin_reorders_fields(event):
    with scope(event=event):
        field_config = [
            {"key": "abstract"},
            {"key": "title"},
            {"key": "description"},
        ]
        form_reordered = InfoForm(event=event, field_configuration=field_config)
        reordered_keys = list(form_reordered.fields.keys())

        configured_fields = [
            k for k in reordered_keys if k in ["abstract", "title", "description"]
        ]
        assert configured_fields == ["abstract", "title", "description"]
        assert reordered_keys.index("abstract") < reordered_keys.index("title")


@pytest.mark.django_db
def test_speaker_profile_form_reorders_fields(event, speaker):
    with scope(event=event):
        field_config = [
            {"key": "biography"},
            {"key": "name"},
            {"key": "avatar"},
        ]
        form = SpeakerProfileForm(
            event=event,
            user=speaker,
            field_configuration=field_config,
        )
        keys = list(form.fields.keys())

        assert keys.index("biography") < keys.index("name")


@pytest.mark.django_db
def test_get_field_config_returns_empty_dict_for_missing(event):
    with scope(event=event):
        assert event.cfp_flow.get_field_config("info", "nonexistent") == {}
        assert event.cfp_flow.get_field_config("nonexistent_step", "title") == {}


@pytest.mark.django_db
def test_get_field_config_returns_field(event):
    with scope(event=event):
        event.cfp_flow.save_config(
            {
                "steps": {
                    "info": {
                        "fields": [
                            {
                                "key": "title",
                                "label": "Custom Title",
                                "help_text": "Help",
                            },
                            {"key": "abstract"},
                        ]
                    }
                }
            }
        )
        # Reload the flow to get updated config
        flow = CfPFlow(event)
        config = flow.get_field_config("info", "title")
        assert config["key"] == "title"
        assert config["label"] == {"en": "Custom Title"}
        assert config["help_text"] == {"en": "Help"}

        assert flow.get_field_config("info", "abstract") == {"key": "abstract"}


@pytest.mark.django_db
def test_update_field_config_creates_new_field(event):
    with scope(event=event):
        event.cfp_flow.update_field_config("info", "title", label="New Label")
        flow = CfPFlow(event)
        config = flow.get_field_config("info", "title")
        assert config["key"] == "title"
        assert config["label"] == {"en": "New Label"}


@pytest.mark.django_db
def test_update_field_config_updates_existing_field(event):
    with scope(event=event):
        event.cfp_flow.save_config(
            {"steps": {"info": {"fields": [{"key": "title", "label": "Old"}]}}}
        )
        flow = CfPFlow(event)
        flow.update_field_config("info", "title", label="New", help_text="Help")
        flow = CfPFlow(event)
        config = flow.get_field_config("info", "title")
        assert config["label"] == {"en": "New"}
        assert config["help_text"] == {"en": "Help"}


@pytest.mark.django_db
def test_update_field_config_creates_step_if_missing(event):
    with scope(event=event):
        event.cfp_flow.update_field_config("profile", "biography", help_text="Bio help")
        flow = CfPFlow(event)
        config = flow.get_field_config("profile", "biography")
        assert config["key"] == "biography"
        assert config["help_text"] == {"en": "Bio help"}


@pytest.mark.django_db
def test_update_field_order_reorders_existing_fields(event):
    with scope(event=event):
        event.cfp_flow.save_config(
            {
                "steps": {
                    "info": {
                        "fields": [
                            {"key": "title", "label": "Title Label"},
                            {"key": "abstract", "help_text": "Abstract help"},
                            {"key": "description"},
                        ]
                    }
                }
            }
        )
        flow = CfPFlow(event)
        flow.update_field_order("info", ["description", "title", "abstract"])
        flow = CfPFlow(event)
        step_config = flow.get_step_config("info")
        keys = [f["key"] for f in step_config["fields"]]
        assert keys == ["description", "title", "abstract"]
        assert step_config["fields"][1]["label"] == {"en": "Title Label"}
        assert step_config["fields"][2]["help_text"] == {"en": "Abstract help"}


@pytest.mark.django_db
def test_update_field_order_creates_new_fields(event):
    with scope(event=event):
        event.cfp_flow.update_field_order("info", ["title", "new_field", "abstract"])
        flow = CfPFlow(event)
        step_config = flow.get_step_config("info")
        keys = [f["key"] for f in step_config["fields"]]
        assert keys == ["title", "new_field", "abstract"]
        assert step_config["fields"][1] == {"key": "new_field"}


@pytest.mark.django_db
def test_update_field_order_creates_step_if_missing(event):
    with scope(event=event):
        event.cfp_flow.update_field_order("newstep", ["field1", "field2"])
        flow = CfPFlow(event)
        step_config = flow.get_step_config("newstep")
        keys = [f["key"] for f in step_config["fields"]]
        assert keys == ["field1", "field2"]


@pytest.mark.parametrize(
    ("visibility", "expect_hide_optional"),
    (
        ("required", True),
        ("optional", False),
    ),
)
@pytest.mark.django_db
def test_speaker_profile_form_avatar_required_matches_cfp(
    event, speaker, visibility, expect_hide_optional
):
    with scope(event=event):
        event.cfp.fields["avatar"] = {"visibility": visibility}
        event.cfp.save()
        form = SpeakerProfileForm(event=event, user=speaker)
        # Field itself is never required (gravatar checkbox is an alternative)
        assert form.fields["avatar"].required is False
        # Widget has hide-optional class when avatar is required
        widget_class = form.fields["avatar"].widget.attrs.get("class", "")
        assert ("hide-optional" in widget_class) is expect_hide_optional
