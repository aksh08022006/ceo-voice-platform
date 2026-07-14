"""Single local composition root for the complete integration workflow."""

from ceo_voice.context import create_context_compiler
from ceo_voice.generation import (
    GenerationEngine,
    GenerationPolicy,
    OutputValidator,
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
)
from ceo_voice.generation.ports import ModelProvider
from ceo_voice.integration.runner import IntegrationRunner
from ceo_voice.profiles import (
    InMemoryProfileWorkspace,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.virality import InMemoryViralityWorkspace, create_virality_builder


def create_local_integration_runner(
    provider: ModelProvider, *, generation_policy: GenerationPolicy
) -> IntegrationRunner:
    """Wire production implementations with isolated in-memory persistence."""

    runtime = build_tier1_runtime()
    profile_workspace = InMemoryProfileWorkspace()
    virality_workspace = InMemoryViralityWorkspace()
    budget = TokenBudgetManager(generation_policy)
    prompt_builder = PromptBuilder(budget)
    prompt_renderer = PromptRenderer(budget)
    return IntegrationRunner(
        profile_builder=create_tier1_profile_builder(
            workspace=profile_workspace,
            runtime=runtime,
        ),
        virality_builder=create_virality_builder(workspace=virality_workspace),
        virality_workspace=virality_workspace,
        feature_registry=runtime.registry,
        context_compiler=create_context_compiler(),
        prompt_builder=prompt_builder,
        prompt_renderer=prompt_renderer,
        generation_engine=GenerationEngine(
            provider,
            prompt_builder,
            prompt_renderer,
            OutputValidator(),
            policy=generation_policy,
        ),
    )
