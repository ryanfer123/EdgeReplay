# Vercel hosting

This repository includes a stateless Python function and a static frontend build.
Select the repository root, Framework Preset **Other**, and keep the settings in
`vercel.json`. The build command is `python3 scripts/build_hosted.py`; browser
assets are copied into `public/`. Python 3.12 is selected in `.python-version`.
Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` in Vercel environment settings
for each environment that should offer private cloud copies. No secret/service
key is used. Apply the migration described in `SUPABASE.md` first.

Only the package's web directory is published as static files. The build injects
`hosted.js` before `app.js` in built workspace pages, leaving the local templates
unchanged. Local cloud configuration, environment files and SQLite files are
excluded from deployment by `.vercelignore`. Add `public/` and `.vercel/` to the
repository's `.gitignore`; both contain generated output or machine-local links.

## Storage and computation

Vercel instances do not share a durable filesystem. The production API never
opens SQLite: existing Python engines validate and compute each submitted
artifact, then return it. The hosting adapter keeps validated responses and
original telemetry CSV in memory plus this tab's `sessionStorage`. A visible
banner explains the temporary scope. Blocked/full browser storage falls back to
memory and changes the banner to advise export/cloud save. Closing a browser tab
normally clears temporary data; browser session restoration may preserve it.

Choose **Cloud → Save a new copy** for durable private storage using Supabase RLS,
or export files for independent backups. Vercel function instances hold neither
user sessions nor workspaces. Authentication connects directly from the browser
to Supabase with the user's JWT.

The browser adapter preserves the normal application endpoint protocol. For
retrieval evaluation it adds the selected dataset to the stateless run request.
Telemetry imports are parsed on the server and original validated CSV is retained
for exact CSV export. Geographic investigations are validated against bundled
metadata (or freshly fetched NASA metadata after Refresh), and NASA imagery is
fetched by the existing engine into `/tmp` only for provenance/cache computation.
Displayed images use the exact NASA source URL; `/tmp` is never treated as durable
or shared between invocations. JSON/Markdown exports come from this tab's actual
investigation record. Direct API export URLs require the running tab's browser
adapter and are not shareable links.

Request limits: retrieval JSON 2 MiB, telemetry JSON envelope 4 MiB, geographic
specification 32 KiB. Platform request/response and execution limits also apply;
large or slow inputs may need the local application. This release does not queue
background jobs. Cloud snapshot payload limits are documented separately.

## Verification

Run `python3 -m unittest discover -s tests -p test_hosted.py` and
`python3 scripts/build_hosted.py` locally. The tests exercise actual HTTP handlers
for validation/real retrieval or telemetry computation, mock NASA success/failure,
and run the real hosting adapter under Node for session storage, export data,
compute request wiring and external authentication pass-through. They do not prove
Vercel routing or a live deployed cloud integration.

After deploying, verify `/api/health` returns JSON, the homepage and workspace
load, each sample computes, exports download, a reload retains the tab's work,
and private cloud saves restore after a fresh browser session. GeoTrace also
needs the production UI to resolve imagery through
`HostedWorkspace.imageSource(source)`; the local path remains `/api/images/key`.

Official runtime reference:
https://vercel.com/docs/functions/runtimes/python/api-directory
