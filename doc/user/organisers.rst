.. SPDX-FileCopyrightText: 2026-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _`user-guide-organisers`:

Organisers & Teams
==================

pretalx uses a hierarchy of organisers, teams, and events to structure access
and permissions. This page explains how to create teams, manage team members,
and configure permissions.

.. note::

   Managing teams and permissions requires access to an organiser account. If
   you do not have access to an organiser account, you are probably looking for
   the section on how to :ref:`accept an invitation <user-guide-teams-accepting>`.

.. _`user-guide-organisers-what`:

Organisers
----------

An organiser represents the entity responsible for running events – this could
be a company, a community, an institution, or any other group. Every event in
pretalx belongs to exactly one organiser.

Grouping events under an organiser has several benefits: you can manage team
access across multiple events at once, and team members can create new events
under an organiser they have access to. When you create your next event, you
can **copy the settings of a prior event**, so that you don't have to set up
your tracks, review settings, email templates, venue setup etc. from scratch.

Setting up an Organiser
^^^^^^^^^^^^^^^^^^^^^^^

On `pretalx.com <https://pretalx.com>`_, an organiser account is created for
you automatically when you `sign up <https://pretalx.com/p/try>`_. If you are
using a self-hosted pretalx instance, contact your administrator to have an
organiser account created for you.

.. _`user-guide-teams`:

Teams
-----

Teams let you grant access to your events and define what members can do. Each
team belongs to one organiser and can provide access to some or all of that
organiser's events.

A user can be a member of multiple teams, both within the same organiser and
across organisers. Their effective permissions **combine all permissions** from
all their teams – if any team grants a particular permission, the user has that
permission.

This means that review restrictions (track limits or hidden speaker names) only
apply if the user has no other team granting broader access. For example: if
someone is in both a "DemoCon 2026 Security Track Reviewers" team (a reviewer
team limited to the Security track) and a "DemoCon 2026 Organisers" team (with
full proposal access), they can view and edit all proposals through their
Organisers membership. However, they can only submit reviews for Security track
proposals, because that's where their review permission applies.

Creating a new team
^^^^^^^^^^^^^^^^^^^

Navigate to **Your organiser → Teams** and click **New team**. The form has
three parts: the team name, event access settings, and permissions.

When choosing a name, pick something that describes the team's role (like
"DemoCon Reviewers 2026" or "Programme Committee") rather than listing
individual permissions.

Recommended team structures
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Teams are flexible and support many different setups. Here are common patterns:

**Administrator team**: Keep a small team with full permissions for all events.
These members can manage other teams and fix mistakes – for example, if someone
accidentally removes their own team's access to an event. The default
"Administrators" team serves this purpose.

**Organiser team**: For the people running your event day-to-day. If your
organiser group is stable across years, one team for all events works well. If
your team changes each year, create a new team per event. You can also combine
both approaches: a core team with all-events access, plus event-specific teams
for additional helpers. This team typically needs **Can change event settings**
and **Can work with and change proposals**, but typically does not need **Can
change teams and permissions** or **Can change organiser settings**.

**Reviewer team**: Create separate reviewer teams for each event to avoid
accidentally exposing past or future submissions. Give this team only the **Is
a reviewer** permission and limit it to the current event. If reviewers need to
reference past proposals, you can add one or two previous events to the team's
access.

**Track-specific reviewer teams**: For larger events with domain experts,
create one reviewer team per track (e.g., "DemoCon 2026 Security Track
Reviewers"). Use track restrictions to limit each team to their area of
expertise.

.. _`user-guide-teams-permissions`:

Choosing team permissions
^^^^^^^^^^^^^^^^^^^^^^^^^

When you create or edit a team, you can select the team’s event scope and permissions:

Event scope
***********

All events
   Members have access to every event under this organiser, including any
   events created in the future. Use this for core team members who should
   always have access.

Specific events
   Members only have access to the events you select. New events will not be
   accessible to this team unless you explicitly add them.

Permissions
***********

Each team has permission flags that determine what members can do. These
permissions apply to the events the team has access to:

Can create events
   Members can create new events under this organiser.

Can change teams and permissions
   Members can create, edit, and delete teams, invite new members, and modify
   permissions. At least one team must have this permission to ensure the
   organiser can always be administered. pretalx will prevent you from removing
   the permission, removing the last team member, or deleting a team if it
   would result in nobody remaining with this permission.

Can change organiser settings
   Members can modify settings that apply to the organiser as a whole, such as
   its name.

Can change event settings
   Members can modify event configuration, including dates, CfP settings, and
   other event properties.

Can work with and change proposals
   Members can view, edit, and manage submitted proposals – including changing
   their state, editing content, and managing speakers. This is the primary
   permission for day-to-day event management, covering scheduling, email
   templates, and other event operations.

Is a reviewer
   Members can participate in the review process, scoring and commenting on
   proposals. See the :ref:`Review Guide <user-guide-review>` for details on
   configuring review workflows. Combine this with track restrictions to limit
   reviewers to specific topic areas.

Always hide speaker names
   For teams with review permissions, this setting overrides the event's
   anonymisation settings. Even if the event shows speaker names to reviewers,
   members of this team will always see proposals anonymised. Use this to
   maintain blind review for specific team members.

Track restrictions
   For teams with review permissions, you can restrict access to specific
   tracks. Use this when you have domain experts who should only review
   proposals in their area of expertise. Track restrictions only affect
   reviewing – they do not limit other team permissions.

.. _`user-guide-teams-invitations`:

Adding team members
-------------------

Navigate to **Your organiser → Teams** and click on the team you want to add
members to. Enter an email address and click **Add**. To invite multiple people,
click **Add multiple team members?** to enter several addresses at once, one per
line.

pretalx always sends an invitation email, even if the address belongs to an
existing account. Recipients must click the link in the email to join the team.
Until they accept, they appear as pending invitations, where you can resend or
retract the invitation.

.. _`user-guide-teams-accepting`:

Accepting an invitation to a team
---------------------------------

When someone invites you to a team, you will receive an email with a link.
Click the link to accept the invitation. If you do not have an account yet, you
can create one on the same page. If you already have an account, log in to
complete the process.

When you open an invitation with a logged-in account, you can accept it, or
choose to log in with a different account. pretalx will not automatically
accept the invitation when you follow the link, in order to give you the option
to accept it from a different account.

Removing access
---------------

To remove someone from a team, navigate to **Your organiser → Teams**, click on
the team, and click **Remove** next to the member's name. They will lose access
immediately, though they may retain access through other teams.

Removing a team member is completely non-destructive: their reviews, comments,
and log entries remain intact. Only their access is revoked, and you can restore
it at any time by re-inviting them.

To remove an entire team, navigate to **Your organiser → Teams**, and click on
**Remove** next to the team. This revokes access for all members, just
as if you had removed them individually.
