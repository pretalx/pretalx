# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.fields import I18nFormField, I18nTextarea

from pretalx.common.forms.mixins import (
    HierarkeyMixin,
    JsonSubfieldMixin,
    PretalxI18nFormMixin,
    PretalxI18nModelForm,
    ReadOnlyFlag,
)
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.common.text.phrases import phrases
from pretalx.submission.domain.review import update_review_score
from pretalx.submission.models import (
    Review,
    ReviewPhase,
    ReviewScore,
    ReviewScoreCategory,
)
from pretalx.submission.validators.review import validate_review_scores_present


class ReviewSettingsForm(
    ReadOnlyFlag, PretalxI18nFormMixin, HierarkeyMixin, JsonSubfieldMixin, forms.Form
):
    use_submission_comments = forms.BooleanField(
        label=_("Enable submission comments"),
        help_text=_(
            "Allow organisers and reviewers to comment on submissions, separate from reviews."
        ),
        required=False,
    )
    score_mandatory = forms.BooleanField(
        label=_("Require a review score"), required=False
    )
    text_mandatory = forms.BooleanField(
        label=_("Require a review text"), required=False
    )
    score_format = forms.ChoiceField(
        label=pgettext_lazy("review setting: how scores are shown", "Score display"),
        required=True,
        choices=(
            ("words_numbers", _("Text and score, e.g “Good (3)”")),
            ("numbers_words", _("Score and text, e.g “3 (good)”")),
            ("numbers", _("Just scores")),
            ("words", _("Just text")),
        ),
        initial="words_numbers",
        help_text=_(
            "This is how the score will look like on the review interface. The dashboard will always show numerical scores."
        ),
        widget=forms.RadioSelect,
    )
    aggregate_method = forms.ChoiceField(
        label=_("Score aggregation method"),
        required=True,
        choices=(("median", _("Median")), ("mean", _("Average (mean)"))),
        widget=forms.RadioSelect,
    )
    review_help_text = I18nFormField(
        label=_("Help text for reviewers"),
        help_text=_(
            "This text will be shown at the top of every review, as long as reviews can be created or edited."
        )
        + " "
        + phrases.base.use_markdown,
        widget=I18nTextarea,
        required=False,
    )

    class Media:
        js = [forms.Script("orga/js/forms/reviewsettings.js", defer="")]

    class Meta:
        json_fields = {
            "score_mandatory": "review_settings",
            "text_mandatory": "review_settings",
            "aggregate_method": "review_settings",
            "score_format": "review_settings",
            "use_submission_comments": "feature_flags",
        }
        hierarkey_fields = ("review_help_text",)


class ReviewPhaseForm(PretalxI18nModelForm):
    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)

        if event and not event.get_feature_flag("speakers_can_edit_submissions"):
            self.fields["speakers_can_change_submissions"].disabled = True
            self.fields["speakers_can_change_submissions"].initial = False
            link_tag = f'<a href="{event.cfp.urls.text}">{_("Change this in the CfP settings")}</a>'
            help_text = _(
                "Speaker editing is currently disabled at the event level. "
                "{link_tag} to enable speaker editing."
            ).format(link_tag=link_tag)
            help_text = f'<span class="text-danger">{help_text}</span>'
            self.fields["speakers_can_change_submissions"].help_text = help_text

    class Meta:
        model = ReviewPhase
        fields = [
            "name",
            "start",
            "end",
            "can_review",
            "proposal_visibility",
            "can_see_speaker_names",
            "can_see_reviewer_names",
            "can_change_submission_state",
            "can_see_other_reviews",
            "can_tag_submissions",
            "speakers_can_change_submissions",
        ]


def strip_zeroes(value):
    if not isinstance(value, Decimal):
        return value
    value = str(value)
    return Decimal(value.rstrip("0"))


class ReviewScoreCategoryForm(PretalxI18nModelForm):
    new_scores = forms.CharField(required=False, initial="")

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        if not event or not event.has_active_tracks:
            self.fields.pop("limit_tracks")
        else:
            self.fields["limit_tracks"].queryset = event.tracks.all()
        ids = self.data.get(self.prefix + "-new_scores")
        self.new_label_ids = ids.strip(",").split(",") if ids else []
        for label_id in self.new_label_ids:
            self._add_score_fields(label_id=label_id)

        self.label_fields = []
        if self.instance.id:
            scores = self.instance.scores.all()
            for score in scores:
                self.label_fields.append(
                    {
                        "score": score,
                        "label_field": score._meta.get_field("label").formfield(
                            initial=score.label
                        ),
                        "value_field": score._meta.get_field("value").formfield(
                            initial=strip_zeroes(score.value), required=False
                        ),
                    }
                )
        for score in self.label_fields:
            score_id = score["score"].id
            self.fields[f"value_{score_id}"] = score["value_field"]
            self.fields[f"label_{score_id}"] = score["label_field"]

    def _add_score_fields(self, label_id):
        self.fields[f"value_{label_id}"] = ReviewScore._meta.get_field(
            "value"
        ).formfield()
        self.fields[f"label_{label_id}"] = ReviewScore._meta.get_field(
            "label"
        ).formfield()

    def get_label_fields(self):
        for score in self.label_fields:
            score_id = score["score"].id
            yield (self[f"value_{score_id}"], self[f"label_{score_id}"])

    @property
    def affects_review_scores(self):
        """Whether saving this form would change Review.score for existing reviews."""
        if self.cleaned_data.get("DELETE"):
            return not self.instance.is_independent
        watched = {"weight", "active", "is_independent", "limit_tracks"} | {
            f"value_{entry['score'].id}" for entry in self.label_fields
        }
        return bool(watched.intersection(self.changed_data))

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        for score in self.label_fields:
            score_id = score["score"].id
            if any(f"_{score_id}" in changed for changed in self.changed_data):
                value = self.cleaned_data.get(f"value_{score_id}")
                label = self.cleaned_data.get(f"label_{score_id}")
                if value is None or value == "":
                    score["score"].delete()
                else:
                    score["score"].value = value
                    score["score"].label = label
                    score["score"].save()
        for score in self.new_label_ids:
            value = self.cleaned_data.get(f"value_{score}")
            label = self.cleaned_data.get(f"label_{score}")
            if (value is not None) and label:
                ReviewScore.objects.create(category=instance, value=value, label=label)
        return instance

    class Meta:
        model = ReviewScoreCategory
        fields = (
            "name",
            "is_independent",
            "weight",
            "required",
            "active",
            "limit_tracks",
        )
        field_classes = {"limit_tracks": SafeModelMultipleChoiceField}
        widgets = {"limit_tracks": EnhancedSelectMultiple(color_field="color")}


class ReviewForm(ReadOnlyFlag, forms.ModelForm):
    def __init__(
        self,
        event,
        user,
        *args,
        instance=None,
        categories=None,
        submission=None,
        default_renderer=None,
        **kwargs,
    ):
        self.event = event
        self.user = user
        self.categories = categories
        self.submission = submission
        self.default_renderer = default_renderer or self.default_renderer

        super().__init__(*args, instance=instance, **kwargs)

        self.fields["text"].required = self.event.review_settings["text_mandatory"]
        self.scores = (
            {
                score.category: str(score.id)
                for score in self.instance.scores.select_related("category")
            }
            if self.instance.id
            else {}
        )
        for category in categories:
            self.fields[f"score_{category.id}"] = self.build_score_field(
                category,
                read_only=kwargs.get("read_only", False),
                initial=self.scores.get(category),
                hide_optional=self.event.review_settings["score_mandatory"],
            )
        self.fields["text"].widget.attrs["rows"] = 2

    def build_score_field(
        self, category, read_only=False, initial=None, hide_optional=False
    ):
        choices = [("-", _("No score"))] if not category.required else []
        choices.extend(
            (
                score.id,
                score.format(
                    self.event.review_settings.get("score_format", "words_numbers")
                ),
            )
            for score in category.scores.all()
        )

        field = forms.ChoiceField(
            choices=choices,
            required=category.required,
            widget=forms.RadioSelect,
            disabled=read_only,
            initial=initial,
            label=category.name,
        )
        field.widget.attrs["autocomplete"] = "off"
        if hide_optional:
            field.widget.attrs["class"] = "hide-optional"
        return field

    def get_score_fields(self):
        for category in self.categories:
            yield self[f"score_{category.id}"]

    def get_score_field(self, category):
        with suppress(KeyError):
            return self[f"score_{category.id}"]

    def clean(self):
        cleaned_data = super().clean()

        selected_scores = []
        for category in self.categories:
            key = f"score_{category.id}"
            score = cleaned_data.get(key)
            if score not in ("", "-", None):
                selected_scores.append(score)
            if score == "-":
                cleaned_data[key] = ""

        try:
            validate_review_scores_present(self.event, selected_scores)
        except ValidationError as exc:
            self.add_error(None, exc)

        return cleaned_data

    def save(self, *args, **kwargs):
        self.instance.submission = self.submission
        self.instance.user = self.user
        instance = super().save(*args, **kwargs)
        current_scores = []
        for category in self.categories:
            score_id = self.cleaned_data.get(f"score_{category.id}")
            if score_id:
                current_scores.append(score_id)
        instance.scores.set(current_scores)
        update_review_score(instance)
        return instance

    class Media:
        js = [forms.Script("orga/js/forms/review.js", defer="")]

    class Meta:
        model = Review
        fields = ("text",)
