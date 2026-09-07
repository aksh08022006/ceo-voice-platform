# Production editorial workflow

CEO Voice is being changed from an anonymous, browser-owned showcase into an authenticated editorial workspace. Its purpose is to help The Narrative Company draft and revise posts and replies in an executive's documented written style, while editors retain responsibility for factual claims and publication.

The first deployment is scoped to the internal Narrative editorial team. It does not claim to be an externally audited multi-client SaaS product. Separate customer workspaces, onboarding authority and retention policies require an explicit rollout decision.

## What the architecture separates

1. **Identity and access.** Managed sign-in proves the user's identity. The API verifies EdDSA signature, issuer, audience and lifetime, then reads current email verification, ban state and workspace membership. The browser cannot grant roles. Signing up alone grants no workspace access. The first owner is restricted to the email verified on the connected Vercel account.
2. **Voice evidence.** Immutable profile releases supply stylistic examples and measurements. These examples describe writing; they are not factual proof for a new post. The existing Ali Ghodsi and Matei Zaharia releases retain their development status and source-provenance limitations.
3. **Factual brief.** The idea, constraints, source contents and attributed parent post are preserved with the draft. A URL alone does not establish a fact. Source contents enter generation as well as review.
4. **Candidate and revisions.** PostgreSQL owns the current revision. Each saved version binds encrypted content and brief to the workspace, workflow, candidate hash and author. Edits create a new version and invalidate the previous review and approval. Browser continuation expiry does not delete saved work.
5. **Claim screening.** A bounded model call screens factual and editorial claims for support, contradiction, missing evidence and uncertainty. The server verifies exact quotations, coverage, hashes and source authority. It can align an incorrectly counted offset only to a unique verbatim quotation in the declared unit or source. It never fuzzy-matches invented evidence. Screening remains fallible.
6. **Named approval and export.** Approval binds a reviewer to the exact current revision, brief, content and review run. Failed, unavailable or uncertain screening cannot be approved. Export checks the same current approval atomically. The application does not post automatically to social accounts.

## Operational behavior

Model actions reserve an idempotency key and commit dispatch before contacting the provider. A repeated completed request returns the saved workflow's current state without another provider call. Stale edits conflict instead of overwriting newer work. An expired dispatched run is indeterminate and stays fenced pending reconciliation; it is not silently billed again. The database enforces a rolling hourly run limit per workspace member. Provider retries are disabled for the authenticated workspace; bounded content repairs are separate, recorded calls.

PostgreSQL is mandatory when the workspace is enabled. SQLite exists only for local tests. The API uses a restricted database role that can read six managed identity columns and the application tables; it cannot read session/password/signing-key data, delete rows, rewrite history or perform DDL. TLS verifies the server certificate using an explicit CA bundle. Migrations use a separate administrator credential.

See [durable storage operations](DURABLE_WORKSPACE.md) for leases, migrations and recovery. Preserve both immutable profile bundles and encryption keys independently of deployment source. A database backup without its keys is not a usable recovery plan.

The API deploys in `iad1` beside the database, with a 300-second function limit. `uv.lock` pins the Vercel Python build to the same package versions as the checked pip lock files; CI checks that the uv lock remains current. Frontend dependencies use `npm ci` and its committed lock. Runtime configuration and secrets are provisioned separately from source. See [Vercel Python dependency support](https://vercel.com/docs/functions/runtimes/python).

## Sign-in dependency and rollout

The selected managed identity service is Neon Auth. Its official SDK currently carries a beta version; the Next.js integration was inspected and tested rather than assumed stable from older examples. The application uses the API integration, with no anonymous-token fallback. Browser API calls obtain a JWT from the authenticated same-origin `/api/auth/token` proxy using an uncached fetch and the existing HttpOnly cookie. The SDK's `token()` method shares its in-memory session cache, so it is not used to issue the API bearer. Neon's signed session cache can contain an opaque session token without the upstream `set-auth-jwt` header; treating that field as a JWT failed during live sign-in and is covered by a regression test. Authentication responses explicitly use `private, no-store`. The identity boundary is separated from editorial persistence to make a future provider migration possible. Replacing an identity provider requires an explicit subject-to-membership migration, not just a configuration swap.

Verified provider configuration:

- Issuer is the complete managed auth base URL, including `/neondb/auth`.
- Audience is the HTTPS origin of that provider.
- JWKS is at the auth base URL plus `/.well-known/jwks.json` and currently publishes EdDSA keys.
- The existing Vercel domain is registered as a trusted origin. A negative sign-in probe now reaches the provider's credential check (401), replacing the earlier `INVALID_ORIGIN` response. Email verification is required at sign-up and uses codes. The UI supports that code flow and the configured Google provider. Application sign-in and the first owner's workspace access are checked separately from Neon console account linking.

Human voice-quality acceptance remains separate from passing software tests. The supplied profiles still need dated, independently held-out samples, suitable reuse authority and named editorial evaluations before they can represent verified client voices. The engineering assignment's acceptance packet remains pending rather than being filled with generated ratings.

The frontend keeps `output: standalone` only for self-hosted builds. Vercel uses its adapter's server packaging; enabling both hit a [reported Next.js 16.3 integration defect](https://github.com/vercel/next.js/issues/96646), reproduced during staging and resolved by this configuration.

## References

- [Neon Auth overview](https://neon.com/docs/auth/overview)
- [Neon Next.js server integration](https://neon.com/docs/auth/reference/nextjs-server)
- [Neon authentication flow](https://neon.com/docs/auth/authentication-flow)
- [Semantic fidelity implementation and research](SEMANTIC_FIDELITY.md)
- [Written voice research and evaluation decisions](WRITTEN_VOICE_RESEARCH.md)
