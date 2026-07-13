# Contributing

## Change philosophy

Each change should be independently understandable, testable, and reversible. A pull request should
solve one cohesive problem and preserve the architecture's dependency direction. Feature speed is
not a reason to bypass typed contracts, evaluation design, provenance, tenant isolation, or quality
gates.

## Before starting

1. Read [Architecture Overview](docs/ARCHITECTURE.md) and
   [Coding Guidelines](docs/CODING_GUIDELINES.md).
2. Identify the module that owns the behavior and the contract it will expose.
3. Confirm the work belongs to the active milestone. Do not bundle future-phase behavior into a
   foundation or infrastructure change.
4. For cross-module decisions, document alternatives and reversal cost before implementation.

## Branch and commit workflow

- Branch from the current default branch using a descriptive name.
- Keep commits focused and buildable where practical.
- Do not commit `.env`, local data, generated personal content, logs, coverage output, virtual
  environments, or editor state.
- Review staged changes for secrets and unrelated files before committing.
- Commit dependency changes together with `pyproject.toml`, `requirements.lock`, and relevant
  compatibility documentation.

## Required validation

Set up the repository and hooks as described in [Development Setup](docs/DEVELOPMENT.md), then run:

```bash
make check
```

A contribution is not ready for review until Ruff, Black, strict mypy, pytest, and the coverage
threshold succeed. New behavior requires tests for its success path, edge cases, and expected
failures.

## Pull request content

Explain:

- the outcome and reason for the change;
- the owning module and affected contracts;
- alternatives considered and important trade-offs;
- failure modes and operational impact;
- tests and evaluation evidence;
- configuration, migration, rollback, or data-compatibility requirements.

Screenshots are useful only for visible UI changes. Logs and provider payloads must be redacted.

## Review expectations

Reviewers evaluate correctness, cohesion, dependency direction, type safety, failure handling,
observability, security, data isolation, and test quality. A reviewer may request an architecture
decision record when a choice creates a lasting cross-module constraint.

Comments should identify the risk and desired invariant, not prescribe unnecessary implementation
detail. Authors should respond with evidence: code behavior, tests, measurements, or documented
trade-offs.

## Architecture decision records

Create an ADR under `docs/adr/` when a decision:

- selects a long-lived provider, database, workflow engine, or protocol;
- changes dependency direction or module ownership;
- changes the canonical representation of voice, evidence, generation, or evaluation;
- introduces a compatibility or migration burden;
- deliberately accepts a material security, quality, cost, or scalability trade-off.

An ADR states context, decision, considered alternatives, consequences, failure modes, and reversal
strategy. Creating the directory is part of the first ADR change; it is not needed for this phase.

## Security issues

Do not publish suspected vulnerabilities, exposed credentials, or private content in an issue or
pull request. Use the repository owner's private security-reporting channel. If a credential is
exposed, revoke it first; deleting it from the latest commit is not sufficient remediation.
