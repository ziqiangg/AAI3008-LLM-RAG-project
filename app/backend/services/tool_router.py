"""
Centralized tool and retrieval routing decisions.

Single source of truth for query-intent keyword checks so routing logic is not
duplicated across query handling and prompt assembly.
"""
from dataclasses import dataclass
from typing import Optional


WEB_INTENT_KEYWORDS = [
    "search the web", "search online", "look up online", "lookup online",
    "browse the web", "check the latest", "latest info", "verify online",
    "current", "recent", "today", "news", "update",
]

DIAGRAM_INTENT_KEYWORDS = [
    "draw", "diagram", "flowchart", "chart", "visuali", "illustrate", "sketch",
    "show a", "create a", "mermaid", "desmos", "plot", "graph", "visualize"
]


def _contains_any_keyword(text: str, keywords: list[str]) -> bool:
    q = (text or "").lower()
    return any(k in q for k in keywords)


def user_requested_web(text: str) -> bool:
    return _contains_any_keyword(text, WEB_INTENT_KEYWORDS)


def user_requested_diagram(text: str) -> bool:
    return _contains_any_keyword(text, DIAGRAM_INTENT_KEYWORDS)


@dataclass
class RoutingDecision:
    original_query: str
    effective_query: str
    web_toggle: bool
    diagram_toggle: bool
    web_requested_explicit: bool
    diagram_requested_explicit: bool
    web_enabled: bool
    diagram_enabled: bool


def decide_tool_routing(
    *,
    original_query: str,
    effective_query: Optional[str] = None,
    web_toggle: bool = False,
    diagram_toggle: bool = False,
) -> RoutingDecision:
    """
    Produce a single routing decision for web retrieval and diagram mode.

    Notes:
    - Web retrieval is enabled by toggle OR explicit web-request phrasing.
        - Diagram mode is enabled by toggle OR explicit diagram-request phrasing,
            matching web behavior so users can imply tool usage naturally.
    """
    effective = effective_query if effective_query is not None else original_query

    # Tool-selection intent must always reflect the user's original phrasing,
    # not rewritten retrieval formulations (e.g., HyDE passages).
    web_requested_explicit = user_requested_web(original_query)
    diagram_requested_explicit = user_requested_diagram(original_query)

    return RoutingDecision(
        original_query=original_query,
        effective_query=effective,
        web_toggle=bool(web_toggle),
        diagram_toggle=bool(diagram_toggle),
        web_requested_explicit=web_requested_explicit,
        diagram_requested_explicit=diagram_requested_explicit,
        web_enabled=bool(web_toggle) or web_requested_explicit,
        diagram_enabled=bool(diagram_toggle) or diagram_requested_explicit,
    )
