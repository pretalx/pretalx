.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`user-guide-review`:

Reviews
=======

Reviews are pretalx's structured way to evaluate proposals. Unlike
:ref:`proposal comments <user-guide-proposals>`, which are free-form discussion
threads, reviews produce scores and structured feedback that let you compare
proposals and make acceptance decisions based on aggregated evaluations.

Reviews are **never visible to speakers** unless explicitly included in
feedback emails, even if a speaker also happens to be a reviewer. This strict
separation means reviewers can be candid without worrying about hurt feelings.
We enforce this rule on all levels, from the review interface to the
:ref:`API <rest-api>`.

.. _`user-guide-review-phases`:

Review Phases
-------------

A review phase defines *what reviewers can do* during a particular stage of
your review process. At any given time, exactly one review phase is active, and
its settings control reviewer permissions, visibility, and speaker editing
rights.

You configure review phases under **Settings → Review**, in the "Phases" tab.
pretalx creates two default phases for you:

1. A **review phase** where reviewers can submit reviews, but cannot change
   proposal states.
2. A **selection phase** where reviewing is closed, but organisers (and
   optionally reviewers) can accept or reject proposals based on the collected
   scores.

You can add more phases if your process requires additional rounds – for
example, a second review phase for shortlisted proposals, or a separate phase
for a programme committee to make final decisions.

Each phase is defined by its time boundaries and the permissions it grants:

Start and end dates
   Optional time boundaries. When set, pretalx can automatically activate the
   next phase when the current one's end date passes. You do not have to set a
   start date on the first review phase, or an end date on the last review
   phase. All other review phases must have a start date and an end date.
   Review phases must not overlap. pretalx will automatically activate and
   deactivate review phases based on their dates. If this ever goes wrong or
   seems stuck, you can also click the button showing a star to manually
   activate a review phase.

Can review
   Whether reviewers can write and edit reviews during this phase. Disable
   this for selection phases where you only want to make accept/reject
   decisions based on existing reviews.

Speakers can change submissions
   Whether speakers can edit their proposals during this phase (provided the
   CfP is closed – while the CfP is open, speakers can always edit, unless
   speaker editing is globally disabled in the :ref:`CfP settings
   <user-guide-cfp>`). This is useful to lock down proposals once reviewing has
   started, so reviewers don't see a moving target.

Can change proposal state
   Whether reviewers (not just organisers) can accept and reject proposals.
   Enable this for selection phases where you want your review team to
   participate in acceptance decisions.

Can tag proposals
   Controls whether reviewers can work with tags. You can choose between
   *never*, *use existing tags* (reviewers add and remove tags that organisers
   have created), and *create tags* (full tag management for reviewers).

Each phase also has visibility settings that control anonymisation and what
reviewers can see of each other's work – these are covered in the
:ref:`visibility section <user-guide-review-visibility>` below.

.. _`user-guide-review-scores`:

Score Categories
----------------

Score categories define *what* reviewers score and *how* those scores combine
into a total. You configure them under **Settings → Review**, in the "Scores"
tab.

Every score category has a **name** (the label reviewers see, e.g. "Content
quality" or "Relevance") and a set of **score values** with optional labels
that reviewers choose from (e.g. 0 = "Poor", 1 = "Below average", 2 =
"Average", 3 = "Good", 4 = "Excellent"). You can define as many values as you
like per category, and you don't have to use consecutive numbers. Score labels
are optional – they help reviewers interpret what each value means.

Categories can be marked as **required** (reviewers must provide a score)
or **optional** (reviewers can skip them). You can also **deactivate** a
category to hide it from the review form and dashboard without deleting it or
its existing scores – useful when you adjust your criteria between review
rounds.

Weighting and aggregation
^^^^^^^^^^^^^^^^^^^^^^^^^

When you have more than one score category, pretalx calculates a **total
score** per review as a weighted sum. Each category has a **weight** (default
1) that acts as a multiplier. If you give "Content quality" a weight of 2 and
"Speaker experience" a weight of 1, content quality counts twice as much. The
total formula is displayed in the settings interface so you can verify it.

The review dashboard then aggregates the total scores across all reviewers for
each proposal, using either the **median** or the **mean** (configurable in the
general review settings). Median is less sensitive to outliers; mean gives a
more granular ranking when you have enough reviewers per proposal.

Independent categories
^^^^^^^^^^^^^^^^^^^^^^

Sometimes you want to collect a score that informs decisions but shouldn't
affect the ranking – for example, a "Speaker is a first-timer" flag that the
programme committee wants to see without it changing which proposals sort
highest. Mark such categories as **independent**: they appear as separate
columns on the dashboard but are excluded from the total score (their weight is
automatically set to 0).

You must always have at least one non-independent score category, so that
pretalx can calculate a total review score.

Track-specific categories
^^^^^^^^^^^^^^^^^^^^^^^^^

Score categories can be **limited to specific tracks**, so that they only
appear in the review form for proposals in those tracks. This is useful for
criteria that only make sense in certain contexts – for example, a "Hands-on
component" score that only applies to workshop proposals.

It is highly recommended that you mark track-specific review categories
as **independent**. Otherwise, some tracks will have a higher potential
maximum review score. If you decide to go down this route, make sure to
make your acceptance decisions for each track individually, to avoid unfairly
preferencing one track over another.

.. _`user-guide-review-custom-fields`:

Reviewer Custom Fields
^^^^^^^^^^^^^^^^^^^^^^

In addition to scores and free-text feedback, you can add custom fields that
reviewers fill in as part of their review. These are configured as
:ref:`custom fields <user-guide-custom-fields>` with the "Reviewer" target.

Use reviewer custom fields for structured data that doesn't fit neatly into a
score – for example, "Would you be willing to mentor this speaker?" or "Does
this proposal overlap with another submission?".

.. _`user-guide-review-settings`:

Review Settings
---------------

The "General" tab under **Settings → Review** controls how reviews behave
across all phases. The most important decisions here are about what reviewers
*must* provide and how their scores are presented.

If you want every review to contain substantive feedback, enable **Require a
review score** and/or **Require a review text**. When neither is required,
reviewers see an additional "Abstain" button that lets them record that they
looked at a proposal without scoring it.

The **score display** setting controls how scores appear on the review form –
you can show text labels with numbers ("Good (3)"), numbers with labels ("3
(Good)"), or either one alone. The dashboard always shows numerical scores
regardless of this setting.

You can also write a **help text for reviewers** that is displayed at the top
of every review form. Use this to explain your review criteria, remind
reviewers of your event's values, or link to external guidelines.

.. _`user-guide-review-teams`:

Reviewers, Teams, and Tracks
-----------------------------

Reviewer access is managed through :ref:`teams <user-guide-teams>`. To set up
reviewers, go to **Settings → Teams** and either create a new team with the
"Reviewer" role or add the reviewer permission to an existing team. Any user
added to a team with reviewer permissions becomes a reviewer for your event.

Track-based assignment
^^^^^^^^^^^^^^^^^^^^^^

If your event uses :ref:`tracks <user-guide-tracks>`, you can restrict reviewer
teams to specific tracks. A team limited to the "Security" and "Privacy" tracks
will only see proposals in those tracks.

This is useful when your reviewers are domain experts: your security reviewers
shouldn't need to evaluate web development talks, and vice versa. To set track
restrictions, edit the team under **Settings → Teams** and select the tracks
that team should review.

If a reviewer belongs to multiple teams, their access is the union of all
their teams' track restrictions. A reviewer on both the "Security" team and the
"Privacy" team can see proposals in both tracks. This also means that if *any* of
their teams has no track restriction, a reviewer can see all proposals.

Individual reviewer assignment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Beyond track-based access, you can assign specific reviewers to individual
proposals. Go to **Review → Assign reviewers** to manage assignments. You
can assign reviewers one at a time, or import assignments from a CSV file.

How assignment interacts with proposal visibility depends on the active review
phase. When proposal visibility is set to "Assigned only" (see
:ref:`visibility <user-guide-review-visibility>`), reviewers *only* see
proposals they are explicitly assigned to. When set to "All proposals",
assigned proposals are highlighted and shown first, but reviewers can still
review other proposals in their tracks.

Reviewers are not automatically notified when assigned to proposals. To let
them know, use the :ref:`email composer <user-guide-emails-compose>` to send a
message to the relevant reviewer teams.

.. _`user-guide-review-visibility`:

Visibility and Anonymisation
----------------------------

Each review phase carries visibility settings that shape how reviewers
experience the review process. These settings let you tune the balance between
transparency and independence at each stage.

Speaker anonymisation
^^^^^^^^^^^^^^^^^^^^^

Disabling **Can see speaker names** hides speaker names, biographies, and
other identifying information from reviewers. This enables blind review,
helping to reduce bias based on speaker reputation or identity.

:ref:`Custom fields <user-guide-custom-fields>` have a separate "Show answers
to reviewers" setting – you can collect personal information from speakers
without exposing it to reviewers, even when speaker names are visible.

Additionally, :ref:`teams <user-guide-teams>` can have an **Always hide
speaker names** setting that overrides the phase setting, so that specific
reviewer groups always review anonymously regardless of the active phase.

Anonymising proposal content
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Hiding speaker names is not always enough – a proposal's title, abstract, or
description may contain identifying information. To handle this, organisers can
**anonymise individual proposals**: on the proposal detail page, click the
"Anonymise" tab to create a redacted version of the proposal's text fields.
Reviewers will see the anonymised version instead of the original whenever
speaker names are hidden. You can use "Save and next" to move efficiently
through all proposals that still need anonymisation.

Proposals that have been anonymised are marked with an icon in the first column
of the :ref:`session list <user-guide-proposals>`, so you can see at a glance
which proposals have been processed.

Proposal visibility
^^^^^^^^^^^^^^^^^^^

The **proposal visibility** setting controls which proposals reviewers can see:

All proposals
   Reviewers see every proposal their team or track permissions allow. Assigned
   proposals are highlighted and shown first in the list, making it easy to
   prioritise assigned work while still allowing reviewers to pick up
   unreviewed proposals.

Assigned only
   Reviewers see only proposals they are explicitly assigned to. Use this when
   you want tight control over who reviews what – for example, to ensure
   balanced coverage or to prevent conflicts of interest.

Seeing other reviews
^^^^^^^^^^^^^^^^^^^^

The **Can see other reviews** setting controls whether reviewers can read each
other's reviews. You can choose between "Always", "After submitting their own
review" and "Never".

Seeing other reviews before writing their own review can lead to an unconscious
adjustment of the review score, so we recommend that in the first review phase,
this setting should be "After submitting their own review" or "Never".

As never showing other reviews prevents reviewers from discussing
disagreements, that option should be reserved for events where reviewers are
not closely integrated in the decision-making process, or where they will
discuss the review results in a later review phase.

Disabling **Can see reviewer names** hides reviewer identities from other
reviewers even when reviews are shown. This is similar to speaker anonymisation
– it controls whether *reviewers* can see who wrote *other reviews*. Organisers
can always see who wrote each review.

.. _`user-guide-review-dashboard`:

The Review Dashboard
--------------------

The review dashboard at **Review → Review** is where the review process comes
together. It shows all proposals in a sortable, filterable table with
aggregated scores, review counts, and proposal states.

What you see on the dashboard depends on your permissions:

- **All users** see the proposal title, track, state, and their own score (if
  they have reviewed the proposal), and most other configurable columns, such as custom fields.
- **Users who can see all reviews** also see the total number of reviews, the
  median or mean score across all reviewers, plus any independent score
  categories as separate columns.
- **Users who can change proposal states** see action buttons for accepting and
  rejecting proposals.

By default, the dashboard sorts proposals by state first (submitted proposals
at the top, then accepted, confirmed, and rejected), then by aggregate score in
descending order. This puts the highest-rated proposals that need an acceptance
decision at the top.

Accepting and rejecting proposals
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When you have the right permissions, you can accept or reject proposals
directly from the dashboard using the action buttons or checkboxes for bulk
operations.

You have two options for how state changes take effect:

- **Immediate**: The proposal's state changes right away, and the corresponding
  email (acceptance or rejection) is generated and placed in your
  :ref:`outbox <user-guide-emails-outbox>`, where you can review it before
  sending it.
- **Pending**: The proposal keeps its current visible state but gains a pending
  state. Speakers and the public see no change yet. You can then apply all
  pending states at once when you're ready to notify speakers – see
  :ref:`pending states <user-guide-proposals-pending>` for details.

Using pending states is the recommended workflow: review scores, set pending
acceptances and rejections over several sessions, review the acceptance and
rejection email templates, and then apply all pending states in one go.

If you want to share reviewer feedback with speakers, you can add the
``{all_reviews}`` placeholder to your acceptance or rejection email template.
It will be replaced with all review texts for the proposal, separated by
dividers. See :ref:`email placeholders <user-guide-emails-placeholders>` for
the full list of available placeholders.

.. _`user-guide-review-writing`:

Writing Reviews
---------------

pretalx offers two ways to write reviews: one proposal at a time (the detail
view), or many proposals at once (the bulk view). Both are accessible from the
review dashboard.

Detail view
^^^^^^^^^^^

When you open a proposal from the review dashboard, you see its review page.
The top half shows the proposal's content — title, session type, track,
abstract, description, notes, and any custom field answers visible to
reviewers. If speaker names are visible in the current review phase, you also
see speaker biographies and links to their other proposals, which is helpful
for spotting duplicate submissions.

Below the proposal content, the review form shows one row of radio buttons per
score category and a text field for your written review. If the event uses
reviewer custom fields, those appear here too. If you have permission to tag
proposals, the tag selector appears above the review form.

At the bottom of the page you'll find a progress bar showing how many of
your assigned proposals you have reviewed (e.g. "12 / 45"). Use the action buttons
right above the progress bar to navigate through your review queue:

- **Save and next** saves your review and takes you to the next unreviewed
  proposal — this is the primary workflow button. The proposal is selected
  among the proposals with the fewest reviews. That means if most reviewers
  just keep using this button, reviews should be distributed evenly across
  proposals.
- **Skip for now** moves to the next proposal without saving a review. The
  skipped proposal is set aside for the rest of your session and will reappear
  once you have worked through everything else.
- **Abstain** records that you looked at the proposal but chose not to score
  it, then moves to the next proposal. This button only appears when neither a
  score nor a review text is required in the review settings.
- **Save** saves your review and stays on the same page, useful when you want
  to come back and refine your text or look at the other reviews.

You can also press **Ctrl+Enter** (or **Cmd+Enter** on macOS) to submit the
form.

Bulk view
^^^^^^^^^

The bulk view shows all proposals in a single table, with one row per proposal.
Each row contains the proposal title, speaker names (if visible), one column
per score category, and a comment field. You can filter and sort the table
using the filter bar at the top. To review a proposal, fill in the score and
comment fields in its row and click the checkmark button.

The bulk view is best suited for lightweight review processes where a score
and a short comment are sufficient. If your review form includes many score
categories, reviewer custom fields, or you need to read long proposal texts,
the detail view is more practical. A link at the top of the bulk view lets
you switch to the detail view for any proposals you haven't reviewed yet.

.. _`user-guide-review-examples`:

Example Configurations
----------------------

Here are some example configurations for review processes of different
complexity. You can mix and match these ideas.

Small event with simple review
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A community meetup with 30 proposals and 5 organisers who review everything
together:

- **One score category** ("Overall", scores 0–3) with labels like "Reject",
  "Weak", "Good", "Must have".
- **One review phase** with "Can review" and "Can change proposal state" both
  enabled. Speaker names visible, other reviews visible after submitting own
  review.
- **No track restrictions** – all reviewers see all proposals.
- **Score aggregation**: Median, so a single outlier review doesn't dominate.
- Set both score and text as optional, so reviewers can move fast.

Then, once most proposals have been reviewed by most organisers, meet up
to go through the proposals and reviews and quickly accept or reject the
proposals in bulk.

Medium conference with track-based review
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A conference with 200 proposals, 3 tracks, and 15 reviewers:

- **Two score categories**: "Content quality" (weight 2) and "Relevance to
  conference" (weight 1).
- **Two review phases**: "Review" (reviewers can score but not accept/reject)
  and "Selection" (reviewing closed, organisers accept and reject).
- **Track-restricted teams**: One reviewer team per track, each limited to
  their track's proposals.
- **Speaker names hidden** during the review phase for blind review, visible
  during the selection phase so the programme committee can consider speaker
  diversity.
- **Other reviews visible after submitting own review**, so reviewers can see
  where they agree or disagree with colleagues.

Large conference with multi-round review
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A major conference with 800 proposals, multiple tracks, and 50 reviewers:

- **Three score categories**: "Technical quality" (weight 2), "Presentation
  quality" (weight 1), and "Needs mentor" (independent, not included in
  total score but shown as a separate column).
- **Three review phases**:

  1. "Initial review" – all reviewers score proposals in their tracks. Speaker
     names hidden. Other reviews hidden. Proposal visibility set to "Assigned
     only" to ensure balanced coverage.
  2. "Calibration" – reviewing closed. Programme committee reviews scores and
     edge cases. Other reviews now visible so disagreements can be discussed.
  3. "Final selection" – organisers accept and reject proposals. Speaker names
     visible for diversity considerations.

- **Track-restricted teams** with individual reviewer assignment for proposals
  that span multiple tracks.
- **Score and text both required** during the initial review, to ensure
  substantive feedback.
- **Reviewer custom fields**: "Suitable as keynote?" (Yes/No).
- **Score aggregation**: Mean, because with enough reviewers per proposal,
  outliers average out and the mean gives a more granular ranking.
