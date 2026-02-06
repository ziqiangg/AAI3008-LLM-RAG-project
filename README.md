# AAI3008-LLM-RAG-project

This project builds a Retrieval-Augmented Generation (RAG) learning assistant that enables students to upload academic documents (PDFs, DOCX, etc.) and receive AI-powered, context-aware answers grounded in their materials. Using Flask, Gemini 1.5 API, and LangChain, the system extracts text, applies semantic chunking, and stores embeddings in a PostgreSQL + pgvector database on AWS RDS. Queries trigger a two-stage retrieval process—vector similarity search followed by cross-encoder reranking—to fetch the most relevant content, which Gemini 1.5 uses to generate accurate, cited responses. The assistant supports interactive sessions with dynamic conversation memory, multilingual translation, and optional diagram generation via Mermaid/Desmos. Hosted on AWS (EC2, S3, RDS), it offers a scalable, cost-efficient platform for personalized, document-grounded learning.

## Development

### Tech Stack

**Backend Framework:**
- Flask 3.0.3 - Web framework
- Flask-CORS 4.0.0 - Cross-Origin Resource Sharing

**AI/ML Stack:**
- Google Gemini 1.5 API - Large Language Model
- LangChain 0.2.12 - LLM framework for RAG orchestration
- Sentence Transformers 3.0.1 - Embedding generation (All-MiniLM-L6-v2)
- Cross-Encoder 0.4.0 - Reranking (ms-marco model)
- PyTorch 2.3.1 - Deep learning backend

**Database:**
- PostgreSQL 18 - Relational database
- pgvector 0.3.4 - Vector similarity search extension
- SQLAlchemy 2.0.30 - ORM

**Document Processing:**
- Unstructured 0.15.7 - Multi-format document parsing (PDF, DOCX, PPTX)
- pdf2image 1.17.0 - PDF rendering
- Pillow 10.3.0 - Image processing

**Utilities:**
- python-dotenv 1.0.1 - Environment variable management
- boto3 1.34.124 - AWS SDK (for S3 integration)

### Project Structure

```
AAI3008-LLM-RAG-project/
├── app/
│   ├── backend/
│   │   ├── routes/          # API endpoints
│   │   ├── services/        # Business logic
│   │   ├── utils/           # Helper functions
│   │   ├── models.py        # Database models
│   │   ├── config.py        # Configuration settings
│   │   ├── database.py      # Database connection
│   │   └── app.py           # Flask application factory
│   └── frontend/            # Frontend files (to be implemented)
├── schema_dump/             # Database schema SQL
├── docker-compose.yml       # Docker orchestration
├── Dockerfile               # Docker image definition
├── requirements.txt         # Python dependencies
└── .env.example             # Environment variables template
```

## Setup Options

You can set up this project using either **Docker** (recommended) or a **traditional Python virtual environment**.

---

## Option 1: Docker Setup (Recommended)

Docker simplifies the setup by automatically handling PostgreSQL, pgvector, and all dependencies.

### Prerequisites

- **Docker** and **Docker Compose** installed ([Install Docker](https://docs.docker.com/get-docker/))
- **Git**
- **Google Gemini API Key** (obtain from [Google AI Studio](https://aistudio.google.com/))

### Setup Instructions

#### 1. Clone the Repository

```bash
git clone https://github.com/ziqiangg/AAI3008-LLM-RAG-project.git
cd AAI3008-LLM-RAG-project
```

#### 2. Configure Environment Variables

Create a `.env` file in the project root (use `.env.example` as template):

```bash
# Copy the example file
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
# Gemini API (REQUIRED)
GEMINI_API_KEY=your_gemini_api_key_here

# Database Configuration (defaults are fine for Docker)
DB_NAME=llm_rag_db
DB_USER=postgres
DB_PASSWORD=your_secure_password_here

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=your_secret_key_here
```

#### 3. Start the Application

```bash
docker-compose up --build
```

This command will:
- Build the Flask application Docker image
- Pull the PostgreSQL with pgvector image
- Start both containers
- Automatically initialize the database schema
- Start the Flask development server

#### 4. Access the Application

- **API**: [http://localhost:5000](http://localhost:5000)
- **Health Check**: [http://localhost:5000/health](http://localhost:5000/health)

#### 5. Stop the Application

```bash
# Stop containers (keeps data)
docker-compose down

# Stop containers and remove volumes (deletes database data)
docker-compose down -v
```

### Useful Docker Commands

```bash
# View running containers
docker-compose ps

# View logs
docker-compose logs -f

# View backend logs only
docker-compose logs -f backend

# View database logs only
docker-compose logs -f db

# Restart services
docker-compose restart

# Rebuild and restart
docker-compose up --build

# Execute commands in backend container
docker-compose exec backend bash

# Execute commands in database container
docker-compose exec db psql -U postgres -d llm_rag_db

# Stop all services
docker-compose down

# Stop all services and remove volumes (delete data)
docker-compose down -v
```

### Database Management with Docker

```bash
# Access PostgreSQL shell
docker-compose exec db psql -U postgres -d llm_rag_db

# Run SQL commands
docker-compose exec db psql -U postgres -d llm_rag_db -c "SELECT * FROM users;"

# Backup database
docker-compose exec db pg_dump -U postgres llm_rag_db > backup.sql

# Restore database
docker-compose exec -T db psql -U postgres llm_rag_db < backup.sql
```

---

## Option 2: Traditional Setup (Without Docker)

Use this option if you prefer managing dependencies manually or cannot use Docker.

### Prerequisites

- **Python 3.14.x** (required)
- **PostgreSQL 18 + pgvector** (for installation guide, see [postgre_vector_db_installation_guide.md](postgre_vector_db_installation_guide.md))
- **Git**
- **Visual Studio C++ Build Tools** (for pgvector compilation on Windows)
- **Google Gemini API Key** (obtain from [Google AI Studio](https://aistudio.google.com/))

### Setup Instructions

#### 1. Clone the Repository

```bash
git clone https://github.com/ziqiangg/AAI3008-LLM-RAG-project.git
cd AAI3008-LLM-RAG-project
```

#### 2. Create a Virtual Environment

**Windows:**
```powershell
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Set Up PostgreSQL Database

1. Install PostgreSQL 18 and pgvector extension following [postgre_vector_db_installation_guide.md](postgre_vector_db_installation_guide.md)

2. Create a new database for the project:
   ```sql
   CREATE DATABASE llm_rag_db;
   ```

3. Connect to the database and initialize the schema using the provided SQL dump:
   ```sql
   \c llm_rag_db
   \i schema_dump/schema.sql
   ```
   
   Alternatively, you can run the schema directly in pgAdmin 4's Query Tool by opening [schema_dump/schema.sql](schema_dump/schema.sql) and executing it.

#### 5. Configure Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=llm_rag_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password

# Flask Configuration
FLASK_APP=app.backend.app:app
FLASK_ENV=development
SECRET_KEY=your_secret_key_here

# Optional: AWS Configuration (for S3 file storage)
# AWS_ACCESS_KEY_ID=your_aws_access_key
# AWS_SECRET_ACCESS_KEY=your_aws_secret_key
# AWS_REGION=us-east-1
# S3_BUCKET_NAME=your_bucket_name
```

#### 6. Run the Application

```bash
flask run
```

The application should now be running at `http://localhost:5000`

---

## API Endpoints

The Flask backend provides the following REST API endpoints:

- `GET /health` - Health check and database connection status
- `GET /api/users` - Get all users
- `POST /api/users` - Create a new user
- `GET /api/users/<id>` - Get user by ID
- `DELETE /api/users/<id>` - Delete user
- `GET /api/documents` - Get all documents
- `POST /api/documents` - Upload a new document
- `GET /api/documents/<id>` - Get document by ID
- `DELETE /api/documents/<id>` - Delete document
- `GET /api/sessions` - Get all sessions
- `POST /api/sessions` - Create a new session
- `GET /api/sessions/<id>` - Get session by ID
- `PUT /api/sessions/<id>` - Update session
- `DELETE /api/sessions/<id>` - Delete session
- `POST /api/query` - Ask a question (RAG pipeline - to be implemented)

### Database Schema Reference

The database schema includes the following tables:
- **users** - User account information
- **documents** - Uploaded document metadata
- **sessions** - User session management with conversation history
- **document_chunks** - Text chunks with vector embeddings (384-dimensional)

For detailed schema structure, see [schema_dump/schema.sql](schema_dump/schema.sql)

## Production (Cloud Deployment)

### Cloud Infrastructure Stack

**Compute:**
- AWS EC2 - Application hosting

**Storage:**
- AWS S3 - Document file storage

**Database:**
- AWS RDS (PostgreSQL 18 + pgvector) - Managed database service

**Networking:**
- VPC - Virtual Private Cloud
- Security Groups - Firewall rules
- Elastic IP - Static IP address (optional)

### Prerequisites

- AWS Account with appropriate IAM permissions
- AWS CLI installed and configured
- Domain name (optional, for custom DNS)
- SSL/TLS certificate (recommended for HTTPS) #NOT CONFIRMED IF WE ARE DOING THIS

### Deployment Instructions

(To be added) 
