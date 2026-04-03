import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

try:
    import google.generativeai as genai
    _HAS_GENAI = True
except ImportError:
    _HAS_GENAI = False

load_dotenv()

# Ensure repo root is on sys.path so we can import app config when available
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API_BASE   = os.getenv("API_BASE",  "http://localhost:5000")
JWT_TOKEN  = os.getenv("JWT_TOKEN", "").strip()
DATA_PATH  = os.getenv("EVAL_DATA", "test/eval_candidate_qa_with_chunks.json")
OUT_JSON   = os.getenv("EVAL_OUT",  "").strip()
RUN_TAG    = os.getenv("RAGAS_RUN_TAG", "").strip()
MODEL_NAME = os.getenv("RAGAS_GEMINI_MODEL", "").strip()
EMBED_MODEL = os.getenv("RAGAS_GEMINI_EMBED_MODEL", "").strip()
USE_DB_CONTEXT = os.getenv("RAGAS_USE_DB_CONTEXT", "1").strip() not in {"0", "false", "False"}

# Normalise API key: prefer GOOGLE_API_KEY; fall back to GEMINI_API_KEY
gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if gemini_key and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = gemini_key

_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro",
    "gemini-1.5-pro-001",
    "gemini-2.0-pro",
]


def read_config_llm_model() -> Optional[str]:
    try:
        from app.backend.config import Config
        return getattr(Config, "LLM_MODEL", None)
    except Exception:
        return None


def _strip_model_prefix(name: str) -> str:
    return name.replace("models/", "").strip()


def list_available_models() -> List[str]:
    if not _HAS_GENAI:
        return []
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    available = []
    for m in genai.list_models():
        if "generateContent" in (m.supported_generation_methods or []):
            available.append(_strip_model_prefix(m.name))
    return available


def list_available_embedding_models() -> List[str]:
    if not _HAS_GENAI:
        return []
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    available = []
    for m in genai.list_models():
        if "embedContent" in (m.supported_generation_methods or []):
            available.append(_strip_model_prefix(m.name))
    return available


def _match_model(candidate: str, available: List[str]) -> Optional[str]:
    cand = _strip_model_prefix(candidate)
    for a in available:
        if a == cand or a.endswith(cand):
            return a
    return None


def choose_gemini_model(preferred: str | None = None) -> str:
    config_model = read_config_llm_model()
    preferred = preferred or config_model

    available = list_available_models()
    if preferred:
        if not available:
            return _strip_model_prefix(preferred)
        match = _match_model(preferred, available)
        if match:
            return match

    if available:
        priority = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash-001",
            "gemini-1.5-flash",
            "gemini-1.5-pro-001",
            "gemini-1.5-pro",
            "gemini-2.0-pro",
        ]
        for p in priority:
            match = _match_model(p, available)
            if match:
                if preferred:
                    print(
                        f"[RAGAS] Requested model '{_strip_model_prefix(preferred)}' not available; "
                        f"using '{match}' instead.",
                        flush=True,
                    )
                return match
        if preferred:
            print(
                f"[RAGAS] Requested model '{_strip_model_prefix(preferred)}' not available; "
                f"falling back to '{available[0]}'.",
                flush=True,
            )
        return available[0]

    # google-generativeai not installed — use hardcoded default
    fallback = _strip_model_prefix(preferred or _FALLBACK_MODELS[0])
    print(f"[RAGAS] google-generativeai not installed; defaulting to {fallback}", flush=True)
    return fallback


def choose_embedding_model(preferred: str | None = None) -> str:
    preferred = preferred or "models/embedding-001"
    available = list_available_embedding_models()

    if not available:
        return _strip_model_prefix(preferred)

    match = _match_model(preferred, available)
    if match:
        return match

    # Prefer the standard Google text embedding models if available
    priority = [
        "text-embedding-004",
        "text-embedding-003",
        "embedding-001",
    ]
    for p in priority:
        match = _match_model(p, available)
        if match:
            print(
                f"[RAGAS] Requested embedding model '{_strip_model_prefix(preferred)}' not available; "
                f"using '{match}' instead.",
                flush=True,
            )
            return match

    print(
        f"[RAGAS] Requested embedding model '{_strip_model_prefix(preferred)}' not available; "
        f"falling back to '{available[0]}'.",
        flush=True,
    )
    return available[0]


if not JWT_TOKEN:
    raise SystemExit("JWT_TOKEN is required in environment")


def load_eval_data(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    flat = []
    for doc_block in data:
        for qa in doc_block.get("questions", []):
            flat.append(qa)
    return flat


def fetch_answer(question: str, document_ids=None, folder_ids=None) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"question": question}
    if document_ids:
        payload["document_ids"] = document_ids
    if folder_ids:
        payload["folder_ids"] = folder_ids

    r = requests.post(f"{API_BASE}/api/query", headers=headers, json=payload, timeout=300)
    r.raise_for_status()
    return r.json()


def fetch_full_chunk_contents(chunk_ids: List[int]) -> Dict[int, str]:
    if not chunk_ids:
        return {}
    try:
        from app.backend.database import get_db_session
        from app.backend.models import DocumentChunk
    except Exception:
        return {}

    unique_ids = [int(cid) for cid in chunk_ids if isinstance(cid, (int, str)) and str(cid).isdigit()]
    if not unique_ids:
        return {}

    with get_db_session() as db:
        rows = (
            db.query(DocumentChunk.id, DocumentChunk.content)
            .filter(DocumentChunk.id.in_(unique_ids))
            .all()
        )
    return {row.id: row.content for row in rows}


def build_default_out_path() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"_{RUN_TAG}" if RUN_TAG else ""
    return f"test/ragas_results_{ts}{tag}.json"


def main():
    items = load_eval_data(DATA_PATH)

    records = []
    total = len(items)
    for idx, qa in enumerate(items, start=1):
        question   = (qa.get("question")        or "").strip()
        reference  = (qa.get("expected_answer") or "").strip()
        scope      = qa.get("scope") or {}
        document_ids = scope.get("document_ids")
        folder_ids   = scope.get("folder_ids")

        resp     = fetch_answer(question, document_ids=document_ids, folder_ids=folder_ids)
        answer   = (resp.get("answer")  or "").strip()
        sources  = resp.get("sources")  or []
        if USE_DB_CONTEXT:
            chunk_ids = [s.get("chunk_id") for s in sources if s.get("chunk_id") is not None]
            full_map = fetch_full_chunk_contents(chunk_ids)
            contexts = []
            for s in sources:
                cid = s.get("chunk_id")
                full = full_map.get(cid)
                if full:
                    contexts.append(full)
                elif s.get("content"):
                    contexts.append(s.get("content"))
        else:
            contexts = [s.get("content", "") for s in sources if s.get("content")]

        print(f"[RAGAS] {idx}/{total} collected contexts: {len(contexts)}", flush=True)

        records.append({
            "question":    question,
            "answer":      answer,
            "contexts":    contexts,
            "ground_truth": reference,
        })

    ds = Dataset.from_list(records)

    model_name = choose_gemini_model(MODEL_NAME or None)
    embed_model = choose_embedding_model(EMBED_MODEL or None)
    print(f"[RAGAS] Using Gemini model: {model_name}", flush=True)
    print(f"[RAGAS] Using embedding model: {embed_model}", flush=True)

    # Wrap LLM and embeddings for ragas v0.4+
    wrapped_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(model=model_name, temperature=0)
    )
    wrapped_embeddings = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(model=embed_model)
    )

    # Instantiate metric objects — ragas v0.4+ requires instances, not singletons
    metrics = [
        Faithfulness(llm=wrapped_llm),
        AnswerRelevancy(llm=wrapped_llm, embeddings=wrapped_embeddings),
        ContextPrecision(llm=wrapped_llm),
        ContextRecall(llm=wrapped_llm),
    ]

    print("[RAGAS] Running metrics evaluation...", flush=True)
    results = evaluate(
        ds,
        metrics=metrics,
        llm=wrapped_llm,
        embeddings=wrapped_embeddings,
    )

    out_path = OUT_JSON or build_default_out_path()
    out = {
        "model":      model_name,
        "embedding_model": embed_model,
        "run_tag":    RUN_TAG or None,
        "count":      len(records),
        "settings": {
            "api_base": API_BASE,
            "rerank_top_k": os.getenv("RERANK_TOP_K"),
            "use_db_context": USE_DB_CONTEXT,
            "eval_data": DATA_PATH,
        },
        "scores":     results.to_pandas().mean(numeric_only=True).to_dict(),
        "per_sample": results.to_pandas().to_dict(orient="records"),
    }

    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    for k, v in out["scores"].items():
        print(f"{k}: {v:.4f}")


if __name__ == "__main__":
    main()
