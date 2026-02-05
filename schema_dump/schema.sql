-- SQL Dump for LLM Document Management Schema
-- Includes tables, indexes, functions, and triggers

-- Ensure pgvector extension is enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Table: users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: documents
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50), -- e.g., 'pdf', 'docx'
    title TEXT,
    subject VARCHAR(255), -- e.g., 'Mathematics', 'ML'
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chunk_count INTEGER DEFAULT 0
);

-- Table: sessions
CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    document_ids INTEGER[], -- Array of document IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: document_chunks
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    chunk_order INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(384), -- Dimension 384 for All-MiniLM-L6-v2
    metadata JSONB -- For storing page numbers, headings, etc.
);

-- Function: update_updated_at_column
-- Purpose: Automatically updates the 'updated_at' column to the current timestamp on row updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

-- Trigger: update_users_updated_at
-- Purpose: Calls the update_updated_at_column function before any update on the users table
CREATE TRIGGER update_users_updated_at 
BEFORE UPDATE ON users 
FOR EACH ROW 
EXECUTE FUNCTION update_updated_at_column();

-- Index: idx_document_chunks_embedding
-- Purpose: Accelerates vector similarity searches using cosine distance
-- Note: This index uses the HNSW algorithm which is efficient for approximate nearest neighbor searches
CREATE INDEX idx_document_chunks_embedding 
ON document_chunks 
USING hnsw (embedding vector_cosine_ops);

-- Optional: Index for faster document lookup by user
CREATE INDEX idx_documents_user_id ON documents (user_id);

-- Optional: Index for faster chunk lookup by document
CREATE INDEX idx_document_chunks_document_id ON document_chunks (document_id);

-- Optional: Index for faster session lookup by user
CREATE INDEX idx_sessions_user_id ON sessions (user_id);

COMMIT;