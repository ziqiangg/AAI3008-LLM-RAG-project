# Use Python 3.12 slim image (3.14 doesn't exist yet)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY schema_dump/ ./schema_dump/

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose Flask port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.backend.app:app

# Run Flask application
CMD ["flask", "run", "--host=0.0.0.0"]
