"""
Session memory normalization and per-query auto-refresh utilities.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
import re


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def default_structured_memory() -> Dict[str, Any]:
    return {
        'factual_summary_short': '',
        'factual_summary_long': '',
        'unresolved_questions': [],
        'entities_and_aliases': [],
    }


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _jaccard_similarity(a: str, b: str) -> float:
    sa = set(_tokenize(a))
    sb = set(_tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _extract_first_sentence(text: str, max_len: int) -> str:
    raw = (text or '').strip()
    if not raw:
        return ''
    first = re.split(r'(?<=[.!?])\s+', raw, maxsplit=1)[0]
    return first[:max_len]


def _contains_any(text: str, needles: List[str]) -> bool:
    t = (text or '').lower()
    return any(n in t for n in needles)


def _is_answer_insufficient(answer: str) -> bool:
    markers = [
        "couldn't find",
        "could not find",
        "cannot",
        "not enough information",
        "insufficient",
        "no relevant",
        "not available",
        "i apologize",
        "i don't have",
    ]
    return _contains_any(answer, markers)


def _normalize_unresolved_item(item: Any) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        ts = _now_iso()
        return {
            'id': str(uuid4()),
            'text': text,
            'status': 'open',
            'created_at': ts,
            'updated_at': ts,
            'created_by': {
                'query_text': text,
            },
            'resolved_by': None,
            'manual_override': False,
        }

    if not isinstance(item, dict):
        return None

    text = str(item.get('text', '')).strip()
    if not text:
        return None

    status = str(item.get('status', 'open')).lower().strip()
    if status not in ('open', 'resolved'):
        status = 'open'

    created_at = item.get('created_at') or _now_iso()
    updated_at = item.get('updated_at') or created_at

    created_by = item.get('created_by') if isinstance(item.get('created_by'), dict) else {}
    resolved_by = item.get('resolved_by') if isinstance(item.get('resolved_by'), dict) else None

    return {
        'id': str(item.get('id') or uuid4()),
        'text': text,
        'status': status,
        'created_at': created_at,
        'updated_at': updated_at,
        'created_by': created_by,
        'resolved_by': resolved_by,
        'manual_override': bool(item.get('manual_override', False)),
    }


def normalize_unresolved_questions(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for raw in items:
        item = _normalize_unresolved_item(raw)
        if not item:
            continue
        key = item['text'].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)

    return normalized[:40]


def normalize_entities_and_aliases(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        entity = str(raw.get('entity', '')).strip()
        if not entity:
            continue

        aliases_raw = raw.get('aliases')
        if isinstance(aliases_raw, str):
            aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()]
        elif isinstance(aliases_raw, list):
            aliases = [str(a).strip() for a in aliases_raw if str(a).strip()]
        else:
            aliases = []

        entry = {
            'entity': entity,
            'aliases': aliases,
        }

        if isinstance(raw.get('source_query_text'), str):
            entry['source_query_text'] = raw.get('source_query_text').strip()
        if isinstance(raw.get('source_message_id'), int):
            entry['source_message_id'] = raw.get('source_message_id')
        if isinstance(raw.get('last_seen_at'), str):
            entry['last_seen_at'] = raw.get('last_seen_at')

        normalized.append(entry)

    return normalized[:80]


def normalize_structured_memory(structured: Any) -> Dict[str, Any]:
    base = default_structured_memory()
    if not isinstance(structured, dict):
        return base

    result = {
        'factual_summary_short': str(structured.get('factual_summary_short') or '').strip(),
        'factual_summary_long': str(structured.get('factual_summary_long') or '').strip(),
        'unresolved_questions': normalize_unresolved_questions(structured.get('unresolved_questions') or []),
        'entities_and_aliases': normalize_entities_and_aliases(structured.get('entities_and_aliases') or []),
    }

    return result


def is_structured_memory_empty(structured: Dict[str, Any]) -> bool:
    s = normalize_structured_memory(structured)
    return (
        not s['factual_summary_short']
        and not s['factual_summary_long']
        and not s['unresolved_questions']
        and not s['entities_and_aliases']
    )


def extract_latest_diagram_artifact(messages: List[Any]) -> Optional[Dict[str, Any]]:
    for msg in reversed(messages or []):
        if getattr(msg, 'role', None) != 'assistant':
            continue
        src = msg.sources if isinstance(msg.sources, dict) else {}
        tool = src.get('tool') if isinstance(src, dict) else None
        if not isinstance(tool, dict):
            continue

        tool_type = tool.get('type')
        if tool_type not in ('mermaid', 'desmos'):
            continue

        value = tool.get(tool_type) or tool.get('code')
        if value:
            if tool_type == 'mermaid':
                return {'type': 'mermaid', 'mermaid': tool.get('code') or value}
            return {'type': 'desmos', 'desmos': tool.get('expressions') or value}
    return None


def build_bootstrap_structured_memory_from_messages(messages: List[Any]) -> Dict[str, Any]:
    structured = default_structured_memory()
    user_messages = [
        (m.content or '').strip() for m in (messages or [])
        if getattr(m, 'role', None) == 'user' and (m.content or '').strip()
    ]
    assistant_messages = [
        (m.content or '').strip() for m in (messages or [])
        if getattr(m, 'role', None) == 'assistant' and (m.content or '').strip()
    ]

    if assistant_messages:
        structured['factual_summary_short'] = assistant_messages[-1][:280]
        structured['factual_summary_long'] = '\n\n'.join(assistant_messages[-2:])[:1600]
    elif user_messages:
        structured['factual_summary_short'] = user_messages[-1][:280]
        structured['factual_summary_long'] = '\n\n'.join(user_messages[-2:])[:1600]

    unresolved: List[Dict[str, Any]] = []
    ts = _now_iso()
    for msg in reversed(user_messages):
        if not msg.endswith('?'):
            continue
        unresolved.append({
            'id': str(uuid4()),
            'text': msg,
            'status': 'open',
            'created_at': ts,
            'updated_at': ts,
            'created_by': {'query_text': msg},
            'resolved_by': None,
            'manual_override': False,
        })
        if len(unresolved) >= 5:
            break

    unresolved.reverse()
    structured['unresolved_questions'] = unresolved
    return structured


def _find_best_unresolved_match(open_items: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    best = None
    best_score = 0.0
    for item in open_items:
        score = _jaccard_similarity(item.get('text', ''), query)
        if score > best_score:
            best = item
            best_score = score
    if best_score >= 0.50:
        return best
    return None


def _update_entity_last_seen(entities: List[Dict[str, Any]], text: str, source_query_text: str, source_message_id: int):
    body = (text or '').lower()
    now = _now_iso()
    for ent in entities:
        tokens = [ent.get('entity', '')] + list(ent.get('aliases') or [])
        tokens = [t.lower() for t in tokens if t]
        if any(t and t in body for t in tokens):
            ent['last_seen_at'] = now
            if 'source_query_text' not in ent:
                ent['source_query_text'] = source_query_text
            if 'source_message_id' not in ent:
                ent['source_message_id'] = source_message_id


def update_structured_memory_from_query(
    *,
    structured_data: Any,
    original_question: str,
    answer: str,
    user_message_id: int,
    assistant_message_id: int,
    rewrite_strategy: Optional[str],
    rewritten_query: Optional[str],
    score_improvement: Optional[float],
    web_enabled: bool,
    diagram_enabled: bool,
    web_requested_explicit: bool,
    diagram_requested_explicit: bool,
    num_doc_chunks: int,
    num_web_chunks: int,
) -> Dict[str, Any]:
    structured = normalize_structured_memory(structured_data)
    now = _now_iso()

    # Length-aware rolling summaries refreshed per query.
    short = _extract_first_sentence(answer, 280)
    if short:
        structured['factual_summary_short'] = short

    event_block = f"Q: {original_question.strip()}\nA: {answer.strip()[:700]}".strip()
    prev_long = structured.get('factual_summary_long', '').strip()
    long_joined = f"{prev_long}\n\n{event_block}".strip() if prev_long else event_block
    structured['factual_summary_long'] = long_joined[-1600:]

    unresolved = normalize_unresolved_questions(structured.get('unresolved_questions') or [])
    open_items = [u for u in unresolved if u.get('status') == 'open']

    insufficient = _is_answer_insufficient(answer)
    best = _find_best_unresolved_match(open_items, original_question)

    provenance = {
        'query_text': original_question,
        'user_message_id': user_message_id,
        'assistant_message_id': assistant_message_id,
        'rewrite_strategy': rewrite_strategy,
        'rewritten_query': rewritten_query,
        'score_improvement': score_improvement,
        'web_enabled': bool(web_enabled),
        'diagram_enabled': bool(diagram_enabled),
        'web_requested_explicit': bool(web_requested_explicit),
        'diagram_requested_explicit': bool(diagram_requested_explicit),
        'num_doc_chunks': int(num_doc_chunks),
        'num_web_chunks': int(num_web_chunks),
    }

    if insufficient:
        if best and not bool(best.get('manual_override', False)):
            best['updated_at'] = now
            if not best.get('created_by'):
                best['created_by'] = provenance
        else:
            unresolved.append({
                'id': str(uuid4()),
                'text': original_question.strip(),
                'status': 'open',
                'created_at': now,
                'updated_at': now,
                'created_by': provenance,
                'resolved_by': None,
                'manual_override': False,
            })
    else:
        if best and not bool(best.get('manual_override', False)):
            best['status'] = 'resolved'
            best['updated_at'] = now
            best['resolved_by'] = provenance

    # Hard cap to keep payload bounded while preserving newest entries.
    if len(unresolved) > 40:
        unresolved = unresolved[-40:]
    structured['unresolved_questions'] = unresolved

    entities = normalize_entities_and_aliases(structured.get('entities_and_aliases') or [])
    _update_entity_last_seen(
        entities,
        text=f"{original_question}\n{answer}",
        source_query_text=original_question,
        source_message_id=user_message_id,
    )
    structured['entities_and_aliases'] = entities

    return structured
