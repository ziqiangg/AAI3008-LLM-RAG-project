"""
Vector similarity search service using pgvector
Retrieves relevant document chunks based on embedding similarity
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.backend.models import DocumentChunk, Document
from app.backend.config import Config


def retrieve_relevant_chunks(
    db_session: Session,
    question_embedding: List[float],
    document_ids: Optional[List[int]] = None,
    top_k: int = None
) -> List[Dict]:
    """
    Retrieve top K most similar document chunks using pgvector cosine similarity.
    
    Args:
        db_session: Active SQLAlchemy session
        question_embedding: Question embedding vector (384 dimensions)
        document_ids: Optional list of document IDs to filter by
        top_k: Number of chunks to retrieve (defaults to Config.TOP_K_RETRIEVAL)
    
    Returns:
        List of dicts containing chunk information and similarity scores
    """
    if top_k is None:
        top_k = Config.TOP_K_RETRIEVAL
    
    # Convert embedding list to pgvector format string
    embedding_str = '[' + ','.join(map(str, question_embedding)) + ']'
    
    # Build query with optional document_ids filtering
    if document_ids and len(document_ids) > 0:
        query = text("""
            SELECT 
                dc.id as chunk_id,
                dc.document_id,
                d.filename,
                dc.content,
                dc.chunk_order,
                dc.chunk_metadata,
                (dc.embedding <=> cast(:embedding as vector)) as distance
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE dc.document_id = ANY(:doc_ids)
            ORDER BY distance ASC
            LIMIT :top_k
        """)
        params = {
            'embedding': embedding_str,
            'doc_ids': document_ids,
            'top_k': top_k
        }
    else:
        query = text("""
            SELECT 
                dc.id as chunk_id,
                dc.document_id,
                d.filename,
                dc.content,
                dc.chunk_order,
                dc.chunk_metadata,
                (dc.embedding <=> cast(:embedding as vector)) as distance
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            ORDER BY distance ASC
            LIMIT :top_k
        """)
        params = {
            'embedding': embedding_str,
            'top_k': top_k
        }
    
    result = db_session.execute(query, params)
    rows = result.fetchall()
    
    # Convert rows to list of dicts
    chunks = []
    for row in rows:
        chunks.append({
            'chunk_id': row.chunk_id,
            'document_id': row.document_id,
            'filename': row.filename,
            'content': row.content,
            'chunk_order': row.chunk_order,
            'metadata': row.chunk_metadata,
            'distance': float(row.distance),
            'similarity': 1.0 - float(row.distance)  # Convert distance to similarity
        })
    
    return chunks
