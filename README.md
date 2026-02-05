# AAI3008-LLM-RAG-project

This project builds a Retrieval-Augmented Generation (RAG) learning assistant that enables students to upload academic documents (PDFs, DOCX, etc.) and receive AI-powered, context-aware answers grounded in their materials. Using Flask, Gemini 1.5 API, and LangChain, the system extracts text, applies semantic chunking, and stores embeddings in a PostgreSQL + pgvector database on AWS RDS. Queries trigger a two-stage retrieval process—vector similarity search followed by cross-encoder reranking—to fetch the most relevant content, which Gemini 1.5 uses to generate accurate, cited responses. The assistant supports interactive sessions with dynamic conversation memory, multilingual translation, and optional diagram generation via Mermaid/Desmos. Hosted on AWS (EC2, S3, RDS), it offers a scalable, cost-efficient platform for personalized, document-grounded learning.

## Development

### Prerequisites
- Ensure that you are using **Python version 3.14.x**
- PostgreSQL 18 + pgvector (for installation guide, see [postgre_vector_db_installation_guide.md](postgre_vector_db_installation_guide.md))
- Git
- Visual Studio C++ Build Tools (for pgvector compilation on Windows)

### Setup Instructions

(To be added)

## Production (Cloud Deployment)

### Prerequisites

(To be added)

### Deployment Instructions

(To be added) 
