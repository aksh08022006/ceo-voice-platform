# Coding Guidelines

## Design standard

Code should make ownership and change impact obvious. Prefer a small cohesive module with a stable
contract over a configurable abstraction that anticipates unproven use cases.

The default dependency direction is transport → application → feature/domain contracts → core.
Infrastructure adapters implement ports; domain and application code do not import adapter SDKs.

## Typing

- Type every function parameter, return value, public attribute, and collection element.
- Use `UUID`, aware `datetime`, enums, and constrained Pydantic fields instead of unvalidated
  strings at module boundaries.
- Avoid `Any`. If an external library returns it, validate or narrow it at the adapter boundary.
- Use `object` when a value is intentionally opaque and no operation is permitted on it.
- Treat mypy strict-mode failures as design feedback, not annotations to suppress.
- A targeted ignore requires an error code and a comment explaining the external limitation.

## Models and schemas

- `models` contains canonical application concepts, not ORM rows or provider payloads.
- `schemas` contains boundary messages and may compose canonical models.
- Both reject unknown fields so contract drift fails visibly.
- Canonical snapshots are frozen. Create a new version instead of mutating a persisted artifact.
- All stored timestamps are timezone-aware UTC.
- Durable artifacts include tenant ownership and provenance appropriate to their sensitivity.
- Preserve canonical writing whitespace. Never apply generic collapse, strip, or punctuation cleanup
  unless a named pipeline stage stores both the original and transformed representation.
- Field descriptions and class docstrings explain semantics, not merely repeat type names.

## Functions and classes

- Give each unit one reason to change.
- Keep functions small enough that success, failure, and side effects are visible together.
- Prefer pure transformations; isolate I/O behind adapters.
- Do not add an interface solely to wrap one local function. Add a port when a boundary needs
  inversion, substitution, or contract testing.
- Inject clocks, sleep functions, clients, repositories, and policy collaborators where tests or
  deployment choices must control them.
- Constructors establish valid state; partially configured service objects are not allowed.

## Configuration and constants

- Read environment variables only in `config`.
- Pass validated settings or specific primitives to consumers.
- Credentials use secret types and external secret stores; they never have fallback values.
- Shared stable literals belong in `core.constants`. Feature-local literals remain with their
  owner. Not every string is a global constant.
- Provider model names, timeouts, retry counts, thresholds, and logging policy are configuration.

## Errors

- Raise a specific `ApplicationError` subclass for expected boundary failures.
- Use stable error codes; callers must not parse messages.
- `details` contains diagnostic identifiers and safe values, never secrets or full personal data.
- Set `retryable=True` only when the operation is idempotent and the failure class is transient.
- Do not catch `Exception` merely to log and re-raise at multiple layers.
- Unexpected defects should retain their traceback and be handled once at the process boundary.

## Logging and observability

- Obtain a logger with `get_logger(__name__)`.
- Use conventional severity: debug for local diagnostics, info for lifecycle events, warning for
  recoverable degradation, error for failed operations, critical for process-level hazards.
- Use stable structured fields such as tenant ID, CEO ID, artifact version, operation, and duration.
- Do not log raw documents, generated drafts, prompts, credentials, authorization headers, or
  unredacted provider responses.
- Establish request context at entry points. Lower layers consume it implicitly through logging.
- Log an event once at the layer that can explain its business meaning.

## Retry and external calls

- Retries are explicit and bounded.
- Retry only selected transient exceptions, never all failures by habit.
- Confirm idempotency before retrying writes.
- Apply timeouts at every network boundary.
- Provider SDK types and exceptions are translated inside their adapter.
- Backoff and final failure should be observable without exposing request content.

## API design

No API is implemented in the current phase. When transport work begins:

- endpoints translate transport input into application schemas and call one use case;
- no business decision belongs in route handlers;
- idempotency and request correlation are explicit;
- pagination, errors, and versioning use consistent envelopes;
- authorization checks tenant ownership before artifact access;
- provider, database, prompt, and evaluator details remain absent from public contracts.

## Testing

- Unit tests are deterministic and do not use network, real time, or durable services.
- Test observable behavior, invariants, edge cases, and failure paths.
- Adapter contract tests verify translation to external systems.
- Integration tests verify owned boundaries with disposable dependencies.
- Evaluation tests use versioned datasets and compare quality dimensions independently.
- Every defect fix starts with a reproducing test when feasible.
- Coverage must remain at least 90%, but review focuses on assertion quality and risk coverage.

## Documentation

- Public classes and functions have docstrings explaining purpose, important inputs, outputs, and
  failure behavior.
- Architectural decisions that constrain several modules receive an ADR in `docs/`.
- README and setup instructions must remain executable on a clean machine.
- Comments explain why a non-obvious decision exists; code should explain what it does.
- Do not leave undocumented placeholder methods, empty `pass` bodies, or speculative TODOs.

## Style and automation

- Black is the canonical formatter.
- Ruff enforces imports, correctness, modernization, and common maintainability rules.
- Mypy runs in strict mode with the Pydantic plugin.
- Pre-commit applies fast checks; pre-push runs the test suite.
- Do not weaken a shared rule to land one change. Fix the design or document a narrowly scoped,
  reviewed exception.

## Review checklist

Before review, confirm:

- the change belongs to one clear module;
- dependency direction remains inward;
- data ownership, versioning, provenance, and tenant boundaries are preserved;
- no secret, private content, or provider implementation leaks through logs or contracts;
- success and expected failures have tests;
- `make check` succeeds;
- documentation and the dependency lock are updated when their source changes.
