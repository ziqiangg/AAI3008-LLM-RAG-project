# pdf_chunk_embed.py
# config.py already calls load_dotenv() internally — no need to repeat it here

import os
from typing import List

import pdfplumber
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.config import Config                        # load_dotenv runs here
from app.backend.models import Document, DocumentChunk, Base


# ── Load model from Config ────────────────────────────────────────────────
model = SentenceTransformer(Config.EMBEDDING_MODEL)


# ── 1. Extract ────────────────────────────────────────────────────────────
def extract_text_from_pdf(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


# ── 2. Chunk ──────────────────────────────────────────────────────────────
def chunk_text(
    text: str,
    chunk_size: int = Config.CHUNK_SIZE,
    chunk_overlap: int = Config.CHUNK_OVERLAP
) -> List[str]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")
    text = " ".join(text.split())
    chunks, start, step = [], 0, chunk_size - chunk_overlap
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += step
    return chunks


# ── 3. Embed ──────────────────────────────────────────────────────────────
def embed_chunks(chunks: List[str]):
    return model.encode(chunks, convert_to_numpy=True)


# ── 4. Store ──────────────────────────────────────────────────────────────
def store_chunks_in_db(pdf_path: str, subject: str = None, user_id: int = None):
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        print(f"[1] Extracting text from: {pdf_path}")
        text = extract_text_from_pdf(pdf_path)
        print(f"    → {len(text)} characters extracted")

        print(f"[2] Chunking (size={Config.CHUNK_SIZE}, overlap={Config.CHUNK_OVERLAP})")
        chunks = chunk_text(text)
        print(f"    → {len(chunks)} chunks produced")

        print(f"[3] Embedding {len(chunks)} chunks...")
        embeddings = embed_chunks(chunks)
        print(f"    → Embeddings shape: {embeddings.shape}")

        doc = Document(
            user_id=user_id,
            filename=os.path.basename(pdf_path),
            file_path=os.path.abspath(pdf_path),
            file_type="pdf",
            title=os.path.basename(pdf_path),
            subject=subject or "test",
            chunk_count=0,
        )
        session.add(doc)
        session.flush()
        print(f"\n[4] Created Document row → id={doc.id}")

        for idx, (chunk_content, emb) in enumerate(zip(chunks, embeddings)):
            chunk_row = DocumentChunk(
                document_id=doc.id,
                chunk_order=idx,
                content=chunk_content,
                embedding=emb.tolist(),
                chunk_metadata={
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                    "chunk_size": Config.CHUNK_SIZE,
                    "chunk_overlap": Config.CHUNK_OVERLAP,
                },
            )
            session.add(chunk_row)

        doc.chunk_count = len(chunks)
        session.commit()

        print(f"[5] Inserted {len(chunks)} chunks for document id={doc.id}")
        print(f"\n✅ Done. document_id={doc.id}, chunks={len(chunks)}")
        return doc.id

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("Connecting to:", Config.SQLALCHEMY_DATABASE_URI)   # should show localhost
    pdf_file = "AAI3008_Lec2_TextProcessing.pdf"
    store_chunks_in_db(pdf_file, subject="demo", user_id=None)
