"""
Database models for LLM RAG Application
Based on schema_dump/schema.sql
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class User(Base):
    """User model for storing user account information"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


class Document(Base):
    """Document model for storing uploaded document metadata"""
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50))  # e.g., 'pdf', 'docx'
    title = Column(Text)
    subject = Column(String(255))  # e.g., 'Mathematics', 'ML'
    upload_date = Column(TIMESTAMP, default=datetime.utcnow)
    chunk_count = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'filename': self.filename,
            'file_path': self.file_path,
            'file_type': self.file_type,
            'title': self.title,
            'subject': self.subject,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'chunk_count': self.chunk_count
        }
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', user_id={self.user_id})>"


class Session(Base):
    """Session model for managing user sessions with conversation history"""
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    document_ids = Column(ARRAY(Integer))  # Array of document IDs
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    last_accessed = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'document_ids': self.document_ids,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None
        }
    
    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id})>"


class DocumentChunk(Base):
    """Document chunk model for storing text chunks with vector embeddings"""
    __tablename__ = 'document_chunks'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'))
    chunk_order = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384))  # 384-dimensional vector for All-MiniLM-L6-v2
    chunk_metadata = Column(JSONB)  # For storing page numbers, headings, etc. (renamed from 'metadata')
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    def to_dict(self, include_embedding=False):
        """Convert model to dictionary"""
        data = {
            'id': self.id,
            'document_id': self.document_id,
            'chunk_order': self.chunk_order,
            'content': self.content,
            'metadata': self.chunk_metadata
        }
        if include_embedding and self.embedding is not None:
            data['embedding'] = self.embedding
        return data
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_order={self.chunk_order})>"
