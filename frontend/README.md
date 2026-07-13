# Frontend Boundary

The frontend is intentionally not implemented during the engineering-foundation phase. This
directory reserves an independently deployable client boundary without committing the platform to
a framework before operator workflows, API contracts, authentication, and deployment constraints
are validated.

When frontend work is authorized, it should:

- consume versioned public API schemas rather than import backend Python models;
- separate operator review, profile inspection, generation, and evaluation workflows;
- make voice evidence, confidence, profile version, and candidate evaluation visible;
- avoid exposing provider prompts, credentials, or internal storage identifiers;
- implement accessible states for loading, partial results, validation, failure, and retry;
- maintain its own tests, type checking, formatting, build, and dependency lock.

No JavaScript package manifest is present because adding one would imply a framework decision and
frontend implementation outside the current scope.
