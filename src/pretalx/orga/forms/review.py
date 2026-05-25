# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
from collections import defaultdict

from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelMultipleChoiceField

from pretalx.common.forms.renderers import InlineFormRenderer, TabularFormRenderer
from pretalx.common.forms.widgets import EnhancedSelectMultiple
from pretalx.event.domain.queries.team import event_reviewer_teams
from pretalx.submission.models import Tag


class DirectionForm(forms.Form):
    default_renderer = InlineFormRenderer

    direction = forms.ChoiceField(
        choices=(
            ("reviewer", _("Assign proposals to reviewers")),
            ("submission", _("Assign reviewers to proposals")),
        ),
        required=False,
    )


class ReviewAssignmentForm(forms.Form):
    def __init__(
        self,
        *args,
        event=None,
        review_mapping=None,
        submissions=None,
        reviewers=None,
        **kwargs,
    ):
        self.event = event
        self.review_mapping = review_mapping or {}
        self.reviewers = (
            reviewers
            if reviewers is not None
            else self.event.reviewers.order_by("name")
        ).prefetch_related("assigned_reviews", "teams", "teams__limit_tracks")
        self.submissions = (
            (
                submissions
                if submissions is not None
                else self.event.submissions.order_by("title")
            )
            .select_related("track")
            .prefetch_related("assigned_reviewers")
        )
        self.reviewers_by_track = defaultdict(set)
        for team in event_reviewer_teams(self.event).prefetch_related(
            "members", "limit_tracks"
        ):
            if team.limit_tracks.exists():
                for track in team.limit_tracks.all():
                    self.reviewers_by_track[track].update(team.members.all())
            else:
                self.reviewers_by_track[None].update(team.members.all())
        super().__init__(*args, **kwargs)

    class Media:
        js = [
            # select.js is pulled in automatically, but we need it to be
            # loaded BEFORE assignment.js so we list it again explicitly.
            forms.Script("common/js/forms/select.js", defer=""),
            forms.Script("orga/js/forms/assignment.js", defer=""),
        ]


class ReviewerForProposalForm(ReviewAssignmentForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._review_choices_by_track = {}
        for submission in self.submissions:
            initial_assignments = self.review_mapping[
                "submission_to_assigned_reviewers"
            ].get(submission.id, [])

            self.fields[submission.code] = forms.MultipleChoiceField(
                choices=self.get_review_choices_by_track(submission.track),
                widget=EnhancedSelectMultiple,
                initial=initial_assignments,
                label=submission.title,
                required=False,
            )

    def get_review_choices_by_track(self, track):
        """cache() may leak memory, so we use a manual cache here"""
        if track in self._review_choices_by_track:
            return self._review_choices_by_track[track]
        reviewers = list(self.reviewers_by_track[track] | self.reviewers_by_track[None])
        result = [
            (reviewer.id, reviewer.name)
            for reviewer in sorted(reviewers, key=lambda x: (x.name or "").lower())
        ]
        self._review_choices_by_track[track] = result
        return result

    def save(self, *args, **kwargs):
        for submission in self.submissions:
            submission.assigned_reviewers.set(self.cleaned_data[submission.code])


class ProposalForReviewerForm(ReviewAssignmentForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.submissions_by_track = defaultdict(set)
        for submission in self.submissions:
            self.submissions_by_track[submission.track_id].add(
                (submission.id, submission.title)
            )
        self._submission_choices_by_track = {}
        self.all_submission_choices = sorted(
            [(submission.id, submission.title) for submission in self.submissions],
            key=lambda s: (s[1] or "").lower(),
        )
        for reviewer in self.reviewers:
            track_limit = []
            if reviewer not in self.reviewers_by_track[None]:
                for track, reviewers in self.reviewers_by_track.items():
                    if reviewer in reviewers:
                        track_limit.append(track.id)
            initial_assignments = self.review_mapping[
                "reviewer_to_assigned_submissions"
            ].get(reviewer.id, [])

            self.fields[reviewer.code] = forms.MultipleChoiceField(
                choices=self.get_submission_choices_by_tracks(track_limit),
                widget=EnhancedSelectMultiple,
                initial=initial_assignments,
                label=reviewer.name,
                required=False,
            )

    def get_submission_choices_by_tracks(self, track_limit):
        if not track_limit:
            return self.all_submission_choices
        cache_key = ",".join(str(t) for t in sorted(track_limit))
        if result := self._submission_choices_by_track.get(cache_key):
            return result
        submissions = set()
        for track in track_limit:
            submissions.update(self.submissions_by_track[track])
        result = sorted(
            submissions, key=lambda submission: (submission[1] or "").lower()
        )
        self._submission_choices_by_track[cache_key] = result
        return result

    def save(self, *args, **kwargs):
        for reviewer in self.reviewers:
            reviewer.assigned_reviews.set(self.cleaned_data[reviewer.code])


class BulkTagForm(forms.Form):
    default_renderer = InlineFormRenderer

    tags = SafeModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=True,
        label=_("Tags"),
        widget=EnhancedSelectMultiple(color_field="color"),
    )
    action = forms.ChoiceField(
        required=True,
        label=_("Action"),
        choices=(("add", _("Add tags")), ("remove", _("Remove tags"))),
        widget=forms.RadioSelect,
        initial="add",
    )

    def __init__(self, event, **kwargs):
        self.event = event
        super().__init__(**kwargs)
        self.fields["tags"].queryset = event.tags.all()


class ReviewAssignImportForm(DirectionForm):
    default_renderer = TabularFormRenderer

    import_file = forms.FileField(label=_("File"))
    replace_assignments = forms.ChoiceField(
        label=_("Replace current assignments"),
        choices=(
            (0, _("Keep current assignments")),
            (1, _("Replace current assignments")),
        ),
        help_text=_(
            "Select to remove all current assignments and replace them with the import. Otherwise, the import will be an addition to the current assignments."
        ),
        widget=forms.RadioSelect,
        initial=False,
    )

    JSON_ERROR_MESSAGE = _("Cannot parse JSON file.")

    def __init__(self, event, **kwargs):
        self.event = event
        self._user_cache = {}
        self._submissions_cache = {}
        super().__init__(**kwargs)
        self.fields["direction"].required = True

    def _get_user(self, text):
        if text in self._user_cache:
            return self._user_cache[text]
        try:
            user = self.event.reviewers.get(Q(email__iexact=text) | Q(code=text))
            self._user_cache[text] = user
        except ObjectDoesNotExist:
            raise forms.ValidationError(
                str(_("Unknown user: {}")).format(text)
            ) from None
        else:
            return user

    def _get_submission(self, text):
        if not self._submissions_cache:
            self._submissions_cache = {
                sub.code: sub for sub in self.event.submissions.all()
            }
        try:
            return self._submissions_cache[text.strip().upper()]
        except KeyError:
            raise forms.ValidationError(
                str(_("Unknown proposal: {}")).format(text)
            ) from None

    def clean_import_file(self):
        uploaded_file = self.cleaned_data["import_file"]
        try:
            data = json.load(uploaded_file)
        except (ValueError, UnicodeDecodeError):
            raise forms.ValidationError(self.JSON_ERROR_MESSAGE) from None
        return data

    def clean(self):
        super().clean()
        uploaded_data = self.cleaned_data.get("import_file")
        direction = self.cleaned_data.get("direction")
        if not uploaded_data:
            raise forms.ValidationError(self.JSON_ERROR_MESSAGE)
        if direction == "reviewer":
            # keys should be users, values should be lists of proposals
            new_uploaded_data = {
                self._get_user(key): [self._get_submission(val) for val in value]
                for key, value in uploaded_data.items()
            }
        else:
            # keys should be proposals, values should be lists of users
            new_uploaded_data = {
                self._get_submission(key): [self._get_user(val) for val in value]
                for key, value in uploaded_data.items()
            }

        self.cleaned_data["import_file"] = new_uploaded_data
        return self.cleaned_data

    def save(self):
        direction = self.cleaned_data.get("direction")
        replace_assignments = self.cleaned_data.get("replace_assignments")
        uploaded_data = self.cleaned_data.get("import_file")

        if replace_assignments in (1, "1"):
            # There's no .update() for m2m fields
            # We'll just assume that there are less reviewers than proposals, typically,
            # so this should result in less queries
            for user in self.event.reviewers:
                user.assigned_reviews.set([])

        if direction == "reviewer":
            # keys should be users, values should be lists of proposals
            for user, proposals in uploaded_data.items():
                user.assigned_reviews.add(*proposals)
        else:
            for proposal, users in uploaded_data.items():
                proposal.assigned_reviewers.add(*users)
