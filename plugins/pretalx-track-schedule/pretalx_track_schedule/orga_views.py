from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.generic import FormView

from pretalx.common.views.mixins import EventPermissionRequired

from .forms import ColorSettingsForm
from .views import PLUGIN

SETTINGS_PERMISSION = "event.update_event"


class ColorSettingsView(EventPermissionRequired, FormView):
    template_name = "pretalx_track_schedule/settings.html"
    permission_required = SETTINGS_PERMISSION
    form_class = ColorSettingsForm

    def dispatch(self, request, *args, **kwargs):
        if PLUGIN not in request.event.plugin_list:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "event": self.request.event}

    def form_valid(self, form):
        question = form.save()
        shown = form.fields["question"].initial
        if question and getattr(shown, "pk", None) != question.pk:
            messages.info(
                self.request,
                _("Saved with default colours; change them below if you like."),
            )
        else:
            messages.success(self.request, _("Saved."))
        return redirect(self.request.path)
