"""
HF intent classifier for tool routing.

Uses a multi-label DistilBERT model to predict tool intents:
- web_search
- diagram_enabled
"""
from __future__ import annotations

from typing import Dict, Optional
import logging

import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DistilBertTokenizer,
    DistilBertTokenizerFast,
)

from app.backend.config import Config


logger = logging.getLogger(__name__)

_tokenizer = None
_model = None
_device = None
_loaded_model_name: Optional[str] = None
_id2label: Dict[int, str] = {}


def _load_tokenizer(model_name: str):
    """
    Load tokenizer with fallbacks for repos that set a non-standard
    tokenizer_class (e.g. TokenizersBackend).
    """
    attempts = [
        ('auto_fast', lambda: AutoTokenizer.from_pretrained(model_name, use_fast=True)),
        # Force DistilBERT tokenizer mapping when tokenizer_config is malformed.
        ('auto_distilbert_fast', lambda: AutoTokenizer.from_pretrained(model_name, tokenizer_type='distilbert', use_fast=True)),
        ('distilbert_fast', lambda: DistilBertTokenizerFast.from_pretrained(model_name)),
        ('distilbert_slow', lambda: DistilBertTokenizer.from_pretrained(model_name)),
    ]

    last_err: Optional[Exception] = None
    for name, load in attempts:
        try:
            tok = load()
            logger.info(f"[IntentClassifier] Tokenizer loaded via strategy '{name}'")
            return tok
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Tokenizer load failed for '{model_name}': {last_err}")


def _resolve_device() -> str:
    wanted = (getattr(Config, 'INTENT_MODEL_DEVICE', 'cpu') or 'cpu').lower()
    if wanted == 'auto':
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    if wanted == 'cuda' and not torch.cuda.is_available():
        logger.warning('[IntentClassifier] CUDA requested but unavailable, using CPU')
        return 'cpu'
    return wanted


def _normalize_id2label(model) -> Dict[int, str]:
    raw = getattr(model.config, 'id2label', None) or {}
    parsed: Dict[int, str] = {}

    for k, v in raw.items():
        try:
            parsed[int(k)] = str(v)
        except Exception:
            continue

    # Fallback from label2id if id2label missing.
    if not parsed:
        label2id = getattr(model.config, 'label2id', None) or {}
        for label, idx in label2id.items():
            try:
                parsed[int(idx)] = str(label)
            except Exception:
                continue

    return parsed


def _ensure_loaded() -> None:
    global _tokenizer, _model, _device, _loaded_model_name, _id2label

    model_name = getattr(Config, 'INTENT_MODEL_NAME', '').strip()
    if not model_name:
        raise RuntimeError('INTENT_MODEL_NAME is not configured')

    if _model is not None and _tokenizer is not None and _loaded_model_name == model_name:
        return

    _device = _resolve_device()
    logger.info(f"[IntentClassifier] Loading model '{model_name}' on {_device}")

    _tokenizer = _load_tokenizer(model_name)
    _model = AutoModelForSequenceClassification.from_pretrained(model_name)
    _model.to(_device)
    _model.eval()

    _id2label = _normalize_id2label(_model)
    _loaded_model_name = model_name
    logger.info(f"[IntentClassifier] Ready with labels: {_id2label}")


def warm_load_intent_classifier() -> bool:
    """Warm-load intent classifier at startup. Returns True if successful."""
    try:
        _ensure_loaded()
        return True
    except Exception as e:
        logger.warning(f"[IntentClassifier] Warm-load failed: {e}")
        return False


def get_thresholds() -> Dict[str, float]:
    return {
        'web_search': float(getattr(Config, 'INTENT_THRESHOLD_WEB', 0.35)),
        'diagram_enabled': float(getattr(Config, 'INTENT_THRESHOLD_DIAGRAM', 0.6)),
    }


def predict_intents(text: str) -> Dict:
    """
    Predict routing intents from user text.

    Returns:
        {
            'inference_ok': bool,
            'routing_source': 'model' | 'toggles_only_fallback',
            'model_name': str,
            'label_scores': {'web_search': float, 'diagram_enabled': float},
            'web_search': bool,
            'diagram_enabled': bool,
            'error': str|None,
        }
    """
    thresholds = get_thresholds()
    empty_scores = {'web_search': 0.0, 'diagram_enabled': 0.0}

    if not bool(getattr(Config, 'INTENT_ROUTING_ENABLED', True)):
        return {
            'inference_ok': False,
            'routing_source': 'toggles_only_fallback',
            'model_name': getattr(Config, 'INTENT_MODEL_NAME', ''),
            'label_scores': empty_scores,
            'web_search': False,
            'diagram_enabled': False,
            'error': 'intent routing disabled',
        }

    try:
        _ensure_loaded()

        max_len = int(getattr(Config, 'INTENT_MODEL_MAX_LENGTH', 256) or 256)
        encoded = _tokenizer(
            text or '',
            return_tensors='pt',
            truncation=True,
            max_length=max_len,
        )
        encoded = {k: v.to(_device) for k, v in encoded.items()}

        with torch.no_grad():
            logits = _model(**encoded).logits.squeeze(0)
            probs = torch.sigmoid(logits).detach().cpu().tolist()

        label_scores: Dict[str, float] = {}
        for idx, p in enumerate(probs):
            label = _id2label.get(idx, str(idx))
            label_scores[label] = float(p)

        # Guardrails for required labels.
        web_score = float(label_scores.get('web_search', 0.0))
        diagram_score = float(label_scores.get('diagram_enabled', 0.0))

        return {
            'inference_ok': True,
            'routing_source': 'model',
            'model_name': _loaded_model_name or getattr(Config, 'INTENT_MODEL_NAME', ''),
            'label_scores': {
                'web_search': web_score,
                'diagram_enabled': diagram_score,
            },
            'web_search': web_score >= thresholds['web_search'],
            'diagram_enabled': diagram_score >= thresholds['diagram_enabled'],
            'error': None,
        }
    except Exception as e:
        logger.warning(f"[IntentClassifier] Inference failed, fallback to toggles-only: {e}")
        return {
            'inference_ok': False,
            'routing_source': 'toggles_only_fallback',
            'model_name': getattr(Config, 'INTENT_MODEL_NAME', ''),
            'label_scores': empty_scores,
            'web_search': False,
            'diagram_enabled': False,
            'error': str(e),
        }
