"""FastAPI application wiring for browser product workflows."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ceo_voice.config import Settings, get_settings
from ceo_voice.core.exceptions import ApplicationError, ConfigurationError
from ceo_voice.core.logging import configure_logging, request_context
from ceo_voice.generation import HttpxJsonTransport
from ceo_voice.services import create_model_provider
from ceo_voice.showcase import PROFILES, WALKTHROUGHS, ShowcaseWorkflowService
from ceo_voice.showcase.catalog import profile_by_slug
from ceo_voice.showcase.service import WorkflowSession

from .schemas import (
    DimensionResponse,
    EvidenceResponse,
    GenerateWorkflowRequest,
    HealthResponse,
    MetricResponse,
    ProfileResponse,
    ReVoiceWorkflowRequest,
    WalkthroughResponse,
    WorkflowResponse,
)

DISCLAIMER = (
    "Showcase mode uses synthetic corpora. Model-disabled runs use a deterministic local provider; "
    "model-enabled runs use the configured external provider. Named profiles demonstrate workflow "
    "behavior and are not verified identity simulations."
)


def create_app(
    settings: Settings | None = None,
    service: ShowcaseWorkflowService | None = None,
) -> FastAPI:
    """Create an isolated application with injected configuration and workflow service."""

    resolved = settings or get_settings()
    transport: HttpxJsonTransport | None = None
    if service is not None:
        workflows = service
    elif resolved.model.enabled:
        if resolved.model.generation_model is None:
            raise ConfigurationError("enabled model configuration has no generation model")
        transport = HttpxJsonTransport(
            timeout_seconds=resolved.model.request_timeout_seconds,
        )
        workflows = ShowcaseWorkflowService(
            provider=create_model_provider(resolved.model, transport),
            model=resolved.model.generation_model,
            model_context_tokens=resolved.model.context_window_tokens,
            maximum_output_tokens=resolved.model.maximum_output_tokens,
            maximum_provider_retries=resolved.model.max_retries,
        )
    else:
        workflows = ShowcaseWorkflowService()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            level=resolved.logging.level,
            output_format=resolved.logging.format,
            service_name=resolved.application.service_name,
        )
        yield
        if transport is not None:
            await transport.aclose()

    application = FastAPI(
        title="CEO Voice Platform API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.state.workflows = workflows
    application.state.settings = resolved
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.api.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        identifier = request.headers.get("X-Request-ID") or uuid4().hex
        with request_context(identifier):
            response = await call_next(request)
        response.headers["X-Request-ID"] = identifier
        return response

    @application.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=error.to_dict())

    @application.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=resolved.application.service_name,
            showcase_enabled=resolved.api.showcase_enabled,
            model_enabled=resolved.model.enabled,
            model_provider=resolved.model.provider if resolved.model.enabled else None,
        )

    @application.get("/api/v1/profiles", response_model=tuple[ProfileResponse, ...])
    async def profiles() -> tuple[ProfileResponse, ...]:
        _ensure_showcase(resolved)
        return tuple(
            ProfileResponse(
                slug=item.slug,
                name=item.name,
                role=item.role,
                summary=item.summary,
                status=item.status,
            )
            for item in PROFILES
        )

    @application.get("/api/v1/walkthroughs", response_model=tuple[WalkthroughResponse, ...])
    async def walkthroughs() -> tuple[WalkthroughResponse, ...]:
        _ensure_showcase(resolved)
        return tuple(
            WalkthroughResponse(
                slug=item.slug,
                profile_slug=item.profile_slug,
                title=item.title,
                platform=item.platform,
                content_type=item.content_type,
                idea=item.idea,
                constraints=item.constraints,
                human_edit=item.human_edit,
                profile_name=profile_by_slug(item.profile_slug).name,
            )
            for item in WALKTHROUGHS
        )

    @application.post("/api/v1/workflows/generate", response_model=WorkflowResponse)
    async def generate(value: GenerateWorkflowRequest) -> WorkflowResponse:
        _ensure_showcase(resolved)
        try:
            session = await workflows.generate(
                profile_slug=value.profile_slug,
                platform=value.platform,
                content_type=value.content_type,
                idea=value.idea,
                constraints=tuple(
                    line.strip() for line in value.constraints.splitlines() if line.strip()
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return _project(session)

    @application.get("/api/v1/workflows/{session_id}", response_model=WorkflowResponse)
    async def get_workflow(session_id: UUID) -> WorkflowResponse:
        return _project(_session_or_404(workflows, session_id))

    @application.post("/api/v1/workflows/{session_id}/revoice", response_model=WorkflowResponse)
    async def revoice(session_id: UUID, value: ReVoiceWorkflowRequest) -> WorkflowResponse:
        _session_or_404(workflows, session_id)
        return _project(await workflows.revoice(session_id, value.content))

    @application.post("/api/v1/workflows/{session_id}/evaluate", response_model=WorkflowResponse)
    async def evaluate(session_id: UUID) -> WorkflowResponse:
        _session_or_404(workflows, session_id)
        return _project(await workflows.evaluate(session_id))

    return application


def _ensure_showcase(settings: Settings) -> None:
    if not settings.api.showcase_enabled:
        raise HTTPException(status_code=404, detail="showcase mode is disabled")


def _session_or_404(service: ShowcaseWorkflowService, session_id: UUID) -> WorkflowSession:
    try:
        return service.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow session not found") from exc


def _project(session: WorkflowSession) -> WorkflowResponse:
    artifacts = session.outcome.artifacts
    if artifacts.draft is None or artifacts.retrieval is None:
        raise RuntimeError("successful workflow session has incomplete artifacts")
    draft, retrieval = artifacts.draft, artifacts.retrieval
    report = draft.report
    evaluation = session.evaluation
    revoice = session.revoiced
    voice = tuple(
        EvidenceResponse(
            id=item.evidence_id,
            label=(
                item.explanation.supporting_feature_ids[0]
                if item.explanation.supporting_feature_ids
                else "voice evidence"
            ),
            confidence=item.score.final_score,
            source=str(item.document_id),
            reason=item.explanation.reason,
        )
        for item in retrieval.evidence
        if item.explanation.supporting_feature_ids
    )
    structure = tuple(
        EvidenceResponse(
            id=item.evidence_id,
            label="structural pattern",
            confidence=item.score.final_score,
            source=str(item.document_id),
            reason=item.explanation.reason,
        )
        for item in retrieval.evidence
        if item.explanation.supporting_pattern_ids
    )
    return WorkflowResponse(
        session_id=session.id,
        profile_slug=session.profile.slug,
        profile_name=session.profile.name,
        platform=artifacts.context.platform.platform.value if artifacts.context else "unknown",
        content=draft.content,
        edited_content=session.edited.content if session.edited else None,
        revoiced_content=revoice.content if revoice else None,
        report=(
            MetricResponse(label="Model", value=report.model),
            MetricResponse(label="Latency", value=f"{report.total_latency_ms} ms"),
            MetricResponse(
                label="Tokens",
                value=str(report.total_usage.input_tokens + report.total_usage.output_tokens),
            ),
            MetricResponse(
                label="Validation", value="Passed" if report.final_validation.valid else "Failed"
            ),
        ),
        voice_features=voice,
        structural_features=structure,
        evidence_count=len(retrieval.evidence),
        timeline=tuple(
            MetricResponse(
                label=item.stage.value.replace("_", " ").title(), value=f"{item.duration_ms} ms"
            )
            for item in session.outcome.timeline
        ),
        changed_regions=revoice.report.changed_regions if revoice else (),
        preserved=tuple(item.subject for item in revoice.report.preserved) if revoice else (),
        revoice_confidence=revoice.report.confidence if revoice else None,
        evaluation_score=round(evaluation.overall_score * 100, 1) if evaluation else None,
        evaluation_status=evaluation.status.value if evaluation else None,
        dimensions=(
            tuple(
                DimensionResponse(
                    label=item.dimension.value.replace("_", " ").title(),
                    score=round(item.score * 100, 1),
                    passed=item.passed,
                    summary=item.summary,
                )
                for item in evaluation.dimensions
            )
            if evaluation
            else ()
        ),
        recommendations=evaluation.recommended_improvements if evaluation else (),
        disclaimer=DISCLAIMER,
    )


app = create_app()
