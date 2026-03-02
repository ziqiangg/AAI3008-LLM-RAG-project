"""
Cross-encoder reranking service
Reranks retrieved chunks using a cross-encoder model for better precision
"""
from typing import List, Dict, Optional
from sentence_transformers import CrossEncoder

from app.backend.config import Config


# Singleton pattern for model loading
_reranker: Optional[CrossEncoder] = None


def get_reranker() -> CrossEncoder:
    """
    Lazy-load and return the cross-encoder model.
    Model is loaded once and reused across requests.
    """
    global _reranker
    if _reranker is None:
        print(f"[Reranker] Loading cross-encoder model: {Config.RERANK_MODEL}")
        _reranker = CrossEncoder(Config.RERANK_MODEL)
        print(f"[Reranker] Model loaded successfully")
    return _reranker


def rerank_chunks(
    question: str,
    chunks: List[Dict],
    top_k: int = None
) -> List[Dict]:
    """
    Rerank retrieved chunks using cross-encoder for better precision.
    
    Args:
        question: User's question text
        chunks: List of chunk dicts from retrieval service
        top_k: Number of top chunks to return (defaults to Config.RERANK_TOP_K)
    
    Returns:
        Reranked list of chunks with added 'rerank_score' field
    """
    if top_k is None:
        top_k = Config.RERANK_TOP_K
    
    if not chunks:
        return []
    
    # If we have fewer chunks than top_k, return all
    if len(chunks) <= top_k:
        # Still score them for consistency
        reranker = get_reranker()
        pairs = [(question, chunk['content']) for chunk in chunks]
        scores = reranker.predict(pairs)
        
        for chunk, score in zip(chunks, scores):
            chunk['rerank_score'] = float(score)
        
        # Sort by rerank score (descending)
        chunks.sort(key=lambda x: x['rerank_score'], reverse=True)
        return chunks
    
    # Prepare (question, chunk_content) pairs for cross-encoder
    reranker = get_reranker()
    pairs = [(question, chunk['content']) for chunk in chunks]
    
    # Score all pairs
    scores = reranker.predict(pairs)
    
    # Add scores to chunks
    for chunk, score in zip(chunks, scores):
        chunk['rerank_score'] = float(score)
    
    # Sort by rerank score (descending) and keep top K
    chunks.sort(key=lambda x: x['rerank_score'], reverse=True)
    
    return chunks[:top_k]
