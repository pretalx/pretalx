Features
========

This page aims to give an overview over the already implemented pretalx features, as well as
upcoming or planned features. If you have any further suggestions, please open an issue_ – neither
of these lists are complete, and we're looking forward to what you come up with!

Features
--------

pretalx is under active development, so we will add features here on a regular basis.

Talk submission
~~~~~~~~~~~~~~~

- **Publish a Call for Papers:** This is, at first, the most important part. pretalx allows you to
  publish a beautiful (we support full *markdown*) CfP in *different languages* and make it public
  after inspecting it.
- **Build a great team:** pretalx allows you to invite further members to your crew seamlessly, and
  has features a role-based permission system, where you differentiate between superusers, crew,
  and reviewers.
- **Organise the talks:** You can offer different submission types, with default lengths, so that
  speakers can tell you how much time (or which format, e.g. workshops) they require right at the
  start.
- **Work with multi-language events:** pretalx allows you to choose the locales offered at your
  conference, and speakers can then choose the language they feel most comfortable in for their
  talk. Subsequently, speakers will receive all emails in that language. pretalx supports
  English, German and French, but is open to new languages.
- **Ask custom questions:** If you need custom information from your submitters, you can add
  questions to your CfP. We support a wide variety of answer types, such as free-text, number input,
  and choices. (Answers can be optional, too.) You'll see the results as manageable
  statistics. You can ask questions either per speaker or per submission.
- **Set a deadline:** You can configure a deadline for your CfP and choose to show the countdown
  publicly. You can also add deadlines to submission types, to close them before the general deadline,
  or keep them available for longer than that.
- **Accept or reject submissions:** After careful consideration, you can accept or reject
  submissions. Speakers will then receive a notification (if you choose to), and asked to confirm
  their talk.
- **Reviewing:** A reviewing system with both texts and scoring, configurable scales, average
  scores, and reviewer teams that can work separately from the general organiser team.
- **Strong opinions:** Permit reviewers to issue override votes to put a
  submission to the top or bottom of the ranking, for a fixed amount of times
  per event and reviewer.

Scheduling
~~~~~~~~~~

- **Configure your location:** Configure the rooms your talks will be taking place in, including
  their names, descriptions, capacities and availability.
- **Build a schedule:** In the interactive drag'n'drop interface, build a schedule that you are
  happy with. Play around with it freely.
- **Build your schedule offline:** The initial version of a schedule is often hard to figure out.
  You can print out proportionally sized cards of the talks to cut out and play around with.
- **Publish your schedule:** Whenever something has changed noticeably, publish a new schedule.
  Speakers will receive notifications if the new release changes their talk time or location.
- **Transparent updates:** pretalx provides a public changelog and an Atom/RSS feed, so that your
  participants can receive notifications as soon as you release a new schedule version.
- **Integrate recordings:** Unless the speakers have set the do-not-record flag, you may sync and
  integrate the recording in the talk's page for the participants' convenience.
- **Provide feedback:** Attendees can provide anonymous feedback to speakers. The feedback will
  be visible to the speakers themselves and the organisers, but not publicly.

Speaker management
~~~~~~~~~~~~~~~~~~

- **Communicate:** Write emails to your speakers! pretalx comes with an email templating system that
  allows you to write multi-lingual email templates with place holders and send them to all or a
  subset of your speakers.
- **Check, then check again:** pretalx lets you check and edit any email before it's actually sent.
  Until then, pretalx collects the emails in an out-box, ready for editing, sending, or discarding.
- **Resend:** Sent the email to the wrong address? Want to send the same email to a new speaker?
  pretalx allows you to copy any sent email to a draft, edit it, and send it again.
- **Educate:** Speakers can upload files (such as presentations, or papers) along with their talks.

Customisation
~~~~~~~~~~~~~

- **Comunicate:** Change the default mail templates to something that fits your event and says
  precisely what you want it to say.
- **Colorize:** Change your event's primary colour to fit your event, your design, or your organiser.
- **Customize:** If changing the site's primary colour is not adequate for you, you can also upload
  custom CSS files and change anything you want to fit with the look of your event.
- **Link:** You can configure a separate domain for each of your events, in case you have event-
  specific domains, but want to keep all your events on the same instance.

Integration
~~~~~~~~~~~

- **Automate:** pretalx comes with a read-only, well-documented RESTful API to make integration
  with pretalx as easy and fun as possible.
- **Interface:** You can export your schedule in machine readable formats ( JSON, XML, XCAL, iCal),
  and use it elsewhere or even import it in other pretalx instances.
- **Adapt:** You can develop your own pretalx plugins, which can be custom exporters, pages, or
  anything that makes pretalx fit in with every need of your event.

.. _issue: https://github.com/pretalx/pretalx/issues/
