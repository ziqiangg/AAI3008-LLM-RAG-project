# app/backend/services/ingestion.py

import os
from typing import Optional

from langchain_community.document_loaders import (
    PDFPlumberLoader,
    Docx2txtLoader,
    TextLoader,
    UnstructuredPowerPointLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy.orm import Session as DBSession

from app.backend.config import Config
from app.backend.models import Document, DocumentChunk

# ── Singleton: model loaded once at startup ───────────────────────────────
_embeddings: Optional[HuggingFaceEmbeddings] = None

def get_embeddings() -> HuggingFaceEmbeddings:
    """Lazy-load the HuggingFace embedding model once."""
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=Config.EMBEDDING_MODEL,          # from .env / config
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


# ── Step 1: Load ──────────────────────────────────────────────────────────
def load_document(file_path: str):
    """
    Select the appropriate LangChain loader based on file extension.
    Supports pdf, docx, txt, pptx (from Config.ALLOWED_EXTENSIONS).
    """
    ext = os.path.splitext(file_path)[1].lower()
    loader_map = {
        ".pdf":  PDFPlumberLoader,
        ".docx": Docx2txtLoader,
        ".txt":  TextLoader,
        ".pptx": UnstructuredPowerPointLoader,
    }
    loader_cls = loader_map.get(ext)
    if not loader_cls:
        raise ValueError(
            f"Unsupported file extension '{ext}'. "
            f"Allowed: {Config.ALLOWED_EXTENSIONS}"
        )
    return loader_cls(file_path).load()   # returns List[LangChain Document]


# ── Step 2: Chunk ─────────────────────────────────────────────────────────
def split_documents(lc_docs) -> list:
    """
    Split LangChain Documents using RecursiveCharacterTextSplitter.
    chunk_size and chunk_overlap are read from Config (sourced from .env).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=Config.CHUNK_SIZE,           # .env: CHUNK_SIZE
        chunk_overlap=Config.CHUNK_OVERLAP,     # .env: CHUNK_OVERLAP
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(lc_docs)


# ── Step 3: Embed ─────────────────────────────────────────────────────────
def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings using the singleton HuggingFace model."""
    return get_embeddings().embed_documents(texts)


# ── Step 4: Store (preserves existing DocumentChunk schema) ───────────────
def run_ingestion_pipeline(
    db_session: DBSession,
    file_path: str,
    user_id: Optional[int] = None,
    subject: Optional[str] = None,
) -> Document:
    """
    Full LangChain-powered ingestion pipeline:
      Load → Split → Embed → Store into existing Document + DocumentChunk tables.

    Args:
        db_session: Active SQLAlchemy session (passed in from the blueprint).
        file_path:  Absolute path to the saved file.
        user_id:    ID of the uploading user (nullable until auth is wired).
        subject:    Optional subject label (e.g. 'AAI3008').

    Returns:
        The created Document ORM instance.
    """
    filename = os.path.basename(file_path)
    file_ext = os.path.splitext(filename)[1].lstrip(".")

    # ── 1. Load ──
    print(f"[1] Loading  : {filename}")
    lc_docs = load_document(file_path)
    print(f"     → {len(lc_docs)} page(s) loaded")

    # ── 2. Chunk ──
    print(f"[2] Chunking : size={Config.CHUNK_SIZE}, overlap={Config.CHUNK_OVERLAP}")
    chunks = split_documents(lc_docs)
    print(f"     → {len(chunks)} chunks")

    # ── 3. Embed ──
    print(f"[3] Embedding: {len(chunks)} chunks via {Config.EMBEDDING_MODEL}")
    texts = [chunk.page_content for chunk in chunks]
    vectors = embed_texts(texts)
    print(f"     → dim={len(vectors[0])}")

    # ── 4. Create Document metadata row ──
    doc = Document(
        user_id=user_id,
        filename=filename,
        file_path=os.path.abspath(file_path),
        file_type=file_ext,
        title=filename,
        subject=subject or "General",
        chunk_count=0,
    )
    db_session.add(doc)
    db_session.flush()      # get doc.id before inserting chunks
    print(f"[4] Document row created → id={doc.id}")

    # ── 5. Insert DocumentChunk rows with vectors ──
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        db_session.add(DocumentChunk(
            document_id=doc.id,
            chunk_order=idx,
            content=chunk.page_content,
            embedding=vector,                   # List[float] → Vector(384)
            chunk_metadata={
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "chunk_size": Config.CHUNK_SIZE,
                "chunk_overlap": Config.CHUNK_OVERLAP,
                "source": chunk.metadata,       # LangChain page-level metadata
            },
        ))

    doc.chunk_count = len(chunks)
    db_session.commit()
    print(f"[5] Stored   : {len(chunks)} chunks → document_id={doc.id}")
    print(f"✅  Ingestion complete.")
    return doc
