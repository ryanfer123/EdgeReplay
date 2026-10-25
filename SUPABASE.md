# Private cloud workspaces

Cloud storage is optional. Local analysis and local exports do not need an account.
The browser connects directly to Supabase Auth and PostgREST using a publishable
key and the signed-in user's access token. The Python server exposes only public
configuration, and never receives account passwords or stores cloud sessions.

## Configure

Apply `supabase/migrations/202610250001_cloud_workspaces.sql` to your Supabase
project using your normal migration workflow. It creates only
`public.edge_replay_cloud_workspaces` and its policies/index. Do not apply it twice: duplicate table
names fail rather than silently modify existing data.

Set `SUPABASE_URL` to the project's HTTPS URL and `SUPABASE_PUBLISHABLE_KEY` to its
`sb_publishable_…` key. Alternatively use a **git-ignored**, repo-root
`cloud.config.json` with those same two property names. Environment values take
precedence. Never put a secret/service-role key here. The helper rejects other key
formats. No private keys belong in the browser or repository.

Expose `GET /api/cloud/config` as JSON from `edge_replay.cloud.cloud_config()`.
Return `Cache-Control: no-store`. The disabled response is
`{"configured": false, "message": "…"}`. The enabled response contains
`configured`, `url`, `publishableKey`, `table`, and `maxPayloadBytes` (8388608).
Serve `/cloud.js` and `/cloud.css` from the package's web directory, and allow the
configured Supabase HTTPS origin in your Content-Security-Policy `connect-src`.

## Browser integration

Load `cloud.css` and deferred `cloud.js`, then initialize once per page:

```js
const cloud = CloudWorkspace.init({
  kind: 'EdgeReplay',
  title: 'Your cloud workspaces',
  getSnapshot: async () => currentSerializableWorkspace,
  onLoad: async payload => restoreLocalWorkspace(payload),
});
accountButton.addEventListener('click', () => cloud.open());
```

`getSnapshot()` must return a JSON-serializable object representing the current
artifact, including the inputs needed to restore it. Avoid local file paths,
secrets, and ephemeral IDs. `onLoad(payload)` must validate the saved schema and
restore through the app's ordinary local API; show an error for an unsupported
schema. It can return a promise. The dialog closes only after restoration succeeds.
Omit `getSnapshot` on pages that cannot save; omit `onLoad` on pages that cannot
restore. The dialog asks before replacing the current view or deleting a cloud copy.
Loading a copy never executes code contained in its data.

Saving always creates a new copy. The list shows the latest 100 copies; users can
delete old copies. Title length is 1–120 characters, and payloads must be objects.
Both browser and database enforce an 8 MiB payload limit. PostgreSQL measures its
JSON text representation, so near-limit documents may be rejected after upload.
Use local export for large artifacts. A failed cloud operation leaves local work
intact. Cloud copies are private to an account, not end-to-end encrypted.

## Authentication and privacy

Sign in uses `POST /auth/v1/token?grant_type=password`; account creation uses
`POST /auth/v1/signup` only after an explicit click. If email confirmation is
required, confirm the email then return to sign in. Configure confirmation/site
URLs and SMTP in the Supabase dashboard for production. This client does not
consume redirect tokens, automatically create accounts, or automatically send mail.
Projects requiring CAPTCHA or MFA need a corresponding UI flow before they can use
this minimal password client.

Access/refresh tokens are held in memory and `sessionStorage`, scoped by project
URL and table. They are never written to permanent local storage. Normal browser
tab closure clears session storage; some browser session-restoration features may
restore it, so use **Sign out** on shared devices. If browser storage is blocked,
the session is memory-only. Expiring sessions refresh through the official token
endpoint; concurrent requests share one refresh. A transient network failure keeps
the refresh token available for retry; an invalid refresh or unauthorized data
request clears the session. Sign out clears local credentials even when offline;
server-side revocation then cannot be confirmed. Password fields are cleared after
successful authentication and when the dialog closes.

The table has `owner_id` referencing `auth.users`, an owner/created-date index, and
RLS on all four CRUD operations. UPDATE has both USING and WITH CHECK, preventing
ownership transfer. Anonymous users receive no table privileges. Browser account
IDs are not trusted: database policies compare ownership against `auth.uid()`.
Account deletion cascades to its cloud copies.

## Verification

Run `python3 -m unittest discover -s tests -p test_cloud.py` from this repository.
The suite checks config fail-closed behavior and runs the real browser client in
Node with mocked network responses for signup, signin, token persistence, refresh
concurrency, private CRUD, invalid/oversized inputs, expired sessions, signout and
network failures. It does not create accounts, send email, or prove a live policy
deployment. Before release, verify live isolation using two test-user JWTs and
an anonymous request: one user must never read, modify, delete or transfer another
user's copy. Also verify each app restores its own exported artifact correctly.

References: [Auth REST API schema](https://github.com/supabase/auth/blob/master/openapi.yaml),
[password authentication](https://supabase.com/docs/guides/auth/passwords),
[row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security).
