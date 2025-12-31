# AegisAI Docker Build
FROM python:3.10-slim

# Set labels
LABEL maintainer="AegisAI Team"
LABEL description="Smart City Risk Intelligence System"
LABEL version="4.1.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AEGIS_DEBUG=false
ENV AEGIS_API_HOST=0.0.0.0
ENV AEGIS_API_PORT=8080

# Create non-root user
RUN groupadd --gid 1000 aegis && \
    useradd --uid 1000 --gid aegis --shell /bin/bash --create-home aegis

# Set working directory
WORKDIR /app

# Install system dependencies for OpenCV (with retry for network issues)
RUN apt-get update --fix-missing \
    && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    || (sleep 5 && apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev) \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=aegis:aegis . .

# Create data directories
RUN mkdir -p /app/data/input /app/data/output && \
    chown -R aegis:aegis /app/data

# Switch to non-root user
USER aegis

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/status/health')" || exit 1

# Default command - API server only
CMD ["python", "-m", "uvicorn", "aegis.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
