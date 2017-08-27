from django.views.generic import DetailView

from pretalx.cfp.views.event import EventPageMixin
from pretalx.person.models import User


class SpeakerView(EventPageMixin, DetailView):
    context_object_name = 'speaker'
    model = User
    slug_field = 'nick'
    template_name = 'agenda/speaker.html'

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['speaker'] = self.object
        ctx['submissions'] = self.request.event.submissions.filter(speakers__in=[self.object])
        return ctx
