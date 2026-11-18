from django import forms
from django.utils.translation import gettext_lazy as _

from .resubmit import submission_types_for, tracks_for


class ResubmitForm(forms.Form):
    """The parts of a proposal that are specific to the new event."""

    submission_type = forms.ModelChoiceField(
        queryset=None, label=_("Session type"), empty_label=None
    )
    track = forms.ModelChoiceField(queryset=None, label=_("Track"), required=False)
    content_locale = forms.ChoiceField(label=_("Language"))

    def __init__(self, *args, event, source, **kwargs):
        super().__init__(*args, **kwargs)
        types = submission_types_for(event)
        self.fields["submission_type"].queryset = types
        self.fields["submission_type"].initial = _matching(
            types, source.submission_type
        )

        if event.has_active_tracks:
            tracks = tracks_for(event)
            self.fields["track"].queryset = tracks
            self.fields["track"].required = bool(event.cfp.require_track)
            self.fields["track"].initial = _matching(tracks, source.track)
        else:
            del self.fields["track"]

        locales = event.named_content_locales
        self.fields["content_locale"].choices = locales
        codes = [code for code, _name in locales]
        self.fields["content_locale"].initial = (
            source.content_locale if source.content_locale in codes else codes[0]
        )
        if len(locales) == 1:
            self.fields["content_locale"].widget = forms.HiddenInput()


def _matching(queryset, original):
    """The option named like the one the original proposal used, if any."""
    if not original:
        return None
    name = str(original.name).strip().lower()
    for option in queryset:
        if str(option.name).strip().lower() == name:
            return option.pk
    return None
