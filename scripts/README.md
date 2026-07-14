# Scripts Policy

Operational scripts may be added here when a repeated engineering or migration task cannot be
expressed clearly through the package or standard tooling. Product business logic does not belong
in scripts.

Every script must:

- have a single documented purpose and typed entry point;
- import reusable behavior from the backend package instead of duplicating it;
- validate configuration through `ceo_voice.config`;
- use centralized logging and safe structured context;
- default to read-only or dry-run behavior for data changes;
- require explicit scope for tenant- or leader-affecting operations;
- be idempotent when practical and document when it is not;
- return a non-zero exit code on failure;
- include tests for parsing and decision logic;
- avoid accepting secrets as command-line arguments, where process listings can expose them.

The supported release operations are package entry points and Make targets rather than wrapper
scripts:

- `make doctor` validates installation and configuration;
- `make demo` runs the offline profile-to-evaluation fixture and retains artifacts;
- `make benchmark` verifies deterministic benchmark and regression behavior;
- `ceo-voice build|onboard` runs the durable product workflows.

Keeping orchestration in the installed package ensures containers, CI, and local environments use
the same implementation. Add a script only when an operation cannot be represented by those public
interfaces.
