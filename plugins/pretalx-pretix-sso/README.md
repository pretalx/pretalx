# pretalx-pretix-sso

Adds a "Log in with pretix" button to the CfP login page. Speakers sign in with
their pretix customer account via OpenID Connect. Organisers, reviewers and
admins (anyone on a team) are refused and must use their password.

## Setup

1. In pretix: Organizer → Customer accounts → SSO clients → add a client
   (confidential, authorization code) with redirect URI
   `https://<pretalx host>/p/pretix-sso/callback/`.
2. Configure pretalx (`pretalx.cfg`, or the `pretix_sso_*` OpenTofu variables):

   ```ini
   [plugin:pretalx_pretix_sso]
   issuer = https://pretix.eu/<organizer>
   client_id = ...
   client_secret = ...
   ```

3. Enable the "pretix SSO" plugin in each event's settings.

New users are created from the pretix email and name. Only pretix-verified
email addresses are accepted. Each SSO login links the pretalx account to that
pretix account, so later logins find it even if either email changes; if a
speaker logs in with a different pretix account, the link moves to it.

An existing speaker account is matched by email on its first SSO login. Because
pretalx never verified the emails of password accounts, that first link
disables the account's password (the speaker is told so), so only the owner of
the verified address can get in. "Forgot password" still works afterwards.

In the submission wizard, pretix is the only sign-in option: the password login
and registration form is hidden and refused. The regular login page keeps
password login for organisers, but its registration form is hidden and refused,
so new accounts can only be created through pretix.

## Ticket check (organisers)

The organiser sidebar gets a "pretix tickets" page listing speakers and
whether they hold a paid order in the pretix event with the same slug. Speakers
are matched first by the pretix account they last logged in with (linked on
each SSO login), then by order or attendee email. Organisers can mark a speaker
as covered (e.g. a complimentary ticket), and sync two tags: `needsTicket` onto
every proposal where no speaker is covered, and `hasTicket` onto every proposal
where a speaker holds a paid pretix ticket (an override alone is not a ticket, so
a proposal covered only by an override gets neither tag). Both cover all states
and submission types, except drafts and deleted proposals. Only admission
products count as tickets (not add-ons or merchandise), and a ticket belongs to
its named attendee, or to the buyer when no attendee is named. Results are
cached for 60 minutes; "Refresh from pretix" and the tag sync always fetch fresh
data. Only the order fields the check uses are requested from pretix.

When pretalx has a celery worker (a `[celery] broker` is configured, as in the
Docker setup), pretix is never called inside a web request: refreshes and tag
syncs run as background jobs, one at a time per event, and the page shows the
last results with their age and updates itself when a job finishes. Without a
worker, the same work runs within the request instead.

Configure in the same section:

SSO account creation, first-time linking and moved links, ticket overrides and
tag syncs (including failed ones) are recorded in the event's activity log.

The plugin's server logs (logins, pretix fetches, tag syncs, ...) go to stdout
in pretalx's log format, from the web and the celery worker alike, and to
pretalx's log file. They identify people by pretalx user code only.

Give the API token's team only "Can view orders", and only for the events
pretalx needs, since the token can read every attendee's details.

```ini
api_token = <pretix team API token with "Can view orders">
# optional, when slugs differ: pretalx-slug=pretix-slug, ...
event_map = conf2026=conference-2026
# derived from issuer (https://<pretix host>/<organizer>) by default; set
# organizer when your pretix organizer has its own domain
pretix_url = https://pretix.eu
organizer = myorg
```

## Secrets from the environment

Every setting above can also come from an environment variable named
`PRETALX_PRETIX_SSO_<SETTING>` (e.g. `PRETALX_PRETIX_SSO_CLIENT_SECRET`,
`PRETALX_PRETIX_SSO_API_TOKEN`), which takes precedence over `pretalx.cfg`.
The local docker compose setup reads these from `.env` (see `.env.example` in
the repository root), so no secret has to live in a config file.

## Tests

```sh
./run-tests.sh            # all tests, inside the pretalx-sso:latest image
./run-tests.sh -k tickets # a subset; any pytest arguments work
```

The tests run against this source tree with a throwaway SQLite database; pretix
is mocked. Test dependencies are pinned in `tests/requirements.txt`. CI
(`.github/workflows/plugin-tests.yml`) builds the image and runs the suite on
every push that touches the plugin or `Dockerfile.standalone`.

`tests/test_restrict.py` goes through pretalx's full request stack, so run the
suite after every pretalx upgrade: it is what notices when the patched pretalx
internals change. The supported pretalx versions are declared in
`pyproject.toml`; a test fails when the installed pretalx is outside that range,
so bumping the pretalx submodule forces a deliberate check.
