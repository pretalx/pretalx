from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.common.forms.widgets import MarkdownWidget

from .models import FixedSession


class SpeakerChoiceSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.choices = [
            ("unknown", _("Speaker chooses")),
            ("true", _("Yes")),
            ("false", _("No")),
        ]


class FixedSessionForm(forms.ModelForm):
    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        tracks = event.tracks.all()
        if tracks.exists():
            self.fields["track"].queryset = tracks
        else:
            self.fields.pop("track")

    class Meta:
        model = FixedSession
        fields = ["title", "abstract", "description", "track", "do_not_record"]
        widgets = {
            "abstract": MarkdownWidget(attrs={"rows": 3}),
            "description": MarkdownWidget(),
            "do_not_record": SpeakerChoiceSelect(),
        }
        # Track is a scoped model: the default field would query it when this
        # class is defined, which fails outside an event scope
        field_classes = {"track": SafeModelChoiceField}


class NewFixedSessionForm(FixedSessionForm):
    """Creates the session type together with its fixed content."""

    name = forms.CharField(
        max_length=100,
        label=_("Session type name"),
        help_text=_("Shown to speakers when they choose a session type."),
    )
    default_duration = forms.IntegerField(
        min_value=1, initial=60, label=_("Duration"), help_text=_("Duration in minutes")
    )
    field_order = ["name", "default_duration"]

    def save(self, commit=True):
        from pretalx.submission.models import SubmissionType

        self.instance.submission_type = SubmissionType.objects.create(
            event=self.event,
            name=self.cleaned_data["name"],
            default_duration=self.cleaned_data["default_duration"],
        )
        return super().save(commit=commit)
