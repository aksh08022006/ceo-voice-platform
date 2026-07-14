"""Curated showcase catalog; labels are illustrative and not identity claims."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShowcaseProfile:
    """A selectable synthetic demonstration profile."""

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
        "ali-ai-feature",
        "ali-ghodsi",
        "Launching a governed AI feature",
        "linkedin",
        "announcement",
        "Launch a governed AI feature that lets data teams move from prototype to production faster.",
        "Avoid hype. Explain the operating consequence and end with a practical question.",
        "Teams do not need another AI demo.\n\nThey need a clear path from prototype to production.\n\nToday we are launching governed AI workflows that keep data, evaluation, and ownership connected. The goal is simple: help teams ship useful systems faster without losing control.\n\nWhere does your AI workflow slow down today?",
    ),
    Walkthrough(
        "matei-technical-announcement",
        "matei-zaharia",
        "A technical systems announcement",
        "linkedin",
        "announcement",
        "Announce a new query engine optimization that improves mixed analytical workloads.",
        "Explain the mechanism before the benefit. Do not use unsupported benchmark claims.",
        "Mixed analytical workloads are hard because the best execution strategy changes with the data.\n\nOur new optimizer observes those changes during execution and adapts the plan without asking teams to rewrite their queries.\n\nThat makes performance more predictable while preserving the interfaces developers already use.\n\nThe technical note includes the design and its current limits.",
    ),
    Walkthrough(
        "jensen-visionary-keynote",
        "jensen-huang",
        "A visionary keynote moment",
        "x",
        "thread",
        "Explain why accelerated computing is becoming infrastructure for every industry.",
        "Use a three-part thread. Connect the platform shift to builders without making forecasts.",
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
