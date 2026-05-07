# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField, SafeModelMultipleChoiceField

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import EnhancedSelect, EnhancedSelectMultiple
from pretalx.common.text.phrases import phrases
from pretalx.event.models import Event
from pretalx.person.domain.queries.profile import filter_by_accepted_role
from pretalx.submission.models import Question

ROLE_CHOICES = (
    ("speaker", phrases.schedule.speakers),
    ("submitter", _("Non-accepted submitters")),
)


class SpeakerFilterForm(forms.Form):
    """Filters the per-event SpeakerProfile list."""

    default_renderer = InlineFormRenderer

    role = forms.ChoiceField(
        choices=(("", _("Submitters and speakers")), *ROLE_CHOICES),
        required=False,
        widget=EnhancedSelect,
    )
    arrived = forms.ChoiceField(
        choices=(
            ("", _("Any arrival status")),
            ("true", _("Marked as arrived")),
            ("false", _("Not yet arrived")),
        ),
        required=False,
        widget=EnhancedSelect,
    )
    fulltext = forms.BooleanField(required=False, label=_("Full text search"))
    question = SafeModelChoiceField(
        queryset=Question.objects.none(), required=False, widget=forms.HiddenInput()
    )

    def __init__(self, *args, event=None, filter_arrival=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.fields["question"].queryset = event.questions.all()
        if not filter_arrival:
            self.fields.pop("arrived")

    def filter_queryset(self, queryset):
        data = self.cleaned_data
        queryset = filter_by_accepted_role(queryset, data.get("role"))
        if has_arrived := data.get("arrived"):
            queryset = queryset.filter(has_arrived=(has_arrived == "true"))
        return queryset

    class Media:
        js = [forms.Script("orga/js/forms/fulltext-toggle.js", defer="")]
        css = {"all": ["orga/css/forms/search.css"]}


class UserSpeakerFilterForm(forms.Form):
    """Filters the cross-event Organiser speaker list (a User queryset)."""

    default_renderer = InlineFormRenderer

    role = forms.ChoiceField(
        choices=(*ROLE_CHOICES, ("all", phrases.base.all_choices)),
        required=False,
        widget=EnhancedSelect,
    )
    events = SafeModelMultipleChoiceField(
        queryset=Event.objects.none(), required=False, widget=EnhancedSelectMultiple
    )

    def __init__(self, *args, events=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = events
        if len(events) > 1:
            self.fields["events"].queryset = events
        else:
            self.fields.pop("events")

    def filter_queryset(self, qs):
        data = self.cleaned_data
        # Empty role here means "show speakers" — the dropdown's first option,
        # not "no filter"; that's what the explicit 'all' choice is for.
        role = data.get("role") or "speaker"
        if events := data.get("events"):
            qs = qs.filter(profiles__event__in=events)
        qs = filter_by_accepted_role(qs, role)
        return qs.order_by("id").distinct()

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}


__all__ = ["SpeakerFilterForm", "UserSpeakerFilterForm"]
