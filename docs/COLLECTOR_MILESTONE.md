# Public-content collector: first milestone

## Requirement and risk assessment

The collector accepts only operator-supplied local JSON, JSON Lines, and CSV data. It does not
make network requests, automate a browser, use cookies, or implement an X or LinkedIn connector.
Public visibility is not considered an authorization basis.

Before a file is opened, the source policy must be human-approved and name a known reuse basis.
The gate blocks unknown reuse, authentication, payment, unsupported methods, connector-policy
mismatches, and all network-capable connectors. Each decision creates a content-free receipt.

The remaining human decisions are source terms, asserted authorization, authorship evidence, and
whether an account export was obtained lawfully. The system cannot establish those facts itself.

## Implemented boundary

`ceo_voice.collector` provides immutable authorization, capability, checkpoint, version, and
report contracts; an offline local connector; filesystem storage; and a CLI. Canonical output is
written to `<storage-root>/canonical/<source-id>.jsonl`; original provider payloads go to
`<storage-root>/raw/<source-id>/`, and receipts/checkpoints/version fingerprints go under
`<storage-root>/metadata/`. `data/collector/` is Git-ignored for local development use.

Supported inputs are `.json` (a list or `{ "records": [...] }`), `.jsonl`, and `.csv`. CSV
booleans, nulls, and nested `performance` values must be JSON-encoded cells. Export the record
schema with `ceo-collector export-schema --output PATH`.

Commands: `inspect-source`, `collect`, `resume`, `validate-dataset`, `export-schema`, `report`,
and `doctor`. `resume` is idempotent: unchanged post fingerprints are skipped, while changed
content is appended as a new version rather than overwriting history.

## Explicitly blocked

No official API adapter is enabled, and no credentialless X or LinkedIn collection exists. Those
ports must remain disabled until access method, terms, and policy approval are recorded.
