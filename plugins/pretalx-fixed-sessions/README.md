# pretalx-fixed-sessions

Core sessions: session types whose proposals all have the same title, abstract
and description, set by the organisers. Every other session type is a write-in
session and works as usual.

## Setup

Enable the "Fixed sessions" plugin in the event's settings. Then go to
Settings → Fixed sessions (`/orga/event/<event>/settings/p/fixed-sessions/`).

- **New core session** creates a session type (name, duration) together with
  its fixed content. Use one per core session, e.g. "Intro to Contact Staff".
- **Make core session** on an existing session type adds fixed content to it.
- **Make write-in session** removes the fixed content. Proposals keep the text
  they have; speakers can edit it again.

Organisers need permission to change event settings.

## Fixed content

| Field | Applied |
| --- | --- |
| Title, abstract, description | always |
| Track | only when set; empty lets the speaker choose |
| Don't record | only when set to Yes or No; "Speaker chooses" leaves it alone |

Duration comes from the session type, as for any session. Notes to the
organisers, co-speakers, answers to questions and resources stay the speaker's.

## How it works

- The content is applied on every save of a proposal of a core session type
  (`pre_save` on `Submission`): the CfP, the speaker's edit page, the organiser
  backend and the API all go through it. What speakers type into these fields
  is discarded.
- Saving a core session's content in the plugin also writes it to every
  existing proposal of that type (drafts and deleted ones included), and logs
  it in the event's activity log.
- In the CfP form and the speaker's edit page, choosing a core session type
  fills in the title, abstract and description and makes them read-only, with
  a note that the organisers set them (`static/pretalx_fixed_sessions/form.js`).
  Without JavaScript, the speaker still has to enter a title to get past form
  validation; it is replaced on save.
- When the plugin is disabled for an event, nothing is enforced and the pages
  return 404. The stored content is kept.

## Tests

```sh
./run-tests.sh            # uses the pretalx-sso:latest image; set IMAGE= to change
IMAGE=pretalx:local ./run-tests.sh -k orga
```

The tests run against this source tree with a throwaway SQLite database. The
form script itself isn't run in the tests; they check that the pages carry the
data and field ids it uses.
