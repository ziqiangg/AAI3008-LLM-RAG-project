# Docker Commands Reference

Quick reference for common Docker commands used in this project.

## Starting and Stopping

```bash
# Start all services (with build)
docker-compose up --build

# Start all services (detached mode - runs in background)
docker-compose up -d

# Start specific service
docker-compose up backend
docker-compose up db

# Stop all services (preserves data)
docker-compose down

# Stop all services and remove volumes (deletes ALL data)
docker-compose down -v

# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart backend
```

## Viewing Logs

```bash
# View logs from all services
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# View logs from specific service
docker-compose logs backend
docker-compose logs db

# Follow logs from specific service
docker-compose logs -f backend

# View last N lines of logs
docker-compose logs --tail=100 backend
```

## Container Management

```bash
# List running containers
docker-compose ps

# List all containers (including stopped)
docker ps -a

# Execute command in running container
docker-compose exec backend bash
docker-compose exec db bash

# Execute command without entering container
docker-compose exec backend python -c "print('Hello')"

# Stop a specific container
docker-compose stop backend

# Remove stopped containers
docker-compose rm
```

## Database Operations

```bash
# Access PostgreSQL shell
docker-compose exec db psql -U postgres -d llm_rag_db

# Run SQL query
docker-compose exec db psql -U postgres -d llm_rag_db -c "SELECT * FROM users;"

# Create database backup
docker-compose exec db pg_dump -U postgres llm_rag_db > backup_$(date +%Y%m%d).sql

# Restore database from backup
docker-compose exec -T db psql -U postgres llm_rag_db < backup.sql

# Check if pgvector extension is installed
docker-compose exec db psql -U postgres -d llm_rag_db -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

## Building and Cleaning

```bash
# Rebuild images
docker-compose build

# Rebuild specific service
docker-compose build backend

# Rebuild without cache (fresh build)
docker-compose build --no-cache

# Remove all unused Docker resources
docker system prune

# Remove all unused images
docker image prune -a

# Remove all unused volumes
docker volume prune
```

## Debugging

```bash
# View container resource usage
docker stats

# Inspect container details
docker inspect llm_rag_backend
docker inspect llm_rag_db

# View container environment variables
docker-compose exec backend env

# Check container health
docker-compose ps
```

## Development Workflow

```bash
# 1. Start development environment
docker-compose up

# 2. Make code changes (hot reload enabled via volume mount)
# Edit files in app/ directory - changes reflect immediately

# 3. View logs to debug
docker-compose logs -f backend

# 4. Access database if needed
docker-compose exec db psql -U postgres -d llm_rag_db

# 5. Restart if configuration changes
docker-compose restart backend

# 6. Stop when done
docker-compose down
```

## Troubleshooting

```bash
# Container won't start - check logs
docker-compose logs backend

# Database connection issues
docker-compose exec db pg_isready -U postgres

# Port already in use - check what's using port 5000
# Windows PowerShell:
netstat -ano | findstr :5000

# Clean everything and start fresh
docker-compose down -v
docker-compose up --build

# Remove all project containers and volumes
docker-compose down -v --remove-orphans
docker volume rm aai3008-llm-rag-project_postgres_data

# Check Docker Compose configuration
docker-compose config
```

## Useful PostgreSQL Commands (Inside Container)

```sql
-- List all databases
\l

-- Connect to database
\c llm_rag_db

-- List all tables
\dt

-- Describe table structure
\d users
\d documents
\d sessions
\d document_chunks

-- Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';

-- View table contents
SELECT * FROM users;
SELECT * FROM documents LIMIT 10;

-- Check vector dimensions
SELECT embedding <=> '[0,1,2,...]'::vector FROM document_chunks LIMIT 1;

-- Quit psql
\q
```
