from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DeleteView, DetailView, TemplateView, UpdateView
from django_context_decorator import context

from pretalx.common.mail import SendMailException
from pretalx.common.mixins.views import PermissionRequired
from pretalx.common.views import CreateOrUpdateView
from pretalx.event.forms import OrganiserForm, TeamForm, TeamInviteForm, TeamTrackForm
from pretalx.event.models import Organiser, Team, TeamInvite


class TeamMixin:
    def get_queryset(self):
        return Team.objects.filter(organiser=self.request.organiser)


class TeamDetail(PermissionRequired, TeamMixin, CreateOrUpdateView):
    permission_required = 'orga.change_teams'
    template_name = 'orga/settings/team_detail.html'
    form_class = TeamForm
    model = Team

    def get_permission_object(self):
        return self.request.organiser

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organiser'] = self.request.organiser
        return kwargs

    def get_object(self):
        if 'pk' not in self.kwargs:
            return None
        return self.get_queryset().filter(pk=self.kwargs.get('pk')).first()

    @context
    @cached_property
    def invite_form(self):
        is_bound = (
            self.request.method == 'POST' and self.request.POST.get('form') == 'invite'
        )
        return TeamInviteForm(self.request.POST if is_bound else None)

    def post(self, *args, **kwargs):
        if self.invite_form.is_bound:
            if self.invite_form.is_valid():
                invite = TeamInvite.objects.create(
                    team=self.get_object(),
                    email=self.invite_form.cleaned_data['email'].lower().strip(),
                )
                invite.send(event=None)
                messages.success(self.request, _('The invitation has been sent.'))
            else:
                return self.form_invalid(*args, **kwargs)
            return redirect(self.request.path)
        return super().post(*args, **kwargs)

    def form_valid(self, form):
        created = not bool(form.instance.pk)
        form.save()
        messages.success(self.request, _('The settings have been saved.'))
        if created:
            return redirect(self.request.organiser.orga_urls.base)
        return redirect(self.request.path)


class TeamTracks(PermissionRequired, TeamMixin, UpdateView):
    permission_required = 'orga.change_teams'
    template_name = 'orga/settings/team_tracks.html'
    form_class = TeamTrackForm
    model = Team
    context_object_name = 'team'

    def get_permission_object(self):
        return self.request.organiser

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organiser'] = self.request.organiser
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _('The settings have been saved.'))
        return redirect(self.object.orga_urls.base)


class TeamDelete(PermissionRequired, TeamMixin, DetailView):
    permission_required = 'orga.change_teams'
    template_name = 'orga/settings/team_delete.html'

    def get_permission_object(self):
        return self.request.organiser

    @context
    @cached_property
    def team(self):
        return get_object_or_404(Team, pk=self.kwargs['pk'])

    def get_object(self):
        if 'user_pk' in self.kwargs:
            return self.team.members.filter(pk=self.kwargs.get('user_pk')).first()
        return self.team

    @context
    def member(self, **kwargs):
        member = self.get_object()
        return member if member != self.team else None

    def post(self, request, *args, **kwargs):
        if 'user_pk' in self.kwargs:
            self.team.members.remove(self.get_object())
            messages.success(request, _('The member was removed from the team.'))
        else:
            self.get_object().delete()
            messages.success(request, _('The team was removed.'))
        return redirect(self.request.organiser.orga_urls.base)


class TeamUninvite(PermissionRequired, DetailView):
    model = TeamInvite
    template_name = 'orga/settings/team_delete.html'
    permission_required = 'orga.change_teams'

    def get_permission_object(self):
        return self.request.organiser

    @context
    def team(self):
        return self.object.team

    def post(self, request, *args, **kwargs):
        self.get_object().delete()
        messages.success(request, _('The team invitation was retracted.'))
        return redirect(self.request.organiser.orga_urls.base)


class TeamResetPassword(PermissionRequired, TemplateView):
    model = Team
    template_name = 'orga/settings/team_reset_password.html'
    permission_required = 'orga.change_teams'

    def get_permission_object(self):
        return self.request.organiser

    @context
    @cached_property
    def team(self):
        return get_object_or_404(Team, pk=self.kwargs['pk'])

    @context
    @cached_property
    def user(self):
        return get_object_or_404(self.team.members, pk=self.kwargs['user_pk'])

    def post(self, request, *args, **kwargs):
        try:
            self.user.reset_password(event=None, user=self.request.user)
            messages.success(
                self.request, _('The password was reset and the user was notified.')
            )
        except SendMailException:
            messages.error(
                self.request,
                _(
                    'The password reset email could not be sent, so the password was not reset.'
                ),
            )
        return redirect(self.request.organiser.orga_urls.teams)


class OrganiserDetail(PermissionRequired, CreateOrUpdateView):
    template_name = 'orga/organiser/detail.html'
    model = Organiser
    permission_required = 'orga.change_organiser_settings'
    form_class = OrganiserForm

    def get_object(self):
        return getattr(self.request, 'organiser', None)

    def get_success_url(self):
        messages.success(self.request, _('Saved!'))
        return self.request.path


class OrganiserDelete(PermissionRequired, DeleteView):
    template_name = 'orga/organiser/delete.html'
    permission_required = 'person.is_administrator'
    model = Organiser

    def get_object(self):
        return getattr(self.request, 'organiser', None)

    def delete(self, request, *args, **kwargs):
        organiser = self.get_object()
        if organiser:
            organiser.shred()
        return HttpResponseRedirect('/orga/')
