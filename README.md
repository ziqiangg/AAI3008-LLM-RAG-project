# AAI3008 LLM RAG Project

A personalized RAG study assistant for asking questions over your own learning materials. The app supports user accounts, document and link ingestion, session-based conversations with memory, and cited answers generated with Gemini. Retrieval uses multilingual embeddings plus cross-encoder reranking. Tool routing for web search and diagram behavior is classifier-based (Hugging Face) with user toggles that act as hard ON switches.

## Core Features

- JWT-based user authentication with per-user sessions and data scope
- Document ingestion from PDF, DOCX, PPTX, and TXT into PostgreSQL plus pgvector
- Trusted web link ingestion into chunked, retrievable content
- Folder-based document scoping for query and quiz workflows
- Multilingual vector retrieval plus cross-encoder reranking
- Optional web retrieval lane with trusted-domain and language-aware filtering
- Optional diagram tool outputs (Mermaid or Desmos)
- Session memory support with structured memory endpoints
- Quiz generation from scoped context

## Architecture At A Glance

- Flask API serves backend endpoints and the frontend static app
- Frontend sends query payloads with user toggles and scope filters
- PostgreSQL plus pgvector stores chunks, embeddings, sessions, and memory state
- Gemini generates answers from retrieved context
- Hugging Face intent classifier controls model-based tool routing for `web_search` and `diagram_enabled`

## Tech Stack

### Backend Framework

- Flask 3.0.3
- Flask-CORS 4.0.0
- Flask-JWT-Extended 4.7.1
- SQLAlchemy 2.0.30

### AI and NLP Stack

- Google Generative AI SDK 0.8.3 (Gemini 2.5 Flash API)
- langchain 0.2.13
- langchain-community 0.2.12
- langchain-core 0.2.30
- langchain-huggingface 0.0.3
- sentence-transformers 3.0.1
- transformers 4.41.2
- torch 2.3.1

### Database

- PostgreSQL with pgvector container image: ankane/pgvector:latest (Docker)
- pgvector Python package 0.3.4
- psycopg2-binary 2.9.9

### Document Processing

- unstructured 0.15.7
- PyMuPDF 1.24.5
- pdfplumber 0.7.0
- python-pptx (unpinned)
- docx2txt 0.8
- pdf2image 1.17.0
- Pillow 10.3.0

### Utilities

- python-dotenv 1.0.1
- google-cloud-storage 2.14.0
- langdetect 1.0.9
- deep-translator 1.11.4

## Models Used

- Embedding model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  - Used for multilingual semantic embeddings in retrieval.
- Cross-encoder reranking model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
  - Used to rerank retrieved chunks by relevance before generation.
- Tool routing classifier: aitraineracc/intent-classification-multilabel
  - A fine-tuned DistilBERT multi-label classifier developed specifically for this project use case, used to infer web_search and diagram_enabled intents.

## Quick Start (Docker First)

Use Docker setup as the primary way to run this project.
For extra Docker workflows, see [DOCKER_COMMANDS.md](DOCKER_COMMANDS.md).
If you need manual PostgreSQL plus pgvector installation (non-Docker), see [postgre_vector_db_installation_guide.md](postgre_vector_db_installation_guide.md).

### 1) Create .env

Create a `.env` file in the repository root with the minimum required values (use .env.example as template):

```env
GEMINI_API_KEY=your_key_here
DB_NAME=llm_rag_db
DB_USER=postgres
DB_PASSWORD=postgres
FLASK_ENV=development
SECRET_KEY=change_me
SERPER_API_KEY=optional_for_web_search
DESMOS_API_KEY=optional_for_desmos_client
```

### 2) Build and start

```bash
docker-compose up --build
```

Optional detached mode:

```bash
docker-compose up -d
```

### 3) Verify

- API base: http://localhost:5000
- Health: http://localhost:5000/api/health

### 4) Stop

```bash
docker-compose down
```

Remove DB volume too:

```bash
docker-compose down -v
```

## How To Use The Application

1. Open http://localhost:5000 in your browser.
2. Register an account or log in.
3. Upload one or more documents from the sidebar.
4. Optionally create folders and scope your documents by folder.
5. Ask questions in chat.
6. Optionally enable web search or diagram mode using the UI toggles.
7. Review cited sources and generated tool output (for example Mermaid/Desmos) in the response.
8. Reopen sessions and memory from the session and user menu areas.

## Guest vs Logged-In Features

### Guest User

- Can open the application UI.
- Can ask direct queries without creating an account (sessionless use).
- Does not get user-owned ingestion, persistent sessions, or memory management.

### Logged-In User

- Can upload and ingest documents.
- Can ingest web links into their own document space.
- Can create and manage folders, sessions, and session memory.
- Can use quiz generation and other user-scoped features.

## API Overview (High Level)

### System

- GET /api/health
- GET /api/config/client

### Auth and Users

- POST /api/users/register
- POST /api/users/login
- GET /api/users/me
- PATCH /api/users/me
- DELETE /api/users/me

### Documents and Folders

- GET /api/documents/
- POST /api/documents/upload
- GET /api/documents/{doc_id}
- PATCH /api/documents/{doc_id}
- DELETE /api/documents/{doc_id}
- GET /api/folders/
- POST /api/folders/
- PATCH /api/folders/{folder_id}
- DELETE /api/folders/{folder_id}

### Sessions and Memory

- POST /api/sessions/
- GET /api/sessions/
- GET /api/sessions/{session_id}
- PATCH /api/sessions/{session_id}
- DELETE /api/sessions/{session_id}
- POST /api/sessions/{session_id}/messages
- GET /api/sessions/{session_id}/messages
- GET /api/sessions/{session_id}/memory
- PATCH /api/sessions/{session_id}/memory

### Query, Quiz, and Links

- POST /api/query
- POST /api/quiz/generate
- POST /api/links/ingest

## Key Configuration

- `GEMINI_API_KEY`: required for answer generation. Get it from Google AI Studio.
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: database connection
- `SECRET_KEY` and `JWT_SECRET_KEY`: auth and token security
- `SERPER_API_KEY`: enables web search retrieval lane. Get it from serper.dev.
- `DESMOS_API_KEY`: client config endpoint for graph tooling. Get it from the Desmos API signup/docs page.

## Known Behavior

- Tool routing is classifier-based and returns routing metadata in query responses.
- User toggles are hard ON signals for web and diagram behavior.
- If classifier inference fails, routing falls back to toggles-only behavior.

## Troubleshooting

- Hugging Face model download or tokenizer errors:
  - Check container internet access and model name in `INTENT_MODEL_NAME`.
  - Restart backend after model or tokenizer config changes.
- Database initialization issues:
  - Ensure `db` service is healthy before backend starts.
  - Recreate containers with `docker-compose down -v` then `docker-compose up --build`.
- Missing API keys:
  - Missing `GEMINI_API_KEY` will prevent response generation.
  - Missing `SERPER_API_KEY` disables web retrieval results.

## Project Structure

- `app/backend`: Flask routes, services, models, config
- `app/frontend`: browser UI
- `schema_dump`: database schema
- `uploads`: uploaded content
- `docker-compose.yml`, `Dockerfile`: local container setup
