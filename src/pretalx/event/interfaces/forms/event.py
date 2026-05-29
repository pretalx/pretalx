# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.conf import settings
from django.db import transaction
from django.forms import inlineformset_factory
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes.forms import SafeModelMultipleChoiceField
from i18nfield.forms import I18nFormSetMixin

from pretalx.common.fonts import get_fonts
from pretalx.common.forms.fields import ColorField, ImageField, MultiDomainField
from pretalx.common.forms.mixins import (
    JsonSubfieldMixin,
    PretalxI18nModelForm,
    ReadOnlyFlag,
)
from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    HtmlDateInput,
    HtmlDateTimeInput,
    TextInputWithAddon,
)
from pretalx.common.plugins import get_all_plugins_grouped
from pretalx.common.text.css import validate_css
from pretalx.common.text.phrases import phrases
from pretalx.event.domain.event import apply_event_changes
from pretalx.event.models import Event, Organiser
from pretalx.event.models.event import EventExtraLink
from pretalx.event.validators.event import (
    custom_domain_points_to_site,
    normalize_custom_domain,
    validate_custom_domain,
)
from pretalx.orga.forms.widgets import (
    FontSelect,
    HeaderSelect,
    MultipleLanguagesWidget,
    PluginSelectWidget,
)
from pretalx.submission.models import SubmissionType, Track

SCHEDULE_DISPLAY_CHOICES = (
    ("grid", pgettext_lazy("schedule display format", "Grid")),
    ("list", pgettext_lazy("schedule display format", "List")),
)


class EventForm(ReadOnlyFlag, JsonSubfieldMixin, PretalxI18nModelForm):
    # Warning set by clean_custom_domain when the domain resolves but does not
    # appear to point at us.
    custom_domain_warning = None

    locales = forms.MultipleChoiceField(
        label=_("Active languages"),
        choices=[],
        widget=MultipleLanguagesWidget,
        help_text=_(
            "Users will be able to use pretalx in these languages, and you will be able to provide all texts in these"
            " languages. If you don’t provide a text in the language a user selects, it will be shown in your event’s"
            " default language instead."
        ),
    )
    content_locales = forms.MultipleChoiceField(
        label=_("Content languages"),
        choices=[],
        widget=EnhancedSelectMultiple,
        help_text=_("Users will be able to submit proposals in these languages."),
    )
    custom_css_text = forms.CharField(
        required=False,
        widget=forms.Textarea(),
        label="",
        help_text=_("You can type in your CSS instead of uploading it, too."),
    )
    imprint_url = forms.URLField(
        label=_("Imprint URL"),
        help_text=_(
            "This should point e.g. to a part of your website that has your contact details and legal information."
        ),
        required=False,
    )
    show_schedule = forms.BooleanField(
        label=_("Show schedule publicly"),
        help_text=_(
            "Unset to hide your schedule, e.g. if you want to use the HTML export exclusively."
        ),
        required=False,
    )
    schedule = forms.ChoiceField(
        label=phrases.orga.event_schedule_format_label,
        choices=SCHEDULE_DISPLAY_CHOICES,
        required=True,
    )
    show_featured = forms.ChoiceField(
        label=_("Show featured sessions"),
        choices=(
            ("never", _("Never")),
            ("pre_schedule", _("Until the first schedule is released")),
            ("always", _("Always")),
        ),
        help_text=_(
            "Marking sessions as “featured” is a good way to show them before the first schedule release, or to highlight them once the schedule is visible."
        ),
        required=True,
    )
    use_feedback = forms.BooleanField(
        label=_("Enable anonymous feedback"),
        help_text=_(
            "Attendees will be able to send in feedback after a session is over."
        ),
        required=False,
    )
    html_export_url = forms.URLField(
        label=_("HTML Export URL"),
        help_text=_(
            "If you publish your schedule via the HTML export, you will want the correct absolute URL to be set in various places. "
            "Please only set this value once you have published your schedule. Should end with a slash."
        ),
        required=False,
    )
    header_pattern = forms.ChoiceField(
        label=phrases.orga.event_header_pattern_label,
        help_text=phrases.orga.event_header_pattern_help_text,
        choices=Event.HEADER_PATTERN_CHOICES,
        required=False,
        widget=HeaderSelect,
    )
    heading_font = forms.ChoiceField(
        label=_("Heading font"),
        help_text=_("Select a font for headings and buttons."),
        required=False,
    )
    text_font = forms.ChoiceField(label=_("Text font"), required=False)
    meta_noindex = forms.BooleanField(
        label=_("Ask search engines not to index the event pages"), required=False
    )
    use_tracks = forms.BooleanField(
        label=_("Use tracks"),
        help_text=_("Do you organise your sessions by tracks?"),
        required=False,
    )
    present_multiple_times = forms.BooleanField(
        label=_("Slot count"),
        help_text=_("Can sessions be held multiple times?"),
        required=False,
    )
    attendee_signup = forms.BooleanField(
        label=_("Enable attendee signup"),
        help_text=_("Allow attendees to sign up for sessions."),
        required=False,
    )
    signup_domains = MultiDomainField(
        label=_("Allowed email domains"),
        help_text=_(
            "Only attendees with email addresses on these domains will be "
            "allowed to sign up. Leave empty to allow any email address."
        ),
        required=False,
    )
    attendee_signup_tracks = SafeModelMultipleChoiceField(
        label=_("Tracks requiring signup"),
        help_text=_(
            "Sessions in these tracks will require attendee signup by "
            "default. You can override this for individual sessions."
        ),
        queryset=Track.objects.none(),
        required=False,
        widget=EnhancedSelectMultiple(color_field="color"),
    )
    attendee_signup_types = SafeModelMultipleChoiceField(
        label=_("Session types requiring signup"),
        help_text=_(
            "Sessions of these types will require attendee signup by "
            "default. You can override this for individual sessions."
        ),
        queryset=SubmissionType.objects.none(),
        required=False,
        widget=EnhancedSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        self.is_administrator = kwargs.pop("is_administrator", False)
        super().__init__(*args, **kwargs)
        site_url = f"<code>{settings.SITE_HOST}</code>"
        self.fields["custom_domain"].help_text += ". " + _(
            "Make sure to point a CNAME record from your domain to {site_url}."
        ).format(site_url=site_url)
        self.initial["locales"] = self.instance.locale_array.split(",")
        self.initial["content_locales"] = self.instance.content_locale_array.split(",")
        self.initial["custom_css_text"] = (
            self.instance.custom_css.read().decode() if self.instance.custom_css else ""
        )
        self.fields["show_featured"].help_text = (
            str(self.fields["show_featured"].help_text)
            + " "
            + str(_("You can find the page <a {href}>here</a>.")).format(
                href=f'href="{self.instance.urls.featured}"'
            )
        )
        if self.instance.custom_domain:
            self.fields["slug"].widget.addon_before = f"{self.instance.custom_domain}/"
        if not self.is_administrator:
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = _(
                "Please contact your administrator if you need to change the short name of your event."
            )
        self.fields["date_to"].help_text = _(
            "Any sessions you have scheduled already will be moved if you change the event dates. You will have to release a new schedule version to notify all speakers."
        )
        self.fields["locales"].choices = [
            choice
            for choice in settings.LANGUAGES
            if settings.LANGUAGES_INFORMATION[choice[0]].get("visible", True)
            or choice[0] in self.instance.plugin_locales
        ]
        self.fields["content_locales"].choices = self.instance.available_content_locales

        fonts = get_fonts(self.instance)
        if fonts:
            default = pgettext_lazy("default choice in a menu", "Default")
            font_choices = [("", f"Titillium Web ({default})")]
            font_choices += sorted([(name, name) for name in fonts], key=lambda c: c[0])
            text_font_choices = [("", f"Muli ({default})")]
            text_font_choices += sorted(
                [(name, name) for name in fonts], key=lambda c: c[0]
            )
            self.fields["heading_font"].choices = font_choices
            self.fields["heading_font"].widget = FontSelect(
                fonts=fonts, choices=font_choices, default_font="Titillium Web"
            )
            self.fields["text_font"].choices = text_font_choices
            self.fields["text_font"].widget = FontSelect(
                fonts=fonts, choices=text_font_choices, default_font="Muli"
            )
        else:
            del self.fields["heading_font"]
            del self.fields["text_font"]

        self._init_attendee_signup_fields()

    def _init_attendee_signup_fields(self):
        self.fields[
            "attendee_signup_types"
        ].queryset = self.instance.submission_types.all()
        self.initial["attendee_signup_types"] = list(
            self.instance.submission_types.filter(
                attendee_signup_required=True
            ).values_list("pk", flat=True)
        )

        if not self.instance.get_feature_flag("use_tracks"):
            del self.fields["attendee_signup_tracks"]
        else:
            self.fields["attendee_signup_tracks"].queryset = self.instance.tracks.all()
            self.initial["attendee_signup_tracks"] = list(
                self.instance.tracks.filter(attendee_signup_required=True).values_list(
                    "pk", flat=True
                )
            )

    def _post_clean(self):
        if "locales" in self.cleaned_data:
            self.instance.locale_array = ",".join(self.cleaned_data["locales"])
            self.instance.__dict__.pop("locales", None)
        if "content_locales" in self.cleaned_data:
            self.instance.content_locale_array = ",".join(
                self.cleaned_data["content_locales"]
            )
            self.instance.__dict__.pop("content_locales", None)
        super()._post_clean()

    def clean_custom_domain(self):
        value = normalize_custom_domain(self.cleaned_data["custom_domain"])
        # Only run the (slow) DNS lookups when the domain has changed.
        # Run normalization just to be safe.
        if value == normalize_custom_domain(self.initial.get("custom_domain")):
            return value
        value, resolution = validate_custom_domain(value)
        # Reusing resolved value to avoid running the same DNS call twice.
        if value and not custom_domain_points_to_site(value, resolution):
            self.custom_domain_warning = _(
                "The domain “{domain}” does not appear to point to {site} yet. "
                "It will not work until you set up a CNAME record from your "
                "domain to {site}."
            ).format(domain=value, site=settings.SITE_HOST)
        return value

    def clean_custom_css(self):
        css = self.cleaned_data.get("custom_css") or self.files.get("custom_css")
        if not css or self.is_administrator:
            return css
        try:
            validate_css(css.read())
        except (
            IsADirectoryError
        ):  # pragma: no cover -- defensive against corrupted file descriptors
            return None
        return css

    def clean_custom_css_text(self):
        css = self.cleaned_data.get("custom_css_text").strip()
        if not css or self.is_administrator:
            return css
        validate_css(css)
        return css

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(commit=False)
        apply_event_changes(
            self.instance,
            self.changed_data,
            custom_css_text=self.cleaned_data.get("custom_css_text"),
        )
        self.save_m2m()
        self._save_attendee_signup_relations()
        return self.instance

    def _save_attendee_signup_relations(self):
        if not self.cleaned_data.get("attendee_signup"):
            # If attendee signup gets switched off, we do not touch existing
            # settings. They will appear hidden, but make it trivial to restore
            # the setting if it was switched off accidentally.
            return

        if (
            "attendee_signup_tracks" in self.fields
            and "attendee_signup_tracks" in self.changed_data
        ):
            self._apply_signup_required_flag(
                self.instance.tracks,
                self.cleaned_data.get("attendee_signup_tracks") or [],
            )

        if "attendee_signup_types" in self.changed_data:
            self._apply_signup_required_flag(
                self.instance.submission_types,
                self.cleaned_data.get("attendee_signup_types") or [],
            )

    @staticmethod
    def _apply_signup_required_flag(queryset, selection):
        # We save one-by-one instead of running a trivial update()
        # because this way, the updated timestamp and logging data
        # gets populated correctly. As the typical event has only
        # a handful of either, this is fine wrt performance.
        selected_pks = {item.pk for item in selection}
        currently_required = set(
            queryset.filter(attendee_signup_required=True).values_list("pk", flat=True)
        )
        to_add = selected_pks - currently_required
        to_remove = currently_required - selected_pks
        if not to_add and not to_remove:
            return
        for obj in queryset.filter(pk__in=to_add | to_remove):
            obj.attendee_signup_required = obj.pk in to_add
            obj.save(update_fields=["attendee_signup_required", "updated"])

    class Media:
        js = [forms.Script("orga/js/forms/settings.js", defer="")]
        css = {"all": ["orga/css/ui/settings.css"]}

    class Meta:
        model = Event
        fields = [
            "name",
            "slug",
            "date_from",
            "date_to",
            "timezone",
            "email",
            "locale",
            "custom_domain",
            "primary_color",
            "custom_css",
            "logo",
            "header_image",
            "og_image",
            "landing_page_text",
            "featured_sessions_text",
        ]
        field_classes = {
            "logo": ImageField,
            "header_image": ImageField,
            "og_image": ImageField,
            "primary_color": ColorField,
        }
        widgets = {
            "date_from": HtmlDateInput(attrs={"data-date-before": "#id_date_to"}),
            "date_to": HtmlDateInput(attrs={"data-date-after": "#id_date_from"}),
            "locale": EnhancedSelect,
            "timezone": EnhancedSelect,
            "slug": TextInputWithAddon(addon_before=settings.SITE_URL + "/"),
        }
        json_fields = {
            "imprint_url": "display_settings",
            "show_schedule": "feature_flags",
            "schedule": "display_settings",
            "show_featured": "feature_flags",
            "use_feedback": "feature_flags",
            "html_export_url": "display_settings",
            "header_pattern": "display_settings",
            "heading_font": "display_settings",
            "text_font": "display_settings",
            "meta_noindex": "display_settings",
            "use_tracks": "feature_flags",
            "present_multiple_times": "feature_flags",
            "attendee_signup": "feature_flags",
            "signup_domains": "attendee_signup_settings",
        }


class EventExtraLinkForm(PretalxI18nModelForm):
    default_renderer = InlineFormLabelRenderer

    class Meta:
        model = EventExtraLink
        fields = ["label", "url"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["label"].required = True


class BaseEventExtraLinkFormSet(I18nFormSetMixin, forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop("event", None)
        if event:
            kwargs["locales"] = event.locales
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        if not hasattr(self, "_queryset"):
            self._queryset = super().get_queryset().filter(role=self.role)
        return self._queryset

    def save_new(self, form, commit=True):
        instance = super().save_new(form, commit=False)
        instance.role = self.role
        if commit:
            instance.save()
        return instance


class BaseEventFooterLinkFormSet(BaseEventExtraLinkFormSet):
    role = "footer"


class BaseEventHeaderLinkFormSet(BaseEventExtraLinkFormSet):
    role = "header"


EventFooterLinkFormset = inlineformset_factory(
    Event,
    EventExtraLink,
    EventExtraLinkForm,
    formset=BaseEventFooterLinkFormSet,
    can_order=False,
    can_delete=True,
    extra=0,
)
EventHeaderLinkFormset = inlineformset_factory(
    Event,
    EventExtraLink,
    EventExtraLinkForm,
    formset=BaseEventHeaderLinkFormSet,
    can_order=False,
    can_delete=True,
    extra=0,
)


class EventWizardInitialForm(forms.Form):
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Use languages"),
        help_text=_("Choose all languages that your event should be available in."),
        widget=MultipleLanguagesWidget,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["locales"].choices = [
            choice
            for choice in settings.LANGUAGES
            if settings.LANGUAGES_INFORMATION[choice[0]].get("visible", True)
        ]
        self.fields["organiser"] = forms.ModelChoiceField(
            label=_("Organiser"),
            queryset=(
                Organiser.objects.filter(
                    id__in=user.teams.filter(can_create_events=True).values_list(
                        "organiser", flat=True
                    )
                )
                if not user.is_administrator
                else Organiser.objects.all()
            ),
            widget=EnhancedSelect,
            empty_label=None,
            required=True,
            help_text=_(
                "The organiser running the event can copy settings from previous events and share team permissions across all or multiple events."
            ),
        )
        self.fields["organiser"].initial = self.fields["organiser"].queryset.first()


class EventWizardBasicsForm(PretalxI18nModelForm):
    def __init__(self, *args, user, locales, organiser=None, **kwargs):
        self.locales = locales or []
        super().__init__(*args, **kwargs, locales=locales)
        self.instance.locale_array = ",".join(self.locales)
        self.fields["locale"].choices = [
            (code, lang) for code, lang in settings.LANGUAGES if code in self.locales
        ]
        self.fields["slug"].help_text = format_lazy(
            "{} <strong>{}</strong>",
            _(
                "This is the address your event will be available at. "
                "Should be short, only contain lowercase letters and numbers, and must be unique. "
                "We recommend some kind of abbreviation with less than 30 characters that can be easily remembered."
            ),
            _("You cannot change the slug later on!"),
        )
        copy_from_queryset = user.get_events_for_permission(
            can_change_event_settings=True
        )
        if copy_from_queryset.exists():
            self.fields["copy_from_event"] = forms.ModelChoiceField(
                label=_("Copy configuration from"),
                queryset=copy_from_queryset,
                widget=EnhancedSelect(color_field="visible_primary_color"),
                help_text=_(
                    "You can copy settings from previous events here, such as email settings, session types, and email templates. "
                    "Please check those settings once the event has been created!"
                ),
                empty_label=_("Do not copy"),
                required=False,
            )

    class Media:
        js = [forms.Script("orga/js/forms/wizard.js", defer="")]

    class Meta:
        model = Event
        fields = ("name", "slug", "timezone", "email", "locale")
        widgets = {
            "locale": EnhancedSelect,
            "timezone": EnhancedSelect,
            "slug": TextInputWithAddon(addon_before=settings.SITE_URL + "/"),
        }


class EventWizardTimelineForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        required=False,
        help_text=_(
            "The default deadline for your Call for Proposals. You can assign additional deadlines to individual session types, which will take precedence over this deadline."
        ),
        widget=HtmlDateTimeInput,
    )

    def __init__(self, *args, user=None, locales=None, organiser=None, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ("date_from", "date_to")
        widgets = {"date_from": HtmlDateInput, "date_to": HtmlDateInput}


class EventWizardDisplayForm(forms.Form):
    primary_color = ColorField(
        label=Event._meta.get_field("primary_color").verbose_name,
        help_text=Event._meta.get_field("primary_color").help_text,
        required=False,
    )
    header_pattern = forms.ChoiceField(
        label=phrases.orga.event_header_pattern_label,
        help_text=phrases.orga.event_header_pattern_help_text,
        choices=Event.HEADER_PATTERN_CHOICES,
        required=False,
        widget=HeaderSelect,
    )

    def __init__(
        self,
        *args,
        user=None,
        locales=None,
        organiser=None,
        copy_from_event=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        logo = Event._meta.get_field("logo")
        self.fields["logo"] = ImageField(
            required=False, label=logo.verbose_name, help_text=logo.help_text
        )
        if copy_from_event:
            self.fields["primary_color"].initial = copy_from_event.primary_color
            self.fields[
                "header_pattern"
            ].initial = copy_from_event.display_settings.get("header_pattern")


class EventWizardPluginForm(forms.Form):
    def __init__(
        self,
        *args,
        user=None,
        locales=None,
        organiser=None,
        copy_from_event=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.grouped_plugins = get_all_plugins_grouped()
        all_plugins = []
        choices = []
        for (_category_key, category_label), plugins in self.grouped_plugins.items():
            all_plugins.extend(plugins)
            choices.append(
                (category_label, [(plugin.module, plugin.name) for plugin in plugins])
            )
        if not all_plugins:
            return
        initial_plugins = []
        if copy_from_event:
            available_modules = {p.module for p in all_plugins}
            initial_plugins = [
                p for p in copy_from_event.plugin_list if p in available_modules
            ]
        self.fields["plugins"] = forms.MultipleChoiceField(
            label=_("Plugins"),
            required=False,
            choices=choices,
            initial=initial_plugins,
            widget=PluginSelectWidget(plugins=all_plugins),
        )
