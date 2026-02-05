# AAI3008-LLM-RAG-project

This project builds a Retrieval-Augmented Generation (RAG) learning assistant that enables students to upload academic documents (PDFs, DOCX, etc.) and receive AI-powered, context-aware answers grounded in their materials. Using Flask, Gemini 1.5 API, and LangChain, the system extracts text, applies semantic chunking, and stores embeddings in a PostgreSQL + pgvector database on AWS RDS. Queries trigger a two-stage retrieval process—vector similarity search followed by cross-encoder reranking—to fetch the most relevant content, which Gemini 1.5 uses to generate accurate, cited responses. The assistant supports interactive sessions with dynamic conversation memory, multilingual translation, and optional diagram generation via Mermaid/Desmos. Hosted on AWS (EC2, S3, RDS), it offers a scalable, cost-efficient platform for personalized, document-grounded learning.

## Development

### Tech Stack

**Backend Framework:**
- Flask 3.0.3 - Web framework

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

2. Create a new database for the project if you have not:
   ```sql
   CREATE DATABASE postgres;
   ```

3. Connect to the database and initialize the schema using the provided SQL dump:
   ```sql
   \c postgres
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
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_postgres_password

# Flask Configuration
FLASK_APP=app.py
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
