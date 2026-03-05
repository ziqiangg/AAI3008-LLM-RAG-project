-- SQL Dump for LLM Document Management Schema
-- Includes tables, indexes, functions, and triggers

-- Ensure pgvector extension is enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Table: users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: folders (user-defined document organization)
CREATE TABLE IF NOT EXISTS folders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: documents
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50), -- e.g., 'pdf', 'docx'
    title TEXT,
    subject TEXT[], -- Array of subjects, e.g., ['Math', 'Physics']
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chunk_count INTEGER DEFAULT 0
);

-- Table: sessions
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'New Chat',
    document_ids INTEGER[], -- Array of document IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: messages
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    sources JSONB, -- Retrieved chunk references
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: document_chunks
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_order INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(384), -- Dimension 384 for All-MiniLM-L6-v2
    chunk_metadata JSONB -- For storing page numbers, headings, etc.
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

-- Optional: Index for faster folder lookup by user
CREATE INDEX idx_folders_user_id ON folders (user_id);

-- Optional: Index for faster document lookup by folder
CREATE INDEX idx_documents_folder_id ON documents (folder_id);

COMMIT;