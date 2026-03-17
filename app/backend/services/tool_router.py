"""Centralized tool and retrieval routing decisions.

Routing intent is inferred with a multi-label HF classifier.
"""
from dataclasses import dataclass
from typing import Optional

from app.backend.services.intent_classifier import predict_intents, get_thresholds


def user_requested_web(text: str) -> bool:
    result = predict_intents(text)
    return bool(result.get('web_search', False))


def user_requested_diagram(text: str) -> bool:
    result = predict_intents(text)
    return bool(result.get('diagram_enabled', False))


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
    routing_source: str
    inference_ok: bool
    intent_scores: dict
    thresholds: dict
    model_name: str
    inference_error: Optional[str]


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
    - Web retrieval is enabled by toggle OR classifier intent.
    - Diagram mode is enabled by toggle OR classifier intent.
    - If inference fails, fallback is toggles-only (no keyword fallback).
    """
    effective = effective_query if effective_query is not None else original_query
    thresholds = get_thresholds()
    intent_result = predict_intents(original_query)

    # Intent must reflect the original user phrasing, not rewritten variants.
    web_requested_explicit = bool(intent_result.get('web_search', False))
    diagram_requested_explicit = bool(intent_result.get('diagram_enabled', False))

    return RoutingDecision(
        original_query=original_query,
        effective_query=effective,
        web_toggle=bool(web_toggle),
        diagram_toggle=bool(diagram_toggle),
        web_requested_explicit=web_requested_explicit,
        diagram_requested_explicit=diagram_requested_explicit,
        web_enabled=bool(web_toggle) or web_requested_explicit,
        diagram_enabled=bool(diagram_toggle) or diagram_requested_explicit,
        routing_source=str(intent_result.get('routing_source', 'toggles_only_fallback')),
        inference_ok=bool(intent_result.get('inference_ok', False)),
        intent_scores=dict(intent_result.get('label_scores', {})),
        thresholds=thresholds,
        model_name=str(intent_result.get('model_name', '')),
        inference_error=intent_result.get('error'),
    )
