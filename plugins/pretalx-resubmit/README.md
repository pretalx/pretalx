# pretalx-resubmit

Lets speakers submit a copy of one of their proposals from another event of the
same organiser, instead of filling in the CfP again.

## Setup

Enable the "Resubmit proposals" plugin in the settings of each event that should
accept resubmissions. The plugin does not need to be enabled on the events that
proposals are copied from.

## How it works

While the event's CfP is open, a speaker's "Your proposals" page lists their
proposals from the organiser's other events (any state except draft). After
choosing "Resubmit", they pick the session type, track and language for this
event; the session type and track default to ones with the same name as in the
original event. The copy is then submitted as usual: the speaker gets the normal
acknowledgement email, and organisers are notified if they asked to be.

Copied: title, abstract, description, notes, image and the "don't record" flag.
If the speaker has no biography or profile picture for this event yet, those are
taken from their profile in the original event.

Not copied: co-speakers (they have to be invited again, so nobody is added to an
event without agreeing), tags, answers to questions, resources, reviews and
internal notes. After resubmitting, the speaker lands on the new proposal's page,
where they can edit it, answer this event's questions and invite co-speakers.

Each proposal can be resubmitted to an event once. The original proposal is not
changed. The copy's history shows which proposal it came from.

Session types and tracks that need an access code are not offered.

## Tests

```sh
./run-tests.sh            # uses the pretalx-sso:latest image; set IMAGE= to change
```
