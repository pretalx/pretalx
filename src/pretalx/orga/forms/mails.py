# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict
from contextlib import suppress

from django import forms
from django.db import transaction
from django.db.models import Count, Q
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from pretalx.common.exceptions import SendMailException
from pretalx.common.forms.fields import CountableOption
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.renderers import InlineFormRenderer, TabularFormRenderer
from pretalx.common.forms.widgets import (
    EnhancedSelectMultiple,
    MultiEmailInput,
    SelectMultipleWithCount,
)
from pretalx.common.language import language
from pretalx.common.text.phrases import phrases
from pretalx.mail.context import get_available_placeholders, get_invalid_placeholders
from pretalx.mail.models import MailTemplate, QueuedMail, QueuedMailStates
from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.forms import SubmissionFilterForm
from pretalx.submission.models import Track


class MailTemplateForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, event=None, **kwargs):
        self.event = getattr(self, "event", None) or event
        if self.event:
            kwargs["locales"] = self.event.locales
        super().__init__(*args, **kwargs)
        self.fields["subject"].required = True
        self.fields["text"].required = True

    def get_valid_placeholders(self, **kwargs):
        if not getattr(self.instance, "event", None):
            self.instance.event = self.event
        return self.instance.valid_placeholders

    @cached_property
    def valid_placeholders(self):
        return self.get_valid_placeholders()

    @cached_property
    def grouped_placeholders(self):
        placeholders = self.get_valid_placeholders(ignore_data=True)
        grouped = defaultdict(list)
        specificity = ["slot", "submission", "user", "event", "other"]
        for placeholder in placeholders.values():
            if not placeholder.is_visible:
                continue
            placeholder.rendered_sample = escape(placeholder.render_sample(self.event))
            for arg in specificity:
                if arg in placeholder.required_context:
                    grouped[arg].append(placeholder)
                    break
            else:
                grouped["other"].append(placeholder)
        return grouped

    def clean_subject(self):
        text = self.cleaned_data["subject"]
        try:
            warnings = get_invalid_placeholders(text, self.valid_placeholders)
        except Exception:
            raise forms.ValidationError(
                _(
                    "Invalid email template! "
                    "Please check that you don’t have stray { or } somewhere, "
                    "and that there are no spaces inside the {} blocks."
                )
            ) from None
        if warnings:
            warnings = ", ".join("{" + warning + "}" for warning in warnings)
            raise forms.ValidationError(str(_("Unknown placeholder!")) + " " + warnings)
        return text

    def clean_text(self):
        text = self.cleaned_data["text"]
        try:
            warnings = get_invalid_placeholders(text, self.valid_placeholders)
        except Exception:
            raise forms.ValidationError(
                _(
                    "Invalid email template! "
                    "Please check that you don’t have stray { or } somewhere, "
                    "and that there are no spaces inside the {} blocks."
                )
            ) from None
        if warnings:
            warnings = ", ".join("{" + warning + "}" for warning in warnings)
            raise forms.ValidationError(str(_("Unknown placeholder!")) + " " + warnings)

        from bs4 import BeautifulSoup  # noqa: PLC0415

        from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415
            render_markdown_abslinks,
        )

        for locale in self.event.locales:
            with language(locale):
                message = text.localize(locale)
                preview_text = render_markdown_abslinks(
                    message.format_map(
                        {
                            key: escape(value.render_sample(self.event))
                            for key, value in self.valid_placeholders.items()
                        }
                    )
                )
                doc = BeautifulSoup(preview_text, "lxml")
                for link in doc.find_all("a"):
                    if link.attrs.get("href") in (None, "", "http://", "https://"):
                        raise forms.ValidationError(
                            _(
                                "You have an empty link in your email, labeled “{text}”!"
                            ).format(text=link.text)
                        )
        return text

    class Media:
        css = {"all": ["orga/css/forms/email.css"]}

    class Meta:
        model = MailTemplate
        fields = ["subject", "text", "reply_to", "bcc"]
        widgets = {"bcc": MultiEmailInput, "reply_to": MultiEmailInput}


class MailDetailForm(ReadOnlyFlag, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance or not self.instance.to_users.all().count():
            self.fields.pop("to_users")
        else:
            self.fields["to_users"].queryset = User.objects.filter(
                profiles__in=self.instance.event.submitters
            ).distinct()
            self.fields["to_users"].required = False

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)
        if not cleaned_data["to"] and not cleaned_data.get("to_users"):
            self.add_error(
                "to",
                forms.ValidationError(
                    _("An email needs to have at least one recipient.")
                ),
            )
        return cleaned_data

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        if self.has_changed() and "to" in self.changed_data:
            addresses = list(
                {
                    address.strip().lower()
                    for address in (obj.to or "").split(",")
                    if address.strip()
                }
            )
            found_addresses = []
            for address in addresses:
                user = User.objects.filter(email__iexact=address).first()
                if user:
                    obj.to_users.add(user)
                    found_addresses.append(address)
            addresses = set(addresses) - set(found_addresses)
            addresses = ",".join(addresses) if addresses else ""
            obj.to = addresses
            obj.save()
        return obj

    class Meta:
        model = QueuedMail
        fields = ["to", "to_users", "reply_to", "cc", "bcc", "subject", "text"]
        widgets = {
            "to_users": EnhancedSelectMultiple,
            "to": MultiEmailInput,
            "reply_to": MultiEmailInput,
            "cc": MultiEmailInput,
            "bcc": MultiEmailInput,
        }


class WriteMailBaseForm(MailTemplateForm):
    skip_queue = forms.BooleanField(
        label=_("Send immediately"),
        required=False,
        help_text=_(
            "If you check this, the emails will be sent immediately, instead of being put in the outbox."
        ),
    )

    def __init__(self, *args, may_skip_queue=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not may_skip_queue:
            self.fields.pop("skip_queue", None)

    class Media:
        js = [forms.Script("orga/js/forms/placeholder.js", defer="")]
        css = {"all": ["orga/css/forms/email.css"]}


class WriteTeamsMailForm(WriteMailBaseForm):
    recipients = forms.MultipleChoiceField(
        label=_("Recipient groups"), required=False, widget=EnhancedSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Placing reviewer emails in the outbox would lead to a **ton** of permission
        # issues: who is allowed to see them, who to edit/send them, etc.
        self.fields.pop("skip_queue")

        reviewer_teams = self.event.teams.filter(is_reviewer=True)
        other_teams = self.event.teams.exclude(is_reviewer=True)
        if reviewer_teams and other_teams:
            self.fields["recipients"].choices = [
                (_("Reviewers"), [(team.pk, team.name) for team in reviewer_teams]),
                (_("Other teams"), [(team.pk, team.name) for team in other_teams]),
            ]
        else:
            self.fields["recipients"].choices = [
                (team.pk, team.name) for team in self.event.teams.all()
            ]

    def get_valid_placeholders(self, **kwargs):
        return get_available_placeholders(event=self.event, kwargs=["event", "user"])

    def get_recipients(self):
        recipients = self.cleaned_data.get("recipients")
        teams = self.event.teams.all().filter(pk__in=recipients)
        return User.objects.filter(is_active=True, teams__in=teams)

    @transaction.atomic
    def save(self):
        self.instance.event = self.event
        self.instance.is_auto_created = True
        template = super().save()
        result = []
        users = self.get_recipients()
        for user in users:
            # This happens when there are template errors
            with suppress(SendMailException):
                result.append(
                    template.to_mail(
                        user=user,
                        event=self.event,
                        locale=user.locale,
                        context_kwargs={"user": user, "event": self.event},
                        skip_queue=True,
                        commit=False,
                    )
                )
        return result


class WriteSessionMailForm(SubmissionFilterForm, WriteMailBaseForm):
    default_renderer = TabularFormRenderer

    submissions = forms.MultipleChoiceField(
        required=False,
        label=_("Proposals"),
        help_text=_(
            "Select proposals that should receive the email regardless of the other filters."
        ),
        widget=EnhancedSelectMultiple(attrs={"placeholder": _("Proposals")}),
    )
    speakers = forms.ModelMultipleChoiceField(
        queryset=SpeakerProfile.objects.none(),
        required=False,
        label=phrases.schedule.speakers,
        help_text=_(
            "Select speakers that should receive the email regardless of the other filters."
        ),
        widget=EnhancedSelectMultiple(attrs={"placeholder": phrases.schedule.speakers}),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        initial = kwargs.get("initial", {})
        self.filter_search = initial.get("q")
        question = initial.get("question")
        if question:
            self.filter_question = (
                self.event.questions.all().filter(pk=question).first()
            )
            if self.filter_question:
                self.filter_option = self.filter_question.options.filter(
                    pk=initial.get("answer__options")
                ).first()
                self.filter_answer = initial.get("answer")
                self.filter_unanswered = initial.get("unanswered")
        self.fields["submissions"].choices = [
            (sub.code, sub.title)
            for sub in self.event.submissions.all().order_by("title")
        ]
        speakers_field = self.fields["speakers"]
        speakers_field.queryset = self.event.submitters.all().order_by("name")
        speakers_field.label_from_instance = lambda obj: obj.get_display_name()
        if len(self.event.locales) > 1:
            self.fields["subject"].help_text = _(
                "If you provide only one language, that language will be used for all emails. If you provide multiple languages, the best fit for each speaker will be used."
            )
        self.warnings = []

    def get_valid_placeholders(self, ignore_data=False):
        kwargs = ["event", "user", "submission", "slot"]
        if (
            getattr(self, "cleaned_data", None)
            and not ignore_data
            and self.cleaned_data.get("speakers")
        ):
            kwargs.remove("submission")
            kwargs.remove("slot")
        return get_available_placeholders(event=self.event, kwargs=kwargs)

    def clean(self):
        cleaned_data = super().clean()
        filter_keys = (
            "state",
            "submission_type",
            "content_locale",
            "track",
            "tags",
            "question",
        )
        has_filters = any(cleaned_data.get(key) for key in filter_keys)
        added_submissions = cleaned_data.get("submissions")
        added_speakers = cleaned_data.get("speakers")

        if not has_filters and not added_submissions and not added_speakers:
            raise forms.ValidationError(
                _(
                    "Please select at least one filter or specific proposals/speakers as recipients."
                )
            )

        if has_filters:
            submissions = (
                self.filter_queryset(self.event.submissions)
                .select_related("track", "submission_type", "event")
                .with_sorted_speakers()
            )
        else:
            submissions = self.event.submissions.none()

        if added_submissions:
            specific_submissions = (
                self.event.submissions.filter(code__in=added_submissions)
                .select_related("track", "submission_type", "event")
                .with_sorted_speakers()
            )
            submissions = submissions | specific_submissions

        result = []
        for submission in submissions:
            for slot in submission.current_slots or []:
                result.extend(
                    {"submission": submission, "slot": slot, "user": speaker}
                    for speaker in submission.sorted_speakers
                )
            result.extend(
                {"submission": submission, "user": speaker}
                for speaker in submission.sorted_speakers
            )
        if added_speakers:
            result.extend({"user": user} for user in added_speakers)
        self._recipients = result
        return cleaned_data

    def get_recipients(self):
        return self._recipients

    def clean_question(self):
        return getattr(self, "filter_question", None)

    def clean_answer__options(self):
        return getattr(self, "filter_option", None)

    def clean_answer(self):
        return getattr(self, "filter_answer", None)

    def clean_unanswered(self):
        return getattr(self, "filter_unanswered", None)

    def clean_q(self):
        return getattr(self, "filter_search", None)

    @transaction.atomic
    def save(self):
        self.instance.event = self.event
        self.instance.is_auto_created = True
        template = super().save()

        mails_by_user = defaultdict(list)
        contexts = self.get_recipients()
        for context in contexts:
            with suppress(
                SendMailException
            ):  # This happens when there are template errors
                speaker = context["user"]
                user = speaker.user if hasattr(speaker, "user") else speaker
                context["user"] = user
                locale = user.locale
                if submission := context.get("submission"):
                    locale = submission.get_email_locale(user.locale)
                mail = template.to_mail(
                    user=None,
                    event=self.event,
                    locale=locale,
                    context_kwargs=context,
                    commit=False,
                    allow_empty_address=True,
                )
                mails_by_user[user].append((mail, context))

        result = []
        for user, user_mails in mails_by_user.items():
            # Deduplicate emails: we don't want speakers to receive the same
            # email twice, just because they have multiple submissions.
            mail_dict = defaultdict(list)
            for mail, context in user_mails:
                mail_dict[mail.subject + mail.text].append((mail, context))
            # Now we can create the emails and add the speakers to them
            for mail_list in mail_dict.values():
                mail = mail_list[0][0]
                mail.save()
                mail.to_users.add(user)
                for __, context in mail_list:
                    if submission := context.get("submission"):
                        mail.submissions.add(submission)
                result.append(mail)
        if self.cleaned_data.get("skip_queue"):
            for mail in result:
                mail.send()
        return result


class QueuedMailFilterForm(forms.Form):
    status = forms.MultipleChoiceField(
        required=False, widget=SelectMultipleWithCount(attrs={"title": _("Status")})
    )
    track = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Track.objects.none(),
        widget=SelectMultipleWithCount(
            attrs={"title": _("Tracks")}, color_field="color"
        ),
    )

    default_renderer = InlineFormRenderer

    def __init__(self, *args, event=None, sent=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

        if sent:
            self.fields.pop("status")
        else:
            counts = event.queued_mails.filter(state=QueuedMailStates.DRAFT).aggregate(
                total=Count("pk"),
                failed=Count("pk", filter=Q(error_data__isnull=False)),
            )
            failed_count = counts["failed"]
            pending_count = counts["total"] - failed_count
            if not failed_count:
                self.fields.pop("status")
            else:
                self.fields["status"].choices = [
                    ("draft", CountableOption(_("Pending"), pending_count)),
                    ("failed", CountableOption(_("Failed"), failed_count)),
                ]

        # Only show track filter if tracks are enabled
        if not event.get_feature_flag("use_tracks"):
            self.fields.pop("track")
        else:
            mail_filter = Q(submissions__mails__event=event)
            if sent is not None:
                if sent:
                    mail_filter &= Q(
                        submissions__mails__state__in=[
                            QueuedMailStates.SENT,
                            QueuedMailStates.SENDING,
                        ]
                    )
                else:
                    mail_filter &= Q(submissions__mails__state=QueuedMailStates.DRAFT)

            self.fields["track"].queryset = event.tracks.annotate(
                count=Count("submissions__mails", distinct=True, filter=mail_filter)
            ).order_by("-count")

    def filter_queryset(self, qs):
        status = self.cleaned_data.get("status")
        if status:
            qs = qs.filter(computed_state__in=status)
        tracks = self.cleaned_data.get("track")
        if tracks:
            qs = qs.filter(submissions__track__in=tracks)
        return qs.distinct()

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}
