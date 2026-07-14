# Operations guide

## Runtime modes

The release is a CLI package, not a continuously running web service. `ceo-voice doctor` is the
startup/readiness check used by local setup and the container image. A scheduler may invoke build
or onboarding commands as jobs; it must retain the workspace volume between retries.

| Mode | Configuration | Persistence | Intended use |
|---|---|---|---|
| Development | `configs/development.env` | local JSON/in-memory | engineering and inspection |
| Offline demo | deterministic test configuration | `data/demo/` | wiring and regression evidence |
| Production CLI | `configs/production.env` plus injected secrets | mounted workspace or organization adapter | governed batch jobs |

Do not put API keys in Compose files, manifests, logs, or images. Inject them with the deployment's
secret manager. `SecretStr` prevents routine representation but does not make an exposed secret
safe after logging or serialization.

## CEO onboarding runbook

1. Obtain material through official exports, licensed feeds, owner-provided files, or authorized
   APIs. Record license/consent, source URL, acquisition method, collection time, and deletion
   obligations.
2. Normalize source records through the ingestion pipeline. `LocalExportConnector` accepts a JSON
   array or JSONL with the fields demonstrated in `data/examples/local-export.jsonl`. The connector
   root is fixed at construction; a request path cannot escape it.
3. Review authorship and source modality. Remove ghostwritten, quoted, duplicated, truncated,
   translated, or low-confidence items unless the identity policy explicitly models them.
4. Build an `OnboardingManifest` containing the curated `ProfileBuildManifest` and the independently
   governed `ViralityCorpus`. The two corpora share a tenant but need not contain the same posts.
5. Run:

   ```bash
   ceo-voice onboard --manifest onboarding.json --workspace ./data/runtime
   ```

6. Inspect `onboarding/report.json`, the profile inspection report, corpus health, validation
   findings, evidence coverage, and VKR inspection. Exit codes are:

   - `0`: both releases published and the HVM passed configured generation-authority gates;
   - `1`: expected application/storage failure;
   - `2`: invalid manifest;
   - `3`: releases published, but the HVM is descriptive and not authorized for generation.

7. A qualified reviewer may approve a generation-capable registry/release using the organization's
   existing release-governance process. Never edit the report or set `generation_ready` manually.

Onboarding is idempotent for an unchanged content-addressed corpus. A changed corpus creates the next
immutable release and retains predecessor lineage.

## Container operation

```bash
docker compose build
docker compose run --rm cli doctor
```

The image runs as UID/GID `10001`, drops capabilities, sets `no-new-privileges`, and uses a read-only
root filesystem in Compose. `/app/exports` is read-only input; `/app/workspace` is the only durable
output. Back up and encrypt the workspace according to the source-data classification.

To run a manifest mounted below `data/exports`:

```bash
docker compose run --rm cli onboard \
  --manifest /app/exports/onboarding.json \
  --workspace /app/workspace
```

The Docker `HEALTHCHECK` calls `ceo-voice doctor`. Because the default container is a one-shot CLI
job, orchestrators should use its process exit status as the primary health signal.

## Logging and diagnostics

Production configuration requires JSON logging. Logs may contain stable IDs, stage, latency,
attempt number, status, and error code. They must not contain source text, prompts, drafts, API keys,
or full provider responses. Integration failures preserve all artifacts completed before the failed
stage and write an `integration-outcome.json` diagnostic with retryability.

Common diagnoses:

- `invalid_manifest`: validate JSON against the installed Pydantic contract and check UTC timezone
  offsets, UUIDs, content hashes, and tenant/leader alignment.
- `profile_not_generation_ready` or onboarding exit `3`: expected governance gate; inspect corpus
  health and authority rather than retrying the provider.
- production configuration error: disable debug and set logging format to `json`.
- container cannot write: mount a writable workspace owned or writeable by UID `10001`.
- unchanged export yields no new documents: confirm the stored cursor/checkpoint or intentionally
  start a new workspace for a full replay.

## Data and failure policy

Raw source bytes are retained before transformation. Malformed individual records are rejected with
structured findings while valid peers may complete. Connector, scope, or storage failures abort the
batch and do not advance its checkpoint. Retries therefore resume from the last fully successful
batch. Deletion requests must cover raw, clean, observation, prompt, draft, and report artifacts in
accordance with the operator's retention policy.
