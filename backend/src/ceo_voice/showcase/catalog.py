"""Curated showcase catalog; labels are illustrative and not identity claims."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShowcaseProfile:
    """A selectable browser profile projection, independent of its artifact source."""

    slug: str
    name: str
    role: str
    summary: str
    status: str = "showcase"


@dataclass(frozen=True, slots=True)
class Walkthrough:
    """A polished, reproducible browser walkthrough."""

    slug: str
    profile_slug: str
    title: str
    platform: str
    content_type: str
    thread_post_count: int | None
    virality_influence: float
    minimum_words: int | None
    maximum_words: int | None
    idea: str
    constraints: str
    human_edit: str


PROFILES = (
    ShowcaseProfile(
        "ali-ghodsi",
        "Ali Ghodsi",
        "Co-founder & CEO, Databricks",
        "Illustrative data-and-execution profile built from synthetic showcase documents.",
    ),
    ShowcaseProfile(
        "matei-zaharia",
        "Matei Zaharia",
        "Co-founder & CTO, Databricks",
        "Illustrative technical profile emphasizing mechanisms, clarity, and developer impact.",
    ),
    ShowcaseProfile(
        "jensen-huang",
        "Jensen Huang",
        "Founder & CEO, NVIDIA",
        "Illustrative keynote profile emphasizing technological transitions and long horizons.",
    ),
)

WALKTHROUGHS = (
    Walkthrough(
        "ali-tabular-acquisition",
        "ali-ghodsi",
        "Open source and the Tabular acquisition",
        "linkedin",
        "announcement",
        None,
        0.125,
        150,
        300,
        "Databricks acquired Tabular, the company behind Apache Iceberg. Explain why this validates open-source data infrastructure and brings the teams behind Spark and Iceberg together.",
        "Avoid hype. Include a company-specific detail and close with a forward-looking statement.",
        "I still remember an early conversation with the Tabular founders about a simple idea: data formats should remain open.\n\nThat belief shaped the structural change I wanted to preserve. Spark opened compute. Iceberg opened table formats. Bringing these teams together gives the ecosystem a clearer path to build on both.\n\nThe acquisition matters because customers should not have to choose between performance and openness. The best infrastructure earns adoption by making it easier for everyone to participate, extend it, and move their data without being trapped.\n\nWe are excited to work with the Tabular team and the broader community on the next chapter of open lakehouse infrastructure.",
    ),
    Walkthrough(
        "matei-compound-ai-systems",
        "matei-zaharia",
        "Compound AI systems",
        "x",
        "thread",
        3,
        0.10,
        None,
        None,
        "The AI industry is converging on compound systems. Progress will come from orchestrating models, retrieval, and tools rather than only making one model larger.",
        "Explain the mechanism before the benefit. Keep it technical and avoid corporate announcement language.",
        "A useful shift in AI systems: the model is becoming one component, not the whole application.\n---\nRetrieval, tools, routing, memory, and evaluation determine whether a system works reliably. Improving their orchestration can matter more than increasing one model's size.\n---\nThis is why compound AI systems are an important systems problem: progress now depends on the interfaces and feedback loops between components.",
    ),
    Walkthrough(
        "jensen-visionary-keynote",
        "jensen-huang",
        "A visionary keynote moment",
        "x",
        "post",
        None,
        0.125,
        None,
        None,
        "Explain why accelerated computing is becoming infrastructure for every industry.",
        "Connect the platform shift to builders without making forecasts.",
        "Computing is entering a new platform transition.\n\nAs models become part of every product, accelerated computing becomes infrastructure—not a specialty.\n\nThe next chapter belongs to builders who can turn that infrastructure into useful intelligence for every industry.",
    ),
)


def profile_by_slug(slug: str) -> ShowcaseProfile:
    """Return a profile or raise a stable lookup error."""

    try:
        return next(item for item in PROFILES if item.slug == slug)
    except StopIteration as exc:
        raise KeyError(slug) from exc


def walkthrough_by_slug(slug: str) -> Walkthrough:
    """Return a walkthrough or raise a stable lookup error."""

    try:
        return next(item for item in WALKTHROUGHS if item.slug == slug)
    except StopIteration as exc:
        raise KeyError(slug) from exc
