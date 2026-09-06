# Browser-held workflow continuation

Vercel instances do not share a Python dictionary. When a deployed catalog and
`CEO_VOICE_API__CONTINUATION_KEY` are configured, successful workflow responses include an
encrypted, authenticated `continuation_token`. The browser saves it in session storage and sends
it in the JSON body of resume, revoice, and evaluation requests. Tokens never enter URLs, cookies,
public logs, or profile analytics. Workflow responses use `Cache-Control: no-store`.

The token contains the original draft, current revision, edit decisions, generation context,
retrieved evidence, and evaluation. Full voice/structure profiles and rendered prompts remain on
the server. Restoration requires the same profile slug, voice and structure release IDs, and
content hashes. An updated profile cannot silently change a draft's voice midway through editing.

Fernet provides authenticated encryption; JSON contracts provide typed deserialization. The server
authenticates before decompressing and bounds both token (2,000,000 characters) and decoded state
(8,000,000 bytes). Invalid, expired, foreign-session, and changed-profile snapshots return 410.
Requests without the token return 401 when continuation is enabled, even if a warm instance has a
copy. Never substitute a client-supplied unprotected profile or use pickle.

The default lifetime is seven days after the latest successful step. It is configurable via
`CEO_VOICE_API__CONTINUATION_TTL_SECONDS`. Generate a random Fernet key and store it as a Vercel
secret, shared by deployments that should resume each other's sessions. Replacing the key expires
existing tokens. Loss of the key also loses access to those snapshots.

This is a single-editor continuation protocol, not durable team storage. Closing the browser tab
removes its session storage. Disabled browser storage falls back to page memory, so refresh then
loses the token. A session URL alone does not transfer access. A copied valid old token can resume
that older branch; there is no global latest-revision registry or selective server revocation.
Expected revision checks detect stale edits within the supplied branch and a warm process. Add
authenticated shared storage and atomic revision updates before supporting simultaneous team editing.

In local model-disabled showcase mode the existing in-process workflow remains available for
tests. The production aliases still serve development-status Ali and Matei source bundles; hosting
on a production URL does not promote their data or human review status.

The regression suite creates a draft in application A, resumes and revoices it in new application B,
then evaluates it in application C. It also checks expiry, tampering, key rotation, release changes,
payload limits, malformed authenticated data and thread/revision preservation.

Reference: [Fernet documentation](https://cryptography.io/en/latest/fernet/).
