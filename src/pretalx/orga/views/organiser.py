# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: bithive

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView
from django_context_decorator import context
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.common.text.phrases import phrases
from pretalx.common.ui import Button, delete_link
from pretalx.common.views.generic import (
    CreateOrUpdateView,
    OrgaCRUDView,
    OrgaTableMixin,
)
from pretalx.common.views.mixins import (
    ActionConfirmMixin,
    Filterable,
    PermissionRequired,
)
from pretalx.event.domain.organiser import shred_organiser
from pretalx.event.domain.queries.team import speaker_access_events_for_user
from pretalx.event.domain.team import (
    create_team_invites,
    remove_team_member,
    retract_team_invite,
    send_team_invite,
)
from pretalx.event.interfaces.forms import OrganiserForm, TeamForm, TeamInviteForm
from pretalx.event.models.organiser import Organiser, Team, TeamInvite
from pretalx.event.validators.organiser import check_access_permissions
from pretalx.orga.tables.organiser import TeamTable
from pretalx.orga.tables.speaker import SpeakerOrgaTable
from pretalx.person.domain.queries.profile import annotate_user_submission_counts
from pretalx.person.domain.queries.user import submitter_users_for_events
from pretalx.person.domain.user import reset_password
from pretalx.person.interfaces.forms import UserSpeakerFilterForm
from pretalx.person.models import User


class TeamView(OrgaCRUDView):
    model = Team
    form_class = TeamForm
    table_class = TeamTable
    template_namespace = "orga/organiser"
    url_name = "organiser.teams"
    context_object_name = "team"
    permission_required = "event.update_team"
    create_button_label = _("New team")

    def get_queryset(self):
        return (
            self.request.organiser.teams.all()
            .annotate(member_count=Count("members"))
            .prefetch_related("members")
            .order_by("-all_events", "name")
        )

    def get_permission_required(self):
        return self.permission_required

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organiser"] = self.request.organiser
        return kwargs

    def get_success_url(self):
        if self.invite_form:
            return self.reverse("update", instance=self.object)
        return self.reverse("list")

    def get_generic_permission_object(self):
        return self.request.organiser

    def get_generic_title(self, instance=None):
        if instance:
            return (
                phrases.orga.team
                + f" {phrases.base.quotation_open}{instance.name}{phrases.base.quotation_close}"
            )
        if self.action == "create":
            return _("New team")
        return _("Teams")

    @context
    @cached_property
    def invite_form(self):
        if self.action not in ("update", "detail") or not self.object:
            return None
        is_bound = (
            self.request.method == "POST" and self.request.POST.get("form") == "invite"
        )
        return TeamInviteForm(self.request.POST if is_bound else None, prefix="invite")

    def get_deletion_blocked_reason(self):
        try:
            check_access_permissions(self.request.organiser, exclude_team=self.object)
        except ValidationError as exc:
            return " ".join(exc.messages)
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.action == "update":
            context["invite_form"] = self.invite_form
            context["members"] = self.object.members.order_by("name")
            context["invites"] = self.object.invites.all()
            # Viewing this page already requires the can_change_teams
            # predicate, which is also what permits deletion, so the delete
            # button is always shown here (disabled when deletion would break
            # the organiser's required team coverage).
            context["submit_buttons_extra"] = [
                self.get_back_button(),
                delete_link(
                    self.object.orga_urls.delete,
                    disabled=self.get_deletion_blocked_reason(),
                ),
            ]
        return context

    def invite_form_handler(self, request):
        if self.invite_form.is_valid():
            invites = create_team_invites(
                team=self.object, emails=self.invite_form.cleaned_data["emails"]
            )
            if len(invites) == 1:
                messages.success(self.request, _("The invitation has been sent."))
            else:
                messages.success(self.request, _("The invitations have been sent."))
            return redirect(self.request.path)
        for error in self.invite_form.errors.values():
            messages.error(self.request, "\n".join(error))
        return self.form_invalid(self.get_form(instance=self.object))

    def form_handler(self, request, *args, **kwargs):
        if self.action == "update" and request.POST.get("form") == "invite":
            return self.invite_form_handler(request)
        return super().form_handler(request, *args, **kwargs)

    def form_valid(self, form):
        if self.action == "create":
            form.instance.organiser = self.request.organiser
            return super().form_valid(form)
        warnings = []
        try:
            with transaction.atomic():
                form.instance.organiser = self.request.organiser
                result = super().form_valid(form)
                warnings = check_access_permissions(self.request.organiser)
        except (ValidationError, IntegrityError) as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        if warnings:
            for warning in warnings:
                messages.warning(self.request, warning)
        return result

    def perform_delete(self):
        warnings = []
        with transaction.atomic():
            self.object.log_action(
                "pretalx.team.delete", person=self.request.user, orga=True
            )
            self.object.invites.all().delete()
            self.object.delete()
            warnings = check_access_permissions(self.request.organiser)
            messages.success(self.request, _("The team was removed."))

        if warnings:
            for warning in warnings:
                messages.warning(self.request, warning)
        return True

    @transaction.atomic
    def delete_handler(self, request, *args, **kwargs):
        """POST handler for delete view"""
        pk = self.object.pk
        try:
            return super().delete_handler(request, *args, **kwargs)
        except (ValidationError, IntegrityError) as exc:
            messages.error(self.request, str(exc))
        self.object.pk = pk
        return redirect(self.reverse("update", instance=self.object))


class InviteMixin(PermissionRequired):
    permission_required = "event.update_team"
    model = TeamInvite

    def get_permission_object(self):
        return self.request.organiser

    @cached_property
    def invite(self):
        return self.get_object()

    def get_object(self):
        return get_object_or_404(
            TeamInvite.objects.filter(
                team__organiser=self.request.organiser, team__pk=self.kwargs["pk"]
            ),
            pk=self.kwargs["invite_pk"],
        )

    @cached_property
    def team(self):
        return self.invite.team


class TeamUninvite(InviteMixin, ActionConfirmMixin, DetailView):
    action_title = _("Retract invitation")
    action_text = _("Are you sure you want to retract the invitation to this user?")

    def action_object_name(self):
        return self.invite.email

    @property
    def action_back_url(self):
        return self.team.orga_urls.base

    def post(self, request, *args, **kwargs):
        team = self.team
        retract_team_invite(self.invite, actor=self.request.user)
        messages.success(request, _("The team invitation was retracted."))
        return redirect(team.orga_urls.base)


class TeamResend(InviteMixin, ActionConfirmMixin, DetailView):
    action_title = _("Resend invite")
    action_text = _("Are you sure you want to resend the invitation to this user?")
    action_confirm_color = "success"
    action_confirm_icon = "envelope"
    action_confirm_label = phrases.base.send

    def action_object_name(self):
        return self.invite.email

    @property
    def action_back_url(self):
        return self.team.orga_urls.base

    def post(self, request, *args, **kwargs):
        send_team_invite(self.invite)
        messages.success(request, _("The team invitation was sent again."))
        return redirect(self.team.orga_urls.base)


class TeamMemberMixin(PermissionRequired):
    permission_required = "event.update_team"

    def get_permission_object(self):
        return self.request.organiser

    @cached_property
    def team(self):
        return get_object_or_404(
            self.request.organiser.teams.all(), pk=self.kwargs["team_pk"]
        )

    def get_object(self, queryset=None):
        return get_object_or_404(self.team.members.all(), pk=self.kwargs["user_pk"])

    @context
    @cached_property
    def member(self):
        return self.get_object()

    @property
    def action_back_url(self):
        return self.team.orga_urls.base

    def action_object_name(self):
        return f"{self.member.get_display_name()} ({self.member.email})"


class TeamMemberDelete(TeamMemberMixin, ActionConfirmMixin, DetailView):
    def post(self, request, *args, **kwargs):
        warnings = []
        try:
            with transaction.atomic():
                remove_team_member(
                    team=self.team, member=self.member, actor=self.request.user
                )
                warnings = check_access_permissions(self.request.organiser)
                messages.success(request, _("The member was removed from the team."))
        except (ValidationError, IntegrityError) as e:
            messages.error(request, str(e))
            return redirect(self.action_back_url)

        if warnings:
            for warning in warnings:
                messages.warning(request, warning)
        return redirect(self.action_back_url)


class TeamResetPassword(TeamMemberMixin, ActionConfirmMixin, TemplateView):
    action_confirm_icon = "key"
    action_confirm_label = phrases.base.password_reset_heading
    action_title = phrases.base.password_reset_heading
    action_text = phrases.base.password_reset_confirm

    def post(self, request, *args, **kwargs):
        user_to_reset = self.member
        try:
            reset_password(user_to_reset, event=None, log_actor=self.request.user)
            messages.success(self.request, phrases.orga.password_reset_success)
        except SendMailException:
            messages.error(self.request, phrases.orga.password_reset_fail)
        return redirect(self.action_back_url)


class OrganiserDetail(PermissionRequired, CreateOrUpdateView):
    template_name = "orga/organiser/detail.html"
    model = Organiser
    permission_required = "event.update_organiser"
    write_permission_required = "event.update_organiser"
    form_class = OrganiserForm

    def get_object(self, queryset=None):
        return getattr(self.request, "organiser", None)

    @cached_property
    def object(self):
        return self.get_object()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_administrator and (
            organiser := getattr(self.request, "organiser", None)
        ):
            context["submit_buttons_extra"] = [delete_link(organiser.orga_urls.delete)]
        context["submit_buttons"] = [Button()]
        return context

    def get_permission_object(self):
        return self.object

    def get_success_url(self):
        return self.request.path


class OrganiserDelete(PermissionRequired, ActionConfirmMixin, DetailView):
    permission_required = "person.administrator_user"
    model = Organiser
    action_text = (
        _(
            "ALL related data for ALL events, such as proposals, and speaker profiles, and uploads, "
            "will also be deleted and cannot be restored."
        )
        + " "
        + phrases.base.delete_warning
    )

    def get_object(self, queryset=None):
        return self.request.organiser

    def get_permission_object(self, queryset=None):
        return self.request.user

    def action_object_name(self):
        return _("Organiser") + f": {self.get_object().name}"

    @property
    def action_back_url(self):
        return self.get_object().orga_urls.settings

    def post(self, *args, **kwargs):
        organiser = self.get_object()
        shred_organiser(organiser, person=self.request.user)
        messages.success(
            self.request, _("The organiser and all related data have been deleted.")
        )
        return HttpResponseRedirect(reverse("orga:event.list"))


@method_decorator(scopes_disabled(), "dispatch")
class OrganiserSpeakerList(PermissionRequired, Filterable, OrgaTableMixin, ListView):
    template_name = "orga/organiser/speaker_list.html"
    permission_required = "event.view_organiser"
    context_object_name = "speakers"
    table_class = SpeakerOrgaTable
    default_filters = ("email__icontains", "name__icontains")
    pagination_class = Paginator

    def get_permission_object(self):
        return self.request.organiser

    def get_filter_form(self):
        return UserSpeakerFilterForm(self.request.GET, events=self.events)

    @context
    @cached_property
    def events(self):
        return speaker_access_events_for_user(user=self.request.user).filter(
            organiser=self.request.organiser
        )

    def get_queryset(self):
        return self.filter_queryset(
            annotate_user_submission_counts(
                User.objects.filter(profiles__event__in=self.events).prefetch_related(
                    "profiles", "profiles__event"
                ),
                events=self.events,
            )
        )

    def get(self, request, *args, **kwargs):
        # Eagerly evaluate the queryset while scopes_disabled is active
        # (TemplateResponse renders after dispatch returns, outside the scope).
        # Using a list also lets the table and context share one evaluation.
        self.object_list = list(self.get_queryset())
        context = self.get_context_data()
        return self.render_to_response(context)

    def get_table(self, *args, **kwargs):
        table = super().get_table(*args, **kwargs)
        len(
            table.paginated_rows
        )  # access property to force fetching while scopes disabled
        return table

    def get_table_data(self):
        if hasattr(self, "object_list"):
            return self.object_list
        return self.get_queryset()


def speaker_search(request, *args, **kwargs):
    search = request.GET.get("search")
    if not search or len(search) < 3:
        return JsonResponse({"count": 0, "results": []})

    with scopes_disabled():
        events = speaker_access_events_for_user(user=request.user).filter(
            organiser=request.organiser
        )
        users = list(
            submitter_users_for_events(events).filter(
                Q(name__icontains=search) | Q(email__icontains=search)
            )[:8]
        )

    return JsonResponse(
        {
            "count": len(users),
            "results": [{"email": user.email, "name": user.name} for user in users],
        }
    )
