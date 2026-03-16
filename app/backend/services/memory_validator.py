"""
Session memory payload validation.
Hard-blocks unsafe intent in memory edits.
"""
import re
from typing import Dict, Tuple, List, Any


DANGEROUS_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"override\s+(system|developer)\s+(prompt|instruction)",
    r"reveal\s+(system|hidden)\s+(prompt|instruction)",
    r"jailbreak",
    r"bypass\s+safety",
    r"disable\s+guardrails",
    r"execute\s+(shell|command|code)",
    r"exfiltrat(e|ion)",
    r"steal\s+credentials",
    r"drop\s+table",
]


def _flatten_texts(payload: Dict[str, Any]) -> List[str]:
    texts: List[str] = []

    structured = payload.get('structured_data') or {}
    if isinstance(structured, dict):
        for key in ('factual_summary_short', 'factual_summary_long'):
            val = structured.get(key)
            if isinstance(val, str):
                texts.append(val)

        unresolved = structured.get('unresolved_questions') or []
        if isinstance(unresolved, list):
            texts.extend([x for x in unresolved if isinstance(x, str)])

        entities = structured.get('entities_and_aliases') or []
        if isinstance(entities, list):
            for item in entities:
                if isinstance(item, dict):
                    ent = item.get('entity')
                    if isinstance(ent, str):
                        texts.append(ent)
                    aliases = item.get('aliases') or []
                    if isinstance(aliases, list):
                        texts.extend([a for a in aliases if isinstance(a, str)])

    freeform = payload.get('freeform_text')
    if isinstance(freeform, str):
        texts.append(freeform)

    return texts


def _contains_dangerous_intent(text: str) -> bool:
    lower = (text or '').lower()
    return any(re.search(pattern, lower) for pattern in DANGEROUS_PATTERNS)


def validate_memory_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, 'Invalid payload: expected JSON object.'

    structured = payload.get('structured_data')
    if structured is None or not isinstance(structured, dict):
        return False, 'Invalid payload: structured_data is required and must be an object.'

    # Required structured keys
    for key in ('factual_summary_short', 'factual_summary_long', 'unresolved_questions', 'entities_and_aliases'):
        if key not in structured:
            return False, f'Invalid structured_data: missing key {key}.'

    if not isinstance(structured.get('factual_summary_short'), str):
        return False, 'Invalid structured_data: factual_summary_short must be a string.'
    if not isinstance(structured.get('factual_summary_long'), str):
        return False, 'Invalid structured_data: factual_summary_long must be a string.'

    unresolved = structured.get('unresolved_questions')
    if not isinstance(unresolved, list) or not all(isinstance(x, str) for x in unresolved):
        return False, 'Invalid structured_data: unresolved_questions must be a list of strings.'

    entities = structured.get('entities_and_aliases')
    if not isinstance(entities, list):
        return False, 'Invalid structured_data: entities_and_aliases must be a list.'
    for idx, item in enumerate(entities):
        if not isinstance(item, dict):
            return False, f'Invalid entities_and_aliases[{idx}]: must be an object.'
        if not isinstance(item.get('entity', ''), str):
            return False, f'Invalid entities_and_aliases[{idx}].entity: must be a string.'
        aliases = item.get('aliases', [])
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            return False, f'Invalid entities_and_aliases[{idx}].aliases: must be a list of strings.'

    freeform_enabled = bool(payload.get('freeform_enabled', False))
    freeform_text = payload.get('freeform_text')

    if freeform_text is not None and not isinstance(freeform_text, str):
        return False, 'Invalid payload: freeform_text must be a string when provided.'

    if freeform_text and not freeform_enabled:
        return False, 'Freeform text edits are blocked unless freeform_enabled is true.'

    # Size guards
    if len(structured['factual_summary_short']) > 1000:
        return False, 'factual_summary_short is too long (max 1000 chars).'
    if len(structured['factual_summary_long']) > 5000:
        return False, 'factual_summary_long is too long (max 5000 chars).'
    if freeform_text and len(freeform_text) > 8000:
        return False, 'freeform_text is too long (max 8000 chars).'

    # Hard-block unsafe intent
    for txt in _flatten_texts(payload):
        if _contains_dangerous_intent(txt):
            return False, 'Memory update blocked: potentially malicious intent detected.'

    return True, ''
