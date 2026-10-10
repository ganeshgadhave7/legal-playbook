# Backend Dockerfile for Railway deployment
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for asyncpg, docx extraction, cryptography, and xhtml2pdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure upload storage directory exists (ephemeral; use S3/R2 for production persistence)
RUN mkdir -p storage/uploads

# Expose port (Railway sets PORT env var at runtime)
EXPOSE 8000

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Run migrations then start server
ENTRYPOINT ["./entrypoint.sh"]
