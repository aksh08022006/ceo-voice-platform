# Release checklist

## Code and contracts

- [ ] `make check` passes on a clean Python 3.13 environment.
- [ ] Public contract changes are backwards compatible or include a documented migration.
- [ ] Runtime and development dependency locks were regenerated and reviewed together.
- [ ] No source material, prompt content, model output, credential, or local workspace is tracked.
- [ ] New behavior has unit, failure, and end-to-end evidence proportional to risk.

## AI quality and governance

- [ ] Corpus provenance, consent/license, authorship, source modality, retention, and deletion owner
      are recorded outside filenames.
- [ ] HVM and VKR releases pass structural validation and retain exact evidence lineage.
- [ ] Generation authority was granted through review; no descriptive fixture was promoted by
      editing an artifact.
- [ ] Held-out evaluation includes named baselines, human rubric, inter-rater agreement, uncertainty,
      and failure examples before any real-person fidelity claim.
- [ ] Platform limits, protected facts, user edits, negative constraints, and safety constraints are
      covered by regression cases.

## Deployment

- [ ] `docker compose build` and `docker compose run --rm cli doctor` succeed.
- [ ] Image is scanned, pinned by digest, and signed according to organizational policy.
- [ ] Production secrets are injected externally and excluded from logs and artifacts.
- [ ] Durable storage adapter/volume is encrypted, backed up, tenant-isolated, and restore-tested.
- [ ] Job retry, concurrency, timeout, and checkpoint policies match provider and storage limits.
- [ ] Structured logs, metrics, alerts, trace correlation, and data-access audit events reach the
      organization observability stack.
- [ ] Rollback resolves the previous immutable HVM/VKR releases rather than mutating the active one.

## Product acceptance

- [ ] A new engineer can complete Quickstart without undocumented credentials.
- [ ] `make demo` produces the documented artifact set and its fixture limitation is visible.
- [ ] A new leader can be added through manifests without source changes.
- [ ] Onboarding exit `3` is treated as “review required,” not a failed build or a reason to bypass
      governance.
- [ ] Benchmark JSON and Markdown agree, and all real-person claims link to approved evidence.
- [ ] Operations, troubleshooting, contribution, license, and current limitations are accurate.
